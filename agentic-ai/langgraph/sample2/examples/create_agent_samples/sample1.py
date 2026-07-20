from typing import Annotated, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AnyMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


def get_weather(city: str) -> str:
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

result = workflow.invoke({
    "messages": [
        {"role": "user", "content": "What is the weather in SF?"}
    ]
})
