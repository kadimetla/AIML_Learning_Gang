# Reducers

A reducer decides how a node's return value gets merged into a state key —
the default with no reducer is plain overwrite (whichever node ran last
wins). `Annotated[type, reducer_fn]` attaches a custom merge function
instead.

```bash
uv run examples/reducers/01_default_vs_reducer.py
uv run examples/reducers/02_operator_add.py
uv run examples/reducers/03_add_messages.py
```

## `01_default_vs_reducer.py` — overwrite vs custom function

Runs the same two-node graph twice: once with a plain `list[str]` field
(node `b`'s return value replaces node `a`'s entirely — only `"b ran"`
survives), once with `Annotated[list[str], append]` (both survive, merged).

## `02_operator_add.py` — `operator.add` as a ready-made reducer

`operator.add` is just the `+` operator as a function, so it works as a
reducer for both list concatenation and number addition — the common case
when writing your own merge function would just be `lambda a, b: a + b`.
Shown with three nodes fanned out in parallel from `START`, each
contributing one number to the same list.

## `03_add_messages.py` — the reducer behind chat graphs

`add_messages` (used internally by `MessagesState`, see
[`../tool_node/`](../tool_node/) and [`../tool_node_weather/`](../tool_node_weather/))
is smarter than plain append: a message with a *new* `id` gets appended, but
one reusing an *existing* `id` replaces that message in place — how a node
can correct/update an earlier message without duplicating the conversation.

## Quick comparison

| reducer | behavior |
|---|---|
| none (default) | overwrite — last node to write wins |
| custom function | whatever you define — e.g. `append` |
| `operator.add` | concatenate lists / sum numbers |
| `add_messages` | append by default, replace-in-place if `id` matches |
