from typing import TypedDict

from langgraph.constants import START, END
from langgraph.graph import StateGraph


# state

class GlobalState(TypedDict):
    question: str
    answer: str


def answer_node(state: GlobalState) -> dict:
    return {"answer": f" you asked : {state["question"] } " + " is 42"}

graph = StateGraph(GlobalState)
graph.add_node("answer", answer_node)
graph.add_edge(START, "answer")
graph.add_edge("answer", END)
app = graph.compile()
print(app.invoke({"question": "what is the answer to life, the universe and everything"}))