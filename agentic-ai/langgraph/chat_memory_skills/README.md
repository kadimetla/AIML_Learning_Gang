# chat_memory_skills — end-to-end chat: memory + tools + skills

One LangGraph chat app that combines what samples 2–5 showed separately:
a multi-turn REPL, **short-term memory** (checkpointer), **long-term memory**
(store + semantic recall), ordinary **tools**, and local **skills** loaded with
progressive disclosure.

```
 START ──► recall ──► agent ◄──► tools
                        │
                        └──► END  (no tool calls)
```

| Node | What it does |
|---|---|
| `recall` | `store.search(("memories", user_id), query=<last message>)` → `state["recalled"]` |
| `agent` | System prompt = rules + skill catalog (name + description only) + recalled memories. LLM answers or calls tools. |
| `tools` | `ToolNode` with three kinds of tool, see below |

| Tool | Kind | File |
|---|---|---|
| `lookup_order`, `calculator` | capability | [`tools.py`](tools.py) |
| `load_skill`, `read_skill_file` | skill (know-how) | [`skills.py`](skills.py), [`skills/`](skills/) |
| `save_memory`, `forget_memory` | long-term memory write | [`memory.py`](memory.py) |

The graph wiring and REPL are in [`chat.py`](chat.py).

## The two memory layers

| | Short-term | Long-term |
|---|---|---|
| Holds | this conversation's messages | durable facts about the user |
| LangGraph object | checkpointer (`SqliteSaver`) | store (`SqliteStore` + embeddings) |
| Keyed by | `thread_id` | namespace `("memories", user_id)` |
| File | `checkpoints.db` | `memories.db` |
| Written by | LangGraph, automatically after every node | the **model**, through `save_memory` |
| Read by | LangGraph, automatically at the start of a run | the `recall` node (semantic search) |
| `/new` thread | starts empty | still there |

Both are passed in when you compile:
`build_graph().compile(checkpointer=saver, store=store)`. Inside nodes and
tools, `get_store()` / `get_config()` (from `langgraph.config`) return the
store and the `user_id` for the current run.

## Skills: progressive disclosure

1. **Discover**: at startup, `skills.py` scans `skills/*/SKILL.md` and parses
   the frontmatter. Only `name: description` goes into the prompt.
2. **Load**: the model calls `load_skill("refund-policy")` and gets the full body.
3. **Drill**: if `SKILL.md` says so, the model calls
   `read_skill_file("refund-policy", "references/escalation.md")`.
4. **Act**: the skill tells the model which ordinary tool to call (`lookup_order`).

`meal-planner` shows skills and memory working together: its instructions tell
the model to respect the "Known about this user" facts.

## How to run

```bash
cd agentic-ai/langgraph/chat_memory_skills
cp .env.example .env       # OPENAI_API_KEY=sk-...  (chat model + embeddings)
uv sync
```

### Scripted demo

```bash
uv run demo.py
```

Thread A: you state a fact (→ `save_memory`), ask about a refund
(→ `load_skill` → `lookup_order` → `read_skill_file`), then ask a follow-up
("that order") that only short-term memory can answer. Thread B is a **new**
thread: the history is empty, but `recall` still knows you're vegetarian, so
`meal-planner` uses that.

### Interactive

```bash
uv run chat.py                 # user "adi", new random thread
uv run chat.py --user sam      # different user = separate long-term memory
uv run chat.py --thread 1a2b3c4d   # resume a thread (short-term memory)
```

| Command | Effect |
|---|---|
| `/new` | start a new thread (history gone, memories stay) |
| `/thread <id>` | switch to an existing thread |
| `/memories` | list this user's long-term memories |
| `/quit` | exit |

Things to try: "I'm vegetarian", then `/new` and ask for dinner ideas.
"Actually I eat fish now" (→ `forget_memory` + `save_memory`).
"Refund on A400?" (final sale). Delete `*.db` to reset everything.

## Exercises

1. Add a `summarize` node that runs before `agent` when `len(messages) > 20`.
   It replaces old messages with a summary (use `RemoveMessage`).
2. Move memory writing out of the hot path: after `END`, a background step
   extracts facts from the last turn instead of the model calling `save_memory`.
3. Add a third skill that needs a new tool, e.g. `trip-planner` with a
   `get_weather` tool.
4. Load the same `skills/` folder from the sample5 MCP skills server instead
   of from disk. Only `skills.py` should need to change.
