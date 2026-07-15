"""Same ToolNode + tools_condition loop as examples/tool_node/, but the tool
makes a real network call to a free, no-API-key weather service
(open-meteo.com) instead of doing pure arithmetic.

The "LLM" is still GenericFakeChatModel with a scripted tool call, since this
project has no LLM API key configured -- but nothing else about the pattern
changes. To use a real model instead, replace `model` with e.g.:

    from langchain_anthropic import ChatAnthropic
    model = ChatAnthropic(model="claude-sonnet-5").bind_tools([get_weather])

and the model would decide *which* city to call get_weather with, instead of
that being scripted here.
"""

import requests
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city name."""
    geo = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1},
        timeout=10,
    ).json()
    if not geo.get("results"):
        return f"Could not find a location named {city!r}."
    location = geo["results"][0]

    weather = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": "temperature_2m",
        },
        timeout=10,
    ).json()
    temp_c = weather["current"]["temperature_2m"]
    return f"It is currently {temp_c}°C in {location['name']}, {location.get('country', '')}."


# scripted: the model "decides" to call get_weather(city="London"), then
# answers using whatever the tool actually returned
scripted_replies = iter(
    [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_weather", "args": {"city": "London"}, "id": "call_1"}],
        ),
        AIMessage(content="Here's the current weather you asked about."),
    ]
)
model = GenericFakeChatModel(messages=scripted_replies)


def chatbot(state: MessagesState) -> dict:
    return {"messages": [model.invoke(state["messages"])]}


graph = StateGraph(MessagesState)
graph.add_node("chatbot", chatbot)
graph.add_node("tools", ToolNode([get_weather]))
graph.add_edge(START, "chatbot")
graph.add_conditional_edges("chatbot", tools_condition)
graph.add_edge("tools", "chatbot")
app = graph.compile()


if __name__ == "__main__":
    result = app.invoke({"messages": [HumanMessage("what's the weather in London?")]})
    for message in result["messages"]:
        label = type(message).__name__
        calls = getattr(message, "tool_calls", None)
        print(f"{label:12s} tool_calls={calls} content={message.content!r}")
