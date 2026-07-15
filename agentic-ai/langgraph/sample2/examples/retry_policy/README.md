# `RetryPolicy`

Automatically re-run a node that raises, with exponential backoff, instead
of failing the whole graph on the first transient error. Attach it per-node:
`graph.add_node(name, fn, retry_policy=RetryPolicy(...))`.

```bash
uv run examples/retry_policy/01_retry_on_failure.py
```

## `01_retry_on_failure.py`

`flaky_api_call` raises `ValueError` on its first two calls, then succeeds.
With `RetryPolicy(max_attempts=5, retry_on=(ValueError,))` attached, the
node is simply called again (up to `max_attempts` times) each time it
raises, until it either succeeds or the attempts run out.

## The `retry_on` gotcha worth knowing

LangGraph's **default** `retry_on` deliberately does *not* retry
`ValueError`, `TypeError`, `KeyError`, and similar — it treats those as
"probably a real bug, retrying won't help" and only retries connection
errors and 5xx HTTP responses out of the box. That's why this example passes
`retry_on=(ValueError,)` explicitly — otherwise the simulated failure would
propagate on the very first attempt, same as with no `RetryPolicy` at all.

## Where this fits

Natural pairing with [`../tool_node_weather/`](../tool_node_weather/) — a
tool node that calls a real external API is exactly the kind of thing that
occasionally times out or 5xx's for reasons that have nothing to do with
your code, and is worth retrying automatically.
