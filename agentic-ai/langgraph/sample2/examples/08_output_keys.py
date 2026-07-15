"""invoke(..., output_keys=...) — return only specific state keys instead of the whole state."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    name: str
    greeting: str
    shout_count: int


def greet(state: GraphState) -> GraphState:
    return {"greeting": f"Hello, {state['name']}!"}


def shout(state: GraphState) -> GraphState:
    return {"greeting": state["greeting"].upper(), "shout_count": 1}


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_node("shout", shout)
graph.add_edge(START, "greet")
graph.add_edge("greet", "shout")
graph.add_edge("shout", END)
app = graph.compile()


if __name__ == "__main__":
    full = app.invoke({"name": "sample2", "shout_count": 0})
    print(f"default (all keys):        {full}")

    trimmed = app.invoke({"name": "sample2", "shout_count": 0}, output_keys="greeting")
    print(f"output_keys='greeting':    {trimmed}")

    trimmed_multi = app.invoke(
        {"name": "sample2", "shout_count": 0}, output_keys=["greeting", "shout_count"]
    )
    print(f"output_keys=[...]:         {trimmed_multi}")
