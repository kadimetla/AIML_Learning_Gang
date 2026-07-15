"""config={"max_concurrency": N} — caps how many branches run in parallel when a graph fans out."""

import time
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph


def append(a: list[str], b: list[str]) -> list[str]:
    return a + b


class GraphState(TypedDict):
    log: Annotated[list[str], append]


def make_worker(name: str):
    def worker(state: GraphState) -> GraphState:
        start = time.monotonic()
        time.sleep(0.5)
        return {"log": [f"{name} ran at t={start:.2f}"]}

    return worker


graph = StateGraph(GraphState)
for worker_name in ("a", "b", "c", "d"):
    graph.add_node(worker_name, make_worker(worker_name))
    graph.add_edge(START, worker_name)
    graph.add_edge(worker_name, END)
app = graph.compile()


if __name__ == "__main__":
    t0 = time.monotonic()
    # all 4 branches run at once (unbounded) -> finishes in ~0.5s
    result = app.invoke({"log": []}, config={})
    print(f"unbounded: {time.monotonic() - t0:.2f}s -> {result['log']}")

    t0 = time.monotonic()
    # only 1 branch runs at a time -> finishes in ~2.0s (4 x 0.5s, serialized)
    result = app.invoke({"log": []}, config={"max_concurrency": 1})
    print(f"max_concurrency=1: {time.monotonic() - t0:.2f}s -> {result['log']}")
