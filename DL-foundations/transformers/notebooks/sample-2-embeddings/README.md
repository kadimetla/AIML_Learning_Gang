# Sample 2 — Embeddings, by hand

Continues from `sample-1-tokenization`'s token ids.

## Goal

- Build a tiny embedding lookup table (`d_model = 4`) by hand and look up vectors for token ids.
- Compute sinusoidal positional encoding from its formula, term by term.
- Add token embedding + positional encoding to get the vectors that attention will operate on.
- Plot the positional encoding to see the pattern it produces.

## Run it

```bash
uv sync
uv run jupyter lab
```

Open `embeddings_by_hand.ipynb`.
