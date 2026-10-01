# sample5 — LangGraph + MCP (stdio, HTTP, skills)

Same ReAct loop as `sample3` (agent node + `ToolNode` + `tools_condition`,
in `common.py`). The only thing MCP changes is **where the tools come from**:
they are discovered from an MCP server by `langchain-mcp-adapters` instead of
being `@tool` functions in the file.

| Script | Server | Concept |
|---|---|---|
| [`01_stdio.py`](01_stdio.py) | [`servers/math_server.py`](servers/math_server.py) | **stdio** transport: client launches the server as a subprocess. Shows all three server primitives: tools, resources, prompts. |
| [`02_http.py`](02_http.py) | [`servers/weather_http_server.py`](servers/weather_http_server.py) | **Streamable HTTP**: long-lived, possibly remote, multi-client server. One client mixes stdio + HTTP servers into one flat tool list. |
| [`03_skills.py`](03_skills.py) | [`servers/skills_server.py`](servers/skills_server.py) | **Skills over MCP** ([SEP-2640](https://modelcontextprotocol.io/seps/2640-skills-extension), Final Sept 2026): skills served as `skill://` resources, loaded with progressive disclosure. |

Slides for students: [`docs/langgraph_mcp_slides.html`](docs/langgraph_mcp_slides.html) (open in a browser, arrow keys to navigate).

Needs `OPENAI_API_KEY` in `.env` (copy `.env.example`).

```bash
uv sync
uv run 01_stdio.py
uv run 02_http.py          # starts the HTTP server for you; or run it yourself:
uv run servers/weather_http_server.py   # (another terminal) then 02 reuses it
uv run 03_skills.py
```

## Talking points

**stdio vs HTTP.** Server code is identical (`mcp.run(transport=...)`); only the
client config differs: `{"transport": "stdio", "command", "args"}` vs
`{"transport": "streamable_http", "url"}`. stdio = local, one client, zero
networking, lifecycle tied to the client, and **stdout is the protocol channel
so never `print()` in a stdio server**. HTTP = deploy once, many clients, auth
(OAuth), load balancers. (SSE is the older HTTP transport; streamable HTTP
replaces it.)

**Tools vs resources vs prompts.** Tools are model-controlled actions;
resources are application-controlled data; prompts are user-controlled
templates. LangChain adapters turn tools into LangChain tools automatically;
resources/prompts are read through the session (`01` shows how).

**Do MCP servers have "skills"?** Yes, as of the 2026 spec, via the *Skills
Extension* (`io.modelcontextprotocol/skills`, SEP-2640). Key ideas:

- A skill is an [Agent Skills](https://agentskills.io/specification) folder:
  `SKILL.md` (YAML frontmatter `name` + `description`, then instructions) plus
  optional `references/`, `scripts/`.
- No new primitive: every file is an ordinary **resource** at
  `skill://<skill-name>/<path>`, read with `resources/read`.
- Discovery: extension methods `skills/list` / `skills/get` (frontmatter + a
  sha256 digest and size per file), or the server's `instructions` pointing at
  URIs.
- Hosts must verify digests, get user approval before activating a skill, and
  never load a skill just because a resource happened to be read.
- **Skills vs tools**: a tool is a capability (`lookup_order`); a skill is the
  know-how for using it (refund rules). `03` shows the model loading
  `refund-policy`, calling the tool, then drilling into
  `references/escalation.md` only when the rules say to.

## What's deliberately simplified in 03

- Python `mcp` SDK (1.30) has no `skills/list`/`skills/get` yet, so the server
  doesn't declare the extension and the client discovers skills with plain
  `resources/list`, filtering on `skill://…/SKILL.md`. Adoption is early; as of
  the spec's finalization no mainstream IDE/CLI harness supports it.
- No digest verification, no user-approval gate, no nested skills.
- Skill scripts are never executed (the extension serves bytes; running them
  is the host's job and would need sandboxing + approval, see
  `sample2/examples/agent_skills/03_*`).

## Gotchas hit while building

- MCP tools from the adapters are async-only: use `app.ainvoke`, not `invoke`.
- Tool results come back as content blocks (`[{'type': 'text', ...}]`), not
  bare strings — the model handles it, but students will notice in the trace.
- `FastMCP` stdio servers log every request to stderr; that's normal.
