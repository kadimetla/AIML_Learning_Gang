"""Skills, take 1: file-based skills discovered from disk, loaded through
progressive disclosure -- the core idea behind Microsoft Agent Framework's
Agent Skills (and, before that, Anthropic's own Skill format: the same
"advertise -> load -> read resources -> run scripts" shape used by the
`Skill` tool available in this very session).

There's no SkillsProvider here, because LangGraph doesn't have one -- but
the pattern is just two primitives this repo already teaches, combined:
    - a ToolNode + tools_condition loop, so the model decides *which* skill
      (if any) applies, exactly like ../tool_node_weather/ decides whether
      to call a weather tool                              (../tool_node/)
    - the skill catalog only advertises name+description up front (cheap);
      full instructions and reference docs are fetched on demand through
      tool calls (load_skill, read_skill_resource), never dumped into the
      system prompt wholesale

Each skill on disk is a `skills/<name>/SKILL.md` file (--- frontmatter with
name/description, then instructions --) plus an optional `references/`
directory of extra docs a skill can point the model at.

Needs OPENAI_API_KEY in .env (see .env.example) -- the whole point of this
example is the model *deciding* which skill applies, so it needs to reason
for real, not follow a script.
"""

from dotenv import load_dotenv

load_dotenv()

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import MessagesState, START, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition

SKILLS_DIR = Path(__file__).parent / "skills"


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    resources: dict[str, str] = field(default_factory=dict)


def _parse_skill_md(path: Path) -> Skill:
    _, frontmatter, instructions = path.read_text().split("---", 2)
    meta = dict(line.split(":", 1) for line in frontmatter.strip().splitlines())
    return Skill(
        name=meta["name"].strip(),
        description=meta["description"].strip(),
        instructions=instructions.strip(),
    )


def _load_skills(skills_dir: Path) -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        skill = _parse_skill_md(skill_md)
        references_dir = skill_dir / "references"
        if references_dir.exists():
            for ref in references_dir.iterdir():
                skill.resources[f"references/{ref.name}"] = ref.read_text()
        skills[skill.name] = skill
    return skills


SKILLS = _load_skills(SKILLS_DIR)


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


@tool
def read_skill_resource(name: str, resource_path: str, state: Annotated[dict, InjectedState]) -> str:
    """Read a reference file bundled with a skill (e.g. 'references/examples.md')."""
    skill = SKILLS.get(name)
    if not skill or resource_path not in skill.resources:
        return f"no such resource: {name}/{resource_path}"
    content = skill.resources[resource_path]
    if _already_returned(state, content):
        return f"'{resource_path}' is already shown above -- don't read it again, answer the user directly now."
    return content


# stage 1: advertise -- just names + descriptions, cheap enough to always
# include. Full instructions (stage 2) and resources (stage 3) only load if
# the model actually decides it needs them.
_catalog = "\n".join(f"- {s.name}: {s.description}" for s in SKILLS.values())
SYSTEM_PROMPT = (
    "You have access to these skills (name: description only -- call "
    f"load_skill(name) to get full instructions before using one):\n{_catalog}\n\n"
    "Only load a skill if the user's request actually needs it. Load a given "
    "skill at most once -- once you have its instructions (and any resource "
    "you read), apply them yourself and answer directly. Never call "
    "load_skill or read_skill_resource twice with the same arguments."
)

model = init_chat_model("openai:gpt-4o-mini", temperature=0)
model_with_tools = model.bind_tools([load_skill, read_skill_resource])


def chatbot(state: MessagesState) -> dict:
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    return {"messages": [model_with_tools.invoke(messages)]}


graph = StateGraph(MessagesState)
graph.add_node("chatbot", chatbot)
graph.add_node("tools", ToolNode([load_skill, read_skill_resource]))
graph.add_edge(START, "chatbot")
graph.add_conditional_edges("chatbot", tools_condition)  # -> "tools" or END
graph.add_edge("tools", "chatbot")
app = graph.compile()


def ask(question: str) -> dict:
    # recursion_limit is a safety net, not the primary fix -- a real LLM can
    # still get stuck re-calling a tool with identical arguments (a known
    # temperature=0 repetition trap); the system prompt above is what tells
    # it to stop, this just guarantees the demo fails fast instead of
    # burning API calls forever if that instruction doesn't land
    try:
        return app.invoke({"messages": [HumanMessage(question)]}, config={"recursion_limit": 10})
    except GraphRecursionError:
        return {"messages": [], "_gave_up": True}


if __name__ == "__main__":
    result = ask("Translate 'hello friend, are you ready?' like a pirate would say it")
    if result.get("_gave_up"):
        print("gave up after too many tool calls -- see the recursion_limit comment in ask()")
    else:
        for message in result["messages"]:
            label = type(message).__name__
            calls = getattr(message, "tool_calls", None)
            print(f"{label:14s} tool_calls={calls} content={message.content!r}")

    # a question no skill applies to -- the model shouldn't load anything
    result = ask("What's 2 + 2?")
    print(f"\nno relevant skill needed: {result['messages'][-1].content!r}")
