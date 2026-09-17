"""Minimal tool-calling ReAct loop: an `agent` node (an LLM bound to tools)
and a `tools` node (langgraph.prebuilt.ToolNode) wired together with
`tools_condition`, the prebuilt conditional edge that checks whether the
last AIMessage requested any tool calls.

Two tools are provided so a single prompt can trigger parallel tool calls
(get_weather + calculator in the same turn), which is where ToolNode earns
its keep -- it dispatches both by name and runs them concurrently instead
of you writing that loop by hand.

The model is constructed via `init_chat_model("litellm:gpt-4o-mini", ...)`,
routing the call through `langchain_litellm.ChatLiteLLM`. Here it lands on
OpenAI using the existing OPENAI_API_KEY (same as sample2's
03_litellm_and_bedrock.py) -- swapping the provider string is what would
route this same graph to Bedrock/Anthropic/etc. without touching the
agent/tools wiring below.
"""

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition


@tool
def get_weather(city: str) -> str:
    """Look up the current weather for a city."""
    fake_weather = {
        "boston": "58F and cloudy",
        "san francisco": "62F and foggy",
        "austin": "89F and sunny",
    }
    return fake_weather.get(city.lower(), f"No weather data for {city!r}")


@tool
def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression, e.g. '12 * 7'."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return f"Rejected unsafe expression: {expression!r}"
    return str(eval(expression))


tools = [get_weather, calculator]
llm = init_chat_model("litellm:gpt-4o-mini", temperature=0).bind_tools(tools)


def agent_node(state: MessagesState) -> dict:
    return {"messages": [llm.invoke(state["messages"])]}


graph = StateGraph(MessagesState)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(tools))

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", tools_condition)
graph.add_edge("tools", "agent")

app = graph.compile()


def main():
    result = app.invoke(
        {
            "messages": [
                (
                    "user",
                    "What's the weather in Austin, and what's 23 * 17?",
                )
            ]
        }
    )
    for message in result["messages"]:
        message.pretty_print()


if __name__ == "__main__":
    main()
