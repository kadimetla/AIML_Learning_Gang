# `ToolNode` calling a real API

Same `ToolNode` + `tools_condition` loop as [`../tool_node/`](../tool_node/),
except the tool itself makes a real HTTP call instead of pure arithmetic.

```bash
uv run examples/tool_node_weather/01_weather_tool_agent.py
```

Requires internet access (calls `open-meteo.com`, a free weather API that
needs no key or signup).

## `01_weather_tool_agent.py`

`get_weather(city)` first geocodes the city name, then fetches current
temperature for those coordinates, and returns a plain-language string —
that's what becomes the `ToolMessage` content the model sees on its next
turn.

The "LLM" is still `GenericFakeChatModel` with a scripted tool call
(`get_weather(city="London")`), since this project has no LLM API key
configured. The file's docstring shows the one-line swap to use a real
model instead:

```python
from langchain_anthropic import ChatAnthropic
model = ChatAnthropic(model="claude-sonnet-5").bind_tools([get_weather])
```

With a real model, *it* decides which city to call `get_weather` with, based
on the user's actual question — nothing else about the graph changes.
