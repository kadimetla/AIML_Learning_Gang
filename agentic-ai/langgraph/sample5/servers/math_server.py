"""MCP server #1 -- runs over STDIO.

The client (01_stdio.py) launches this file as a child process and talks to it
over its stdin/stdout using JSON-RPC. Nothing listens on a port; the server
lives and dies with the client. NEVER print() to stdout in a stdio server --
stdout *is* the protocol channel, so stray prints corrupt it (use stderr).

It exposes all three MCP server primitives so students can see them side by side:
  * tool     -- model-controlled actions        (add, multiply)
  * resource -- application-controlled data     (math://constants)
  * prompt   -- user-controlled templates       (explain_step_by_step)
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("math")


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


@mcp.resource("math://constants")
def constants() -> str:
    """Handy mathematical constants."""
    return "pi = 3.14159265\ne = 2.71828183\nphi = 1.61803399"


@mcp.prompt()
def explain_step_by_step(expression: str) -> str:
    """Prompt template: ask the model to explain a calculation."""
    return f"Explain, step by step, how to compute: {expression}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
