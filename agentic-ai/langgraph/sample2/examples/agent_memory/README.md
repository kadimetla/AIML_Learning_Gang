# Agent memory: working, episodic, semantic, procedural

Four kinds of memory an agent can have, each backed by a different LangGraph
primitive already used elsewhere in `examples/`:

| Type | Definition | Script | Primitive |
|---|---|---|---|
| Working | what's happening *right now* | [`01_working_memory.py`](01_working_memory.py) | plain graph state, no checkpointer -- gone as soon as `invoke()` returns |
| Episodic | what *happened before* | [`02_episodic_memory.py`](02_episodic_memory.py) | checkpointer + `get_state_history()` -- every past turn kept, individually recallable (see [`../checkpointing/`](../checkpointing/), [`../time_travel/`](../time_travel/)) |
| Semantic | what's *true* | [`03_semantic_memory.py`](03_semantic_memory.py) | `Store`, keyed by namespace -- one current value per key, reachable from any thread (see [`../store/`](../store/)) |
| Procedural | *how to act* | [`04_procedural_memory.py`](04_procedural_memory.py) | `Store`, holding a rule the node applies to itself -- same shape as semantic memory, but the value shapes behavior instead of being reported back |

No API key needed -- none of these use an LLM, they're isolated
demonstrations of the persistence mechanism each memory type relies on.

```bash
uv run examples/agent_memory/01_working_memory.py
uv run examples/agent_memory/02_episodic_memory.py
uv run examples/agent_memory/03_semantic_memory.py
uv run examples/agent_memory/04_procedural_memory.py
```

## The key distinctions

- **Working vs. everything else**: working memory needs *no* persistence
  mechanism at all -- it's just state flowing through one `invoke()`. The
  other three all exist because something deliberately outlives a single run.
- **Episodic vs. semantic**: both persist across runs, but episodic memory
  *accumulates* (every event kept, checkpoint history only grows) while
  semantic memory *overwrites* (`store.put()` on an existing key replaces
  its value -- a fact only has one current answer).
- **Semantic vs. procedural**: both live in a `Store` with the same
  `namespace`/`key` shape. The difference is what the value is used for --
  semantic memory's value is reported back as a fact ("what I know"),
  procedural memory's value is read by the node and changes *how the node
  itself behaves* ("how I act").
