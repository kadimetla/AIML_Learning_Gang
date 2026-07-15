"""config={"thread_id": ...} + interrupt_before=[...] — pause a graph for human review, then resume.

Requires a checkpointer, since LangGraph needs somewhere to persist state
between the pause and the resume.
"""

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    name: str
    greeting: str


def greet(state: GraphState) -> GraphState:
    return {"greeting": f"Hello, {state['name']}!"}


def shout(state: GraphState) -> GraphState:
    return {"greeting": state["greeting"].upper()}


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_node("shout", shout)
graph.add_edge(START, "greet")
graph.add_edge("greet", "shout")
graph.add_edge("shout", END)
app = graph.compile(checkpointer=InMemorySaver(), interrupt_before=["shout"])


if __name__ == "__main__":
    # thread_id is how the checkpointer knows which "conversation" this is
    config = {"configurable": {"thread_id": "demo-thread-1"}}

    result = app.invoke({"name": "sample2"}, config=config)
    print(f"paused before 'shout', state so far: {result}")

    # ... imagine a human reviews result["greeting"] here before approving ...

    # resume with input=None: continues from the checkpoint instead of restarting
    result = app.invoke(None, config=config)
    print(f"resumed and finished: {result}")
