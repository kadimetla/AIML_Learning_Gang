# Capstone: rebuilding `graph_websearch_agent`

A trimmed, modernized rebuild of
[`graph_websearch_agent`](https://github.com/kadimetla/graph_websearch_agent)
— a real 2024 multi-agent web-research project on LangGraph `0.0.64` — on
LangGraph `1.2.9`. Same overall shape, every piece rebuilt with a modern
primitive from elsewhere in `examples/`.

**Needs `OPENAI_API_KEY` in `.env`** (copy `.env.example`). `search_web`/
`scrape_url` (in `tools.py`) need no key — they hit DuckDuckGo's HTML
endpoint and real pages directly.

```bash
uv run examples/capstone_websearch_agent/01_research_agent.py
```

This makes real search/scrape requests and real (small, `gpt-4o-mini`)
LLM calls — it costs a little money and takes a few seconds, unlike every
other example in this project.

## The pipeline

```
planner → search → selector → scrape → reporter → review_and_route
                                                          │
                                    ┌─────────────────────┤
                                    ▼ (loop back)          ▼ (looks good)
                       planner / selector / reporter   final_report
                                                          │
                                                   interrupt(): human approves?
                                                    │              │
                                              reject │              │ approve
                                                    ▼              ▼
                                                reporter          END
```

## What changed from the original, piece by piece

| Original repo | This capstone |
|---|---|
| `models/` — 6 hand-written provider wrapper files, branched over in `Agent.get_llm()` | one `init_chat_model("openai:gpt-4o-mini")` call ([`../model_init/`](../model_init/)) |
| Every agent prompts "respond in this JSON format", then `json.loads()`s the response | `model.with_structured_output(SearchPlan / SelectorDecision / ReviewDecision)` ([`../structured_output/`](../structured_output/)) |
| `states/state.py` — untyped flat `TypedDict`, `get_agent_graph_state()` helper for reading "latest" values | a `pydantic.BaseModel` (`ResearchState`), validated on every `invoke()` ([`../pydantic_state/`](../pydantic_state/)) |
| Separate `reviewer` (writes feedback text) + `router` (parses that text, decides next node via `add_conditional_edges`) | one `review_and_route` node returning `Command(update=..., goto=...)` ([`../command/`](../command/)) |
| No checkpointer wired in at all — `thread` config is commented out in `app.py` | `checkpointer=InMemorySaver()` + `thread_id`, so the run can actually pause ([`../checkpointing/`](../checkpointing/)) |
| Reviewer's approval is the *only* gate before publishing — no human involved | `interrupt()` human approval gate in front of `final_report`; rejecting loops back to `reporter` with feedback ([`../hitl/`](../hitl/)) |
| `tools/google_serper.py` needs a paid Serper API key; scrape errors are caught but never retried | `search_web`/`scrape_url` (`tools.py`) need no key, and get a `RetryPolicy` for transient failures ([`../retry_policy/`](../retry_policy/)) |
| No cap on the reviewer↔agent feedback loop — could run until `recursion_limit` (default 40 in the original's `app.py`) | `MAX_REVIEW_LOOPS = 2` enforced inside `review_and_route` itself — a real LLM loop costs real money per iteration, so capping it explicitly is worth calling out as its own decision, not just relying on `recursion_limit` as a backstop |

## What's deliberately *not* rebuilt here

- **Multi-provider support** (`claude`/`gemini`/`groq`/`ollama`/`vllm` in the original) — `../model_init/02_runtime_configurable_model.py` shows the mechanism (`config["configurable"]["model_provider"]`); wiring it into this graph is a good extension exercise.
- **Agent-decided tool calls** — `search`/`scrape` are still fixed pipeline steps here, matching the original's architecture. Rebuilding them as real `@tool`s behind a `ToolNode` (so the LLM decides *whether* to search/scrape, and with what arguments) is exactly what [`../tool_node/`](../tool_node/) and [`../tool_node_weather/`](../tool_node_weather/) already teach separately.
- **Parallel candidate selection** — the original (and this capstone) always picks exactly one URL. Having `selector` return a list of 2-3 candidates and fanning `scrape` out over all of them with [`Send`](../send/), then having `reporter` synthesize across every source, is a natural next step.

## Running it again

Each run makes a handful of real `gpt-4o-mini` calls plus one search and one
scrape request — cheap, but not free and not instant like the rest of
`examples/`. `MAX_REVIEW_LOOPS` keeps a single run bounded even if the
reviewer keeps asking for changes.
