"""Custom @field_validator business rules on top of pydantic's built-in checks.

Field constraints like Field(ge=0) only cover simple ranges/lengths. A
@field_validator runs your own function, so you can enforce rules the type
system alone can't express -- e.g. "email must contain an @".
"""

from pydantic import BaseModel, field_validator

from langgraph.graph import END, START, StateGraph


class GraphState(BaseModel):
    email: str
    greeting: str = ""

    @field_validator("email")
    @classmethod
    def email_must_have_at_sign(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError(f"{value!r} is not a valid email (missing '@')")
        return value.lower()  # validators can also normalize the value


def greet(state: GraphState) -> dict:
    return {"greeting": f"Hello, {state.email}!"}


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_edge(START, "greet")
graph.add_edge("greet", END)
app = graph.compile()


if __name__ == "__main__":
    # the validator's .lower() is visible inside "greeting" (built from the
    # validated model that greet() received) -- but the "email" key in the
    # final result keeps the original casing, since LangGraph stores raw
    # channel values and only overwrites what a node actually returns
    print(app.invoke({"email": "Sample2@Example.com"}))

    print("\ninvalid email rejected by the custom validator:")
    try:
        app.invoke({"email": "not-an-email"})
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")
