# dl-basics — Neural Networks From Scratch

Nine notebooks that build a neural network from nothing but numpy, one
concept at a time. Loosely follows the structure of
["Neural Networks from Scratch - First Principles of AI"](https://www.youtube.com/watch?v=vJxK8qWDcdA)
(Ai Guru): neurons → weights/activations → forward pass → loss →
backpropagation → training.

A single running problem threads through every chapter: **can a neuron learn
logic gates?** OR is linearly separable, so a single neuron solves it by
Chapter 6. XOR is not — proving that failure, live, is the whole motivation
for the hidden layer built in Chapter 7.

## Chapters

| # | Notebook | Building block |
|---|---|---|
| 1 | [`01_the_neuron.ipynb`](01_the_neuron.ipynb) | weighted sum + bias + activation |
| 2 | [`02_activation_functions.ipynb`](02_activation_functions.ipynb) | sigmoid, tanh, ReLU, softmax — and why nonlinearity is required |
| 3 | [`03_layers_and_forward_pass.ipynb`](03_layers_and_forward_pass.ipynb) | neurons as one matrix multiply, layers chained |
| 4 | [`04_loss_functions.ipynb`](04_loss_functions.ipynb) | MSE, binary cross-entropy, the loss landscape |
| 5 | [`05_backpropagation.ipynb`](05_backpropagation.ipynb) | the chain rule, verified against numerical gradients |
| 6 | [`06_gradient_descent_training_loop.ipynb`](06_gradient_descent_training_loop.ipynb) | the update rule; a single neuron solves OR, fails XOR |
| 7 | [`07_building_the_full_network.ipynb`](07_building_the_full_network.ipynb) | a reusable `NeuralNetwork` class that solves XOR and two-moons |
| 8 | [`08_backpropagation_deep_dive.ipynb`](08_backpropagation_deep_dive.ipynb) | a from-scratch autodiff engine, backprop through 3 layers, gradient flow |
| 9 | [`09_batch_vs_online_learning.ipynb`](09_batch_vs_online_learning.ipynb) | batch vs. mini-batch vs. online training, and why this series used batch |

Each notebook is self-contained but assumes the previous chapters' vocabulary
— read them in order the first time through.

## Running

```bash
uv run jupyter lab
```

then open any chapter. Every notebook is pure numpy + matplotlib — no
frameworks, no GPU, no dataset downloads.

## Related material in this repo

- `../Backpropagation_Deep_Dive.html`, `../Linear_to_Nonlinear_ReLU.html`,
  `../neuron_weight_explorer.html`, `../hidden_neurons_learn_pattern.html` —
  interactive HTML explainers for the same concepts
- `notebooks/about-weights/symmetry_breaking_random_weights/` — a deep dive on
  the initialization-sensitivity surfaced in Chapter 7's aside
- `../Transformer_Backpropagation.html`, `../Tokenization_Embeddings_Attention.html` —
  where these building blocks lead next (attention, transformers)
