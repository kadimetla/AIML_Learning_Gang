# `ToolNode` + `tools_condition`

The standard "let the model call a tool" loop, built from two LangGraph
prebuilts: `ToolNode` (executes whichever tools an `AIMessage.tool_calls`
names) and `tools_condition` (routes to the tools node if there are pending
tool calls, otherwise to `END`).

```bash
uv run examples/tool_node/01_basic_tool_node.py
```

## `01_basic_tool_node.py`

Flow: `chatbot` node calls the model → model's reply has `tool_calls` →
`tools_condition` routes to `tools` (a `ToolNode`) → it executes the tool(s)
and appends `ToolMessage` results → back to `chatbot` → model gives a final
answer with no more tool calls → `tools_condition` routes to `END`.

Uses `GenericFakeChatModel` with a **scripted** `AIMessage` that already has
`tool_calls` set, so this needs no API key. `ToolNode` doesn't care how the
tool call got there — a real model bound with `.bind_tools([add])` produces
the exact same message shape, and the graph wouldn't change at all.

## Next step

See [`../tool_node_weather/`](../tool_node_weather/) for the same pattern
with a tool that hits a real external API instead of doing arithmetic.
