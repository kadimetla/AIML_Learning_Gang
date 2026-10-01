"""Sample 3 -- Agent Skills served over MCP (SEP-2640), consumed by LangGraph.

Skills over MCP = skills are published as MCP *resources* named
skill://<skill>/SKILL.md (+ supporting files). A host (here: this script)
implements PROGRESSIVE DISCLOSURE, the same pattern as sample2/agent_skills:

  1. DISCOVER  resources/list -> keep skill://*/SKILL.md, parse frontmatter.
               Only name + description go into the system prompt (cheap).
  2. LOAD      model calls load_skill(name) -> we resources/read SKILL.md.
  3. DRILL     model calls read_skill_file(uri) for references/ files, only
               when SKILL.md tells it to.
  4. ACT       the skill's instructions tell the model which ordinary MCP
               TOOL to call (lookup_order). Tool = capability, skill = know-how.

What is simplified vs. the real extension: no skills/list|skills/get calls
(not in the Python SDK yet), no digest verification, no user-approval gate.

    uv run 03_skills.py
"""

import asyncio
import sys
from pathlib import Path

import yaml
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from common import ask, build_app

SERVER = Path(__file__).parent / "servers" / "skills_server.py"


def parse_frontmatter(text: str) -> dict:
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


async def main():
    client = MultiServerMCPClient(
        {
            "skills": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(SERVER)],
            }
        }
    )

    async with client.session("skills") as session:
        # 1. DISCOVER -- advertise names + descriptions only.
        listing = await session.list_resources()
        catalog: dict[str, str] = {}  # skill name -> SKILL.md uri
        blurbs = []
        for r in listing.resources:
            uri = str(r.uri)
            if uri.startswith("skill://") and uri.endswith("/SKILL.md"):
                text = (await session.read_resource(uri)).contents[0].text
                fm = parse_frontmatter(text)
                catalog[fm["name"]] = uri
                blurbs.append(f"- {fm['name']}: {fm['description']}")
        print("discovered skills:\n" + "\n".join(blurbs))

        @tool
        async def load_skill(name: str) -> str:
            """Load the full instructions of a skill by name."""
            if name not in catalog:
                return f"Unknown skill {name!r}. Available: {sorted(catalog)}"
            res = await session.read_resource(catalog[name])
            return res.contents[0].text

        @tool
        async def read_skill_file(uri: str) -> str:
            """Read a supporting file of a skill, e.g. skill://refund-policy/references/escalation.md"""
            if not uri.startswith("skill://"):
                return "Only skill:// URIs may be read."
            res = await session.read_resource(uri)
            return res.contents[0].text

        mcp_tools = await load_mcp_tools(session)  # lookup_order
        tools = [load_skill, read_skill_file, *mcp_tools]

        system = (
            "You are a support agent. You have these skills (load one with "
            "load_skill BEFORE acting on a matching request; never guess the "
            "procedure):\n" + "\n".join(blurbs)
        )
        app = build_app(tools, system)
        await ask(app, "Can I get a refund on order A200?")
        await ask(app, "Customer on order A300 wants their money back -- what do we tell them?")


if __name__ == "__main__":
    asyncio.run(main())
