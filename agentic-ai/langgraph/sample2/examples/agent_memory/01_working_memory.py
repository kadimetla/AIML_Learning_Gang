"""Working memory -- what's happening *right now*, scoped to a single run.

No checkpointer here: state only exists between START and END of one
invoke() call. As soon as invoke() returns, LangGraph forgets everything --
call it again and there's no trace of the last run at all. Compare with
02_episodic_memory.py (specific past runs, individually recallable) and
03_semantic_memory.py (facts that persist regardless of which run produced
them) -- both exist only because they deliberately add persistence that
this example doesn't have.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    task: str
    steps_done: list[str]
    result: str


def step_one(state: GraphState) -> dict:
    return {"steps_done": state["steps_done"] + ["gathered input"]}


def step_two(state: GraphState) -> dict:
    return {"steps_done": state["steps_done"] + ["processed"], "result": f"done: {state['task']}"}


graph = StateGraph(GraphState)
graph.add_node("step_one", step_one)
graph.add_node("step_two", step_two)
graph.add_edge(START, "step_one")
graph.add_edge("step_one", "step_two")
graph.add_edge("step_two", END)
app = graph.compile()  # no checkpointer -- nothing survives past this invoke()


if __name__ == "__main__":
    result = app.invoke({"task": "summarize the report", "steps_done": [], "result": ""})
    print(f"run 1 working memory: {result['steps_done']} -> {result['result']}")

    # a second, unrelated invoke() -- no trace of run 1's steps_done exists
    # anywhere; working memory doesn't carry across runs by design
    result = app.invoke({"task": "translate the report", "steps_done": [], "result": ""})
    print(f"run 2 working memory: {result['steps_done']} -> {result['result']}")
