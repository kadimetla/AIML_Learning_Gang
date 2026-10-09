# sample5 — LangGraph + MCP (stdio, HTTP, skills)

Same ReAct loop as `sample3` (agent node + `ToolNode` + `tools_condition`),
written out in full inside each script (`common.py` only holds the `ask()` runner).
The only thing MCP changes is **where the tools come from**:
they are discovered from an MCP server by `langchain-mcp-adapters` instead of
being `@tool` functions in the file.

| Script | Server | Concept |
|---|---|---|
| [`01_stdio.py`](01_stdio.py) | [`servers/math_server.py`](servers/math_server.py) | **stdio** transport: client launches the server as a subprocess. Shows all three server primitives: tools, resources, prompts. |
| [`02_http.py`](02_http.py) | [`servers/weather_http_server.py`](servers/weather_http_server.py) | **Streamable HTTP**: long-lived, possibly remote, multi-client server. One client mixes stdio + HTTP servers into one flat tool list. |
| [`03_skills.py`](03_skills.py) | [`servers/skills_server.py`](servers/skills_server.py) | **Skills over MCP** ([SEP-2640](https://modelcontextprotocol.io/seps/2640-skills-extension), Final Sept 2026): skills served as `skill://` resources, loaded with progressive disclosure. |

Slides for students: [`docs/langgraph_mcp_slides.html`](docs/langgraph_mcp_slides.html) (open in a browser, arrow keys to navigate).

Needs `OPENAI_API_KEY` in `.env` (copy `.env.example`). Worked solutions for the
deck's three exercises: [`SOLUTIONS.md`](SOLUTIONS.md).

## How to run

### Setup (once)

```bash
cd agentic-ai/langgraph/sample5
cp .env.example .env       # then put your key in it: OPENAI_API_KEY=sk-...
uv sync
```

Python 3.13+ and [uv](https://docs.astral.sh/uv/) are required. Run every
command below from inside `sample5/`. Lines like
`Processing request of type ...` on stderr are MCP server logs and are normal.

### 1. stdio

```bash
uv run 01_stdio.py
```

The script launches `servers/math_server.py` itself as a subprocess; there is
nothing to start. Expected output:

```
MCP tools: ['add', 'multiply']
MCP resources: ['math://constants']
MCP prompts:   ['explain_step_by_step']
math://constants -> pi = 3.14159265; e = 2.71828183; phi = 1.61803399
>>> What is (23 * 17) + 5? Use the tools.
... multiply(23, 17) -> 391.0, add(391, 5) -> 396.0 ...
The result of (23 x 17) + 5 is 396.
```

### 2. Streamable HTTP (mixed with stdio)

Simplest -- the script starts and stops the HTTP server for you:

```bash
uv run 02_http.py
```

To see the server as a real separate service, use two terminals:

```bash
# terminal A: the MCP service, stays running on 127.0.0.1:8765/mcp
uv run servers/weather_http_server.py

# terminal B: the agent (prints "reusing weather server already listening")
uv run 02_http.py
```

Expected: tools from both servers
(`['add', 'multiply', 'get_weather', 'list_cities']`), then one question
triggers `get_weather` (HTTP server) and `multiply` (stdio server) in the same
turn. If port 8765 is busy, stop whatever holds it.

### 3. Skills over MCP

```bash
uv run 03_skills.py
```

Launches `servers/skills_server.py` over stdio and asks two questions:

- *"Can I get a refund on order A200?"* -- `lookup_order`, then "store credit
  only" (45 days old). The model may skip `load_skill` here; skills are advisory.
- *"Customer on order A300 wants their money back"* -- `load_skill` ->
  `lookup_order` -> `read_skill_file(references/escalation.md)` -> "eligible,
  pending manager approval" ($900 > $500).

Orders `A100`-`A400` are fake data in `servers/skills_server.py`.

### See what is sent to the LLM

Add `--show-llm` to any script to print every LLM request and response
(`llm_trace.py`, a LangChain callback):

```bash
uv run 01_stdio.py --show-llm
```

Each trip through the `agent` node prints the model, the **tools sent** (name,
description, JSON schema -- this is how MCP tools reach the model), the **full
message list sent**, and the response (`tool_call`s or final text, plus token
counts). Watch the message list grow: user question -> AI `tool_calls` -> `tool`
results -> final answer. In `03` the system prompt with the skill catalog is
visible as the first `[system]` message.

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `AuthenticationError` / missing key | `OPENAI_API_KEY` not set in `sample5/.env` |
| `ModuleNotFoundError` | run `uv sync`, and use `uv run`, not bare `python` |
| 02: connection refused | server not up yet or port 8765 in use |
| Garbled stdio output / handshake error | a `print()` in a stdio server -- stdout is the protocol channel |

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
