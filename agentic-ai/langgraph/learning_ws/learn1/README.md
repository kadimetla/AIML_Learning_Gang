# learn1 — LangGraph node/edge samples

- `src/learn1/my_sample1/example1.py` — a minimal one-node `StateGraph`.
- `src/learn1/my_sample1/example2.py` — `controller -> service -> formatter`,
  with the `service` node calling a real external API (GitHub) and a
  conditional edge to an error branch on failure. Built with
  `StateGraph`/`add_node`/`add_conditional_edges`.
- `src/learn1/my_sample1/example3.py` — the *exact same* flow, same node
  functions (imported unchanged from `example2.py`), wired with plain
  Python instead of `StateGraph` — straight-line calls and an `if/else`.
  Run both and diff the output: they're identical. The point is that
  LangGraph isn't inventing new execution mechanics for a flow like this;
  it's naming a pattern (nodes, edges, state) and giving it a generic
  engine, in exchange for things plain Python doesn't give you for free —
  visualizing the graph, streaming intermediate steps, checkpointing state,
  swapping in parallel/cyclic edges without rewriting the wiring by hand.

The same `controller -> service -> formatter` flow is also built with
FastAPI (no LangGraph, a small hand-rolled node/edge engine instead) in
`../learn2/src/learn2/api_pipeline/app.py` — see `../learn2/README.md`.

## Run

```bash
uv run python -m learn1.my_sample1.example2   # LangGraph framework
uv run python -m learn1.my_sample1.example3   # plain Python, no framework
```
