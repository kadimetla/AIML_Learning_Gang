"""Capstone extension: replace 01_research_agent.py's fixed
`planner -> search` and `selector -> scrape` pipeline steps with a real
ToolNode + tools_condition loop, per ../tool_node/01_basic_tool_node.py and
../tool_node_weather/01_weather_tool_agent.py.

01 always searches once, always scrapes exactly the one URL the selector
picked -- the LLM only fills in *arguments* (search term, which URL) inside
a scripted pipeline. Here search_web/scrape_url are real @tools bound to the
model, so the model decides *whether* to search, *whether* to scrape, how
many times, and with what arguments -- matching graph_websearch_agent's
underlying intent (an "agent" doing research) more literally than a fixed
node sequence does.

`planner`/`selector` collapse into a single `researcher` node that owns both
decisions. `search`/`scrape` collapse into one `tools` ToolNode, since the
model can call either (or both, in parallel) from the same AIMessage.

Needs OPENAI_API_KEY in .env (see .env.example). search_web/scrape_url need
no key (see tools.py).
"""

from dotenv import load_dotenv

load_dotenv()

from typing import Annotated, Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command, RetryPolicy, interrupt
from pydantic import BaseModel, Field
from tools import scrape_url as _scrape_url
from tools import search_web as _search_web

MAX_REVIEW_LOOPS = 2  # safety cap -- force a finish instead of looping forever


# real @tools wrapping tools.py's plain functions -- kept in this file (not
# tools.py) so 01/02, which call the plain functions directly, are unaffected
@tool
def search_web(query: str) -> str:
    """Search the web for the given query; returns titles/links/snippets."""
    return _search_web(query)


@tool
def scrape_url(url: str) -> str:
    """Fetch a URL and return its visible text content."""
    return _scrape_url(url)


class ResearchState(BaseModel):
    research_question: str = Field(min_length=1)
    messages: Annotated[list, add_messages] = Field(default_factory=list)
    report: str = ""
    feedback: str = ""
    loop_count: int = 0
    final_report: str = ""


model = init_chat_model("openai:gpt-4o-mini", temperature=0)
researcher_model = model.bind_tools([search_web, scrape_url])


class ReviewDecision(BaseModel):
    next_agent: Literal["researcher", "reporter", "final_report"] = Field(
        description="researcher: need more/different research (search again or "
        "scrape a different source). reporter: report needs rework from the "
        "existing research. final_report: report is good, publish it."
    )
    feedback: str = Field(description="feedback to hand to whichever agent runs next")


reviewer_model = model.with_structured_output(ReviewDecision)


RESEARCHER_SYSTEM_PROMPT = (
    "You are a research assistant with access to search_web and scrape_url "
    "tools. Use search_web to find promising sources for the research "
    "question, then scrape_url on the single best result to read its "
    "content. Once you have enough content to answer the question, reply "
    "with a final message (no more tool calls) summarizing the key facts "
    "you found -- do not write the final report yet, just summarize what "
    "you learned."
)


# ---------------------------------- nodes ----------------------------------


def researcher(state: ResearchState, config: RunnableConfig) -> dict:
    if not state.messages:
        # first pass: seed the transcript. Later passes (looping back from
        # `tools`, or from review_and_route's feedback) just continue an
        # existing transcript, so no seeding branch is needed there.
        seed = [
            SystemMessage(content=RESEARCHER_SYSTEM_PROMPT),
            HumanMessage(content=f"research question: {state.research_question}"),
        ]
        response = researcher_model.invoke(seed, config=config)
        return {"messages": seed + [response]}
    response = researcher_model.invoke(state.messages, config=config)
    return {"messages": [response]}


def reporter(state: ResearchState, config: RunnableConfig) -> dict:
    tool_outputs = "\n\n".join(m.content for m in state.messages if isinstance(m, ToolMessage))
    summary = state.messages[-1].content if state.messages else ""
    prompt = (
        f"research question: {state.research_question}\n\n"
        f"raw source content gathered:\n{tool_outputs}\n\n"
        f"researcher's summary: {summary}\n\n"
        "Write a concise report (3-5 sentences) answering the research question, "
        "based only on the content above."
    )
    if state.feedback:
        prompt += f"\n\nfeedback to incorporate: {state.feedback}"
    response = model.invoke(prompt, config=config)  # plain text, no structured output needed here
    return {"report": response.content}


def review_and_route(
    state: ResearchState, config: RunnableConfig
) -> Command[Literal["researcher", "reporter", "final_report"]]:
    loop_count = state.loop_count + 1
    if loop_count > MAX_REVIEW_LOOPS:
        # safety net: real LLM review loops cost real money and real time --
        # don't let a stubborn reviewer run forever
        return Command(
            update={"feedback": "max review loops reached, publishing as-is", "loop_count": loop_count},
            goto="final_report",
        )

    decision = reviewer_model.invoke(
        f"research question: {state.research_question}\n\nreport:\n{state.report}",
        config=config,
    )
    update = {"feedback": decision.feedback, "loop_count": loop_count}
    if decision.next_agent == "researcher":
        # researcher only re-invokes the model on state.messages as-is (see
        # above) -- it needs this feedback appended as a new turn to react to
        update["messages"] = [HumanMessage(content=f"feedback: {decision.feedback} -- please continue researching")]
    return Command(update=update, goto=decision.next_agent)


def final_report(state: ResearchState) -> Command[Literal["reporter"]] | dict:
    decision = interrupt({"question": "Approve this report for publishing?", "report": state.report})
    if decision == "approve":
        return {"final_report": state.report}
    return Command(update={"feedback": f"human requested changes: {decision}"}, goto="reporter")


# ---------------------------------- graph ----------------------------------

graph = StateGraph(ResearchState)
graph.add_node("researcher", researcher)
graph.add_node("tools", ToolNode([search_web, scrape_url]), retry_policy=RetryPolicy(max_attempts=3))
graph.add_node("reporter", reporter)
graph.add_node("review_and_route", review_and_route)
graph.add_node("final_report", final_report)

graph.add_edge(START, "researcher")
# tools_condition's normal "no tool calls" branch would go to END -- redirect
# it to "reporter" instead, so the graph continues past the research loop
graph.add_conditional_edges("researcher", tools_condition, {"tools": "tools", END: "reporter"})
graph.add_edge("tools", "researcher")
graph.add_edge("reporter", "review_and_route")
# no edges out of review_and_route or final_report -- both return Command,
# which picks the next node dynamically at runtime (see ../command/)
graph.add_edge("final_report", END)

app = graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "research-1"}}

    result = app.invoke({"research_question": "What is LangGraph and how is it different from LangChain?"}, config=config)
    print("research transcript:")
    for message in result["messages"]:
        label = type(message).__name__
        calls = getattr(message, "tool_calls", None)
        print(f"  {label:14s} tool_calls={calls} content={message.content[:120]!r}")

    interrupt_payload = result["__interrupt__"][0].value
    print(f"\npaused for human review:\n  report: {interrupt_payload['report']}\n")

    # reject once, to exercise the reporter feedback loop with real content
    result = app.invoke(Command(resume="make it one sentence shorter"), config=config)
    interrupt_payload = result["__interrupt__"][0].value
    print(f"revised report, paused again:\n  report: {interrupt_payload['report']}\n")

    # approve the revised report
    result = app.invoke(Command(resume="approve"), config=config)
    print(f"published:\n  {result['final_report']}")
