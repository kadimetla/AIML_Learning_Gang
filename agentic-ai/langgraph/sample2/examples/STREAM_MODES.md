# `stream_mode` reference

`app.stream(input, stream_mode=...)` controls what shape each chunk takes as a
LangGraph run progresses. `app.invoke(...)` accepts the same argument, but
just collects every chunk instead of yielding them one at a time (see the
bottom of `09_stream_mode.py`).

Run any file directly, e.g.:

```bash
uv run examples/09_stream_mode.py
```

## `"values"` — full state snapshot after each node

Yields the entire state dict, as it stands right after each super-step. Best
default when you just want to watch state evolve.

```python
for chunk in app.stream(inputs, stream_mode="values"):
    print(chunk)
# {'name': 'sample2'}
# {'name': 'sample2', 'greeting': 'Hello, sample2!'}
# {'name': 'sample2', 'greeting': 'HELLO, SAMPLE2!'}
```

File: `09_stream_mode.py` (also in `main.py`)

## `"updates"` — only what each node returned

Yields `{node_name: node_return_value}` for whichever node just ran, instead
of the whole state. Cheaper to read when you only care what changed.

```python
for chunk in app.stream(inputs, stream_mode="updates"):
    print(chunk)
# {'greet': {'greeting': 'Hello, sample2!'}}
# {'shout': {'greeting': 'HELLO, SAMPLE2!'}}
```

File: `09_stream_mode.py` (also in `main.py`)

## `"debug"` — internal step-by-step trace

Yields LangGraph's own internal execution events (`task`, `task_result`, ...).
Useful for understanding/debugging execution order, not for application logic.

File: `09_stream_mode.py`

## `"messages"` — LLM tokens as they're generated

Yields `(message_chunk, metadata)` tuples, one per token, from any chat model
invoked inside a node — even if that node calls the model's `.invoke()` rather
than `.stream()`. This is what powers token-by-token UI streaming for chat
apps built on LangGraph.

```python
for message_chunk, metadata in app.stream(inputs, stream_mode="messages"):
    print(message_chunk.content, metadata["langgraph_node"])
```

File: `10_stream_mode_messages.py` — uses `GenericFakeChatModel` so it runs
with no API key.

## `"custom"` — your own arbitrary progress events

Yields whatever a node pushes via `get_stream_writer()`, completely
independent of state — e.g. a percent-complete update partway through a long
step. Nothing is yielded unless a node explicitly calls the writer.

```python
from langgraph.config import get_stream_writer

def my_node(state):
    writer = get_stream_writer()
    writer({"progress": "halfway"})
    ...
```

File: `11_stream_mode_custom.py`

## Multiple modes at once

Pass a list instead of a single string, and each yielded item becomes a
`(mode, chunk)` tuple instead of a bare chunk:

```python
for mode, chunk in app.stream(inputs, stream_mode=["values", "updates"]):
    print(mode, chunk)
```

Shown in `09_stream_mode.py` (`values` + `updates`) and
`11_stream_mode_custom.py` (`custom` + `updates`).

## Quick comparison

| mode | yields | needs |
|---|---|---|
| `values` | full state after each node | nothing extra |
| `updates` | `{node: return_value}` per node | nothing extra |
| `debug` | internal execution trace | nothing extra |
| `messages` | `(token_chunk, metadata)` per LLM token | a chat model called inside a node |
| `custom` | whatever you pass to the writer | a node calling `get_stream_writer()` |
