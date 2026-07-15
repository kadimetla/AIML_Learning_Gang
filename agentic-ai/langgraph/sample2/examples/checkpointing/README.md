# Checkpointing basics

The foundation every other stateful example in this project builds on —
[`../hitl/`](../hitl/) (pause/resume), [`../time_travel/`](../time_travel/)
(rewind/fork), and [`../store/`](../store/) (contrasted with cross-thread
memory) all assume you already understand this part.

```bash
uv run examples/checkpointing/01_multi_turn_memory.py
uv run examples/checkpointing/02_thread_isolation.py
uv run examples/checkpointing/03_persistent_checkpointer.py
```

## `01_multi_turn_memory.py` — memory across separate `invoke()` calls

Every super-step gets written to the checkpointer, keyed by `thread_id`. The
second `invoke()` only sends the *new* message — the checkpointer already
has the first turn, and `add_messages` (see
[`../reducers/03_add_messages.py`](../reducers/03_add_messages.py)) appends
to it. `get_state(config)` reads the accumulated conversation without
invoking anything.

## `02_thread_isolation.py` — each `thread_id` is a separate history

Two threads (`alice`, `bob`) on the exact same compiled graph and
checkpointer instance never see each other's messages. This is the mirror
image of [`../store/`](../store/), where data is deliberately shared
*across* threads instead.

## `03_persistent_checkpointer.py` — surviving a process restart

`InMemorySaver` (used everywhere else in this project, for simplicity) is
gone the instant the Python process exits. `SqliteSaver` writes checkpoints
to an actual file on disk, so a completely separate process — simulated
here with two separate `with SqliteSaver.from_conn_string(...)` blocks — can
open the same file and recover a thread's state. This is what "memory that
survives a server restart" actually requires; `InMemorySaver` cannot do it
no matter how you configure it.

## Checkpointer vs. `Store`, one more time

| | scope | survives process restart? |
|---|---|---|
| checkpointer (`InMemorySaver`) | one `thread_id` | no |
| checkpointer (`SqliteSaver`, Postgres, ...) | one `thread_id` | yes |
| `Store` | across all threads | depends on backend, same idea as checkpointer |
