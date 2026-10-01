"""Shared LangGraph wiring for the sample5 scripts.

This is exactly sample3's ReAct loop (agent node + ToolNode + tools_condition).
The ONLY thing MCP changes is where `tools` comes from: instead of @tool
functions defined in this file, they are discovered from an MCP server.
"""

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition


def build_app(tools, system_prompt: str | None = None):
    llm = init_chat_model("litellm:gpt-4o-mini", temperature=0).bind_tools(tools)

    def agent_node(state: MessagesState) -> dict:
        messages = state["messages"]
        if system_prompt:
            messages = [("system", system_prompt), *messages]
        return {"messages": [llm.invoke(messages)]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile()


async def ask(app, question: str) -> None:
    print(f"\n>>> {question}\n")
    # MCP tools are async-only, so use ainvoke (not invoke).
    result = await app.ainvoke(
        {"messages": [("user", question)]}, {"recursion_limit": 12}
    )
    for message in result["messages"]:
        message.pretty_print()
