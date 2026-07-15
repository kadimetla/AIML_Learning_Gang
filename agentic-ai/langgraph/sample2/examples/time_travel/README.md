# Time travel (`get_state_history` + `update_state`)

Every super-step of a checkpointed run is its own checkpoint — nothing is
deleted when you `invoke()` again, so you can always look back at (and
resume from) an earlier point. Builds on the same checkpointer +
`thread_id` mechanism as [`../hitl/`](../hitl/) and
[`../07_interrupt_before.py`](../07_interrupt_before.py).

```bash
uv run examples/time_travel/01_replay_and_fork.py
```

## `01_replay_and_fork.py`

`app.get_state_history(config)` yields every checkpoint for a thread, newest
first, each with `.values` (the state at that point) and `.next` (which
node would run next). We pick the checkpoint right after `step1` ran, then:

```python
forked_config = app.update_state(checkpoint.config, {"steps": [...]})
app.invoke(None, config=forked_config)
```

`update_state()` doesn't mutate the past checkpoint — it writes a *new*
checkpoint with the edited values and returns a config pointing at it.
Resuming from that config (`invoke(None, ...)`) continues from `step2`
onward, but using the overridden `steps` value. The original run's history
(the real, un-overridden `step1` → `step2` → `step3`) is still there
untouched — this forks a branch, it doesn't rewrite history.

## Why this matters

This is the mechanism behind "edit an earlier AI response and regenerate
from there" UIs, and behind debugging a multi-step agent run by rewinding to
right before the step that went wrong.
