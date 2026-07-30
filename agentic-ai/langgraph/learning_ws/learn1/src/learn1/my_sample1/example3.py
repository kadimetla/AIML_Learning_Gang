"""Same controller -> service -> formatter flow, wired with plain Python.

No `StateGraph`, no node/edge dicts, no framework at all -- just ordinary
sequential function calls with an if/else for the one branch. `PipelineState`
and every `*_node` function are imported unchanged from `example2.py`: they
have zero LangGraph-specific code in them, only the *wiring* differs.

`run_pipeline()` below does exactly what `graph.compile().invoke(state)`
does in example2.py. LangGraph didn't invent new mechanics for this flow --
it gave a name (nodes, edges, state) and a generic engine to a pattern
you'd write by hand anyway.
"""

from learn1.my_sample1.example2 import (
    PipelineState,
    controller_node,
    format_error_node,
    formatter_node,
    service_node,
)


def run_pipeline(state: PipelineState) -> PipelineState:
    state = {**state, **controller_node(state)}
    state = {**state, **service_node(state)}
    if state["status"] == "fetched":
        state = {**state, **formatter_node(state)}
    else:
        state = {**state, **format_error_node(state)}
    return state  # type: ignore[return-value]


if __name__ == "__main__":
    ok = run_pipeline({"username": "octocat", "profile": None, "summary": None, "status": "new"})
    print(ok)

    broken = run_pipeline(
        {"username": "this-user-should-not-exist-12345", "profile": None, "summary": None, "status": "new"}
    )
    print(broken)
