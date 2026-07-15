# `Command(update=..., goto=...)`

Fold a state update and a routing decision into one node's return value,
instead of a separate `add_conditional_edges` function.

```bash
uv run examples/command/01_update_and_goto.py
```

## `01_update_and_goto.py`

`evaluate` returns `Command(update={"verdict": verdict}, goto=verdict)` —
`update` merges into state exactly like a normal `dict` return would,
`goto` names the next node directly. Notice there's no edge from
`"evaluate"` to `"accept"`/`"reject"` in the graph definition at all —
`Command.goto` replaces what `add_conditional_edges` would otherwise do.

## vs. `Send` ([`../send/`](../send/))

Easy to conflate — both are returned from a node/routing function and both
affect control flow, but they solve different problems:

| | picks | typical use |
|---|---|---|
| `Command(goto=...)` | one (or a fixed few) next node | data-dependent branching, still updates state |
| `Send(node, arg)` | N parallel copies of one node | fan-out over a runtime-sized list (map-reduce) |
