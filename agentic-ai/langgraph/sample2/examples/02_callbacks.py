"""config={"callbacks": [...]} — hook into node start/end events (basis for tracing/OTel)."""

from typing import Any, TypedDict
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    name: str
    greeting: str


def greet(state: GraphState) -> GraphState:
    return {"greeting": f"Hello, {state['name']}!"}


def shout(state: GraphState) -> GraphState:
    return {"greeting": state["greeting"].upper()}


class PrintingCallbackHandler(BaseCallbackHandler):
    """Every chain/node LangGraph runs fires these — a real tracer (e.g. OTel)
    would open/close a span here instead of printing."""

    def on_chain_start(
        self, serialized: dict[str, Any], inputs: dict[str, Any], *, run_id: UUID, **kwargs: Any
    ) -> None:
        name = (serialized or {}).get("name", "?")
        print(f"[START] {name} run_id={str(run_id)[:8]} inputs={inputs}")

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        print(f"[END]   run_id={str(run_id)[:8]} outputs={outputs}")


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_node("shout", shout)
graph.add_edge(START, "greet")
graph.add_edge("greet", "shout")
graph.add_edge("shout", END)
app = graph.compile()


if __name__ == "__main__":
    app.invoke({"name": "sample2"}, config={"callbacks": [PrintingCallbackHandler()]})
