"""stream_mode="custom" — emit your own arbitrary progress data from inside a node.

Unlike "values"/"updates" (tied to state) or "messages" (tied to LLM tokens),
"custom" lets a node push anything it wants via get_stream_writer(), e.g. a
percent-complete update for a long-running step. It doesn't touch state at all.
"""

from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    name: str
    greeting: str


def greet(state: GraphState) -> GraphState:
    writer = get_stream_writer()
    writer({"node": "greet", "progress": "starting"})
    greeting = f"Hello, {state['name']}!"
    writer({"node": "greet", "progress": "done"})
    return {"greeting": greeting}


def shout(state: GraphState) -> GraphState:
    writer = get_stream_writer()
    writer({"node": "shout", "progress": "shouting"})
    return {"greeting": state["greeting"].upper()}


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_node("shout", shout)
graph.add_edge(START, "greet")
graph.add_edge("greet", "shout")
graph.add_edge("shout", END)
app = graph.compile()


if __name__ == "__main__":
    print("custom progress events (no state involved):")
    for chunk in app.stream({"name": "sample2"}, stream_mode="custom"):
        print(f"  {chunk}")

    print("\ncombine with 'updates' to see both progress events and state changes:")
    for mode, chunk in app.stream({"name": "sample2"}, stream_mode=["custom", "updates"]):
        print(f"  mode={mode} chunk={chunk}")
