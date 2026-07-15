"""Send -- dynamically fan out to N copies of the same node, one per item in
a list you only know the size of at runtime (a "map" step), then let a
reducer combine their results back together (the "reduce" step).

Different from a normal conditional edge, which routes to a fixed, known set
of next nodes -- Send lets a single routing function launch an arbitrary
number of parallel node invocations, each with its own input.
"""

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send


class OverallState(TypedDict):
    topics: list[str]
    summaries: Annotated[list[str], operator.add]  # reduce step needs a reducer


class WorkerState(TypedDict):
    topic: str


def dispatch(state: OverallState) -> list[Send]:
    # one Send per topic -- "summarize" runs once per item, each with its
    # own WorkerState-shaped input, all in parallel
    return [Send("summarize", {"topic": t}) for t in state["topics"]]


def summarize(state: WorkerState) -> dict:
    return {"summaries": [f"summary of {state['topic']}"]}


graph = StateGraph(OverallState)
graph.add_node("summarize", summarize)
# a conditional edge straight off START, returning Send objects instead of
# node-name strings, is what makes the fan-out dynamic (topics can be any length)
graph.add_conditional_edges(START, dispatch, ["summarize"])
graph.add_edge("summarize", END)
app = graph.compile()


if __name__ == "__main__":
    result = app.invoke({"topics": ["cats", "dogs", "birds"], "summaries": []})
    print(result)

    # works the same for any number of topics -- nothing about the graph
    # structure changes
    result = app.invoke({"topics": ["one"], "summaries": []})
    print(result)
