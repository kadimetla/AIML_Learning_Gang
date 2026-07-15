# Subgraphs

A compiled `StateGraph` is just a `Runnable` — it takes a state dict in and
returns a state dict out — so it can be used directly as a node in another
graph. Useful for building independently testable, reusable pieces instead
of one flat graph with every node crammed into it.

```bash
uv run examples/subgraphs/01_compiled_graph_as_node.py
```

## `01_compiled_graph_as_node.py`

`child_app` (a small "uppercase the text" graph) is compiled completely on
its own and works standalone. `parent_graph.add_node("shout", child_app)`
then drops that entire compiled graph in as a single step between `greet`
and `measure` — the parent graph has no idea `"shout"` is actually a
2-node graph underneath.

The two graphs share the key name `"text"` in their state schemas, which is
what lets the child graph read the parent's state and write back into it.
