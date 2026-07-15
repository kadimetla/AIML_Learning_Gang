"""stream_mode=... — controls what shape each "chunk" of a graph run takes.

Most naturally used with .stream(), which yields one chunk per super-step as
the graph runs instead of waiting for the end. invoke() accepts it too, but
just collects the chunks instead of yielding them (see the bottom of this file).
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    name: str
    greeting: str


def greet(state: GraphState) -> GraphState:
    return {"greeting": f"Hello, {state['name']}!"}


def shout(state: GraphState) -> GraphState:
    return {"greeting": state["greeting"].upper()}


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_node("shout", shout)
graph.add_edge(START, "greet")
graph.add_edge("greet", "shout")
graph.add_edge("shout", END)
app = graph.compile()


if __name__ == "__main__":
    inputs = {"name": "sample2"}

    print("stream_mode='values' (full state snapshot after each node):")
    for chunk in app.stream(inputs, stream_mode="values"):
        print(f"  {chunk}")

    print("\nstream_mode='updates' (only what each node returned):")
    for chunk in app.stream(inputs, stream_mode="updates"):
        print(f"  {chunk}")

    print("\nstream_mode='debug' (internal step-by-step trace):")
    for chunk in app.stream(inputs, stream_mode="debug"):
        print(f"  type={chunk['type']} step={chunk['step']}")

    print("\nstream_mode=['values', 'updates'] (multiple modes -> (mode, chunk) tuples):")
    for mode, chunk in app.stream(inputs, stream_mode=["values", "updates"]):
        print(f"  mode={mode} chunk={chunk}")

    print("\ninvoke() does respect stream_mode, it just collects every chunk instead of")
    print("yielding them one at a time. With the default 'values' it returns only the")
    print("final state (last chunk); with other modes it returns the full list:")
    print(f"  stream_mode='values'  -> {app.invoke(inputs, stream_mode='values')}")
    print(f"  stream_mode='updates' -> {app.invoke(inputs, stream_mode='updates')}")
