# `NotRequired` / `Required`

Per-field overrides to a `TypedDict`'s `total=True`/`total=False` setting
(PEP 655). Purely a static type-checker hint — zero runtime effect, same as
`total` itself.

```bash
uv run examples/not_required/01_optional_state_field.py
uv run examples/not_required/02_required_override.py
```

## `01_optional_state_field.py` — `NotRequired[str]`

`GraphState` is `total=True` (the default), so every field is required by
default — except `greeting`, marked `NotRequired[str]` since it genuinely
doesn't exist until the `greet` node produces it. A type checker accepts
`invoke({"name": "sample2"})` with `greeting` absent.

## `02_required_override.py` — `Required[str]`

The inverse: `ApiRequestConfig` is `total=False` (everything optional by
default), except `user_id`, marked `Required[str]` since it can never be
missing. A type checker flags a call that omits it.

## The point either way

Both files also call the "wrong" case at runtime — a missing field a node
actually reads — and it's still just a plain `KeyError`, not caught by
`NotRequired`/`Required`/`total` in any way. These are annotations for
`mypy`/`pyright`, not runtime guarantees. If you want real runtime
validation, see [`../pydantic_state/`](../pydantic_state/).
