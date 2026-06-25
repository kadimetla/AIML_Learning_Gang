"""
LangGraph + Tool Calling Demo: Weather Agent (multi-backend edition)
=====================================================================
One agent graph, swappable LLM backend via the LLM_BACKEND env var:

  openai        -> OpenAI hosted models (gpt-4o, gpt-4o-mini)        [paid, very reliable tool calling]
  gemma_ollama  -> Google's Gemma 2, run locally via Ollama          [free, local]
  gemma_groq    -> Google's Gemma 2 9B, hosted fast via Groq         [free tier, hosted]
  ollama        -> Llama 3.1 via Ollama                              [free, local]
  groq          -> Llama 3.3 70B via Groq                            [free tier, hosted]

Install deps (only install what you need):
    pip install langgraph requests --break-system-packages
    pip install langchain-openai --break-system-packages   # for openai
    pip install langchain-ollama --break-system-packages   # for gemma_ollama / ollama
    pip install langchain-groq   --break-system-packages   # for gemma_groq / groq

Env setup per backend:
    openai:        export OPENAI_API_KEY=sk-...
    gemma_ollama:  ollama pull gemma2:9b      (gemma2:2b also works but weaker at tool args)
    gemma_groq:    export GROQ_API_KEY=gsk_...
    ollama:        ollama pull llama3.1
    groq:          export GROQ_API_KEY=gsk_...

Run:
    export LLM_BACKEND=openai
    python langgraph_weather_agent_multi.py
"""

import os
import requests
from typing import Annotated, TypedDict

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode


# ---------------------------------------------------------------------------
# 1. Tool — unchanged across all backends
# ---------------------------------------------------------------------------
@tool
def get_weather(city: str) -> str:
    """Get the current weather for a given city name.

    Args:
        city: The name of the city, e.g. "Atlanta" or "Tokyo".
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY")

    if not api_key:
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
# 2. Backend factory — this is the only part that changes per provider
# ---------------------------------------------------------------------------
def build_llm(backend: str):
    if backend == "openai":
        from langchain_openai import ChatOpenAI
        # gpt-4o-mini is cheap and has excellent tool-calling reliability
        return ChatOpenAI(model="gpt-4o-mini", temperature=0)

    elif backend == "gemma_ollama":
        from langchain_ollama import ChatOllama
        # Gemma 2 9B has reasonable tool calling; 27B is stronger if you have the VRAM
        return ChatOllama(model="gemma3:12b", temperature=0)


    elif backend == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model="llama3.1", temperature=0)

    elif backend == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model="openai/gpt-oss-120b", temperature=0)

    else:
        raise ValueError(
            f"Unknown LLM_BACKEND: {backend!r}. "
            "Use one of: openai, gemma_ollama, gemma_groq, ollama, groq"
        )


BACKEND = os.environ.get("LLM_BACKEND", "ollama").lower()
llm = build_llm(BACKEND)
llm_with_tools = llm.bind_tools(tools)


# ---------------------------------------------------------------------------
# 3. Graph — identical regardless of backend (this is the point: the agent
#    architecture is decoupled from the model provider)
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


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
# 4. Run it
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Running with backend: {BACKEND}\n")

    user_input = "What's the weather like in Atlanta right now? Should I bring an umbrella?"
    result = app.invoke({"messages": [HumanMessage(content=user_input)]})

    print("--- Full message trace ---")
    for m in result["messages"]:
        print(f"[{m.__class__.__name__}] {m.content}")

    print("\n--- Final answer ---")
    print(result["messages"][-1].content)