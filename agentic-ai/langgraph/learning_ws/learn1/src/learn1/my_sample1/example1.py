from typing import TypedDict

from langgraph.graph import StateGraph


# state

class GlobalState(TypedDict):
    question: str
    answer: str


def answer_node(state: GlobalState) -> dict:
    return {"answer": f" you asked : {state["question"] } " + " is 42"}

graph = StateGraph(GlobalState)
graph.add_node("answer", answer_node)
graph.add_edge("question", "answer")