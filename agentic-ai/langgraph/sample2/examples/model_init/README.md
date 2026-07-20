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

## Planned: `03_litellm_and_bedrock.py` (not yet built)

Two more provider strings `init_chat_model` already supports natively,
confirmed by reading `langchain/chat_models/base.py`'s provider map directly
(not assumed) -- neither needs new LangGraph code, only a different string
passed to the same `init_chat_model` call `01`/`02` already use:

- **`"bedrock:..."` / `"bedrock_converse:..."`** -- routes to
  `langchain_aws.ChatBedrockConverse`. Already installable today (`uv add
  langchain-aws`); would need real AWS credentials to run for real. This is
  the direct answer to "swap to a Bedrock model": with
  `configurable_fields=("model", "model_provider")` from `02`, a caller
  passes `{"model": "anthropic.claude-...", "model_provider":
  "bedrock_converse"}` in `config["configurable"]` at invoke time -- no code
  change, same mechanism `02` already demonstrates for OpenAI/Anthropic.
- **`"litellm:..."`** -- routes to `langchain_litellm.ChatLiteLLM`. Needs
  `uv add langchain-litellm` (not currently a dependency here). Worth
  building when there's an actual need for litellm's wider provider
  coverage or its proxy-level routing/fallback/cost-tracking -- otherwise
  the native provider strings above do the same provider-agnostic job with
  one fewer dependency.

When this gets built: same shape as `02`, just adding `"bedrock_converse"`
and `"litellm"` to the set of providers exercised at invoke time, plus a
docstring explaining each requires its own installed integration package
(`langchain-aws`, `langchain-litellm`) since `init_chat_model` only ships
the provider *map*, not the provider packages themselves.
