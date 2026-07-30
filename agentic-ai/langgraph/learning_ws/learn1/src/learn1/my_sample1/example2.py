"""Controller -> service (external API) -> formatter, as a LangGraph graph.

Same flow as learn2's `src/learn2/api_pipeline/app.py`, expressed with
LangGraph's `StateGraph` instead of hand-rolled node/edge dicts. Every
`add_node` / `add_edge` / `add_conditional_edges` call below has a literal
counterpart there -- read the two side by side.
"""

from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph


class PipelineState(TypedDict):
    username: str
    profile: dict[str, Any] | None
    summary: str | None
    status: str


def controller_node(state: PipelineState) -> dict:
    """Entry point: validate/normalize the incoming request."""
    return {"username": state["username"].strip().lower(), "status": "received"}


GITHUB_API = "https://api.github.com/users/{username}"


def service_node(state: PipelineState) -> dict:
    """The only node that talks to the network -- calls an external API."""
    try:
        response = httpx.get(GITHUB_API.format(username=state["username"]), timeout=5.0)
    except httpx.HTTPError:
        return {"status": "fetch_failed"}
    if response.status_code != 200:
        return {"status": "fetch_failed"}
    return {"profile": response.json(), "status": "fetched"}


def formatter_node(state: PipelineState) -> dict:
    profile = state["profile"]
    summary = (
        f"{profile.get('name') or profile['login']} has "
        f"{profile['public_repos']} public repos and {profile['followers']} followers."
    )
    return {"summary": summary, "status": "formatted"}


def format_error_node(state: PipelineState) -> dict:
    return {
        "summary": f"Could not fetch a GitHub profile for '{state['username']}'.",
        "status": "error",
    }


def route_after_service(state: PipelineState) -> str:
    return "formatter" if state["status"] == "fetched" else "format_error"


graph = StateGraph(PipelineState)
graph.add_node("controller", controller_node)
graph.add_node("service", service_node)
graph.add_node("formatter", formatter_node)
graph.add_node("format_error", format_error_node)

graph.add_edge(START, "controller")
graph.add_edge("controller", "service")
graph.add_conditional_edges(
    "service",
    route_after_service,
    {"formatter": "formatter", "format_error": "format_error"},
)
graph.add_edge("formatter", END)
graph.add_edge("format_error", END)

app = graph.compile()

if __name__ == "__main__":
    ok = app.invoke({"username": "octocat", "profile": None, "summary": None, "status": "new"})
    print(ok)

    broken = app.invoke(
        {"username": "this-user-should-not-exist-12345", "profile": None, "summary": None, "status": "new"}
    )
    print(broken)
