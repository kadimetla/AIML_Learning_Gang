"""add_messages -- the reducer behind MessagesState / chat-style graphs.

It's smarter than plain append: a returned message with a *new* id is
appended, but a returned message reusing an *existing* id replaces that
message in place. This is how a node can "edit" an earlier message (e.g.
after a tool retries) without duplicating it.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]


if __name__ == "__main__":
    existing = [
        HumanMessage(content="hi", id="1"),
        AIMessage(content="hello", id="2"),
    ]

    # new id -> appended
    appended = add_messages(existing, [HumanMessage(content="how are you?", id="3")])
    print("after appending a new message:")
    for m in appended:
        print(f"  id={m.id} content={m.content!r}")

    # reused id "2" -> replaces the earlier message instead of duplicating it
    edited = add_messages(existing, [AIMessage(content="hello! (corrected)", id="2")])
    print("\nafter 'editing' message id=2:")
    for m in edited:
        print(f"  id={m.id} content={m.content!r}")

    # MessagesState (used by examples/tool_node/, examples/tool_node_weather/)
    # is just: class MessagesState(TypedDict): messages: Annotated[list, add_messages]
