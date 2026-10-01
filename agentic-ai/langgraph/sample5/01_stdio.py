"""Sample 1 -- LangGraph agent using an MCP server over STDIO.

Flow:
  1. MultiServerMCPClient is told HOW to launch the server (command + args).
  2. get_tools() spawns it as a subprocess, does the MCP handshake
     (initialize -> tools/list) and wraps every MCP tool as a LangChain tool.
  3. Those tools go into the same ToolNode loop as sample3. The graph has no
     idea the tools are remote.

Besides tools, MCP servers can also offer resources and prompts; we list them
so students see all three primitives.

    uv run 01_stdio.py
"""

import asyncio
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

from common import ask, build_app

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

    app = build_app(tools)
    await ask(app, "What is (23 * 17) + 5? Use the tools.")


if __name__ == "__main__":
    asyncio.run(main())
