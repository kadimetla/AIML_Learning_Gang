# `with_structured_output`

Get schema-validated output directly from a model call, instead of
prompting "respond in this JSON format" and hand-parsing the response with
`json.loads()` — which is exactly what every LLM node in
[`graph_websearch_agent`](https://github.com/kadimetla/graph_websearch_agent)
(`planner`, `selector`, `router`, `reviewer`) does by hand.

**These examples need a real, tool-calling-capable model.**
`GenericFakeChatModel` (used everywhere else in this project) can't do this
— `with_structured_output`'s default implementation requires real
`.bind_tools()` support. Set `OPENAI_API_KEY` in `.env` (copy
`.env.example`) before running these.

```bash
uv run examples/structured_output/01_with_structured_output.py
uv run examples/structured_output/02_structured_router_node.py
```

## `01_with_structured_output.py`

```python
structured_model = model.with_structured_output(SearchPlan)
result = structured_model.invoke("plan a web search to answer: ...")
result.search_term  # a validated SearchPlan instance, not a dict you hope has the right keys
```

`schema` can be a Pydantic class (validated instance back), a `TypedDict`,
or a raw JSON schema dict (unvalidated dict back). Passing `include_raw=True`
returns `{"raw": AIMessage, "parsed": SearchPlan, "parsing_error": None}`
instead — useful when you want to inspect what the model actually said if
parsing fails.

## `02_structured_router_node.py`

Rebuilds `graph_websearch_agent`'s router-agent pattern properly: the
reviewer's feedback goes to a model with `with_structured_output(RouterDecision)`,
where `RouterDecision.next_agent` is a `Literal["planner", "selector",
"reporter", "final_report"]` — the schema itself guarantees the model can
only pick one of those four values. The result feeds straight into
`Command(goto=...)` (see [`../command/`](../command/)), replacing the
original repo's `pass_review()` function that manually
`json.loads()`'d the router's raw text inside a conditional edge.

## The core trade-off

| | prompt-engineered JSON + `json.loads` | `with_structured_output` |
|---|---|---|
| guarantee | none — model might not follow the format | schema-validated, or an error you can catch |
| code | prompt text spells out the JSON shape, plus manual parsing | schema is the prompt (via tool-calling), no parsing code |
| failure mode | garbled JSON silently breaks downstream code | `ValidationError` (or `parsing_error` with `include_raw=True`) |
