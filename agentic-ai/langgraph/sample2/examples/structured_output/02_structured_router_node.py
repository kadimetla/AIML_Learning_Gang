"""Combine with_structured_output with Command(goto=...) (from ../command/)
to build the exact "router agent" pattern from graph_websearch_agent's
agent_graph/graph.py -- but with the LLM's routing choice schema-validated
by a Literal type instead of free-text JSON hand-parsed with json.loads()
inside a conditional-edge lambda.
"""

from dotenv import load_dotenv

load_dotenv()

from typing import Literal

from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pydantic import BaseModel, Field


class RouterState(BaseModel):
    feedback: str
    next_agent: str = ""


class RouterDecision(BaseModel):
    # a Literal type here is the schema-level guarantee that the model can
    # only pick one of these four values -- no more "what if the model
    # returns 'Planner' with a capital P" parsing bugs
    next_agent: Literal["planner", "selector", "reporter", "final_report"] = Field(
        description="which agent should run next, based on the reviewer's feedback"
    )


model = init_chat_model("openai:gpt-4o-mini", temperature=0)
router_model = model.with_structured_output(RouterDecision)


def router(state: RouterState) -> Command:
    decision = router_model.invoke(f"Reviewer feedback: {state.feedback}")
    return Command(update={"next_agent": decision.next_agent}, goto=decision.next_agent)


def planner(state: RouterState) -> dict:
    return {"next_agent": "planner ran"}


def selector(state: RouterState) -> dict:
    return {"next_agent": "selector ran"}


def reporter(state: RouterState) -> dict:
    return {"next_agent": "reporter ran"}


def final_report(state: RouterState) -> dict:
    return {"next_agent": "final_report ran"}


graph = StateGraph(RouterState)
graph.add_node("router", router)
graph.add_node("planner", planner)
graph.add_node("selector", selector)
graph.add_node("reporter", reporter)
graph.add_node("final_report", final_report)
graph.add_edge(START, "router")
for name in ("planner", "selector", "reporter", "final_report"):
    graph.add_edge(name, END)
app = graph.compile()


if __name__ == "__main__":
    # feedback that implies more work needed -> real model routes to "reporter"
    result = app.invoke({"feedback": "the report needs better formatting and clarity", "next_agent": ""})
    print(f"feedback about formatting -> {result}")

    # feedback that implies it's done -> real model routes to "final_report"
    result = app.invoke({"feedback": "looks great, ready to publish", "next_agent": ""})
    print(f"positive feedback -> {result}")
