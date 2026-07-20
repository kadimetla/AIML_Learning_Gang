# Composing `create_agent` into a bigger LangGraph workflow

[`../react_agent/`](../react_agent/) shows `create_agent` on its own. These
three scripts answer the next question: once you have an agent, how does it
fit *inside* a larger `StateGraph`? `create_agent` returns an ordinary
`CompiledStateGraph`, so there are exactly two ways to compose it, and both
are idiomatic LangGraph -- not a workaround.

```bash
uv run examples/create_agent_samples/sample1.py
uv run examples/create_agent_samples/sample2.py
uv run examples/create_agent_samples/sample3.py
```

All three need `OPENAI_API_KEY` in `.env` (see `../../.env.example`) and were
run for real to verify -- see "Bugs found while verifying" below, since the
original versions of these files didn't actually run clean.

| Script | Pattern | Outer state shape |
|---|---|---|
| [`sample1.py`](sample1.py) | agent **as a subgraph node**: `builder.add_node("agent", agent)` | must be compatible with the agent's own state (`messages`, plus whatever `add_messages` needs) |
| [`sample2.py`](sample2.py) | agent **called inside a plain node**: `agent.invoke(...)` from within a Python function | anything -- the node function translates between outer state and `{"messages": [...]}` |
| [`sample3.py`](sample3.py) | two agents (`writer`, `reviewer`) chained the sample2 way, each a step in a deterministic pipeline | anything |

## Which one to use

- **Outer workflow state genuinely *is* a message list** (a chatbot with a
  bit of extra graph structure around it) -- `sample1`'s subgraph-node
  pattern is less code and lets LangGraph handle the message-passing.
- **Outer workflow state has other shape** (`question`/`answer`,
  `topic`/`draft`/`review`, a research pipeline's typed fields, ...) --
  `sample2`/`sample3`'s pattern, calling `.invoke()` inside an ordinary node
  function, is the only option. This is also what
  [`../capstone_websearch_agent/`](../capstone_websearch_agent/) would need
  if any of its nodes were swapped for a `create_agent` call, since its
  state (`ResearchState`) is nothing like `{"messages": [...]}`.

Both are equally "correct" -- pick based on whether your outer state already
looks like a chat transcript.

## Verified gotcha: subgraph nesting loses fine-grained `interrupt_before`

[`../react_agent/02_create_agent_with_graph_features.py`](../react_agent/02_create_agent_with_graph_features.py)
pauses a top-level `create_agent` before its `"tools"` node with
`interrupt_before=["tools"]`. Nesting the same agent as a subgraph node (like
`sample1.py`) does **not** preserve that granularity. Tested directly:
`interrupt_before=["tools"]`, `["agent:tools"]`, and `["agent.tools"]` on the
*outer* graph all raise `ValueError: Interrupt node '...' not found` --
`sample1`'s outer graph only knows about a node called `"agent"`, full stop.
The only interrupt point available from outside is the whole subgraph:

```python
workflow = builder.compile(checkpointer=InMemorySaver(), interrupt_before=["agent"])
# pauses before ANY subgraph work runs -- including before the model even
# decides whether to call a tool, not specifically before the tool call
```

So: if you need approval gated on a specific *tool call* rather than the
whole agent turn, use `sample2`'s pattern (call `.invoke()` inside a node)
and put `interrupt_before`/`interrupt()` on your own explicit tool-calling
loop instead of nesting a whole `create_agent` -- or accept the coarser
"pause before this agent runs at all" granularity `sample1` gives you for
free.

## Bugs found while verifying

None of these are LangGraph misuse -- they're plain bugs, caught by actually
running the scripts instead of just reading them:

- `sample1.py`'s `get_weather` had no docstring. `create_agent` converts
  plain functions to tools via `StructuredTool.from_function`, which
  **requires** a docstring when no `description=` is given -- this crashed
  with `ValueError: Function must have a docstring` before a single API call
  was made. Fixed by adding one line.
- None of the three files called `load_dotenv()`, so `OPENAI_API_KEY` from
  `.env` was never actually loaded -- they'd only work by accident, in a
  shell that already had the key exported. Every other example in this repo
  calls `load_dotenv()` first; added it here too.
- `sample2.py` and `sample3.py` compiled a workflow but never invoked it (no
  `if __name__ == "__main__":` block), so running them produced no output at
  all -- nothing to actually verify. `sample1.py` invoked but never printed
  the result. Added `__main__` blocks with prints to all three, matching the
  convention every other example folder in this repo follows.

`model="openai:gpt-5.5"` was the one thing that looked suspicious on read
(unfamiliar model string) but turned out fine -- confirmed with a real,
successful API call, not assumed.

## Related

- [`../react_agent/`](../react_agent/) -- `create_agent` standalone, plus the
  `checkpointer=`/`interrupt_before=`/`system_prompt=` knobs these samples
  build on.
- [`../learn1/`](../learn1/) -- `state_schema`/`input_schema`/`output_schema`/`context_schema`,
  the same schema-splitting mechanism `create_agent` uses internally
  (its `AgentState` is `state_schema`, `{"messages": [...]}` is roughly its
  `input_schema`).
- [`../hitl/`](../hitl/) -- `interrupt()` called inside a node/tool, the way
  to get fine-grained approval gates that nesting `create_agent` (per the
  gotcha above) can't give you from outside.
