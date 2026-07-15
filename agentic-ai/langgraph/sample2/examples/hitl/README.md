# Human-in-the-loop (`interrupt()` + `Command`)

The dynamic sibling of [`../07_interrupt_before.py`](../07_interrupt_before.py).
`interrupt_before=[...]` can only pause *before* a whole node runs, declared
once at compile time. `interrupt(value)` pauses *inside* a node, at the
exact line you call it, and hands back whatever a human supplies via
`Command(resume=...)` as that call's return value. Both need a checkpointer
+ `thread_id`, since the paused run has to be persisted somewhere.

```bash
uv run examples/hitl/01_dynamic_interrupt.py
uv run examples/hitl/02_approve_or_reject_loop.py
```

## `01_dynamic_interrupt.py`

`human_review` calls `interrupt({"question": ..., "text": ...})`. The first
`invoke()` runs `draft`, then pauses inside `human_review` and returns a
result containing an `'__interrupt__'` key with that payload. Calling
`invoke(Command(resume="approved"), config=config)` (same `thread_id`)
resumes `human_review` from that exact line, with `decision == "approved"`.

## `02_approve_or_reject_loop.py`

Combines `interrupt()` with a conditional edge: the human's answer
(`"approve"` vs anything else) decides whether the graph routes to `END` or
back to `draft` for another attempt. This is the realistic shape of an
approval workflow — reject sends it back around the loop, approve lets it
finish.

## Key mental model

`interrupt()` doesn't return early — the *whole graph run* pauses and
persists via the checkpointer. Resuming re-enters the node and re-runs it
from the top, but any `interrupt()` calls that already have an answer return
immediately with that answer instead of pausing again (that's why
`human_review` doesn't re-ask after resume).
