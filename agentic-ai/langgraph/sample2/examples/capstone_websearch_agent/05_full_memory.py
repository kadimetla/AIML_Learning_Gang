"""Capstone extension: all four memory types from ../agent_memory/ at once,
inside the real research agent instead of a toy graph.

    working    -- ResearchState flowing through one run (already true of
                  01, unchanged here: search_results/scraped_content/report
                  live only for the duration of a single invoke())
    episodic   -- the checkpointer already wired into 01 records every
                  turn of the HITL loop; here that history is explicitly
                  replayed with get_state_history(), same as
                  ../agent_memory/02_episodic_memory.py
    semantic   -- a Store caches "research question -> approved answer" by
                  exact question text, across threads. Asking the same
                  question again (thread B below) skips search/select/
                  scrape/report entirely and answers from the cached fact
                  -- same mechanism as ../agent_memory/03_semantic_memory.py
    procedural -- the same Store also holds a "report_style" rule that
                  `reporter` reads and applies to its own prompt. Changing
                  that rule (thread C below) changes every future report's
                  style with no code change -- same mechanism as
                  ../agent_memory/04_procedural_memory.py

Needs OPENAI_API_KEY in .env (see .env.example). search_web/scrape_url need
no key (see tools.py).
"""

from dotenv import load_dotenv

load_dotenv()

from typing import Literal

from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_store
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, RetryPolicy, interrupt
from pydantic import BaseModel, Field
from tools import scrape_url, search_web

MAX_REVIEW_LOOPS = 2  # safety cap -- force a finish instead of looping forever

FACTS_NAMESPACE = ("research_facts",)  # semantic memory: question -> answer
PROCEDURES_NAMESPACE = ("procedures",)  # procedural memory: behavioral rules
DEFAULT_REPORT_STYLE = "concise (3-5 sentences)"


class ResearchState(BaseModel):
    research_question: str = Field(min_length=1)
    search_term: str = ""
    search_results: str = ""
    selected_url: str = ""
    selected_reason: str = ""
    scraped_content: str = ""
    report: str = ""
    feedback: str = ""
    loop_count: int = 0
    final_report: str = ""
    recalled_from_memory: bool = False  # did semantic memory already have the answer?


model = init_chat_model("openai:gpt-4o-mini", temperature=0)


# ---- structured-output schemas (same as 01) ----


class SearchPlan(BaseModel):
    search_term: str = Field(description="the single best search term to start with")


class SelectorDecision(BaseModel):
    selected_url: str = Field(description="the exact URL of the most relevant result")
    reason: str = Field(description="why this result was selected")


class ReviewDecision(BaseModel):
    next_agent: Literal["planner", "selector", "reporter", "final_report"] = Field(
        description="planner: need a different search. selector: pick a different "
        "source. reporter: report needs rework. final_report: report is good, publish it."
    )
    feedback: str = Field(description="feedback to hand to whichever agent runs next")


planner_model = model.with_structured_output(SearchPlan)
selector_model = model.with_structured_output(SelectorDecision)
reviewer_model = model.with_structured_output(ReviewDecision)


# ---------------------------------- nodes ----------------------------------


def check_memory(state: ResearchState) -> dict:
    """Semantic memory lookup -- has this exact question already been
    researched (in any thread)? If so, skip the whole pipeline."""
    store = get_store()
    cached = store.get(FACTS_NAMESPACE, state.research_question)
    if cached:
        return {"report": cached.value["answer"], "recalled_from_memory": True}
    return {"recalled_from_memory": False}


def route_after_memory_check(state: ResearchState) -> Literal["planner", "final_report"]:
    return "final_report" if state.recalled_from_memory else "planner"


def planner(state: ResearchState) -> dict:
    prompt = f"research question: {state.research_question}"
    if state.feedback:
        prompt += f"\n\nfeedback from previous attempt: {state.feedback}"
    plan = planner_model.invoke(prompt)
    return {"search_term": plan.search_term}


def search(state: ResearchState) -> dict:
    return {"search_results": search_web(state.search_term)}


def selector(state: ResearchState) -> dict:
    prompt = (
        f"research question: {state.research_question}\n\n"
        f"search results:\n{state.search_results}"
    )
    if state.feedback:
        prompt += f"\n\nfeedback from previous attempt: {state.feedback}"
    decision = selector_model.invoke(prompt)
    return {"selected_url": decision.selected_url, "selected_reason": decision.reason}


def scrape(state: ResearchState) -> dict:
    try:
        content = scrape_url(state.selected_url)
    except Exception as e:  # noqa: BLE001 -- deliberately broad: any scrape failure
        content = f"error scraping {state.selected_url}: {e}"
    return {"scraped_content": content}


def reporter(state: ResearchState) -> dict:
    # procedural memory: how this node writes, not what it knows -- read
    # fresh every call, so a Store update takes effect on the very next run
    store = get_store()
    procedure = store.get(PROCEDURES_NAMESPACE, "report_style")
    style = procedure.value["style"] if procedure else DEFAULT_REPORT_STYLE

    prompt = (
        f"research question: {state.research_question}\n\n"
        f"source: {state.selected_url}\n"
        f"content:\n{state.scraped_content}\n\n"
        f"Write a report answering the research question, based only on the "
        f"content above. Style: {style}."
    )
    if state.feedback:
        prompt += f"\n\nfeedback to incorporate: {state.feedback}"
    response = model.invoke(prompt)  # plain text, no structured output needed here
    return {"report": response.content}


def review_and_route(state: ResearchState) -> Command[Literal["planner", "selector", "reporter", "final_report"]]:
    loop_count = state.loop_count + 1
    if loop_count > MAX_REVIEW_LOOPS:
        # safety net: real LLM review loops cost real money and real time --
        # don't let a stubborn reviewer run forever
        return Command(
            update={"feedback": "max review loops reached, publishing as-is", "loop_count": loop_count},
            goto="final_report",
        )

    decision = reviewer_model.invoke(
        f"research question: {state.research_question}\n\nreport:\n{state.report}"
    )
    return Command(
        update={"feedback": decision.feedback, "loop_count": loop_count},
        goto=decision.next_agent,
    )


def final_report(state: ResearchState) -> Command[Literal["reporter"]] | dict:
    decision = interrupt(
        {
            "question": "Approve this report for publishing?",
            "report": state.report,
            "recalled_from_memory": state.recalled_from_memory,
        }
    )
    if decision == "approve":
        # semantic memory write: cache the approved answer under the exact
        # question text so a future run of check_memory can find it
        store = get_store()
        store.put(FACTS_NAMESPACE, state.research_question, {"answer": state.report})
        return {"final_report": state.report}
    return Command(update={"feedback": f"human requested changes: {decision}"}, goto="reporter")


# ---------------------------------- graph ----------------------------------

graph = StateGraph(ResearchState)
graph.add_node("check_memory", check_memory)
graph.add_node("planner", planner)
graph.add_node("search", search, retry_policy=RetryPolicy(max_attempts=3))
graph.add_node("selector", selector)
graph.add_node("scrape", scrape, retry_policy=RetryPolicy(max_attempts=3))
graph.add_node("reporter", reporter)
graph.add_node("review_and_route", review_and_route)
graph.add_node("final_report", final_report)

graph.add_edge(START, "check_memory")
graph.add_conditional_edges("check_memory", route_after_memory_check, ["planner", "final_report"])
graph.add_edge("planner", "search")
graph.add_edge("search", "selector")
graph.add_edge("selector", "scrape")
graph.add_edge("scrape", "reporter")
graph.add_edge("reporter", "review_and_route")
# no edges out of review_and_route or final_report -- both return Command,
# which picks the next node dynamically at runtime (see ../command/)
graph.add_edge("final_report", END)

store = InMemoryStore()
app = graph.compile(checkpointer=InMemorySaver(), store=store)


if __name__ == "__main__":
    question = "What is LangGraph and how is it different from LangChain?"

    # -- thread A: cache miss -- full pipeline runs, working memory
    # (search_results/scraped_content/report) flows node to node, and the
    # checkpointer records every turn of the HITL loop as it happens
    config_a = {"configurable": {"thread_id": "research-A"}}
    result = app.invoke({"research_question": question}, config=config_a)
    interrupt_payload = result["__interrupt__"][0].value
    first_draft_report = interrupt_payload["report"]
    print(f"[thread A] cache miss, paused for review:\n  report: {first_draft_report}\n")

    result = app.invoke(Command(resume="make it one sentence shorter"), config=config_a)
    interrupt_payload = result["__interrupt__"][0].value
    print(f"[thread A] revised, paused again:\n  report: {interrupt_payload['report']}\n")

    result = app.invoke(Command(resume="approve"), config=config_a)
    print(f"[thread A] published + cached as a semantic fact:\n  {result['final_report']}\n")

    # -- episodic memory: recall the specific past episode right after the
    # *first* draft, before the human asked for a revision -- not just the
    # latest state (compare ../agent_memory/02_episodic_memory.py)
    history = list(app.get_state_history(config_a))
    first_draft_episode = next(h for h in history if h.values.get("report") == first_draft_report)
    print(f"[episodic recall] report exactly as it was at the first pause: {first_draft_episode.values['report']}\n")

    # -- thread B, same question: semantic memory hit -- check_memory finds
    # the cached fact and routes straight to final_report, skipping
    # planner/search/selector/scrape/reporter (and every LLM/network call
    # they'd make) entirely
    config_b = {"configurable": {"thread_id": "research-B"}}
    result = app.invoke({"research_question": question}, config=config_b)
    interrupt_payload = result["__interrupt__"][0].value
    print(
        f"[thread B] recalled_from_memory={interrupt_payload['recalled_from_memory']}, "
        f"paused for review:\n  report: {interrupt_payload['report']}\n"
    )
    result = app.invoke(Command(resume="approve"), config=config_b)
    print(f"[thread B] published with no new research performed:\n  {result['final_report']}\n")

    # -- procedural memory: rewrite the stored *rule* reporter follows, then
    # ask a new (uncached) question -- same code, different report style
    store.put(PROCEDURES_NAMESPACE, "report_style", {"style": "detailed, as a bulleted list of 4-5 facts"})
    config_c = {"configurable": {"thread_id": "research-C"}}
    result = app.invoke({"research_question": "What is a LangGraph checkpointer?"}, config=config_c)
    interrupt_payload = result["__interrupt__"][0].value
    print(f"[thread C, new procedural style] paused for review:\n  report: {interrupt_payload['report']}\n")
    result = app.invoke(Command(resume="approve"), config=config_c)
    print(f"[thread C] published in the new style:\n  {result['final_report']}")
