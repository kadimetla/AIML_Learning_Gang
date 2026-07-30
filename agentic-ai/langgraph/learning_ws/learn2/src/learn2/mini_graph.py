"""Minimal node/edge graph engine, shared by every sample in this package.

This is the reusable plumbing behind LangGraph's `StateGraph`: a dict of
named nodes, a dict of edges (fixed or conditional), and a loop that walks
from START to END. It's pulled out once so each sample module only has to
show its own nodes and edges -- the same way a LangGraph user never has to
reimplement `CompiledGraph.invoke()`.
"""

from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import FastAPI
from pydantic import BaseModel

START = "__start__"
END = "__end__"

NodeFn = Callable[[dict[str, Any]], dict[str, Any]]
EdgeTarget = str | Callable[[dict[str, Any]], str]

StateT = TypeVar("StateT", bound=BaseModel)


class Graph:
    """Mirrors LangGraph's `StateGraph`: add_node, add_edge, invoke."""

    def __init__(self) -> None:
        self.nodes: dict[str, NodeFn] = {}
        self.edges: dict[str, EdgeTarget] = {}

    def add_node(self, name: str, fn: NodeFn) -> None:
        self.nodes[name] = fn

    def add_edge(self, source: str, target: EdgeTarget) -> None:
        """`target` is either a fixed next-node name, or a function of the
        state that returns one -- i.e. `add_edge` vs `add_conditional_edges`.
        """
        self.edges[source] = target

    def invoke(self, initial_state: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        state = dict(initial_state)
        trace: list[str] = []
        current = START
        while True:
            target = self.edges[current]
            current = target(state) if callable(target) else target
            if current == END:
                break
            trace.append(current)
            state.update(self.nodes[current](state))
        return state, trace


def node_route(
    app: FastAPI, graph: Graph, name: str, state_model: type[StateT]
) -> Callable[[NodeFn], NodeFn]:
    """Register `fn` as a graph node AND expose it as its own FastAPI route,
    so a single node can be called over HTTP in isolation -- the same way
    you might poke one LangGraph node function without running the whole
    graph.
    """

    def decorator(fn: NodeFn) -> NodeFn:
        graph.add_node(name, fn)

        @app.post(f"/nodes/{name}", response_model=state_model, tags=["nodes"])
        def run_single_node(state: state_model) -> state_model:  # type: ignore[valid-type]
            update = fn(state.model_dump())
            return state_model(**{**state.model_dump(), **update})

        run_single_node.__name__ = f"run_{name}"
        return fn

    return decorator
