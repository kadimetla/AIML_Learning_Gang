"""Pattern 1: retrieval as a tool (ReAct-style) -- same agent/tools/
tools_condition loop as sample3's tool-calling example, just with a
`retrieve` tool backed by the FAISS index instead of get_weather/calculator.

The model itself decides whether the question needs a lookup at all. Ask it
something answerable purely from general knowledge and it may skip the tool
entirely; ask it something about this repo and it calls `retrieve` first.

Run: uv run query_flows/01_retrieval_as_tool.py
"""

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from store import format_docs, load_faiss_retriever

retriever = load_faiss_retriever(k=4)


@tool
def retrieve(query: str) -> str:
    """Search this workspace's README/wiki docs for content relevant to query."""
    docs = retriever.invoke(query)
    return format_docs(docs) if docs else "No matching documents found."


tools = [retrieve]
llm = init_chat_model("litellm:gpt-4o-mini", temperature=0).bind_tools(tools)


def agent_node(state: MessagesState) -> dict:
    return {"messages": [llm.invoke(state["messages"])]}


graph = StateGraph(MessagesState)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(tools))

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", tools_condition)
graph.add_edge("tools", "agent")

app = graph.compile()


def main():
    for question in [
        "According to this repo, how does init_chat_model let you swap LLM providers at runtime?",
        "What's 2 + 2?",
    ]:
        print(f"\n=== {question} ===")
        result = app.invoke({"messages": [("user", question)]})
        for message in result["messages"]:
            message.pretty_print()


if __name__ == "__main__":
    main()
