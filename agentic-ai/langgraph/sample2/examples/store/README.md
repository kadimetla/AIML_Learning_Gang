# `Store` — cross-thread long-term memory

A checkpointer (used in [`../hitl/`](../hitl/) and
[`../time_travel/`](../time_travel/)) persists state *within* one
`thread_id` — it's how a single conversation survives a pause/resume. A
`Store` is different: it's shared *across every thread*, meant for things
that should outlive any one conversation, like a user's stated preferences.

```bash
uv run examples/store/01_cross_thread_memory.py
```

## `01_cross_thread_memory.py`

`get_store()` (from `langgraph.config`, same module as `get_stream_writer`
used in [`../11_stream_mode_custom.py`](../11_stream_mode_custom.py)) gives
a node access to whatever store was passed to `graph.compile(store=...)`.
Data is addressed by `(namespace_tuple, key)` — here
`(("preferences", user_id), "favorite_color")` — so `thread-A` can write a
preference and `thread-B` (a completely separate conversation, same
`user_id`) can read it back. A different `user_id` sees nothing, since the
namespace is scoped per user.

## Store vs. checkpointer

| | scope | typical use |
|---|---|---|
| checkpointer | one `thread_id` | pause/resume, time travel, one conversation's history |
| `Store` | across all threads | facts that should persist regardless of which conversation is active |

`InMemoryStore` here is for teaching/testing — production stores back onto a
real database (Postgres, Redis, ...) so data survives a process restart.
