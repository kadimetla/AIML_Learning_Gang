"""operator.add as a reducer -- the standard "just concatenate/sum" case,
which is common enough that you don't need to write your own function.

Works for lists (concatenation) the same way it works for numbers
(addition), since operator.add is just the "+" operator as a function.
"""

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    nums: Annotated[list[int], operator.add]


def node_a(state: GraphState) -> GraphState:
    return {"nums": [1]}


def node_b(state: GraphState) -> GraphState:
    return {"nums": [2]}


def node_c(state: GraphState) -> GraphState:
    return {"nums": [3]}


graph = StateGraph(GraphState)
graph.add_node("a", node_a)
graph.add_node("b", node_b)
graph.add_node("c", node_c)
# all three run in parallel, fanned out from START
graph.add_edge(START, "a")
graph.add_edge(START, "b")
graph.add_edge(START, "c")
graph.add_edge("a", END)
graph.add_edge("b", END)
graph.add_edge("c", END)
app = graph.compile()


if __name__ == "__main__":
    # order isn't guaranteed across parallel branches, but every branch's
    # contribution is present -- operator.add concatenated all three lists
    print(app.invoke({"nums": []}))
