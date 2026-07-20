from typing import TypedDict
from langgraph.graph import START, END, StateGraph
from langgraph.runtime import Runtime

class State(TypedDict):
    question: str
    answer: str
    internal_score: int

class InputState(TypedDict):
    question: str

class OutputState(TypedDict):
    answer: str

class Context(TypedDict):
    user_name: str

def answer_node(state: State, runtime: Runtime[Context]) -> State:
    return {
        "answer": f"{runtime.context['user_name']} asked: {state['question']}",
        "internal_score": 1,
    }
builder = StateGraph(
      state_schema=State,
      input_schema=InputState,
      output_schema=OutputState,
      context_schema=Context,
  )

builder.add_node("answer", answer_node)
builder.add_edge(START, "answer")
builder.add_edge("answer", END)

graph = builder.compile()
graph.invoke(
    {"question": "What is state?"},
    context={"user_name": "Ada"},
)
