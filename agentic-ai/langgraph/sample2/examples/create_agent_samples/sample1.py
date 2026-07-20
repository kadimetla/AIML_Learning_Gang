from dotenv import load_dotenv

load_dotenv()

from typing import Annotated, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AnyMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


def get_weather(city: str) -> str:
    """Get the current weather for a city name."""
    return f"The weather in {city} is sunny."


agent = create_agent(
    model="openai:gpt-5.5",
    tools=[get_weather],
    system_prompt="You are a helpful weather assistant.",
    name="weather_agent",
)


class WorkflowState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


builder = StateGraph(WorkflowState)

builder.add_node("agent", agent)
builder.add_edge(START, "agent")
builder.add_edge("agent", END)

workflow = builder.compile()


if __name__ == "__main__":
    result = workflow.invoke({
        "messages": [
            {"role": "user", "content": "What is the weather in SF?"}
        ]
    })
    for message in result["messages"]:
        label = type(message).__name__
        calls = getattr(message, "tool_calls", None)
        print(f"{label:12s} tool_calls={calls} content={message.content!r}")
