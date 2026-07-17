"""Semantic memory -- *what's true*: general facts held independently of
when/how they were learned or which conversation surfaced them. A Store
(unlike a checkpointer) is keyed by namespace/key, not by thread_id, so
facts about "this user" are reachable from any thread -- see
../store/01_cross_thread_memory.py for the base mechanism.

The distinction from 02_episodic_memory.py's checkpoint history: episodic
memory is a growing log of past events (every episode kept). Semantic
memory is the opposite shape -- store.put() on an existing key *overwrites*
it, because a fact only has one current value. Learning the user's favorite
color was blue, then green, means episodic memory keeps both events, but
semantic memory just says "it's green" now.
"""

from typing import TypedDict

from langgraph.config import get_store
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore


class GraphState(TypedDict):
    user_id: str
    fact: str  # "key=value" to learn a fact, "" to recall everything known
    reply: str


def learn_or_recall(state: GraphState) -> dict:
    store = get_store()
    namespace = ("facts", state["user_id"])

    if state["fact"]:
        key, _, value = state["fact"].partition("=")
        store.put(namespace, key.strip(), {"value": value.strip()})
        return {"reply": f"noted: {key.strip()} = {value.strip()}"}

    items = store.search(namespace)
    if not items:
        return {"reply": "I don't know anything about this user yet"}
    facts = ", ".join(f"{item.key}={item.value['value']}" for item in items)
    return {"reply": f"what I know: {facts}"}


graph = StateGraph(GraphState)
graph.add_node("learn_or_recall", learn_or_recall)
graph.add_edge(START, "learn_or_recall")
graph.add_edge("learn_or_recall", END)
app = graph.compile(store=InMemoryStore())


if __name__ == "__main__":
    print(app.invoke({"user_id": "u1", "fact": "favorite_color=blue", "reply": ""})["reply"])

    # updates the *same* fact -- semantic memory holds one current value per
    # key, not a history of every value it ever had (that's episodic memory)
    print(app.invoke({"user_id": "u1", "fact": "favorite_color=green", "reply": ""})["reply"])

    print(app.invoke({"user_id": "u1", "fact": "timezone=IST", "reply": ""})["reply"])

    # recall everything known about u1 -- no thread_id involved at all,
    # semantic memory isn't scoped to a conversation
    result = app.invoke({"user_id": "u1", "fact": "", "reply": ""})
    print(f"recalled: {result['reply']}")
