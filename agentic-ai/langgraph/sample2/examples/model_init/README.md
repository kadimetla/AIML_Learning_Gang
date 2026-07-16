# `init_chat_model` — provider-agnostic model construction

Replaces a directory of hand-written per-provider wrapper functions (like
[`graph_websearch_agent`](https://github.com/kadimetla/graph_websearch_agent)'s
`models/` folder — six files, one per provider, each reimplementing "build a
chat model object") with one function whose first argument is a config
string.

**Needs `OPENAI_API_KEY` in `.env`** (copy `.env.example`) — construction
alone doesn't strictly require a *valid* key, but these examples make real
calls to actually prove routing works, not just construct-and-discard.

```bash
uv run examples/model_init/01_provider_agnostic_construction.py
uv run examples/model_init/02_runtime_configurable_model.py
```

## `01_provider_agnostic_construction.py`

Three equivalent ways to construct the same `ChatOpenAI` instance:
`"openai:gpt-4o-mini"`, `model="gpt-4o-mini", model_provider="openai"`, or
just `"gpt-4o-mini"` (provider inferred from the `gpt-` prefix — same for
`claude-*` → anthropic, `gemini-*` → google, etc.). Contrast this against
`graph_websearch_agent`'s `Agent.get_llm()`: a 6-branch `if/elif` over
server names, each branch importing a different hand-written class.

## `02_runtime_configurable_model.py`

`init_chat_model(configurable_fields=("model", "model_provider"))` returns a
model that isn't bound to any provider yet — the actual model is resolved
inside `invoke()` from `config["configurable"]`, exactly the same mechanism
[`../01_configurable.py`](../01_configurable.py) used for a plain string.
Here it picks *which model runs at all*, not just a value a node reads.
This is what `graph_websearch_agent` was trying to achieve by threading
`server`/`model` arguments through every `Agent` subclass's constructor —
collapsed into ordinary `invoke()` config.

## When to use which

| | use when |
|---|---|
| `init_chat_model("openai:gpt-4o-mini")` | the model is fixed for this node/graph |
| `init_chat_model(configurable_fields=...)` | callers need to pick the model per-request (e.g. a "fast" vs "smart" mode, or a user-selectable model in a UI) |
