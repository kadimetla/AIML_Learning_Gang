# `invoke()` / `stream()` config reference

`app.invoke(input, config={...})` (and `.stream()`) take a `RunnableConfig`
dict as their second argument, plus a few keyword-only args of their own
(`output_keys`, `interrupt_before`, ...). This covers what each one does,
backed by a runnable example.

Run any file directly, e.g.:

```bash
uv run examples/01_configurable.py
```

## `config={"configurable": {...}}` — your own runtime values

A free-form dict for passing per-call parameters into a node. A node reads it
by declaring `config: RunnableConfig` as a second parameter.

```python
def greet(state, config: RunnableConfig):
    title = config["configurable"].get("title", "")
    return {"greeting": f"Hello, {title}{state['name']}!"}

app.invoke({"name": "sample2"}, config={"configurable": {"title": "Dr. "}})
```

File: `01_configurable.py`

## `config={"callbacks": [...]}` — lifecycle hooks

Attach a `BaseCallbackHandler` to get notified on `on_chain_start` /
`on_chain_end` (and `on_llm_*`, `on_tool_*`, ...) for every node run. This is
the mechanism tracing tools (LangSmith, OpenTelemetry instrumentors) build on
— a real tracer opens/closes a span in these methods instead of printing.

File: `02_callbacks.py`

## `config={"tags": [...], "metadata": {...}}` — labels on a run

Carry no behavior themselves — they just ride along on every run/span so an
observability backend can filter or group by them (e.g. `user_id`, `lesson`).
LangGraph also injects its own tags/metadata automatically
(`langgraph_node`, `langgraph_step`, ...), visible to any attached callback.

File: `03_tags_metadata.py`

## `config={"run_name": ..., "run_id": ...}` — name/identify a run

`run_name` overrides the default trace name. `run_id` lets you pin a specific
UUID to a run instead of letting LangChain generate one — useful when you
need to correlate a run with something external (a ticket id, a request id).

File: `04_run_name_run_id.py`

## `config={"recursion_limit": N}` — cap node executions

Caps how many super-steps a graph can take before raising
`GraphRecursionError`. Only matters once a graph has a cycle (a conditional
edge that can route back to an earlier node). Default is 25.

File: `05_recursion_limit.py`

## `config={"max_concurrency": N}` — throttle parallel branches

When a graph fans out (multiple nodes reachable from `START`, or from a
conditional edge), this caps how many run at once. `06_max_concurrency.py`
times an unbounded run against `max_concurrency=1` to make the throttling
visible (~0.5s vs ~2.0s for 4 branches with a 0.5s sleep each).

File: `06_max_concurrency.py`

## `interrupt_before=[...]` (compile-time) + `thread_id` — pause for review

Pass `interrupt_before=["node_name"]` to `graph.compile(...)`, along with a
`checkpointer` (e.g. `InMemorySaver()`), and the graph will pause right
before that node runs. Resume later by calling `invoke(None, config=...)`
with the same `thread_id` — `None` input means "continue from the
checkpoint" rather than "start a new run". This is the basis for
human-in-the-loop approval steps.

File: `07_interrupt_before.py`

## `output_keys=...` (invoke/stream keyword) — trim the returned state

Restricts what `invoke()`/`stream()` returns to only the state keys you name,
instead of the full state dict. Pass a single key (returns just that value)
or a list (returns a dict with just those keys).

File: `08_output_keys.py`

## Quick comparison

| config key | where | effect |
|---|---|---|
| `configurable` | `config={...}` | your own per-call values, read via `config: RunnableConfig` param |
| `callbacks` | `config={...}` | lifecycle hooks — basis for tracing/OTel |
| `tags` / `metadata` | `config={...}` | labels for filtering runs in observability tools |
| `run_name` / `run_id` | `config={...}` | name/pin a specific run |
| `recursion_limit` | `config={...}` | cap on node executions, matters for cyclic graphs |
| `max_concurrency` | `config={...}` | cap on parallel fan-out branches |
| `interrupt_before` | `graph.compile(...)` | pause before a node, needs a checkpointer + `thread_id` |
| `output_keys` | `invoke()`/`stream()` kwarg | trim the returned state to selected keys |

See also [`STREAM_MODES.md`](./STREAM_MODES.md) for `stream_mode` (`values`,
`updates`, `debug`, `messages`, `custom`), which is the other keyword-only
argument `invoke()`/`stream()` accept.
