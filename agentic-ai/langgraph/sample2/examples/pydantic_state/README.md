# Pydantic-based graph state

A `StateGraph` can use a `pydantic.BaseModel` instead of a `TypedDict`. The
difference isn't cosmetic: pydantic actually validates every `invoke()` call
at runtime, where `TypedDict` never does (see [`../not_required/`](../not_required/)).

```bash
uv run examples/pydantic_state/01_pydantic_validation.py
uv run examples/pydantic_state/02_custom_validators.py
```

## `01_pydantic_validation.py` — built-in field constraints

`GraphState(BaseModel)` uses `Field(min_length=1)` and `Field(ge=0, le=150)`.
Calling `invoke()` with a missing field, an empty string, or a negative age
all raise a real `pydantic.ValidationError` before any node runs — contrast
this with `TypedDict`, where `invoke({})` runs the graph and only fails once
a node reads the missing key. Also shows that an unknown extra key is still
silently dropped by default, same as `TypedDict`.

## `02_custom_validators.py` — `@field_validator`

`Field(...)` constraints only cover simple ranges/lengths. A
`@field_validator` runs arbitrary code, so you can enforce rules the type
system can't express (here: "must contain an `@`"), and even normalize the
value (`.lower()`). Note the value returned by the validator is what the
*node* sees (`state.email` is already lowercased inside `greet`) — but the
raw input value is still what comes back in the top-level state dict, since
LangGraph stores channel values as-is and only overwrites what a node
actually returns.

## When to reach for this

Use `TypedDict` (the default in the rest of `examples/`) for internal graph
state where you trust your own nodes. Reach for a pydantic model at a graph's
actual input boundary — e.g. validating a request body before it enters the
graph at all.
