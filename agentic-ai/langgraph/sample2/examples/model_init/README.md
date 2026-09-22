# `init_chat_model` — provider-agnostic model construction

Replaces a directory of hand-written per-provider wrapper functions (like
[`graph_websearch_agent`](https://github.com/kadimetla/graph_websearch_agent)'s
`models/` folder — six files, one per provider, each reimplementing "build a
chat model object") with one function whose first argument is a config
string.

**Needs `OPENAI_API_KEY` in `.env`** (copy `.env.example`) — construction
alone doesn't strictly require a *valid* key, but these examples make real
calls to actually prove routing works, not just construct-and-discard.
`03` additionally needs `langchain-litellm`/`langchain-aws` (already added
to this project's dependencies) — see its section below for what is and
isn't verified for real without AWS credentials.

```bash
uv run examples/model_init/01_provider_agnostic_construction.py
uv run examples/model_init/02_runtime_configurable_model.py
uv run examples/model_init/03_litellm_and_bedrock.py
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

## `03_litellm_and_bedrock.py`

Two more provider strings from `init_chat_model`'s same provider map --
`"litellm:..."` (-> `langchain_litellm.ChatLiteLLM`) and
`"bedrock_converse:..."` (-> `langchain_aws.ChatBedrockConverse`). No new
LangGraph mechanism, just two more strings for the same `init_chat_model`
call `01`/`02` already use.

**What's actually verified vs. not**, and why -- this repo's environment has
`OPENAI_API_KEY` but no AWS credentials (no `AWS_ACCESS_KEY_ID`, no AWS CLI
configured):

- **litellm**: verified with a real call. `"litellm:gpt-4o-mini"` routes
  straight to OpenAI under the hood using the existing key -- no new
  credentials needed to prove this works.
- **Bedrock**: construction succeeds without any AWS credentials (boto3
  builds its client lazily), but the actual `.invoke()` call fails with
  `NoCredentialsError: Unable to locate credentials` -- confirmed by
  running it, not assumed. That failure is left in the script on purpose:
  it shows exactly what's missing (AWS credentials) rather than silently
  skipping the call.
- **The `configurable_fields` swap** -- the direct answer to "swap to a
  Bedrock model at runtime": one model object,
  `configurable_fields=("model", "model_provider", "region_name")` (the
  same mechanism `02` uses, with `region_name` added since Bedrock needs
  it and OpenAI/litellm simply ignore it), routes to openai, litellm, or
  bedrock_converse purely from `config["configurable"]` at invoke time --
  same code, three different providers. The openai and litellm branches
  return real answers; the bedrock_converse branch hits the same
  `NoCredentialsError` as above.

Add real AWS credentials to `.env` and the Bedrock calls in this file would
work exactly as written -- nothing about the code changes, only whether
credentials are present.
