"""config={"run_name": ..., "run_id": ...} — name/identify a specific run."""

import uuid
from typing import Any, TypedDict
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    name: str
    greeting: str


def greet(state: GraphState) -> GraphState:
    return {"greeting": f"Hello, {state['name']}!"}


class IdPrintingHandler(BaseCallbackHandler):
    def on_chain_start(
        self, serialized: dict[str, Any], inputs: dict[str, Any], *, run_id: UUID, **kwargs: Any
    ) -> None:
        print(f"name={(serialized or {}).get('name')!r} run_id={run_id}")


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_edge(START, "greet")
graph.add_edge("greet", END)
app = graph.compile()


if __name__ == "__main__":
    my_run_id = uuid.uuid4()
    print(f"caller-supplied run_id: {my_run_id}")
    app.invoke(
        {"name": "sample2"},
        config={
            "run_name": "classroom-demo-run",
            "run_id": my_run_id,
            "callbacks": [IdPrintingHandler()],
        },
    )
    # useful when you need to correlate this run with something external —
    # e.g. store my_run_id alongside a support ticket, then look it up later
    # in a trace viewer by that exact id
