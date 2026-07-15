"""The most basic thing a checkpointer buys you: memory across separate
invoke() calls, without you manually resending the whole conversation
history each time.

Every super-step gets written to the checkpointer, keyed by thread_id. The
next invoke() with the same thread_id starts from wherever that thread's
state left off, instead of from scratch. This is the foundation
examples/hitl/, examples/time_travel/, and examples/store/ all build on.
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
    config = {"configurable": {"thread_id": "conversation-1"}}

    # first turn: only send the first message
    result = app.invoke({"messages": [HumanMessage("hi")]}, config=config)
    print("after turn 1:", [(m.type, m.content) for m in result["messages"]])

    # second turn: only send the *new* message -- the checkpointer already
    # has "hi" / "you said: hi" from turn 1, add_messages appends to it
    result = app.invoke({"messages": [HumanMessage("how are you?")]}, config=config)
    print("after turn 2:", [(m.type, m.content) for m in result["messages"]])

    # get_state() reads the accumulated conversation without invoking anything
    state = app.get_state(config)
    print("get_state():", [(m.type, m.content) for m in state.values["messages"]])
