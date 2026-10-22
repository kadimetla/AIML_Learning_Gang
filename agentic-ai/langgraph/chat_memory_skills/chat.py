"""chat_memory_skills -- end-to-end chat: short-term memory + long-term memory + tools + skills.

    START -> recall -> agent <-> tools -> END

  recall   Store.search(("memories", user_id), query=last message)  -> state["recalled"]
  agent    system prompt = rules + skill catalog + recalled memories; LLM answers or calls tools
  tools    lookup_order, calculator | load_skill, read_skill_file | save_memory, forget_memory

Two memory layers, two persistence objects (both SQLite files next to this script):
  checkpoints.db  checkpointer, keyed by thread_id -> this conversation's messages
  memories.db     store, namespace ("memories", user_id) -> facts across ALL threads

    uv run chat.py                 # user "adi", new thread
    uv run chat.py --user sam      # another user = separate long-term memory
    REPL commands: /new  /thread <id>  /memories  /quit
"""

import argparse
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.store.sqlite import SqliteStore

from memory import MEMORY_TOOLS, State, recall
from skills import SKILL_TOOLS, catalog_text
from tools import BASIC_TOOLS

HERE = Path(__file__).parent
TOOLS = [*BASIC_TOOLS, *SKILL_TOOLS, *MEMORY_TOOLS]

SYSTEM = """You are a helpful assistant with memory, tools and skills.

Skills (call load_skill BEFORE acting on a matching request; never guess the procedure):
{skills}

Memory: when the user tells you a durable fact about themselves, call save_memory.
If they correct a fact, forget_memory the old one and save the new one.

Known about this user (from earlier conversations):
{memories}"""


def build_graph():
    llm = init_chat_model("litellm:gpt-4o-mini", temperature=0).bind_tools(TOOLS)

    def agent_node(state: State) -> dict:
        system = SYSTEM.format(
            skills=catalog_text(),
            memories="\n".join(state.get("recalled") or []) or "(nothing yet)",
        )
        return {"messages": [llm.invoke([("system", system), *state["messages"]])]}

    graph = StateGraph(State)
    graph.add_node("recall", recall)           # long-term memory READ
    graph.add_node("agent", agent_node)        # LLM decides: answer or call a tool
    graph.add_node("tools", ToolNode(TOOLS))   # runs tools / skills / memory WRITES
    graph.add_edge(START, "recall")
    graph.add_edge("recall", "agent")
    graph.add_conditional_edges("agent", tools_condition)  # tool calls? -> "tools", else END
    graph.add_edge("tools", "agent")           # feed tool results back to the LLM
    return graph


def open_stores():
    """Context managers for the checkpointer (short-term) and store (long-term)."""
    saver = SqliteSaver.from_conn_string(str(HERE / "checkpoints.db"))
    store = SqliteStore.from_conn_string(
        str(HERE / "memories.db"),
        # embed the "fact" field so recall() can do semantic search
        index={"dims": 1536, "embed": "openai:text-embedding-3-small", "fields": ["fact"]},
    )
    return saver, store


def chat_turn(app, text: str, config: dict) -> str:
    """Run one user turn, printing what each node did, and return the reply."""
    reply = ""
    for update in app.stream({"messages": [("user", text)]}, config, stream_mode="updates"):
        for node, delta in update.items():
            if node == "recall":
                for fact in delta["recalled"]:
                    print(f"  [recall] {fact}")
            for msg in (delta or {}).get("messages", []):
                if node == "agent" and msg.tool_calls:
                    for call in msg.tool_calls:
                        print(f"  [tool call] {call['name']}({call['args']})")
                elif node == "tools":
                    print(f"  [tool result] {msg.name}: {str(msg.content)[:100]!r}")
                else:
                    reply = msg.content
    return reply


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="adi")
    parser.add_argument("--thread", default=None, help="resume a thread id")
    args = parser.parse_args()

    saver_cm, store_cm = open_stores()
    with saver_cm as saver, store_cm as store:
        store.setup()
        app = build_graph().compile(checkpointer=saver, store=store)

        thread = args.thread or uuid.uuid4().hex[:8]
        print(f"user={args.user} thread={thread}   (/new /thread <id> /memories /quit)")
        while True:
            try:
                text = input(f"\n{args.user}> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text in ("/quit", "/exit"):
                break
            if text == "/new":  # new thread: history gone, long-term memory stays
                thread = uuid.uuid4().hex[:8]
                print(f"new thread={thread}")
                continue
            if text.startswith("/thread "):
                thread = text.split(maxsplit=1)[1]
                print(f"switched to thread={thread}")
                continue
            if text == "/memories":
                for item in store.search(("memories", args.user), limit=100):
                    print(f"  [{item.key[:8]}] {item.value['fact']}")
                continue

            config = {"configurable": {"thread_id": thread, "user_id": args.user}}
            print(f"\nbot> {chat_turn(app, text, config)}")


if __name__ == "__main__":
    main()
