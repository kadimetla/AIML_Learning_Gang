"""create_agent -- the prebuilt high-level constructor for the exact
ReAct-style loop we built by hand in examples/tool_node/01_basic_tool_node.py
(chatbot -> tools -> chatbot -> ... -> END).

Trade-off: create_agent needs zero graph-wiring code, but you don't see or
control the individual nodes/edges -- examples/tool_node/ is the same loop
with every piece visible and swappable.

Note: langgraph.prebuilt.create_react_agent is deprecated as of LangGraph
1.0 in favor of langchain.agents.create_agent (this file uses the new one).

GenericFakeChatModel doesn't implement .bind_tools() (used internally to
tell the model which tools exist), so this file adds a two-line subclass
that just returns itself -- fine here since we're scripting the model's
replies anyway, not relying on it to actually pick tools.
"""

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool


class ScriptedToolCallingModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@tool
def add(a: int, b: int) -> int:
    """Add two integers together."""
    return a + b


scripted_replies = iter(
    [
        AIMessage(
            content="",
            tool_calls=[{"name": "add", "args": {"a": 2, "b": 3}, "id": "call_1"}],
        ),
        AIMessage(content="2 + 3 is 5."),
    ]
)
model = ScriptedToolCallingModel(messages=scripted_replies)

# this one call replaces the entire StateGraph + ToolNode + tools_condition
# wiring from examples/tool_node/01_basic_tool_node.py
agent = create_agent(model, tools=[add])


if __name__ == "__main__":
    result = agent.invoke({"messages": [HumanMessage("what is 2+3?")]})
    for message in result["messages"]:
        label = type(message).__name__
        calls = getattr(message, "tool_calls", None)
        print(f"{label:12s} tool_calls={calls} content={message.content!r}")
