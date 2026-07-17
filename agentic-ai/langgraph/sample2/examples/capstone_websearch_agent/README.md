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

`02`/`03`/`04` below run the same way, just swap the filename.

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

## Extensions

`01` deliberately left three things unbuilt, as "good extension exercise" material. Each is now its own self-contained script (`02`/`03`/`04`), matching the rest of `examples/`'s convention of numbered, non-cross-importing scripts within a folder — mixing all three into one script would have produced an incoherent graph shape.

| Script | What it changes from `01` | Pattern borrowed from |
|---|---|---|
| [`02_multi_provider.py`](02_multi_provider.py) | `init_chat_model("openai:gpt-4o-mini")` → `init_chat_model(configurable_fields=("model", "model_provider"))`, picked at `invoke()` time via `config`, instead of one provider fixed at import time (what the original's `Agent.get_llm()` branching was trying to achieve by hand) | [`../model_init/02_runtime_configurable_model.py`](../model_init/02_runtime_configurable_model.py) |
| [`03_agent_tool_calls.py`](03_agent_tool_calls.py) | `planner`/`selector` collapse into one `researcher` node bound to real `@tool`-wrapped `search_web`/`scrape_url`; the LLM decides *whether* to search/scrape, how many times, and with what arguments, via a `ToolNode` + `tools_condition` loop, instead of a scripted pipeline | [`../tool_node/01_basic_tool_node.py`](../tool_node/01_basic_tool_node.py), [`../tool_node_weather/01_weather_tool_agent.py`](../tool_node_weather/01_weather_tool_agent.py) |
| [`04_parallel_selection.py`](04_parallel_selection.py) | `selector` returns 2-3 candidate URLs instead of one; `dispatch` fans `scrape` out over all of them in parallel with `Send`; `reporter` synthesizes across every source instead of just one | [`../send/01_map_reduce.py`](../send/01_map_reduce.py) |

## Running it again

Each run makes a handful of real `gpt-4o-mini` calls plus one search and one
scrape request — cheap, but not free and not instant like the rest of
`examples/`. `MAX_REVIEW_LOOPS` keeps a single run bounded even if the
reviewer keeps asking for changes.
