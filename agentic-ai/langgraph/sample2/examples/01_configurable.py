"""config={"configurable": {...}} — pass your own runtime values into a node."""

from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    name: str
    greeting: str


def greet(state: GraphState, config: RunnableConfig) -> GraphState:
    title = config["configurable"].get("title", "")
    return {"greeting": f"Hello, {title}{state['name']}!"}


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_edge(START, "greet")
graph.add_edge("greet", END)
app = graph.compile()


if __name__ == "__main__":
    # same graph, same input — only "configurable" changes between calls
    print(app.invoke({"name": "sample2"}))
    print(app.invoke({"name": "sample2"}, config={"configurable": {"title": "Dr. "}}))
    print(app.invoke({"name": "sample2"}, config={"configurable": {"title": "Capt. "}}))
