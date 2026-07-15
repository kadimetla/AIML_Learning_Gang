"""ToolNode + tools_condition -- the standard "LLM decides to call a tool" loop.

Flow: chatbot node calls the model -> if the reply has tool_calls,
tools_condition routes to the "tools" node (a ToolNode) which executes them
and appends ToolMessage results -> back to chatbot -> model gives a final
answer -> tools_condition routes to END.

Uses GenericFakeChatModel with a *preset* tool call, so this runs with no API
key. ToolNode doesn't care how the AIMessage.tool_calls got there -- a real
chat model bound with .bind_tools([add]) would produce the same shape.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition


@tool
def add(a: int, b: int) -> int:
    """Add two integers together."""
    return a + b


# scripted responses: first the model "decides" to call `add`, then it
# answers using the tool's result
scripted_replies = iter(
    [
        AIMessage(
            content="",
            tool_calls=[{"name": "add", "args": {"a": 2, "b": 3}, "id": "call_1"}],
        ),
        AIMessage(content="2 + 3 is 5."),
    ]
)
model = GenericFakeChatModel(messages=scripted_replies)


def chatbot(state: MessagesState) -> dict:
    return {"messages": [model.invoke(state["messages"])]}


graph = StateGraph(MessagesState)
graph.add_node("chatbot", chatbot)
graph.add_node("tools", ToolNode([add]))
graph.add_edge(START, "chatbot")
graph.add_conditional_edges("chatbot", tools_condition)  # -> "tools" or END
graph.add_edge("tools", "chatbot")
app = graph.compile()


if __name__ == "__main__":
    result = app.invoke({"messages": [HumanMessage("what is 2+3?")]})
    for message in result["messages"]:
        label = type(message).__name__
        calls = getattr(message, "tool_calls", None)
        print(f"{label:12s} tool_calls={calls} content={message.content!r}")
