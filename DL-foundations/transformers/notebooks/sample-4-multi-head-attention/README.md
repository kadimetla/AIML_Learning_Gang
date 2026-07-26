# Sample 4 — Multi-head attention

Extends `sample-3`'s single attention computation into several parallel ones.

## Goal

- See why one attention head is a bottleneck (it can only learn one notion of "relevant").
- Split `d_model` into multiple heads, run scaled dot-product attention independently per head
  (still NumPy, so the reshape/split/concat mechanics stay visible), and project the concatenated
  result back down.
- Re-implement the same computation in PyTorch (`nn.Module`, batched, real reshapes) and check
  it against the NumPy version — the bridge into `sample-5`.

## Run it

```bash
uv sync
uv run jupyter lab
```

Open `multi_head_attention.ipynb`.
