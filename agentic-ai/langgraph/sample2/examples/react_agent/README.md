# `create_agent` — the prebuilt ReAct loop

Everything [`../tool_node/01_basic_tool_node.py`](../tool_node/01_basic_tool_node.py)
wires up by hand (chatbot node → `ToolNode` → `tools_condition` → loop back
→ `END`), collapsed into one function call.

```bash
uv run examples/react_agent/01_create_agent.py
uv run examples/react_agent/02_create_agent_with_graph_features.py
```

## `01_create_agent.py`

```python
agent = create_agent(model, tools=[add])
```

That single line replaces the entire `StateGraph`/`ToolNode`/
`tools_condition` wiring. Same scripted-fake-model trick as the rest of
`examples/` (no API key needed) — except `GenericFakeChatModel` doesn't
implement `.bind_tools()` (which `create_agent` calls internally to attach
tool schemas to the model), so this file adds a two-line subclass that just
returns itself. Fine here since the model's replies are scripted anyway, not
actually chosen based on the tool schemas.

**Note**: `langgraph.prebuilt.create_react_agent` is deprecated as of
LangGraph 1.0 — this uses its replacement, `langchain.agents.create_agent`
(added as a project dependency for this example).

## Trade-off vs. `../tool_node/`

| | `create_agent` | manual `ToolNode` wiring |
|---|---|---|
| code | one function call | full graph definition |
| control | fixed loop shape | every node/edge visible and swappable |
| good for | standard "model + tools" agents | custom routing, extra nodes, non-standard loops |

Start with `create_agent`; drop down to manual wiring the moment you need
something the prebuilt doesn't support (e.g. the `Command`/`interrupt()`
patterns in [`../command/`](../command/) and [`../hitl/`](../hitl/)).

## `02_create_agent_with_graph_features.py`

`create_agent` returns an ordinary `CompiledStateGraph` -- every LangGraph
feature this repo teaches elsewhere still applies to it. This example passes
`checkpointer=InMemorySaver()` and `interrupt_before=["tools"]`, the same
pause-before-a-node mechanism as [`../07_interrupt_before.py`](../07_interrupt_before.py),
aimed at `create_agent`'s built-in `"tools"` node (confirmed via
`agent.get_graph().nodes` -- it's always named `"model"`/`"tools"`) instead
of a hand-written one. Also uses `system_prompt=` instead of a manual
`SystemMessage` check. Real `OPENAI_API_KEY` call -- the model actually
decides to call `send_email`, which then pauses for approval before it
"sends" anything.
