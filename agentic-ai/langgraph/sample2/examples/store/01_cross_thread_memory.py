"""Store -- long-term memory shared *across* threads, unlike a checkpointer
(which is scoped to a single thread_id, see examples/hitl/ and
examples/time_travel/).

get_store() (from langgraph.config, same module as get_stream_writer used in
examples/11_stream_mode_custom.py) gives a node access to the store attached
at compile time. Data is organized under a (namespace_tuple, key) pair --
here (("preferences", user_id), "favorite_color") -- so it's easy to scope
to "this user's data" regardless of which conversation thread wrote it.
"""

from typing import TypedDict

from langgraph.config import get_store
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore


class GraphState(TypedDict):
    user_id: str
    message: str
    reply: str


def remember_and_reply(state: GraphState) -> GraphState:
    store = get_store()
    namespace = ("preferences", state["user_id"])

    if "favorite color is" in state["message"]:
        color = state["message"].split("favorite color is")[-1].strip()
        store.put(namespace, "favorite_color", {"color": color})
        return {"reply": f"got it, your favorite color is {color}"}

    existing = store.get(namespace, "favorite_color")
    if existing:
        return {"reply": f"your favorite color is {existing.value['color']}"}
    return {"reply": "I don't know your favorite color yet"}


graph = StateGraph(GraphState)
graph.add_node("remember_and_reply", remember_and_reply)
graph.add_edge(START, "remember_and_reply")
graph.add_edge("remember_and_reply", END)
app = graph.compile(store=InMemoryStore())


if __name__ == "__main__":
    # thread A: user states a preference
    result = app.invoke(
        {"user_id": "u1", "message": "my favorite color is blue", "reply": ""},
        config={"configurable": {"thread_id": "thread-A"}},
    )
    print(f"thread-A: {result['reply']}")

    # thread B: a *different* conversation thread, same user_id -- the store
    # is shared across threads, unlike checkpointed state
    result = app.invoke(
        {"user_id": "u1", "message": "what is my favorite color?", "reply": ""},
        config={"configurable": {"thread_id": "thread-B"}},
    )
    print(f"thread-B: {result['reply']}")

    # a different user_id has no memory of it -- namespaced per user
    result = app.invoke(
        {"user_id": "u2", "message": "what is my favorite color?", "reply": ""},
        config={"configurable": {"thread_id": "thread-C"}},
    )
    print(f"thread-C (different user): {result['reply']}")
