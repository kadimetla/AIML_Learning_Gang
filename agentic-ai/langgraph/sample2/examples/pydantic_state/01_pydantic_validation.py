"""Using a pydantic BaseModel instead of TypedDict for graph state.

Unlike TypedDict (zero runtime checks, as shown in examples/not_required/),
a pydantic model is validated on every invoke() -- missing/wrong-typed/
out-of-range fields raise a ValidationError before any node runs.
"""

from pydantic import BaseModel, Field

from langgraph.graph import END, START, StateGraph


class GraphState(BaseModel):
    name: str = Field(min_length=1)
    age: int = Field(ge=0, le=150)
    greeting: str = ""


def greet(state: GraphState) -> dict:
    return {"greeting": f"Hello, {state.name} ({state.age})!"}


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_edge(START, "greet")
graph.add_edge("greet", END)
app = graph.compile()


if __name__ == "__main__":
    print(app.invoke({"name": "sample2", "age": 5}))

    print("\nmissing required field:")
    try:
        app.invoke({"age": 5})
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")

    print("\nempty string fails min_length:")
    try:
        app.invoke({"name": "", "age": 5})
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")

    print("\nnegative age fails ge=0:")
    try:
        app.invoke({"name": "sample2", "age": -1})
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")

    print("\nunknown key -- unlike TypedDict, still silently dropped by default:")
    print(app.invoke({"name": "sample2", "age": 5, "bogus": "x"}))
