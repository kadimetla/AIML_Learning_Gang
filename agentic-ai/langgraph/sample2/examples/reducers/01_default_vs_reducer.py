"""A reducer decides how a node's return value gets merged into existing
state for that key, instead of just overwriting it.

Annotated[type, reducer_fn] is how you attach one to a state field.
Without it, the default behavior is plain overwrite (last write wins).
"""

from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph


def append(existing: list[str], new: list[str]) -> list[str]:
    return existing + new


class OverwriteState(TypedDict):
    log: list[str]  # no reducer -> each node's return replaces this key


class AppendState(TypedDict):
    log: Annotated[list[str], append]  # custom reducer -> merged instead


def node_a(state):
    return {"log": ["a ran"]}


def node_b(state):
    return {"log": ["b ran"]}


def build(state_schema):
    graph = StateGraph(state_schema)
    graph.add_node("a", node_a)
    graph.add_node("b", node_b)
    graph.add_edge(START, "a")
    graph.add_edge("a", "b")
    graph.add_edge("b", END)
    return graph.compile()


if __name__ == "__main__":
    overwrite_app = build(OverwriteState)
    print(f"no reducer (overwrite): {overwrite_app.invoke({'log': []})}")
    # only "b ran" survives -- b's return value replaced a's entirely

    append_app = build(AppendState)
    print(f"custom reducer (append): {append_app.invoke({'log': []})}")
    # both survive -- each node's return value is merged via append()
