# Sample 1 — Tokenization by hand

The first step of any transformer pipeline: turning text into a sequence of integers.

## Goal

Build a tokenizer from scratch, using nothing but the Python standard library, so the
mechanics are fully visible:

- Split a tiny corpus into words, build a vocabulary
- Map tokens ↔ integer ids
- Encode a sentence to ids and decode it back
- Compare a word-level vocabulary to a character-level one
- See why real tokenizers (GPT-2, etc.) use subword schemes like BPE instead — picked up
  in `sample-7-pretrained-inference-huggingface`

## Run it

```bash
uv sync
uv run jupyter lab
```

Open `tokenization_by_hand.ipynb`.
