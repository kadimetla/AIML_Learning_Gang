"""A tiny order-processing state machine, built with nothing but FastAPI.

The point of this file is to show that LangGraph's core idea -- a graph of
named *nodes* wired together by *edges*, threading a shared *state* through
them -- is not special machinery. It's the same shape as a web app:

    LangGraph                          This file
    ----------------------------       ----------------------------
    state: TypedDict                   state: OrderState (BaseModel)
    graph.add_node(name, fn)           @node("name") on a plain function
    fn(state) -> dict (partial update) same contract, unchanged
    graph.add_edge(a, b)               EDGES[a] = b
    graph.add_conditional_edges(a, fn) EDGES[a] = fn  (fn(state) -> next name)
    START / END                        START / END
    graph.compile().invoke(state)      run_graph(state)

Each node is *also* a real FastAPI route (POST /nodes/{name}), so you can
call a single node in isolation with curl, exactly like you'd unit-test a
single LangGraph node function. POST /graph/run walks the whole graph, edge
by edge, and returns the path it took plus the final state -- that loop is
literally what `CompiledGraph.invoke()` does under the hood.
"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="State machine, FastAPI edition")

START = "__start__"
END = "__end__"


class OrderState(BaseModel):
    order_id: str
    amount: float
    stock_available: bool = True
    status: str = "new"


class GraphRunResult(BaseModel):
    trace: list[str]
    final_state: OrderState


NodeFn = Callable[[dict[str, Any]], dict[str, Any]]
EdgeTarget = str | Callable[[dict[str, Any]], str]

NODES: dict[str, NodeFn] = {}
EDGES: dict[str, EdgeTarget] = {}


def node(name: str):
    """Register a plain function as a graph node AND expose it as a route.

    Mirrors `graph.add_node(name, fn)`. The wrapped function keeps the
    LangGraph node contract: it takes the current state and returns only
    the fields it wants to change.
    """

    def decorator(fn: NodeFn) -> NodeFn:
        NODES[name] = fn

        @app.post(f"/nodes/{name}", response_model=OrderState, tags=["nodes"])
        def run_single_node(state: OrderState) -> OrderState:
            update = fn(state.model_dump())
            return OrderState(**{**state.model_dump(), **update})

        run_single_node.__name__ = f"run_{name}"
        return fn

    return decorator


def edge(source: str, target: EdgeTarget) -> None:
    """Wire a fixed or conditional transition. Mirrors `graph.add_edge` /
    `graph.add_conditional_edges` (pass a callable for the conditional case).
    """
    EDGES[source] = target


@node("receive_order")
def receive_order(state: dict[str, Any]) -> dict[str, Any]:
    return {"status": "received"}


@node("validate_order")
def validate_order(state: dict[str, Any]) -> dict[str, Any]:
    valid = state["amount"] > 0 and state["stock_available"]
    return {"status": "validated" if valid else "invalid"}


@node("fulfill_order")
def fulfill_order(state: dict[str, Any]) -> dict[str, Any]:
    return {"status": "fulfilled"}


@node("reject_order")
def reject_order(state: dict[str, Any]) -> dict[str, Any]:
    return {"status": "rejected"}


@node("notify_customer")
def notify_customer(state: dict[str, Any]) -> dict[str, Any]:
    return {"status": f"{state['status']}_notified"}


edge(START, "receive_order")
edge("receive_order", "validate_order")
edge(
    "validate_order",
    lambda state: "fulfill_order" if state["status"] == "validated" else "reject_order",
)
edge("fulfill_order", "notify_customer")
edge("reject_order", "notify_customer")
edge("notify_customer", END)


def run_graph(initial_state: OrderState) -> GraphRunResult:
    """The dispatcher loop. Same shape as CompiledGraph.invoke():

    look up where the current node points, run the next node, merge its
    partial update into state, repeat until an edge points at END.
    """
    state: dict[str, Any] = initial_state.model_dump()
    trace: list[str] = []
    current = START

    while True:
        target = EDGES[current]
        current = target(state) if callable(target) else target
        if current == END:
            break
        trace.append(current)
        state.update(NODES[current](state))

    return GraphRunResult(trace=trace, final_state=OrderState(**state))


@app.post("/graph/run", response_model=GraphRunResult, tags=["graph"])
def run(initial_state: OrderState) -> GraphRunResult:
    return run_graph(initial_state)
