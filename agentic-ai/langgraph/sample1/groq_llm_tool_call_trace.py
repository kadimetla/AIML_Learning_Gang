"""
LangGraph + Tool Calling Demo: Weather Agent (VERBOSE / teaching edition)
==========================================================================
Same agent as before, but prints the full raw structure of every message
exchanged with the LLM — not just .content, but the tool_call objects,
ids, args, and finish reasons. This is meant to make the invisible parts
of the agent loop visible:

    1. HumanMessage        -> sent to LLM
    2. AIMessage            -> LLM's response. May have empty .content but
                               a populated .tool_calls list (the structured
                               "I want to call this function" request)
    3. ToolMessage          -> the tool's return value, tagged with
                               tool_call_id so the LLM knows which call
                               this result answers
    4. AIMessage (final)   -> LLM synthesizes ToolMessage + original
                               question into a real answer

Set USE_REAL_API=1 and OPENWEATHER_API_KEY=... to hit the live weather API
instead of the mock.
"""

import os
import json
import requests
from typing import Annotated, TypedDict

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode


# ---------------------------------------------------------------------------
# 1. Tool
# ---------------------------------------------------------------------------
@tool
def get_weather(city: str) -> str:
    """Get the current weather for a given city name.

    Args:
        city: The name of the city, e.g. "Atlanta" or "Tokyo".
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY")

    if not api_key:
        # MOCK: no API key set, so we fabricate a plausible-looking response
        # instead of calling the real OpenWeatherMap endpoint. The LLM has
        # no way to tell this apart from real data -- it just trusts the
        # ToolMessage content. That's worth sitting with: agent reliability
        # is capped by tool reliability.
        return f"[MOCK] Weather in {city}: 24°C, partly cloudy, light breeze."

    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": api_key, "units": "metric"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        return f"Weather in {city}: {temp}°C (feels like {feels_like}°C), {desc}."
    except Exception as e:
        return f"Error fetching weather for {city}: {e}"


tools = [get_weather]
tool_node = ToolNode(tools)


# ---------------------------------------------------------------------------
# 2. State + LLM node
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0)
llm_with_tools = llm.bind_tools(tools)


def call_model(state: AgentState):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END


graph = StateGraph(AgentState)
graph.add_node("agent", call_model)
graph.add_node("tools", tool_node)
graph.set_entry_point("agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")

app = graph.compile()


# ---------------------------------------------------------------------------
# 3. Verbose trace printer — this is the teaching part
# ---------------------------------------------------------------------------
def print_message_detail(msg, step_num):
    print(f"\n{'─' * 70}")
    print(f"STEP {step_num}: {msg.__class__.__name__}")
    print(f"{'─' * 70}")

    if isinstance(msg, HumanMessage):
        print(f"  role:    user")
        print(f"  content: {msg.content!r}")

    elif isinstance(msg, AIMessage):
        print(f"  role:    assistant")
        print(f"  content: {msg.content!r}  {'<- EMPTY: model chose to call a tool instead of answering' if not msg.content else ''}")
        if msg.tool_calls:
            print(f"  tool_calls ({len(msg.tool_calls)}):")
            for tc in msg.tool_calls:
                print(f"    - id:   {tc['id']}")
                print(f"      name: {tc['name']}")
                print(f"      args: {json.dumps(tc['args'])}")
        # token usage if the provider returns it
        if msg.response_metadata.get("usage") or msg.response_metadata.get("token_usage"):
            usage = msg.response_metadata.get("usage") or msg.response_metadata.get("token_usage")
            print(f"  usage:   {usage}")
        # Anthropic uses 'stop_reason'; OpenAI-style (Groq) uses 'finish_reason'
        stop = msg.response_metadata.get("stop_reason") or msg.response_metadata.get("finish_reason")
        if stop:
            print(f"  stop_reason: {stop}")

    elif isinstance(msg, ToolMessage):
        print(f"  role:          tool")
        print(f"  tool_call_id:  {msg.tool_call_id}  <- links this result back to the AIMessage's request")
        print(f"  content:       {msg.content!r}")


def run_with_trace(user_input: str):
    print(f"\n{'=' * 70}")
    print(f"USER ASKS: {user_input}")
    print(f"{'=' * 70}")

    state = {"messages": [HumanMessage(content=user_input)]}
    step = 0
    print_message_detail(state["messages"][0], step)

    # Manually step through the graph so we can print after each node runs
    for output in app.stream(state, stream_mode="values"):
        new_messages = output["messages"]
        # Only print messages we haven't printed yet
        if len(new_messages) > step + 1:
            for m in new_messages[step + 1:]:
                step += 1
                print_message_detail(m, step)
        state = output

    print(f"\n{'=' * 70}")
    print("FINAL ANSWER")
    print(f"{'=' * 70}")
    print(state["messages"][-1].content)
    return state


# ---------------------------------------------------------------------------
# 4. Run it
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_with_trace("What's the weather like in Atlanta right now? Should I bring an umbrella?")