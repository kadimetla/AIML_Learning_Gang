"""NotRequired[...] — mark one TypedDict field optional without touching `total`.

`greeting` doesn't exist until `greet` runs, so `invoke()` is legitimately
called with it missing. NotRequired tells a type checker that's fine, while
`name` stays required.
"""

from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):   # total=True (default): every field required...
    name: str                  # ...except this one:
    greeting: NotRequired[str]


def greet(state: GraphState) -> GraphState:
    return {"greeting": f"Hello, {state['name']}!"}


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_edge(START, "greet")
graph.add_edge("greet", END)
app = graph.compile()


if __name__ == "__main__":
    # a type checker accepts this even though "greeting" is absent
    print(app.invoke({"name": "sample2"}))

    # this is still just a runtime dict -- NotRequired adds no runtime check,
    # so a genuinely missing required field only fails once a node reads it
    try:
        app.invoke({})
    except KeyError as e:
        print(f"missing required field only fails at read time: {e}")
