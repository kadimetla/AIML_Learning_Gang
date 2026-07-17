"""Procedural memory -- *how to act*: behavioral rules the agent follows,
not facts it knows (03_semantic_memory.py) or events it remembers
(02_episodic_memory.py). Stored the same way as semantic memory -- a Store,
keyed by namespace/key -- but holding an instruction the node applies to
*itself*, rather than a fact it reports back to the caller.

Updating the stored procedure changes future behavior with no code change:
the same compiled graph produces a different reply once its own
instructions change, exactly the way a system prompt swap or a learned
"always do X before Y" rule would in a real agent.
"""

from typing import TypedDict

from langgraph.config import get_store
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

PROCEDURE_NAMESPACE = ("procedures", "greeter")
PROCEDURE_KEY = "greeting_style"
DEFAULT_STYLE = "friendly and casual"


class GraphState(TypedDict):
    name: str
    reply: str


def greet(state: GraphState) -> dict:
    store = get_store()
    procedure = store.get(PROCEDURE_NAMESPACE, PROCEDURE_KEY)
    style = procedure.value["style"] if procedure else DEFAULT_STYLE

    if style == "formal and professional":
        reply = f"Good day, {state['name']}. How may I assist you?"
    else:
        reply = f"Hey {state['name']}! What's up?"
    return {"reply": reply}


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_edge(START, "greet")
graph.add_edge("greet", END)

store = InMemoryStore()
app = graph.compile(store=store)


if __name__ == "__main__":
    print(f"default procedure: {app.invoke({'name': 'Sam', 'reply': ''})['reply']}")

    # rewrite the stored *procedure* itself -- not a fact about Sam, a rule
    # about how greet() should behave for anyone, from now on
    store.put(PROCEDURE_NAMESPACE, PROCEDURE_KEY, {"style": "formal and professional"})
    print(f"after updating the procedure: {app.invoke({'name': 'Sam', 'reply': ''})['reply']}")
