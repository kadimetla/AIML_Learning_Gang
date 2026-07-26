# Sample 6 — Mini-GPT: training and generation

Everything from `sample-1` through `sample-5`, assembled into a small trainable decoder-only
transformer (the GPT architecture) and actually trained on text.

## Goal

- Stack `sample-5`'s `TransformerBlock` (with causal masking) into a full model: token embedding
  + positional encoding → N transformer blocks → output projection to vocabulary logits.
- Train it, character-by-character, on a small embedded public-domain text snippet — no dataset
  download required.
- Watch the loss curve drop.
- **Inference**: generate text autoregressively, one token at a time, comparing greedy decoding,
  temperature sampling, and top-k sampling — and explain what a KV cache speeds up.

## Run it

```bash
uv sync
uv run jupyter lab
```

Open `mini_gpt.ipynb`. Training runs on CPU in a couple of minutes given the tiny model size.
