# `state_schema` / `input_schema` / `output_schema` / `context_schema`

Four separate schemas passed to `StateGraph(...)`, each controlling a
different boundary:

| Schema | Controls | In `learn_1.py` |
|---|---|---|
| `state_schema` | every channel a node can read/write during execution | `State`: `question`, `answer`, `internal_score` |
| `input_schema` | what `graph.invoke(...)`'s first argument is allowed to contain | `InputState`: `question` only |
| `output_schema` | what `graph.invoke(...)` returns | `OutputState`: `answer` only |
| `context_schema` | per-run values available via `Runtime[Context].context`, not persisted as graph state | `Context`: `user_name` |

```bash
uv run examples/learn1/learn_1.py
```

`answer_node` writes both `answer` and `internal_score` into state, and
reads `user_name` from `runtime.context` (not from `state` -- context is
injected per-invocation, not carried in the graph's channels). The printed
result is `{'answer': 'Ada asked: What is state?'}` -- `internal_score`
existed during execution but never appears, because it isn't in
`OutputState`.

## `Runtime[Context]` vs `config["configurable"]` -- two different mechanisms

Easy to conflate since both "pass a value in at invoke time without putting
it in graph state," but they're separate systems with separate rules:

| | `config={"configurable": {...}}` | `context={...}` + `Runtime[Context]` |
|---|---|---|
| Where it's from | LangChain-wide `RunnableConfig` (predates LangGraph, works on any `Runnable`) | LangGraph 1.0+, LangGraph-specific |
| Typed? | No -- plain untyped dict, read with `.get()` | Yes -- validated against `context_schema` (a `TypedDict`/dataclass/pydantic model) |
| How a node reads it | extra `config: RunnableConfig` param, then `config["configurable"]["key"]` | extra `runtime: Runtime[ContextType]` param, then `runtime.context["key"]` (or `.key` for dataclasses) |
| Required for | `thread_id` (checkpointer routing -- **must** go through `configurable`, no alternative), `recursion_limit`, callbacks/tags/metadata, and anything read by a generic `Runnable` deep in a chain -- which is why `init_chat_model(configurable_fields=...)` (see [`../model_init/`](../model_init/)) uses this, not `Runtime` -- it has to work through arbitrary `Runnable` composition, not just LangGraph nodes | request-scoped values specific to *this* LangGraph run: who's calling, which tenant, feature flags, an injected client/credentials object |
| Example in this repo | [`../01_configurable.py`](../01_configurable.py), [`../model_init/02_runtime_configurable_model.py`](../model_init/02_runtime_configurable_model.py) | `learn_1.py` (this file) |

**So `configurable_fields` swapping to a Bedrock model is `config["configurable"]`, not `Runtime[Context]`** -- it has to be, since `init_chat_model` needs to work as a plain LangChain `Runnable` outside of any LangGraph node too, and `Runtime` doesn't exist outside a compiled graph's execution.

**Who/when to reach for `Runtime[Context]` specifically**: node functions (and, in `create_agent`, tools/middleware) that need a per-invocation value that (a) shouldn't be persisted in a checkpoint alongside graph state -- credentials, a request-scoped client -- and (b) you want type-checked rather than a loose dict. If you're passing `thread_id` or wiring `configurable_fields` into `init_chat_model`, that's `config["configurable"]` by requirement, not a choice.

## Why this matters for `create_agent`

This is exactly the mechanism `langchain.agents.create_agent` uses
internally, just with schemas LangChain defines for you instead of ones you
write:

- its `state_schema` carries `messages` plus internal fields like
  `structured_response`
- its effective `input_schema` is `{"messages": [...]}`
- its `output_schema` is `{"messages": [...], "structured_response": ...}`
- its `context_schema` is whatever you pass via `context_schema=` to
  `create_agent`, threaded to tools/middleware through `Runtime`

Confirmed directly: `agent.get_input_jsonschema()` and
`agent.get_output_jsonschema()` on a `create_agent(...)` result show exactly
`messages` in, `messages` + `structured_response` out -- see
[`../create_agent_samples/`](../create_agent_samples/), which composes
`create_agent`'s pre-built schemas into bigger hand-written `StateGraph`s the
way `learn_1.py` builds one from scratch.
