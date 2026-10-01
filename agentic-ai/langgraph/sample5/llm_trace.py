"""Print exactly what LangGraph sends to the LLM and what comes back.

Turn it on with the --show-llm flag, e.g.   uv run 01_stdio.py --show-llm

It is a LangChain callback handler, so it sees every chat-model call the graph
makes: once per trip through the `agent` node. Watch the message list grow:
user question -> AI tool_calls -> tool results -> final answer.
"""

import json

from langchain_core.callbacks import BaseCallbackHandler

WIDTH = 100


def _clip(text, n=400):
    text = str(text)
    return text if len(text) <= n else text[:n] + f"... [+{len(text) - n} chars]"


class LLMTrace(BaseCallbackHandler):
    def __init__(self):
        self.calls = 0

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.calls += 1
        print(f"\n{'=' * WIDTH}\nLLM REQUEST #{self.calls}\n{'=' * WIDTH}")
        params = kwargs.get("invocation_params", {})
        print(f"model: {params.get('model') or params.get('model_name')}   "
              f"temperature: {params.get('temperature')}")

        tools = params.get("tools") or []
        if tools:
            print(f"\ntools sent ({len(tools)}) -- name: description")
            for t in tools:
                fn = t.get("function", t)
                print(f"  - {fn['name']}: {_clip(fn.get('description', ''), 90)}")
            if self.calls == 1:  # same schemas ride along on every request; show once
                print("  first tool's full JSON schema (re-sent on every request):")
                print("  " + json.dumps(tools[0], indent=2).replace("\n", "\n  "))

        print(f"\nmessages sent ({len(messages[0])}):")
        for m in messages[0]:
            print(f"  [{m.type}] {_clip(m.content)}")
            for tc in getattr(m, "tool_calls", None) or []:
                print(f"      tool_call: {tc['name']}({tc['args']})  id={tc['id'][-6:]}")
            if m.type == "tool":
                print(f"      (answers tool_call id={m.tool_call_id[-6:]})")

    def on_llm_end(self, response, **kwargs):
        msg = response.generations[0][0].message
        print(f"\n{'-' * WIDTH}\nLLM RESPONSE #{self.calls}\n{'-' * WIDTH}")
        if msg.tool_calls:
            print("model wants tools (graph will route to the `tools` node):")
            for tc in msg.tool_calls:
                print(f"  tool_call: {tc['name']}({tc['args']})  id={tc['id'][-6:]}")
        if msg.content:
            print(f"content: {_clip(msg.content)}")
        if not msg.tool_calls:
            print("(no tool calls -> graph goes to END)")
        usage = getattr(msg, "usage_metadata", None)
        if usage:
            print(f"tokens: in={usage['input_tokens']} out={usage['output_tokens']}")
