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

from common import ask, build_app

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

        app = build_app(tools)
        await ask(app, "What's the weather in Austin, and what's 23 * 17?")
    finally:
        if proc:
            proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
