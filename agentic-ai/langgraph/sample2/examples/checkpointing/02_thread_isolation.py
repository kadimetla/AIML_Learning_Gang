"""Each thread_id gets a fully separate checkpoint history -- the opposite of
examples/store/, where data is deliberately shared *across* threads.

Same graph, same checkpointer instance, but two different thread_ids never
see each other's messages.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]


def responder(state: ChatState) -> ChatState:
    last_message = state["messages"][-1].content
    return {"messages": [("ai", f"you said: {last_message}")]}


graph = StateGraph(ChatState)
graph.add_node("responder", responder)
graph.add_edge(START, "responder")
graph.add_edge("responder", END)
app = graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    alice_config = {"configurable": {"thread_id": "alice"}}
    bob_config = {"configurable": {"thread_id": "bob"}}

    app.invoke({"messages": [HumanMessage("my name is Alice")]}, config=alice_config)
    app.invoke({"messages": [HumanMessage("my name is Bob")]}, config=bob_config)

    alice_history = [(m.type, m.content) for m in app.get_state(alice_config).values["messages"]]
    bob_history = [(m.type, m.content) for m in app.get_state(bob_config).values["messages"]]

    print(f"alice's thread: {alice_history}")
    print(f"bob's thread:   {bob_history}")
    # neither thread's messages leak into the other, even though both used
    # the exact same compiled graph and checkpointer instance
