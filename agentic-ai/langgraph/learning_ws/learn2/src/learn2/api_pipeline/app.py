"""Controller -> service (external API) -> formatter, as a state machine.

The classic web-app layering -- a controller that accepts a request, a
service that calls out to an external API, and a formatter that shapes the
response -- is exactly a small graph: three nodes threading shared state,
plus one conditional edge for the error path when the API call fails.

Compare this file node-for-node with
`learn1/src/learn1/my_sample1/example2.py`, which builds the identical flow
with LangGraph's own `StateGraph`. The engine here (`Graph`, `node_route`)
is `learn2.mini_graph`, the same one used by `learn2.state_machine.app`.
"""

from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from learn2.mini_graph import END, START, Graph, node_route

app = FastAPI(title="Controller -> Service -> Formatter, FastAPI edition")

GITHUB_API = "https://api.github.com/users/{username}"


class PipelineState(BaseModel):
    username: str
    profile: dict[str, Any] | None = None
    summary: str | None = None
    status: str = "new"


class GraphRunResult(BaseModel):
    trace: list[str]
    final_state: PipelineState


graph = Graph()


def node(name: str):
    return node_route(app, graph, name, PipelineState)


@node("controller")
def controller(state: dict[str, Any]) -> dict[str, Any]:
    """Entry point: validate/normalize the incoming request."""
    return {"username": state["username"].strip().lower(), "status": "received"}


@node("service")
def service(state: dict[str, Any]) -> dict[str, Any]:
    """The only node that talks to the network -- calls an external API."""
    try:
        response = httpx.get(GITHUB_API.format(username=state["username"]), timeout=5.0)
    except httpx.HTTPError:
        return {"status": "fetch_failed"}
    if response.status_code != 200:
        return {"status": "fetch_failed"}
    return {"profile": response.json(), "status": "fetched"}


@node("formatter")
def formatter(state: dict[str, Any]) -> dict[str, Any]:
    profile = state["profile"]
    summary = (
        f"{profile.get('name') or profile['login']} has "
        f"{profile['public_repos']} public repos and {profile['followers']} followers."
    )
    return {"summary": summary, "status": "formatted"}


@node("format_error")
def format_error(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": f"Could not fetch a GitHub profile for '{state['username']}'.",
        "status": "error",
    }


graph.add_edge(START, "controller")
graph.add_edge("controller", "service")
graph.add_edge(
    "service",
    lambda state: "formatter" if state["status"] == "fetched" else "format_error",
)
graph.add_edge("formatter", END)
graph.add_edge("format_error", END)


@app.post("/graph/run", response_model=GraphRunResult, tags=["graph"])
def run(initial_state: PipelineState) -> GraphRunResult:
    final_state, trace = graph.invoke(initial_state.model_dump())
    return GraphRunResult(trace=trace, final_state=PipelineState(**final_state))
