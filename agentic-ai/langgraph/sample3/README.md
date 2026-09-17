# sample3 — tool calling with `ToolNode`

A minimal ReAct-style loop: an `agent` node (an LLM bound to tools) and a
`tools` node (`langgraph.prebuilt.ToolNode`), wired together with
`tools_condition` (also prebuilt) as the conditional edge.

Two tools (`get_weather`, `calculator`) let one prompt trigger parallel tool
calls in a single turn -- `ToolNode` dispatches each by name, runs them
concurrently, and wraps each result into a `ToolMessage` keyed by
`tool_call_id` so the model can match results back to its calls.

The model is built with `init_chat_model("litellm:gpt-4o-mini", ...)`,
routing through `langchain_litellm.ChatLiteLLM` (same mechanism as
`sample2/examples/model_init/03_litellm_and_bedrock.py`). It lands on
OpenAI here using `OPENAI_API_KEY`, but the agent/tools graph itself
doesn't change if the provider string is swapped for Bedrock or another
litellm-supported provider.

Needs `OPENAI_API_KEY` in `.env` (copy `.env.example`).

```bash
uv run main.py
```
