"""interrupt() + Command(resume=...) -- pause *inside* a node, not just before it.

This is the more flexible sibling of examples/07_interrupt_before.py, which
can only pause *before* a whole node runs (declared at compile time).
interrupt() lets a node run partway, ask a human something, and continue
using whatever the human answered -- all declared inline in the node itself.

Requires a checkpointer, since the paused state has to be persisted
somewhere until resume.
"""

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class GraphState(TypedDict):
    text: str
    approved_text: str


def draft(state: GraphState) -> GraphState:
    return {"text": state["text"].upper()}


def human_review(state: GraphState) -> GraphState:
    # execution pauses right here -- everything before this line already ran
    decision = interrupt({"question": "approve this draft?", "text": state["text"]})
    return {"approved_text": f"{state['text']} [{decision}]"}


graph = StateGraph(GraphState)
graph.add_node("draft", draft)
graph.add_node("human_review", human_review)
graph.add_edge(START, "draft")
graph.add_edge("draft", "human_review")
graph.add_edge("human_review", END)
app = graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "review-thread-1"}}

    result = app.invoke({"text": "hello"}, config=config)
    print(f"paused: {result}")  # note the '__interrupt__' key with the payload

    state = app.get_state(config)
    print(f"still pending: {state.next}")

    # Command(resume=...) sends a value back to whatever interrupt() call is
    # waiting -- it becomes interrupt()'s return value, and the node
    # continues from that exact line
    result = app.invoke(Command(resume="approved"), config=config)
    print(f"resumed and finished: {result}")
