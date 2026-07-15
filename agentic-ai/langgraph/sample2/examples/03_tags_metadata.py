"""config={"tags": [...], "metadata": {...}} — labels attached to a run for filtering in tracing tools."""

from typing import Any, TypedDict
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    name: str
    greeting: str


def greet(state: GraphState) -> GraphState:
    return {"greeting": f"Hello, {state['name']}!"}


class LabelPrintingHandler(BaseCallbackHandler):
    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        print(f"tags={tags} metadata={metadata}")


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_edge(START, "greet")
graph.add_edge("greet", END)
app = graph.compile()


if __name__ == "__main__":
    # tags/metadata carry no behavior on their own — they just ride along on every
    # run/span so an observability backend (LangSmith, OTel, ...) can filter by them
    app.invoke(
        {"name": "sample2"},
        config={
            "tags": ["classroom-demo", "greeting-flow"],
            "metadata": {"user_id": "student-42", "lesson": "invoke-config"},
            "callbacks": [LabelPrintingHandler()],
        },
    )
