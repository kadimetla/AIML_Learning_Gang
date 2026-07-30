"""A tiny order-processing state machine, built with nothing but FastAPI.

The point of this file is to show that LangGraph's core idea -- a graph of
named *nodes* wired together by *edges*, threading a shared *state* through
them -- is not special machinery. It's the same shape as a web app:

    LangGraph                          This file
    ----------------------------       ----------------------------
    state: TypedDict                   state: OrderState (BaseModel)
    graph.add_node(name, fn)           @node("name") on a plain function
    fn(state) -> dict (partial update) same contract, unchanged
    graph.add_edge(a, b)               graph.add_edge(a, b)
    graph.add_conditional_edges(a, fn) graph.add_edge(a, fn)
    START / END                        START / END (from learn2.mini_graph)
    graph.compile().invoke(state)      graph.invoke(state)

The engine itself (`Graph`, `node_route`) lives in `learn2.mini_graph` and
is shared by every sample in this package -- see it once there instead of
reimplementing it per lesson.

Each node is registered on the graph *and* exposed as its own FastAPI route
(`POST /nodes/{name}`), so you can call a single node in isolation -- the
same way you'd unit-test a single LangGraph node function without running
the whole graph. `POST /graph/run` walks the whole routing table end to end
and returns the path it took plus the final state.
"""

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from learn2.mini_graph import END, START, Graph, node_route

app = FastAPI(title="State machine, FastAPI edition")


class OrderState(BaseModel):
    order_id: str
    amount: float
    stock_available: bool = True
    status: str = "new"


class GraphRunResult(BaseModel):
    trace: list[str]
    final_state: OrderState


graph = Graph()


def node(name: str):
    return node_route(app, graph, name, OrderState)


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


graph.add_edge(START, "receive_order")
graph.add_edge("receive_order", "validate_order")
graph.add_edge(
    "validate_order",
    lambda state: "fulfill_order" if state["status"] == "validated" else "reject_order",
)
graph.add_edge("fulfill_order", "notify_customer")
graph.add_edge("reject_order", "notify_customer")
graph.add_edge("notify_customer", END)


@app.post("/graph/run", response_model=GraphRunResult, tags=["graph"])
def run(initial_state: OrderState) -> GraphRunResult:
    final_state, trace = graph.invoke(initial_state.model_dump())
    return GraphRunResult(trace=trace, final_state=OrderState(**final_state))
