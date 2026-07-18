"""Skills, take 3: running a skill's bundled script, gated behind human
approval -- Agent Skills' `run_skill_script`, which (per Microsoft's own
docs) "requires host approval by default." Combines two things this repo
already teaches separately: the ToolNode + tools_condition loop from
01/02, and interrupt()-based approval from ../hitl/ and the capstone's
final_report gate -- except here interrupt() lives *inside* a tool call
instead of a dedicated node, and it still pauses the whole run the same way.

The word_stats skill's instructions tell the model not to estimate counts
itself -- it has to call run_skill_script, which always pauses for a human
yes/no before the script actually executes.

Needs OPENAI_API_KEY in .env (see .env.example).
"""

from dotenv import load_dotenv

load_dotenv()

from typing import Annotated

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import MessagesState, START, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition
from langgraph.types import Command, interrupt

WORD_STATS_DESCRIPTION = "Compute exact word/character/sentence counts for a piece of text."
WORD_STATS_INSTRUCTIONS = (
    "Don't estimate word/character/sentence counts yourself -- they need to "
    "be exact. Call run_skill_script(text=<the text to analyze>) and report "
    "back the numbers it returns."
)


def _count(text: str) -> str:
    words = len(text.split())
    chars = len(text)
    sentences = sum(text.count(c) for c in ".!?")
    return f"words={words} chars={chars} sentences={sentences}"


@tool
def load_skill(state: Annotated[dict, InjectedState]) -> str:
    """Load the full instructions for the word_stats skill."""
    # gpt-4o-mini at temperature=0 can get stuck re-calling a tool with
    # identical results forever (a real, reproducible repetition trap, see
    # 01_file_based_skill.py) -- refusing a repeat call deterministically
    # breaks that loop no matter what the model does
    already_loaded = any(
        isinstance(m, ToolMessage) and m.content == WORD_STATS_INSTRUCTIONS for m in state["messages"]
    )
    if already_loaded:
        return "word_stats is already loaded above -- don't call load_skill again, use it directly now."
    return WORD_STATS_INSTRUCTIONS


@tool
def run_skill_script(text: str) -> str:
    """Run word_stats' bundled counting script on the given text. Requires
    human approval before it actually executes."""
    decision = interrupt({"question": "approve running word_stats on this text?", "text": text})
    if decision != "approve":
        return f"script execution rejected by human: {decision!r} -- no counts available"
    return _count(text)


SYSTEM_PROMPT = (
    "You have access to one skill, word_stats: "
    f"{WORD_STATS_DESCRIPTION} Call load_skill() at most once to get its full "
    "instructions before using it, then call run_skill_script() at most once "
    "per piece of text and report back what it returns."
)

model = init_chat_model("openai:gpt-4o-mini", temperature=0)
model_with_tools = model.bind_tools([load_skill, run_skill_script])


def chatbot(state: MessagesState) -> dict:
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    return {"messages": [model_with_tools.invoke(messages)]}


graph = StateGraph(MessagesState)
graph.add_node("chatbot", chatbot)
graph.add_node("tools", ToolNode([load_skill, run_skill_script]))
graph.add_edge(START, "chatbot")
graph.add_conditional_edges("chatbot", tools_condition)
graph.add_edge("tools", "chatbot")
app = graph.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    text = "LangGraph makes it easy to build stateful agents. It really does!"

    # recursion_limit is a safety net, not the primary fix -- see the
    # matching comment in 01_file_based_skill.py's ask()
    config = {"configurable": {"thread_id": "approve-1"}, "recursion_limit": 10}
    result = app.invoke(
        {"messages": [HumanMessage(f"How many words are in this text: {text!r}")]}, config=config
    )
    interrupt_payload = result["__interrupt__"][0].value
    print(f"paused for approval: {interrupt_payload}\n")

    result = app.invoke(Command(resume="approve"), config=config)
    print(f"approved -- final answer: {result['messages'][-1].content!r}\n")

    config = {"configurable": {"thread_id": "reject-1"}, "recursion_limit": 10}
    result = app.invoke(
        {"messages": [HumanMessage(f"How many words are in this text: {text!r}")]}, config=config
    )
    interrupt_payload = result["__interrupt__"][0].value
    print(f"paused for approval: {interrupt_payload}\n")

    result = app.invoke(Command(resume="deny"), config=config)
    print(f"rejected -- final answer: {result['messages'][-1].content!r}")
