"""Local Agent Skills with progressive disclosure (same idea as sample5/03_skills.py,
but read from the skills/ folder instead of an MCP server).

  1. DISCOVER  scan skills/*/SKILL.md, parse frontmatter. Only name +
               description go into the system prompt (cheap, every turn).
  2. LOAD      model calls load_skill(name) -> full SKILL.md body.
  3. DRILL     model calls read_skill_file(name, path) for references/ files,
               only when SKILL.md tells it to.
"""

from pathlib import Path

import yaml
from langchain_core.tools import tool

SKILLS_DIR = Path(__file__).parent / "skills"


def parse_frontmatter(text: str) -> dict:
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


def discover() -> dict[str, dict]:
    """skill name -> {"description": ..., "dir": Path}"""
    catalog = {}
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        fm = parse_frontmatter(skill_md.read_text())
        catalog[fm["name"]] = {"description": fm["description"], "dir": skill_md.parent}
    return catalog


CATALOG = discover()


def catalog_text() -> str:
    return "\n".join(f"- {name}: {s['description']}" for name, s in CATALOG.items())


@tool
def load_skill(name: str) -> str:
    """Load the full instructions of a skill by name. Do this BEFORE acting on a matching request."""
    if name not in CATALOG:
        return f"Unknown skill {name!r}. Available: {sorted(CATALOG)}"
    return (CATALOG[name]["dir"] / "SKILL.md").read_text()


@tool
def read_skill_file(name: str, path: str) -> str:
    """Read a supporting file of a skill, e.g. name='refund-policy', path='references/escalation.md'."""
    if name not in CATALOG:
        return f"Unknown skill {name!r}."
    root = CATALOG[name]["dir"].resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():  # no ../ escapes
        return f"No file {path!r} in skill {name!r}."
    return target.read_text()


SKILL_TOOLS = [load_skill, read_skill_file]
