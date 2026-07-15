"""get_state_history() + update_state() -- rewind to an earlier checkpoint,
optionally edit it, and resume from there instead of the beginning.

Builds on the same checkpointer + thread_id mechanism as examples/hitl/ and
examples/07_interrupt_before.py -- every super-step is its own checkpoint,
and nothing is deleted when you invoke() again, so you can always go back.
"""

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    steps: list[str]


def step1(state: GraphState) -> GraphState:
    return {"steps": state["steps"] + ["step1"]}


def step2(state: GraphState) -> GraphState:
    return {"steps": state["steps"] + ["step2"]}


def step3(state: GraphState) -> GraphState:
    return {"steps": state["steps"] + ["step3"]}


graph = StateGraph(GraphState)
graph.add_node("step1", step1)
graph.add_node("step2", step2)
graph.add_node("step3", step3)
graph.add_edge(START, "step1")
graph.add_edge("step1", "step2")
graph.add_edge("step2", "step3")
graph.add_edge("step3", END)
app = graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "time-travel-1"}}
    result = app.invoke({"steps": []}, config=config)
    print(f"final result: {result}")

    print("\nfull checkpoint history (newest first):")
    history = list(app.get_state_history(config))
    for snapshot in history:
        print(f"  next={snapshot.next!r:20} values={snapshot.values}")

    # find the checkpoint right after step1 ran, before step2/step3
    checkpoint_after_step1 = next(h for h in history if h.values.get("steps") == ["step1"])

    # update_state() edits that checkpoint's values and returns a config
    # pointing at the *new* checkpoint it just wrote -- the original history
    # entry is untouched, this forks a new branch instead of mutating the past
    forked_config = app.update_state(
        checkpoint_after_step1.config, {"steps": ["step1", "OVERRIDDEN"]}
    )

    # invoke(None, ...) resumes from that forked checkpoint's "next" node (step2)
    result = app.invoke(None, config=forked_config)
    print(f"\nresult after forking from step1 and overriding: {result}")
    # note: original run's history (steps2/step3 after the real step1) is
    # still there too -- forking creates a new branch, it doesn't erase one
