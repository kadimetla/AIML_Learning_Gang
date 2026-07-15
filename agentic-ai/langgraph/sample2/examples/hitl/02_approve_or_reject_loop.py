"""interrupt() combined with conditional routing -- a human can send the
graph back around a loop (reject -> redraft -> review again) instead of just
approving a single pause.
"""

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class GraphState(TypedDict):
    draft_count: int
    text: str
    status: str


def draft(state: GraphState) -> GraphState:
    count = state["draft_count"] + 1
    return {"draft_count": count, "text": f"draft #{count}"}


def human_review(state: GraphState) -> GraphState:
    decision = interrupt({"text": state["text"], "question": "approve or reject?"})
    return {"status": decision}


def route_after_review(state: GraphState) -> str:
    return END if state["status"] == "approve" else "draft"


graph = StateGraph(GraphState)
graph.add_node("draft", draft)
graph.add_node("human_review", human_review)
graph.add_edge(START, "draft")
graph.add_edge("draft", "human_review")
graph.add_conditional_edges("human_review", route_after_review, {"draft": "draft", END: END})
app = graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "loop-thread-1"}}

    result = app.invoke({"draft_count": 0, "text": "", "status": ""}, config=config)
    print(f"1st draft, paused for review: {result['text']!r}")

    # reject -> routes back to "draft" -> pauses again on the new draft
    result = app.invoke(Command(resume="reject"), config=config)
    print(f"rejected, redrafted, paused again: {result['text']!r}")

    # approve -> routes to END
    result = app.invoke(Command(resume="approve"), config=config)
    print(f"approved, finished: {result}")
