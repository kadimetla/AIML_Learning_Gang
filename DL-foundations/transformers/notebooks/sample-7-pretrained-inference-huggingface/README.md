# Sample 7 — Deep dive: real GPT-2 inference with 🤗 transformers

A capstone, separate from the from-scratch arc (`sample-1`–`sample-6`): instead of code we wrote,
this notebook loads **real pretrained weights** via the HuggingFace `transformers` library and
examines the same concepts — tokenizer, architecture, attention, generation — on the genuine
article.

## Goal

- Load GPT-2's real **BPE tokenizer** and compare it directly to the hand-built tokenizers from
  `sample-1` (vocabulary size, subword splitting, no OOV problem).
- Inspect the loaded model's real configuration (layers, heads, dimensions) against the mini-GPT
  built in `sample-6`.
- Run a forward pass and pull out **real attention weights**, visualized as a heatmap.
- Generate text with `.generate()` under greedy, temperature/top-k/top-p sampling, and beam
  search — and see how HuggingFace's implementation compares to `sample-6`'s hand-rolled one.

## Note

This notebook downloads pretrained model weights (`distilgpt2`, ~330MB) from the HuggingFace Hub
the first time it runs, and needs internet access.

## Run it

```bash
uv sync
uv run jupyter lab
```

Open `pretrained_inference.ipynb`.
