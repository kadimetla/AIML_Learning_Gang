"""Capstone: a trimmed, modernized rebuild of
https://github.com/kadimetla/graph_websearch_agent (LangGraph 0.0.64, 2024)
on LangGraph 1.2.9, exercising nearly every folder in examples/ at once.

Original pipeline:
    planner -> serper_tool -> selector -> scraper_tool -> reporter
        -> reviewer -> router -> (loop back, or) -> final_report -> end

Same shape here, rebuilt with:
    - pydantic state                          (../pydantic_state/)
    - with_structured_output on every LLM
      node instead of prompt-engineered JSON   (../structured_output/)
    - init_chat_model                          (../model_init/)
    - reviewer + router collapsed into one
      Command(update=..., goto=...) node       (../command/)
    - a checkpointer + thread_id, so a run
      can pause and resume                     (../checkpointing/)
    - interrupt() human approval gate in
      front of publishing the final report     (../hitl/)
    - RetryPolicy on the two real-network
      tool calls (search, scrape)               (../retry_policy/)

Needs OPENAI_API_KEY in .env (see .env.example). search_web/scrape_url need
no key (see tools.py).
"""

from dotenv import load_dotenv

load_dotenv()

from typing import Literal

from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy, interrupt
from pydantic import BaseModel, Field
from tools import scrape_url, search_web

MAX_REVIEW_LOOPS = 2  # safety cap -- force a finish instead of looping forever


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


model = init_chat_model("openai:gpt-4o-mini", temperature=0)


# ---- structured-output schemas (replace graph_websearch_agent's *_guided_json dicts) ----


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
    prompt = (
        f"research question: {state.research_question}\n\n"
        f"source: {state.selected_url}\n"
        f"content:\n{state.scraped_content}\n\n"
        "Write a concise report (3-5 sentences) answering the research question, "
        "based only on the content above."
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
graph.add_edge("selector", "scrape")
graph.add_edge("scrape", "reporter")
graph.add_edge("reporter", "review_and_route")
# no edges out of review_and_route or final_report -- both return Command,
# which picks the next node dynamically at runtime (see ../command/)
graph.add_edge("final_report", END)

app = graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "research-1"}}

    result = app.invoke({"research_question": "What is LangGraph and how is it different from LangChain?"}, config=config)
    interrupt_payload = result["__interrupt__"][0].value
    print(f"paused for human review:\n  report: {interrupt_payload['report']}\n")

    # reject once, to exercise the reporter feedback loop with real content
    result = app.invoke(Command(resume="make it one sentence shorter"), config=config)
    interrupt_payload = result["__interrupt__"][0].value
    print(f"revised report, paused again:\n  report: {interrupt_payload['report']}\n")

    # approve the revised report
    result = app.invoke(Command(resume="approve"), config=config)
    print(f"published:\n  {result['final_report']}")
