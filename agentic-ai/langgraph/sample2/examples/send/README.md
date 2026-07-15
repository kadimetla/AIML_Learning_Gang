# `Send` — dynamic map-reduce fan-out

A normal conditional edge routes to a fixed, known set of next nodes. `Send`
is different: a routing function can return a *list* of `Send("node", arg)`
objects, one per item in something whose length you only know at runtime —
launching that many parallel invocations of the same node, each with its
own input. Combine with a [reducer](../reducers/) on the results field to
merge everything back together (the "reduce" step).

```bash
uv run examples/send/01_map_reduce.py
```

## `01_map_reduce.py`

`dispatch(state)` returns one `Send("summarize", {"topic": t})` per topic in
`state["topics"]` — however many there are. Each becomes its own run of
`summarize`, in parallel, receiving only `{"topic": t}` as input (shaped
like `WorkerState`, not the full `OverallState`). Their `{"summaries": [...]}`
returns are merged via `operator.add` on `OverallState.summaries`
(see [`../reducers/02_operator_add.py`](../reducers/02_operator_add.py)).

## When to reach for this

Any "do the same thing to each item in a list, where the list length isn't
fixed in the graph definition" — e.g. summarizing N documents, fanning out
one sub-question per retrieved chunk, or running a check against each item
in a variable-length batch.
