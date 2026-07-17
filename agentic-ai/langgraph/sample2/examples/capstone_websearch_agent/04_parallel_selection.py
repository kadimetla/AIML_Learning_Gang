"""Capstone extension: instead of 01_research_agent.py's selector always
picking exactly one URL to scrape, have it pick 2-3 candidates and fan
`scrape` out over all of them in parallel with Send, per
../send/01_map_reduce.py. `reporter` then synthesizes across every source
instead of just one.

`planner`/`search` are unchanged from 01 -- only selection -> scrape ->
report becomes a real map-reduce: `dispatch` (a conditional edge returning
`Send` objects) is the "map" step, `scrape` runs once per URL with its own
narrow input, and `scraped_sources` (an `operator.add`-reduced list) is the
"reduce" step that collects every parallel `scrape` result back together --
the exact same shape as `summaries` in `send/01_map_reduce.py`.

Needs OPENAI_API_KEY in .env (see .env.example). search_web/scrape_url need
no key (see tools.py).
"""

from dotenv import load_dotenv

load_dotenv()

import operator
from typing import Annotated, Literal

from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy, Send, interrupt
from pydantic import BaseModel, Field
from tools import scrape_url, search_web

MAX_REVIEW_LOOPS = 2  # safety cap -- force a finish instead of looping forever


class ScrapedSource(BaseModel):
    url: str
    content: str


class ResearchState(BaseModel):
    research_question: str = Field(min_length=1)
    search_term: str = ""
    search_results: str = ""
    selected_urls: list[str] = Field(default_factory=list)
    selected_reason: str = ""
    # operator.add so the N parallel `scrape` calls (one per Send) each
    # append their own result instead of clobbering each other -- see the
    # accumulation note on `reporter` below for the one gotcha this creates
    scraped_sources: Annotated[list[ScrapedSource], operator.add] = Field(default_factory=list)
    report: str = ""
    feedback: str = ""
    loop_count: int = 0
    final_report: str = ""


class ScrapeInput(BaseModel):
    """Narrow per-node input for `scrape` -- like WorkerState in
    ../send/01_map_reduce.py, this is never registered anywhere; it only
    documents the shape `dispatch`'s Send payloads use. Unlike WorkerState
    (a TypedDict, i.e. a plain dict at runtime -- no coercion needed),
    LangGraph does *not* auto-construct a pydantic model from a Send
    payload, so `scrape` below validates it explicitly."""

    url: str


model = init_chat_model("openai:gpt-4o-mini", temperature=0)


# ---- structured-output schemas ----


class SearchPlan(BaseModel):
    search_term: str = Field(description="the single best search term to start with")


class SelectorDecision(BaseModel):
    selected_urls: list[str] = Field(description="2-3 most relevant, complementary result URLs")
    reason: str = Field(description="why these results were selected together")


class ReviewDecision(BaseModel):
    next_agent: Literal["planner", "selector", "reporter", "final_report"] = Field(
        description="planner: need a different search. selector: pick different "
        "sources. reporter: report needs rework. final_report: report is good, publish it."
    )
    feedback: str = Field(description="feedback to hand to whichever agent runs next")


planner_model = model.with_structured_output(SearchPlan)
selector_model = model.with_structured_output(SelectorDecision)
reviewer_model = model.with_structured_output(ReviewDecision)


# ---------------------------------- nodes ----------------------------------


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
    return {"selected_urls": decision.selected_urls, "selected_reason": decision.reason}


def dispatch(state: ResearchState) -> list[Send]:
    # one Send per candidate URL -- "scrape" runs once per URL, all in
    # parallel, each with its own ScrapeInput-shaped input
    return [Send("scrape", {"url": url}) for url in state.selected_urls]


def scrape(raw: dict) -> dict:
    state = ScrapeInput.model_validate(raw)
    try:
        content = scrape_url(state.url)
    except Exception as e:  # noqa: BLE001 -- deliberately broad: any scrape failure
        content = f"error scraping {state.url}: {e}"
    return {"scraped_sources": [{"url": state.url, "content": content}]}


def reporter(state: ResearchState) -> dict:
    # operator.add only ever appends, so a review loop that sends control
    # back to `selector` would leave stale sources from the previous round
    # still sitting in scraped_sources. Rather than reaching for a custom
    # reset-capable reducer (overkill for a MAX_REVIEW_LOOPS-capped loop),
    # just filter down to this round's picks before writing the report.
    current_sources = [s for s in state.scraped_sources if s.url in state.selected_urls]
    sources_text = "\n\n".join(
        f"source {i + 1} ({s.url}):\n{s.content}" for i, s in enumerate(current_sources)
    )
    prompt = (
        f"research question: {state.research_question}\n\n"
        f"{sources_text}\n\n"
        "Write a concise report (3-5 sentences) synthesizing across all the sources "
        "above to answer the research question, based only on the content above."
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
    decision = interrupt({"question": "Approve this report for publishing?", "report": state.report})
    if decision == "approve":
        return {"final_report": state.report}
    return Command(update={"feedback": f"human requested changes: {decision}"}, goto="reporter")


# ---------------------------------- graph ----------------------------------

graph = StateGraph(ResearchState)
graph.add_node("planner", planner)
graph.add_node("search", search, retry_policy=RetryPolicy(max_attempts=3))
graph.add_node("selector", selector)
graph.add_node("scrape", scrape, retry_policy=RetryPolicy(max_attempts=3))
graph.add_node("reporter", reporter)
graph.add_node("review_and_route", review_and_route)
graph.add_node("final_report", final_report)

graph.add_edge(START, "planner")
graph.add_edge("planner", "search")
graph.add_edge("search", "selector")
# dispatch fans out to N parallel "scrape" runs (the "map" step); LangGraph
# waits for all of them before continuing on to "reporter" (the "reduce" step)
graph.add_conditional_edges("selector", dispatch, ["scrape"])
graph.add_edge("scrape", "reporter")
graph.add_edge("reporter", "review_and_route")
# no edges out of review_and_route or final_report -- both return Command,
# which picks the next node dynamically at runtime (see ../command/)
graph.add_edge("final_report", END)

app = graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "research-1"}}

    result = app.invoke({"research_question": "What is LangGraph and how is it different from LangChain?"}, config=config)
    print(f"selected {len(result['selected_urls'])} sources: {result['selected_urls']}\n")

    interrupt_payload = result["__interrupt__"][0].value
    print(f"paused for human review:\n  report: {interrupt_payload['report']}\n")

    # reject once, to exercise the reporter feedback loop with real content
    result = app.invoke(Command(resume="make it one sentence shorter"), config=config)
    interrupt_payload = result["__interrupt__"][0].value
    print(f"revised report, paused again:\n  report: {interrupt_payload['report']}\n")

    # approve the revised report
    result = app.invoke(Command(resume="approve"), config=config)
    print(f"published:\n  {result['final_report']}")
