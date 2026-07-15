from typing import NotRequired, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    name: str
    greeting: NotRequired[str]


def greet(state: GraphState, config: RunnableConfig) -> GraphState:
    title = config["configurable"].get("title", "")
    return {"greeting": f"Hello, {title}{state['name']}!"}


def shout(state: GraphState) -> GraphState:
    return {"greeting": state["greeting"].upper()}


def build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("greet", greet)
    graph.add_node("shout", shout)

    graph.add_edge(START, "greet")
    graph.add_edge("greet", "shout")
    graph.add_edge("shout", END)

    return graph.compile()


def main():
    app = build_graph()
    app.get_graph().draw_mermaid_png(output_file_path="graph.png")
    result = app.invoke(
        {"name": "sample2"}, config={"configurable": {"title": "Dr. "}}
    )
    print(result["greeting"])

    # stream_mode="values" yields the full state after each node instead of
    # waiting for the graph to finish
    for chunk in app.stream(
        {"name": "sample2"},
        config={"configurable": {"title": "Dr. "}},
        stream_mode="values",
    ):
        print(chunk)

    # stream_mode="updates" yields only what each node returned, keyed by node name
    for chunk in app.stream(
        {"name": "sample2"},
        config={"configurable": {"title": "Dr. "}},
        stream_mode="updates",
    ):
        print(chunk)


if __name__ == "__main__":
    main()
