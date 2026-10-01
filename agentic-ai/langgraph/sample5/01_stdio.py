"""Sample 1 -- LangGraph agent using an MCP server over STDIO.

Flow:
  1. MultiServerMCPClient is told HOW to launch the server (command + args).
  2. get_tools() spawns it as a subprocess, does the MCP handshake
     (initialize -> tools/list) and wraps every MCP tool as a LangChain tool.
  3. Those tools go into the same agent -> ToolNode loop as sample3 (written out
     below in main()). The graph has no idea the tools are remote.

Besides tools, MCP servers can also offer resources and prompts; we list them
so students see all three primitives.

    uv run 01_stdio.py
"""

import asyncio
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from common import ask

SERVER = Path(__file__).parent / "servers" / "math_server.py"


async def main():
    client = MultiServerMCPClient(
        {
            "math": {
                "transport": "stdio",
                "command": sys.executable,  # same interpreter as this venv
                "args": [str(SERVER)],
            }
        }
    )

    tools = await client.get_tools()
    print("MCP tools:", [t.name for t in tools])

    # A session is one live connection (= one server subprocess for stdio).
    async with client.session("math") as session:
        resources = await session.list_resources()
        prompts = await session.list_prompts()
        print("MCP resources:", [str(r.uri) for r in resources.resources])
        print("MCP prompts:  ", [p.name for p in prompts.prompts])
        const = await session.read_resource("math://constants")
        print("math://constants ->", const.contents[0].text.replace("\n", "; "))

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

    await ask(app, "What is (23 * 17) + 5? Use the tools.")


if __name__ == "__main__":
    asyncio.run(main())
