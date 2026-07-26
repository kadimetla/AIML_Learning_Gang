# Transformers — from hand-traced math to real inference

Hands-on companion to the theory decks in `DL-foundations/`:
[`Tokenization_Embeddings_Attention.html`](../Tokenization_Embeddings_Attention.html) and
[`Transformer_Backpropagation.html`](../Transformer_Backpropagation.html).

Each `notebooks/sample-N-*/` is a self-contained [uv](https://docs.astral.sh/uv/) project with one
notebook. Work through them in order — each one builds on the last.

## Learning path

| # | Sample | What it covers | Tooling |
|---|---|---|---|
| 1 | [`sample-1-tokenization`](notebooks/sample-1-tokenization) | Build a tokenizer by hand: vocabulary, encode/decode | stdlib only |
| 2 | [`sample-2-embeddings`](notebooks/sample-2-embeddings) | Token → embedding vector, sinusoidal positional encoding | NumPy |
| 3 | [`sample-3-attention-by-hand`](notebooks/sample-3-attention-by-hand) | Scaled dot-product attention, every intermediate matrix printed | NumPy |
| 4 | [`sample-4-multi-head-attention`](notebooks/sample-4-multi-head-attention) | Splitting attention into multiple heads | NumPy → PyTorch |
| 5 | [`sample-5-transformer-block`](notebooks/sample-5-transformer-block) | Full encoder block: attention + residual + LayerNorm + feed-forward | PyTorch |
| 6 | [`sample-6-mini-gpt-train-and-generate`](notebooks/sample-6-mini-gpt-train-and-generate) | Decoder-only mini-GPT: causal masking, training loop, autoregressive generation | PyTorch |
| 7 | [`sample-7-pretrained-inference-huggingface`](notebooks/sample-7-pretrained-inference-huggingface) | Deep dive: load real GPT-2 weights, inspect tokenizer/attention, generation strategies | 🤗 `transformers` |

## Progression

Samples 1–3 are **hand-traceable**: dimensions are kept tiny (3–4 tokens, `d_model` of 4–8) and
every intermediate array is printed, so you can check the notebook's output against your own
pen-and-paper calculation. Samples 4–6 move to PyTorch and build up a real, trainable transformer.
Sample 7 steps outside the from-scratch code entirely to show how the same concepts look through a
production library, on a real pretrained model.

## Running a sample

```bash
cd notebooks/sample-1-tokenization
uv sync
uv run jupyter lab
```
