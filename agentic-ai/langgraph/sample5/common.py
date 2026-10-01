"""Tiny helper shared by the sample5 scripts: run one question and print the trace.

The LangGraph wiring (agent node, ToolNode, edges) is deliberately NOT here --
it is written out in each script so students can see it next to the MCP code.
"""


import sys

from llm_trace import LLMTrace

SHOW_LLM = "--show-llm" in sys.argv


async def ask(app, question: str) -> None:
    print(f"\n>>> {question}\n")
    config = {"recursion_limit": 12}
    if SHOW_LLM:  # print every request/response exchanged with the LLM
        config["callbacks"] = [LLMTrace()]
    # MCP tools are async-only, so use ainvoke (not invoke).
    result = await app.ainvoke({"messages": [("user", question)]}, config)
    for message in result["messages"]:
        message.pretty_print()
