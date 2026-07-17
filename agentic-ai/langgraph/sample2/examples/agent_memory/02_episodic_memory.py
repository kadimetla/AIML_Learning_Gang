"""Episodic memory -- *what happened before*: specific, individually
recallable past events, not just "whatever the current state is" (that's
semantic memory, see 03_semantic_memory.py) and not just "state alive for
one run" (working memory, see 01_working_memory.py).

A checkpointer scoped to one thread_id is what makes this possible -- see
../checkpointing/01_multi_turn_memory.py for the base mechanism. The
difference in emphasis here: get_state_history() (the same primitive
../time_travel/01_replay_and_fork.py uses to rewind) lets you go back and
recall one particular past episode out of several, not just the latest one.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    messages: Annotated[list, add_messages]


def log_event(state: GraphState) -> dict:
    return {}  # add_messages already appended the new event -- nothing to add


graph = StateGraph(GraphState)
graph.add_node("log_event", log_event)
graph.add_edge(START, "log_event")
graph.add_edge("log_event", END)
app = graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "diary-1"}}
    for event in ["woke up at 7am", "shipped the PR", "went for a run"]:
        app.invoke({"messages": [HumanMessage(event)]}, config=config)

    history = list(app.get_state_history(config))
    print(f"{len(history)} checkpoints recorded (newest first)")

    # recall one specific past episode -- right after the *second* event
    # happened, before the third -- not just the latest snapshot
    episode = next(h for h in history if len(h.values["messages"]) == 2)
    print(f"episode recalled (right after event 2): {[m.content for m in episode.values['messages']]}")

    latest = history[0]
    print(f"most recent state: {[m.content for m in latest.values['messages']]}")
