# Sample 3 — Scaled dot-product attention, by hand

The core mechanism of a transformer, traced on a tiny example small enough to check against
pen-and-paper arithmetic.

## Goal

On a 4-token sequence with `d_model = 4` (single head, plain NumPy):

- Compute `Q`, `K`, `V` via three weight matrices.
- Compute raw attention scores `QK^T`, scale by `1/sqrt(d_k)`, apply softmax.
- Compute the weighted sum of `V` to get the attention output.
- Every intermediate matrix is printed — verify a value or two by hand.
- Plot the resulting attention-weight matrix as a heatmap.

## Run it

```bash
uv sync
uv run jupyter lab
```

Open `attention_by_hand.ipynb`.
