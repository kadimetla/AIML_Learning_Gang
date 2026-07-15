"""Command(update=..., goto=...) -- update state and choose the next node
from inside a single node's return value, instead of a separate
add_conditional_edges routing function.

Contrast with examples/send/01_map_reduce.py: Send fans out to *many*
parallel copies of a node; Command(goto=...) picks *one* next node (or a
few, via goto=[...]), and folds the routing decision into the node itself.
"""

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command


class GraphState(TypedDict):
    score: int
    verdict: str


def evaluate(state: GraphState) -> Command[Literal["accept", "reject"]]:
    verdict = "accept" if state["score"] >= 50 else "reject"
    # update writes to state exactly like a normal node return would;
    # goto picks which node runs next -- no add_conditional_edges needed
    return Command(update={"verdict": verdict}, goto=verdict)


def accept(state: GraphState) -> GraphState:
    return {"verdict": f"ACCEPTED (score-based verdict was {state['verdict']!r})"}


def reject(state: GraphState) -> GraphState:
    return {"verdict": f"REJECTED (score-based verdict was {state['verdict']!r})"}


graph = StateGraph(GraphState)
graph.add_node("evaluate", evaluate)
graph.add_node("accept", accept)
graph.add_node("reject", reject)
graph.add_edge(START, "evaluate")
# no edge from "evaluate" to "accept"/"reject" -- Command.goto handles that
graph.add_edge("accept", END)
graph.add_edge("reject", END)
app = graph.compile()


if __name__ == "__main__":
    print(app.invoke({"score": 80, "verdict": ""}))
    print(app.invoke({"score": 20, "verdict": ""}))
