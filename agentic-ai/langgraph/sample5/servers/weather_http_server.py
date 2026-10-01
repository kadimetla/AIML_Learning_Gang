"""MCP server #2 -- runs over STREAMABLE HTTP.

Same FastMCP API as the stdio server; only the transport changes. This one is
a normal long-lived web service: many clients can connect, it can sit on
another machine, and it can be put behind auth / a load balancer. The MCP
endpoint is http://127.0.0.1:8765/mcp .

Run it on its own:   uv run servers/weather_http_server.py
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather", host="127.0.0.1", port=8765)

FAKE_WEATHER = {
    "boston": "58F and cloudy",
    "san francisco": "62F and foggy",
    "austin": "89F and sunny",
}


@mcp.tool()
def get_weather(city: str) -> str:
    """Look up the current weather for a city."""
    return FAKE_WEATHER.get(city.lower(), f"No weather data for {city!r}")


@mcp.tool()
def list_cities() -> list[str]:
    """List the cities this server has weather data for."""
    return sorted(FAKE_WEATHER)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
