"""Same controller -> service -> formatter flow as example2, but the
formatter now pauses with `interrupt()` for a human to approve the summary
before it's considered final -- and the graph is checkpointed to a SQLite
database, so a *different* process can resume the paused run just by
knowing the `thread_id`.

Run this file twice against the same `example4_checkpoints.db`: once to
kick off the run (it pauses and returns an `__interrupt__` payload), and
again -- from a fresh Python process, in principle -- to resume it with an
approve/reject decision.
"""

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from learn1.my_sample1.example2 import (
    PipelineState,
    controller_node,
    format_error_node,
    route_after_service,
    service_node,
)


def formatter_node(state: PipelineState) -> dict:
    """Builds the summary like example2's formatter_node, then pauses for a
    human reviewer to approve it before returning it as final."""
    profile = state["profile"]
    summary = (
        f"{profile.get('name') or profile['login']} has "
        f"{profile['public_repos']} public repos and {profile['followers']} followers."
    )
    approved = interrupt({"summary": summary})
    if not approved:
        return {"summary": "Summary rejected by reviewer.", "status": "rejected"}
    return {"summary": summary, "status": "formatted"}


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


if __name__ == "__main__":
    with SqliteSaver.from_conn_string("example4_checkpoints.db") as checkpointer:
        app = graph.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": "octocat-1"}}
        paused = app.invoke(
            {"username": "octocat", "profile": None, "summary": None, "status": "new"},
            config,
        )
        print("after first invoke (paused for review):", paused)

        # Simulates a *different* process resuming the same thread_id later,
        # e.g. after a human clicks "approve" somewhere.
        final = app.invoke(Command(resume=True), config)
        print("after resume (approved):", final)