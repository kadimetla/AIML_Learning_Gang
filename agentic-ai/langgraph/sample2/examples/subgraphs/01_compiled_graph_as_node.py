"""A compiled StateGraph can be used directly as a node in another graph.

Useful for building reusable, independently-testable pieces (e.g. a
"research" subgraph reused by several parent agents), instead of one flat
graph with every node in it.

This works because CompiledStateGraph, like a plain node function, is just a
Runnable: it takes a state dict in and returns a state dict out. The parent
graph doesn't need to know it's actually a whole graph underneath.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class ChildState(TypedDict):
    text: str


def child_upper(state: ChildState) -> ChildState:
    return {"text": state["text"].upper()}


child_graph = StateGraph(ChildState)
child_graph.add_node("upper", child_upper)
child_graph.add_edge(START, "upper")
child_graph.add_edge("upper", END)
child_app = child_graph.compile()  # a fully independent, testable graph


class ParentState(TypedDict):
    text: str
    length: int


def greet(state: ParentState) -> ParentState:
    return {"text": f"hello {state['text']}"}


def measure(state: ParentState) -> ParentState:
    return {"length": len(state["text"])}


parent_graph = StateGraph(ParentState)
parent_graph.add_node("greet", greet)
parent_graph.add_node("shout", child_app)  # <-- compiled graph used as a node
parent_graph.add_node("measure", measure)
parent_graph.add_edge(START, "greet")
parent_graph.add_edge("greet", "shout")
parent_graph.add_edge("shout", "measure")
parent_graph.add_edge("measure", END)
parent_app = parent_graph.compile()


if __name__ == "__main__":
    # the child graph works completely on its own...
    print("child graph alone:", child_app.invoke({"text": "standalone"}))

    # ...and also runs as a single step inside the parent graph
    print("parent graph, using child as a node:", parent_app.invoke({"text": "sample2", "length": 0}))
