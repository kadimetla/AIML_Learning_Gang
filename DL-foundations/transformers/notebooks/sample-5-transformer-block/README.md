# Sample 5 — A full transformer block

Wraps `sample-4`'s multi-head attention in the rest of a transformer encoder block, built as
plain PyTorch `nn.Module` classes (not `nn.TransformerEncoderLayer`) so every piece is visible.

## Goal

- Implement multi-head attention as a batched `nn.Module` (generalizing `sample-4` to arbitrary
  batch size, using `nn.Linear` for the projections).
- Add the position-wise feed-forward network.
- Wire up residual connections and layer normalization around each sub-layer
  (`x = LayerNorm(x + Sublayer(x))`).
- Run a forward pass on a toy batch and check every shape along the way.

## Run it

```bash
uv sync
uv run jupyter lab
```

Open `transformer_block.ipynb`.
