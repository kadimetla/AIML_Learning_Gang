"""MCP server #3 -- serves AGENT SKILLS over MCP (SEP-2640 "Skills Extension").

A skill is a folder: SKILL.md (YAML frontmatter + instructions) plus optional
supporting files. Per the extension, every file is exposed as an ordinary MCP
*resource* under  skill://<skill-name>/<relative-path> . No new primitive --
skills ride on Resources.

Beside the skills, the server also offers a normal TOOL (`lookup_order`) so the
lesson is visible: the tool is a *capability*, the skill is the *know-how* for
using it correctly.

NOT implemented here: the extension's `skills/list` / `skills/get` JSON-RPC
methods and the `io.modelcontextprotocol/skills` capability declaration. The
Python SDK has no hook for them yet (the spec is brand new), so clients discover
skills with plain `resources/list` and filter on skill://.../SKILL.md.
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources import TextResource
from pydantic import AnyUrl

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

mcp = FastMCP(
    "support-skills",
    instructions=(
        "This server publishes agent skills as skill://<name>/SKILL.md "
        "resources. Read a skill before acting on a matching request."
    ),
)

MIME = {".md": "text/markdown", ".py": "text/x-python"}

for path in sorted(SKILLS_DIR.rglob("*")):
    if not path.is_file():
        continue
    rel = path.relative_to(SKILLS_DIR).as_posix()  # e.g. refund-policy/SKILL.md
    mcp.add_resource(
        TextResource(
            uri=AnyUrl(f"skill://{rel}"),
            name=rel,
            description=f"Skill file {rel}",
            mime_type=MIME.get(path.suffix, "text/plain"),
            text=path.read_text(),
        )
    )

ORDERS = {
    "A100": {"status": "delivered", "total": 80, "age_days": 12},
    "A200": {"status": "delivered", "total": 120, "age_days": 45},
    "A300": {"status": "delivered", "total": 900, "age_days": 5},
    "A400": {"status": "final_sale", "total": 40, "age_days": 3},
}


@mcp.tool()
def lookup_order(order_id: str) -> str:
    """Look up an order's status, total (USD) and age in days."""
    order = ORDERS.get(order_id.upper())
    return str(order) if order else f"No such order {order_id!r}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
