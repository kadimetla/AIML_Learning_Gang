"""Long-term memory: facts about the USER that survive across threads.

Short-term memory (this conversation's messages) is the checkpointer's job and
needs no code here -- see chat.py. This file is the other layer:

  READ   recall node, runs before every agent call: semantic search of the
         Store for memories related to the latest user message.
  WRITE  save_memory / forget_memory tools: the MODEL decides what is worth
         remembering ("hot path" memory).

Memories live in the Store under namespace ("memories", user_id), so two users
never see each other's facts, and every thread of one user shares them.
"""

import uuid

from langchain_core.tools import tool
from langgraph.config import get_config, get_store
from langgraph.graph import MessagesState


class State(MessagesState):
    recalled: list[str]  # filled by recall, read by the agent node


def namespace() -> tuple[str, str]:
    return ("memories", get_config()["configurable"]["user_id"])


def recall(state: State) -> dict:
    query = state["messages"][-1].content
    hits = get_store().search(namespace(), query=query, limit=5)
    return {"recalled": [f"[{h.key[:8]}] {h.value['fact']}" for h in hits]}


@tool
def save_memory(fact: str) -> str:
    """Save one durable fact about the user (diet, preferences, name, location...).
    Use for things that will matter in FUTURE conversations, not chit-chat."""
    key = str(uuid.uuid4())
    get_store().put(namespace(), key, {"fact": fact})
    return f"saved [{key[:8]}] {fact}"


@tool
def forget_memory(memory_id: str) -> str:
    """Delete a saved memory by the 8-char id shown in 'Known about this user',
    e.g. when the user says a fact is wrong or no longer true."""
    store = get_store()
    for item in store.search(namespace(), limit=100):
        if item.key.startswith(memory_id):
            store.delete(namespace(), item.key)
            return f"forgot [{memory_id}] {item.value['fact']}"
    return f"No memory with id {memory_id!r}."


MEMORY_TOOLS = [save_memory, forget_memory]
