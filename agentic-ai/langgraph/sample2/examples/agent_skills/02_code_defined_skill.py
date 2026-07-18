"""Skills, take 2: code-defined skills -- no SKILL.md file at all, just a
Skill object built directly in Python. This is what Microsoft Agent
Framework's `InlineSkill` is for: skills sourced from a database, generated
at runtime, or embedded in application logic instead of shipped as files.

Reuses the exact same Skill shape, load_skill tool, and ToolNode +
tools_condition loop as 01_file_based_skill.py -- the whole point is that
*how* a skill's name/description/instructions came to exist (a file on
disk vs. a Python dict simulating a database row) doesn't matter to the
agent loop at all, only that it has those three fields.

Needs OPENAI_API_KEY in .env (see .env.example).
"""

from dotenv import load_dotenv

load_dotenv()

from dataclasses import dataclass
from typing import Annotated

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import MessagesState, START, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition


@dataclass
class Skill:
    name: str
    description: str
    instructions: str


# simulates skills fetched from a database/config service at startup,
# instead of read from disk -- same Skill shape as 01, different source
_SKILL_RECORDS = [
    {
        "name": "metric_converter",
        "description": "Convert numeric values between metric and imperial units (km/miles, kg/lbs, C/F).",
        "instructions": (
            "Apply these exact factors and show your work: "
            "1 km = 0.621371 miles, 1 kg = 2.20462 lbs, C to F = (C * 9/5) + 32. "
            "Round to 2 decimal places."
        ),
    },
    {
        "name": "acronym_expander",
        "description": "Expand a technical acronym into its full name plus a one-sentence explanation.",
        "instructions": (
            "Given an acronym, state what it stands for and explain it in exactly "
            "one plain-English sentence -- no more."
        ),
    },
]
SKILLS = {record["name"]: Skill(**record) for record in _SKILL_RECORDS}


def _already_returned(state: dict, content: str) -> bool:
    # gpt-4o-mini at temperature=0 can get stuck re-calling a tool with
    # identical arguments forever (a real, reproducible repetition trap --
    # not hypothetical, it happened while building this example). A prompt
    # asking the model not to repeat itself isn't reliable enough on its
    # own; this makes the *tool* refuse to repeat instead, which
    # deterministically breaks the loop no matter what the model does.
    return any(isinstance(m, ToolMessage) and m.content == content for m in state["messages"])


@tool
def load_skill(name: str, state: Annotated[dict, InjectedState]) -> str:
    """Load the full instructions for a skill by name."""
    skill = SKILLS.get(name)
    if not skill:
        return f"no such skill: {name!r}"
    if _already_returned(state, skill.instructions):
        return f"'{name}' is already loaded above -- don't call load_skill again, answer the user directly now."
    return skill.instructions


_catalog = "\n".join(f"- {s.name}: {s.description}" for s in SKILLS.values())
SYSTEM_PROMPT = (
    "You have access to these skills (name: description only -- call "
    f"load_skill(name) to get full instructions before using one):\n{_catalog}\n\n"
    "Only load a skill if the user's request actually needs it. Load a given "
    "skill at most once -- once you have its instructions, apply them "
    "yourself and answer directly. Never call load_skill twice with the "
    "same arguments."
)

model = init_chat_model("openai:gpt-4o-mini", temperature=0)
model_with_tools = model.bind_tools([load_skill])


def chatbot(state: MessagesState) -> dict:
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    return {"messages": [model_with_tools.invoke(messages)]}


graph = StateGraph(MessagesState)
graph.add_node("chatbot", chatbot)
graph.add_node("tools", ToolNode([load_skill]))
graph.add_edge(START, "chatbot")
graph.add_conditional_edges("chatbot", tools_condition)
graph.add_edge("tools", "chatbot")
app = graph.compile()


def ask(question: str) -> dict:
    # safety net, not the primary fix -- see the matching comment in
    # 01_file_based_skill.py's ask() for why this exists
    try:
        return app.invoke({"messages": [HumanMessage(question)]}, config={"recursion_limit": 10})
    except GraphRecursionError:
        return {"messages": [], "_gave_up": True}


if __name__ == "__main__":
    result = ask("Convert 10 km to miles")
    if result.get("_gave_up"):
        print("gave up after too many tool calls -- see the recursion_limit comment in ask()")
    else:
        for message in result["messages"]:
            label = type(message).__name__
            calls = getattr(message, "tool_calls", None)
            print(f"{label:14s} tool_calls={calls} content={message.content!r}")

    result = ask("What does LLM stand for?")
    if result.get("_gave_up"):
        print("\ngave up after too many tool calls -- see the recursion_limit comment in ask()")
    else:
        print(f"\nacronym_expander result: {result['messages'][-1].content!r}")
