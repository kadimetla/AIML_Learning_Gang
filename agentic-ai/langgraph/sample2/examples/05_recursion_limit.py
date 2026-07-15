"""config={"recursion_limit": N} — caps how many node executions a graph can take.

Matters once a graph has a cycle. Default limit is 25.
"""

from typing import TypedDict

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    count: int


def increment(state: GraphState) -> GraphState:
    print(f"count={state['count']}")
    return {"count": state["count"] + 1}


def should_continue(state: GraphState) -> str:
    return "increment" if state["count"] < 1000 else END


graph = StateGraph(GraphState)
graph.add_node("increment", increment)
graph.add_edge(START, "increment")
graph.add_conditional_edges("increment", should_continue, {"increment": "increment", END: END})
app = graph.compile()


if __name__ == "__main__":
    # this loop would run 1000 times, but we cap it at 5 super-steps
    try:
        app.invoke({"count": 0}, config={"recursion_limit": 5})
    except GraphRecursionError as e:
        print(f"stopped early: {e}")
