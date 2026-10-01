"""Sample 2 -- the same idea over STREAMABLE HTTP, mixed with a stdio server.

Differences from sample 1 (everything else is identical):
  * server config is {"transport": "streamable_http", "url": ...} -- no command,
    because *you* run the server, the client only connects.
  * the server is a long-lived process that could be remote and shared.
  * one MultiServerMCPClient can mix transports: here `math` is stdio and
    `weather` is HTTP, and the agent just sees one flat tool list.

For the demo this script starts the HTTP server for you. To see it as a real
separate service, run it yourself in another terminal first
(`uv run servers/weather_http_server.py`) and the script will reuse it.

    uv run 02_http.py
"""

import asyncio
import socket
import subprocess
import sys
import time
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from common import ask

SERVERS = Path(__file__).parent / "servers"
HOST, PORT = "127.0.0.1", 8765


def port_open() -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex((HOST, PORT)) == 0


async def main():
    proc = None
    if not port_open():
        proc = subprocess.Popen([sys.executable, str(SERVERS / "weather_http_server.py")])
        for _ in range(50):
            if port_open():
                break
            time.sleep(0.1)
        print(f"started weather server (pid {proc.pid}) on :{PORT}")
    else:
        print(f"reusing weather server already listening on :{PORT}")

    try:
        client = MultiServerMCPClient(
            {
                "math": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [str(SERVERS / "math_server.py")],
                },
                "weather": {
                    "transport": "streamable_http",
                    "url": f"http://{HOST}:{PORT}/mcp",
                },
            }
        )
        tools = await client.get_tools()
        print("tools from both servers:", [t.name for t in tools])

        # ---- LangGraph: identical to sample3; only `tools` came from MCP ----
        llm = init_chat_model("litellm:gpt-4o-mini", temperature=0).bind_tools(tools)

        def agent_node(state: MessagesState) -> dict:
            return {"messages": [llm.invoke(state["messages"])]}

        graph = StateGraph(MessagesState)
        graph.add_node("agent", agent_node)        # LLM decides: answer or call a tool
        graph.add_node("tools", ToolNode(tools))   # runs the MCP tool(s) the LLM asked for
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", tools_condition)  # tool calls? -> "tools", else END
        graph.add_edge("tools", "agent")           # feed tool results back to the LLM
        app = graph.compile()
        # ---------------------------------------------------------------------

        await ask(app, "What's the weather in Austin, and what's 23 * 17?")
    finally:
        if proc:
            proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
