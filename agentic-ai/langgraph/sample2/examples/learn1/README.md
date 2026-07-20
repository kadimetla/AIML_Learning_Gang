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
