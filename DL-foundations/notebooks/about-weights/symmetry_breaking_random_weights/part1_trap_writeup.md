# Part 1 — The Zero-Init Trap, Explained

## The setup

The notebook builds the smallest network that can show the problem:

```
4 inputs  →  4 hidden neurons (sigmoid)  →  1 output
```

- **Observations**: 200 synthetic houses (`n_samples = 200`), each with 4 features
  (`GrLivArea`, `OverallQual`, `YearBuilt`, `TotalBsmtSF`). Part 1 itself only runs
  **one** of these 200 houses (`house_idx = 7`) through the network, so the "same
  observation in, every time" point is easy to see.
- **Learnable weights**: 25 total.

| Parameter | Shape | Count |
|---|---|---|
| `W1` (input → hidden) | 4 × 4 | 16 |
| `b1` (hidden bias) | 4 | 4 |
| `W2` (hidden → output) | 4 × 1 | 4 |
| `b2` (output bias) | 1 | 1 |
| **Total** | | **25** |

200 observations train 25 weights — plenty of data relative to parameters, which is why
Part 5's training actually converges to a sensible price later in the notebook.

## The observations, concretely

Each observation is one house: 4 feature values plus a target price. Here are the first
8 of the 200, raw and standardized (standardized is what actually feeds the network):

**Raw**

| # | GrLivArea | OverallQual | YearBuilt | TotalBsmtSF | SalePrice |
|---|---|---|---|---|---|
| 0 | 1748.4 | 2.0 | 1990.6 | 1103.9 | 171,597.6 |
| 1 | 1430.9 | 10.0 | 1990.7 | 638.3 | 253,541.5 |
| 2 | 1823.8 | 1.0 | 1974.7 | 1255.4 | 174,286.1 |
| 3 | 2261.5 | 8.0 | 1952.6 | 335.4 | 242,329.6 |
| 4 | 1382.9 | 1.0 | 1976.9 | 973.6 | 144,591.7 |
| 5 | 1382.9 | 9.0 | 1958.1 | 515.6 | 210,845.8 |
| 6 | 2289.6 | 6.0 | 1999.4 | 739.3 | 269,363.9 |
| **7** | **1883.7** | **7.0** | **1971.3** | **1019.0** | **261,297.9** |

Row 7 is `x_house`, the single observation Part 1 tracks through the network. All 200
rows share this shape — 4 features, 1 target — they only differ in value.

**Standardized** (mean 0, std 1 per column — this is what `x` actually is in the code)

| # | GrLivArea | OverallQual | YearBuilt | TotalBsmtSF |
|---|---|---|---|---|
| 0 | 0.580 | -1.188 | 0.703 | 0.284 |
| 1 | -0.108 | 1.474 | 0.707 | -0.881 |
| 2 | 0.743 | -1.520 | 0.044 | 0.664 |
| ... | ... | ... | ... | ... |
| **7** | **0.873** | **0.476** | **-0.096** | **0.072** |

## Why W1 is 4×4 and W2 is 4×1

Shape rule: a layer mapping *m* units → *n* units has weight matrix shape *m×n*.

**`W1` (4×4)** connects 4 inputs to 4 hidden neurons. Convention: **rows = input
features, columns = hidden neurons** — column *i* holds neuron *i*'s 4 preferences, one
per feature.

|  | Neuron 1 | Neuron 2 | Neuron 3 | Neuron 4 |
|---|---|---|---|---|
| GrLivArea | 0.783 | -0.033 | -0.278 | 0.941 |
| OverallQual | -0.724 | -1.099 | 0.220 | -0.251 |
| YearBuilt | -0.511 | 0.354 | 0.122 | -0.282 |
| TotalBsmtSF | -0.640 | 0.436 | 0.325 | -0.050 |

`z1 = x @ W1` → `(1×4) @ (4×4) = (1×4)`: one pre-activation number per neuron.
Neuron 4's column (`0.941, -0.251, -0.282, -0.050`) mostly cares about `GrLivArea`;
that's a different question than Neuron 1 asks — different column, different weights,
same 4 input numbers. (This is the Part 2 random-init matrix. In Part 1's trap, this
same 4×4 slot exists but every entry is 0 — still 4×4 in shape, just degenerate.)

**`W2` (4×1)** connects 4 hidden neurons to 1 output. Rows = hidden neurons, columns =
output units.

|  | Output (SalePrice) |
|---|---|
| Neuron 1 | 0.923 |
| Neuron 2 | -0.535 |
| Neuron 3 | -0.763 |
| Neuron 4 | -0.346 |

`out = h @ W2` → `(1×4) @ (4×1) = (1×1)`: one final number. Each entry is how much the
output trusts that neuron (sign and magnitude), matching the Part 4 discussion. Add a
second output (Part 6) and `W2` becomes 4×2 — same rows, one more column per output.

## The trap itself

"Zero feels safe" is the intuition Part 1 is built to break. Set every one of those 25
weights to 0 and push one house through:

```python
z1 = x @ W1_zero + b1_zero   # = [0, 0, 0, 0]  — every neuron sees weight 0 on every feature
h  = sigmoid(z1)             # = [0.5, 0.5, 0.5, 0.5]
out = h @ W2_zero + b2_zero  # = [0.]
```

**Why every neuron is identical**: each hidden neuron computes
`z1_i = x·W1[:,i] + b1[i]`. With `W1` and `b1` all zero, that dot product is 0
*regardless of what `x` is* — the house's actual feature values never even get a chance
to differentiate the neurons, because every neuron is multiplying them by the same
(zero) weight vector. `sigmoid(0) = 0.5` for all four, so the hidden layer produces four
copies of the number 0.5. A 4-neuron layer has degenerated into 1 neuron, copy-pasted 4
times.

## Why training can't fix it — the gradient, not just the forward pass

The tempting-but-wrong intuition is "sure, they're equal *now*, but gradient descent
will pull them apart once we start training." The notebook checks this directly by
hand-deriving backprop for the one house:

```python
error = out - y_true          # dL/d(out)
dW2   = np.outer(h, error)    # dL/dW2
dh    = error @ W2.T          # dL/dh
dz1   = dh * h * (1 - h)      # dL/dz1, via sigmoid'(z) = h(1-h)
dW1   = np.outer(x, dz1)      # dL/dW1
```

With `W2 = 0`, `dh = error @ W2.T = 0` — the error signal never reaches the hidden layer
at all in the first step. But even setting that aside, look at `dz1`: it depends on `dh`
scaled by `h*(1-h)`, and both are the *same value broadcast across all 4 neurons* because
`W2` (a single shared column feeding all neurons the same way) and `h` (identical across
neurons) make the per-neuron terms indistinguishable. The result: `dz1 = [0, 0, 0, 0]`
in this run — every neuron gets an identical gradient.

Identical gradient → identical weight update → still identical after the update. Repeat
that for as many epochs as you like: the four neurons move in lockstep forever. This
isn't slow learning, it's **zero degrees of freedom** — a structural dead end baked into
the starting point, not something more training time can escape.

## Part 2 — The fix, explained

The fix isn't "add randomness" for its own sake — it's "make sure no two neurons start
out computing the same function." Random numbers are just the cheapest way to guarantee
that. Same house (row 7), same 4×4 / 4×1 weight *shapes* as Part 1 — only the values
change, from all-zero to `randn(...) * 0.5`.

```python
W1 = np.random.randn(n_in, n_hidden) * 0.5   # still 4x4, now non-zero
b1 = np.zeros(n_hidden)
W2 = np.random.randn(n_hidden, n_out) * 0.5  # still 4x1, now non-zero
b2 = np.zeros(n_out)
```

**Forward pass, same house as before:**

| | Neuron 1 | Neuron 2 | Neuron 3 | Neuron 4 |
|---|---|---|---|---|
| `z1` (pre-activation) | 0.342 | -0.554 | -0.126 | 0.725 |
| `h` (activation) | 0.585 | 0.365 | 0.469 | 0.674 |

Compare to Part 1's `h = [0.5, 0.5, 0.5, 0.5]`. Same house, same input vector `x` — the
only thing that changed is `W1` went from zero to random, and that alone is enough to
split one number into four different ones. `out = -0.246` (target `y_true = 0.889`, so
this untrained network is still far off — that's expected, it hasn't trained yet).

**Backward pass — the part that actually matters:**

```
dz1 (gradient per neuron): [-0.2545, 0.1407, 0.2156, 0.0863]
```

Four *different* gradients. Contrast with Part 1's `dz1 = [0, 0, 0, 0]` — identical, so
every neuron updated identically. Here, `dW1` (the full 4×4 gradient matrix) is also
different column by column:

| | Neuron 1 | Neuron 2 | Neuron 3 | Neuron 4 |
|---|---|---|---|---|
| GrLivArea | -0.222 | 0.123 | 0.188 | 0.075 |
| OverallQual | -0.121 | 0.067 | 0.103 | 0.041 |
| YearBuilt | 0.024 | -0.014 | -0.021 | -0.008 |
| TotalBsmtSF | -0.018 | 0.010 | 0.016 | 0.006 |

Since each column of `dW1` is different, the SGD update `W1 -= lr * dW1` pushes each
neuron's weight column in a *different* direction. That's the actual mechanism of
symmetry breaking: it's not that random init makes the neurons different once — it's
that random init makes their *gradients* different on every subsequent step too, so
gradient descent has somewhere new to push each neuron on every epoch instead of
re-confirming the same stuck point.

**The moment worth sitting with**: the input (`x_house`) didn't change between Part 1
and Part 2. Only the weights did. Four neurons, four different weight columns, four
different ways of combining the same 4 numbers — that's what turns a dead 4-neuron layer
into a live one.

## Part 3 — What "different" actually means, explained

Part 2 showed *that* the 4 neurons produce different numbers. Part 3 answers *why*, in a
way that resolves the notebook's opening confusion: if all 4 neurons look at the exact
same house, how can they "learn different things" without contradicting each other?

The answer is in the shape of `W1` itself. Each **column** of `W1` is one neuron's
weight vector — 4 numbers, one per feature. A neuron doesn't receive a different house;
it applies a different *weighting* to the same 4 numbers. Different weighting ⇒
different dot product ⇒ different activation, even though `x` never changes.

**Made concrete, feature by feature, for house 7** — breaking `z1_j = Σ_i x_i · W1[i,j]`
into its 4 individual terms shows exactly how much each feature pushes each neuron:

| | Neuron 1 | Neuron 2 | Neuron 3 | Neuron 4 |
|---|---|---|---|---|
| GrLivArea (x=0.873) | 0.683 | -0.029 | -0.242 | 0.821 |
| OverallQual (x=0.476) | -0.344 | -0.523 | 0.105 | -0.119 |
| YearBuilt (x=-0.096) | 0.049 | -0.034 | -0.012 | 0.027 |
| TotalBsmtSF (x=0.072) | -0.046 | 0.031 | 0.023 | -0.004 |
| **sum = z1** | **0.342** | **-0.554** | **-0.126** | **0.725** |

Read down a column and you see one neuron's "reasoning" about the house; read across a
row and you see the same feature value multiplied by 4 different weights. That's the
whole resolution: it's one house (one row of numbers going in), refracted through 4
different weight columns.

It also shows each neuron isn't equally influenced by everything — one feature usually
dominates:

- Neuron 1 → driven mostly by `GrLivArea` (+0.683)
- Neuron 2 → driven mostly by `OverallQual` (-0.523)
- Neuron 3 → driven mostly by `GrLivArea`, but in the *opposite* direction (-0.242)
- Neuron 4 → driven mostly by `GrLivArea` too, but far more strongly (+0.821)

Note Neurons 1, 3, and 4 all key off `GrLivArea` right now — at random init that's just
coincidence, not specialization. Nothing has *learned* anything yet; the neurons are
only *capable* of specializing because they start with distinct weight columns. Part 5's
training is what actually pulls each neuron toward consistently tracking a particular
feature across all 200 houses, not just this one.

**The analogy the notebook uses**: 4 junior appraisers looking at the same listing. One
focuses on square footage, one on quality, one on age, one on basement space. They don't
disagree about which house they're looking at — they emphasize different *aspects* of
it. `W1`'s 4 columns are literally 4 different emphasis patterns over the same 4 facts.

## Part 4 — Reconciling 4 opinions into 1 price, explained

Part 3 showed how one house becomes 4 different neuron activations. Part 4 asks the
reverse question: how do those 4 different numbers become 1 number again, without just
throwing away the diversity Part 2 worked to create?

The answer is: the output layer does exactly the same kind of operation the hidden layer
did — a weighted combination — just one level up. Instead of weighting 4 *raw features*,
it weights 4 *neuron opinions*:

```
out = h @ W2 + b2  =  Σ_i (h_i · W2_i)  +  b2
```

**For house 7, with the same random `W2` (4×1) from Part 2:**

| | Neuron 1 | Neuron 2 | Neuron 3 | Neuron 4 |
|---|---|---|---|---|
| Activation `h` | 0.585 | 0.365 | 0.469 | 0.674 |
| Output weight `W2` | 0.923 | -0.535 | -0.763 | -0.346 |
| Contribution `h·W2` | **0.540** | **-0.195** | **-0.357** | **-0.233** |

`0.540 - 0.195 - 0.357 - 0.233 + b2(0) = -0.246`, which matches `out` from the raw
forward pass exactly. Nothing hidden — the final number is a literal sum of 4 signed
contributions.

**Reading the signs and magnitudes as "trust":**

- Neuron 1 gets `W2 = +0.923` — the largest-magnitude weight, and positive. Its opinion
  (`h=0.585`, moderately high) pulls the price prediction *up* the hardest.
- Neuron 2 and Neuron 3 get *negative* weights (`-0.535`, `-0.763`). Their opinions pull
  the prediction *down*, and Neuron 3's contribution (`-0.357`) ends up as the single
  largest push in either direction after Neuron 1's.
- Neuron 4 has the highest activation of all (`h=0.674`) but a small-magnitude weight
  (`-0.346`), so despite "having a strong opinion," the output layer has decided (at
  this random, untrained point) not to weight it heavily.

That's the resolution to the notebook's opening question: 4 neurons don't need to
*agree* to produce 1 coherent number — the output layer's job is precisely to arbitrate
disagreement, the same way a manager weighs 4 analysts' conflicting takes into one
decision. A neuron with a large negative `W2` isn't "wrong" or being ignored; it's being
actively counted *against* the total.

Worth noting: at this point in the notebook the weights are still random and untrained,
so `out = -0.246` (unstandardized, roughly $201k) is far from the true price ($261k) —
the *mechanism* of reconciliation is correct and already working, but the *values* being
reconciled are still noise. Part 5 is what makes the numbers being combined trustworthy,
not just combinable.

## Part 5 — Training, explained

Parts 1-4 all used the network at a single frozen point: either all-zero weights or one
fresh random draw. Part 5 asks what happens once you actually train — full batch
gradient descent on all 200 houses, 400 epochs, `lr=0.5`, using the exact same
`forward`/`backward` math from Part 1, just applied to the whole dataset each step
instead of one house.

**Loss drops fast, then levels off:**

| Epoch | MSE loss (standardized) |
|---|---|
| 0 | 1.857 |
| 10 | 0.893 |
| 50 | 0.092 |
| 100 | 0.083 |
| 399 | 0.075 |

Most of the improvement happens in the first ~50 epochs; after that it's fine-tuning.

**House 7's hidden activations, before vs. after training** — same house, same 4
neurons, weights reshaped by 400 epochs of gradient descent:

| | Neuron 1 | Neuron 2 | Neuron 3 | Neuron 4 |
|---|---|---|---|---|
| `h` before (Part 2, random) | 0.585 | 0.365 | 0.469 | 0.674 |
| `h` after (trained) | 0.295 | 0.425 | 0.757 | 0.612 |

And the prediction that matters: unstandardized, the trained network predicts
**$263,575** for house 7 against an actual price of **$261,298** — close, versus the
~$201k an untrained random network produced in Part 4.

**What actually moved — the trained `W1` and `W2`:**

| | Neuron 1 | Neuron 2 | Neuron 3 | Neuron 4 |
|---|---|---|---|---|
| GrLivArea | -0.504 | -0.230 | 0.563 | 0.574 |
| OverallQual | -0.831 | -0.237 | **1.166** | -0.001 |
| YearBuilt | -0.185 | 0.109 | 0.056 | -0.322 |
| TotalBsmtSF | -0.444 | **-1.069** | -0.184 | -0.426 |

| | Output weight `W2` |
|---|---|
| Neuron 1 | -2.415 |
| Neuron 2 | -0.789 |
| Neuron 3 | 1.541 |
| Neuron 4 | 0.014 |

Compare to the random-init `W1`/`W2` from Part 2/4: the columns aren't just "still
different," they've grown some large, decisive entries (`OverallQual → Neuron 3 =
1.166`, `TotalBsmtSF → Neuron 2 = -1.069`) while others shrank toward near-zero
(`OverallQual → Neuron 4 = -0.001`, `Neuron 4`'s output weight `= 0.014`). Training
didn't just nudge everything a little — it sharpened some connections and nearly
silenced others.

**Does each neuron end up tracking one particular feature?** Correlating each trained
neuron's activation against each raw feature, across all 200 houses (not just house 7):

| | GrLivArea | OverallQual | YearBuilt | TotalBsmtSF |
|---|---|---|---|---|
| Neuron 1 | -0.36 | **-0.75** | -0.28 | -0.36 |
| Neuron 2 | -0.13 | -0.13 | -0.01 | **-0.95** |
| Neuron 3 | 0.32 | **0.88** | 0.11 | -0.21 |
| Neuron 4 | **0.73** | -0.09 | -0.46 | -0.58 |

- Neuron 1 → mostly tracks `OverallQual` (-0.75)
- Neuron 2 → almost purely `TotalBsmtSF` (-0.95, the strongest single specialization)
- Neuron 3 → mostly `OverallQual` (0.88), but in the *opposite direction* from Neuron 1
- Neuron 4 → mostly `GrLivArea` (0.73)

This is the payoff the whole notebook has been building toward: **random init only
guarantees the neurons start different; training is what makes "different" become
"meaningfully different."** Nobody told Neuron 2 to become a basement-size detector —
it emerged because Neuron 2 started at a different random point than the other three,
and gradient descent pulled each neuron toward whichever feature most reduced its share
of the error. Note Neurons 1 and 3 both ended up keyed on `OverallQual`, just with
opposite sign — not a failure, just two different (and, per their `W2` weights of -2.415
and +1.541, oppositely-trusted) ways of using the same feature.

## Part 6 — Multiple outputs, explained

Part 5 ended with 4 trained specialists (`W1_t`) feeding 1 output. Part 6 asks: what if
we want to predict *two* things from the same house — `SalePrice` and a made-up
`DaysOnMarket` score? The notebook's point is that this costs nothing structurally: the
hidden layer doesn't change at all, you just add a second output column.

**Nothing about `W1` changes.** The same 4 trained specialists from Part 5 are reused
as-is — house 7's hidden activations are identical to Part 5's "after training" row:

```
h = [0.295, 0.425, 0.757, 0.612]   (Neurons 1-4, unchanged from Part 5)
```

**What changes is `W2`'s shape**: 4×1 becomes **4×2** — one extra column, one weight per
neuron per new output. Same shape rule as always (*m* units → *n* units ⇒ *m×n*), just
now *n* = 2:

| | Output 1 (SalePrice) | Output 2 (DaysOnMarket) |
|---|---|---|
| Neuron 1 | -0.023 | 0.122 |
| Neuron 2 | -0.121 | 0.176 |
| Neuron 3 | -0.626 | 0.722 |
| Neuron 4 | -0.041 | 0.559 |

(This particular `W2_multi` is freshly random and untrained — the notebook is
illustrating the *mechanism*, not training a real second task.)

**Each output is still just a weighted sum of the same 4 activations** — now there are
two sums instead of one:

| | Neuron 1 | Neuron 2 | Neuron 3 | Neuron 4 | **Sum (= output)** |
|---|---|---|---|---|---|
| Output 1 contribution | -0.007 | -0.051 | **-0.474** | -0.025 | **-0.557** |
| Output 2 contribution | 0.036 | 0.075 | **0.547** | 0.342 | **0.999** |

Notice Neuron 3 dominates *both* outputs here (largest-magnitude contribution to each),
but with different signs relative to its neighbors — Output 1's column and Output 2's
column are two independent votes over the identical set of 4 opinions, not two different
sets of neurons.

**Why this matters conceptually**: the network isn't duplicating its understanding of
the house to handle a second task — it's *reusing* it. Output 1 can lean on
Neuron 3 (the quality-tracking specialist from Part 5, correlation 0.88 with
`OverallQual`) heavily and negatively; Output 2 can lean on the very same Neuron 3
heavily and positively, plus draw more on Neuron 4 (the size-tracking specialist)
than Output 1 does. Two different aggregation strategies, one shared representation.

This is the general pattern behind real multi-output and multi-task networks: hidden
layers learn shared, reusable features; each task-specific output head just learns its
own weighting over that shared pool. Scaling to more outputs never requires more hidden
neurons — it only ever adds columns to the final weight matrix.

## The general principle (not just about zero)

The failure mode is symmetry, not specifically "zero." *Any* initialization where all
neurons in a layer start **identical** (all weights = 0.3, say, instead of 0) produces
the same trap: identical forward outputs, identical gradients, identical updates,
forever. Zero is just the most tempting-looking way to accidentally create that
symmetry. The fix in Part 2 — small random weights — works not because randomness is
special, but because it's the cheap, reliable way to guarantee no two neurons start out
computing the same function.

## One-line summary

> With identical (e.g. zero) initial weights, a layer of N neurons has the *forward
> pass* and the *backward pass* of a single neuron wearing an N-neuron costume. Width
> without asymmetry buys you nothing.

## Recap, explained

The notebook's closing recap is six bullets; each one maps directly onto a section
above:

- **Trap** (identical init → identical neurons → identical gradients → useless width)
  is Part 1, demonstrated with `h=[0.5,0.5,0.5,0.5]` and `dz1=[0,0,0,0]`.
- **Fix** (random init guarantees neurons start different) is Part 2, where the same
  house's `h` splits into `[0.585, 0.365, 0.469, 0.674]` for no reason other than `W1`
  going from zero to random.
- **The confusion, resolved** ("different things, same observation" means different
  *weightings*, not different *data*) is Part 3's feature-by-feature contribution
  breakdown.
- **Reconciliation** (output layer = weighted vote across opinions) is Part 4's
  `h·W2` contribution table summing to `out`.
- **Training** (random-different → meaningfully-different) is Part 5, where
  correlation with raw features jumps from coincidental (3 of 4 neurons keying off
  `GrLivArea` at random init) to genuine specialization (`Neuron 2 → TotalBsmtSF` at
  -0.95).
- **Multiple outputs** (new aggregators, same specialists) is Part 6's 4×2 `W2_multi`,
  reusing Part 5's exact hidden activations for both outputs.

## Reflection questions, answered

**1. If all 4 neurons were initialized to the same non-zero value (e.g. all `0.3`
instead of all `0`), would the symmetry problem still happen?**

Yes — verified directly. Setting `W1 = W2 = 0.3` everywhere (house 7's input, same as
Part 1) gives:

```
z1 = [0.3975, 0.3975, 0.3975, 0.3975]   (identical, but not zero this time)
h  = [0.5981, 0.5981, 0.5981, 0.5981]   (identical)
dz1 = [-0.01235, -0.01235, -0.01235, -0.01235]   (identical gradient, all 4 neurons)
```

Same trap, non-zero flavor. The failure was never "zero specifically" — it's that
`z1_j = Σ_i x_i · W1[i,j]` gives the same result for every column *j* whenever every
column contains the same numbers, regardless of what those numbers are. Zero is just
the version people reach for by instinct because it "feels neutral." This is exactly
the notebook's own "general principle" section, and the doc's Part 1 gradient
derivation predicts this result without needing to run it.

**2. In Part 4, what happens to the final prediction if `W2` for one neuron is exactly
0? What does that mean about "trust"?**

Mechanically: that neuron's term drops out of `out = Σ_i (h_i · W2_i) + b2` entirely —
`h_i · 0 = 0` no matter what `h_i` is. The prediction becomes whatever the *other 3*
neurons' contributions sum to, plus bias. This is close to Part 6's actual data:
Neuron 4's trained output weight is `0.014` (not exactly zero, but small enough to be
functionally silent) — its contribution to Output 1 in that section is `-0.041` while
Neuron 3 alone contributes `-0.626`, over 15× larger.

In plain English: `W2_i = 0` means the output layer has learned that neuron *i*'s
opinion, however strong that neuron's own activation is, tells it nothing useful about
the target. The neuron can still be firing hard (`h_i` close to 1) — but if nobody
downstream is listening, that activation never reaches the prediction. Trust is encoded
entirely in `W2`'s magnitude, independent of how "excited" the neuron itself is.

**3. If two neurons in the correlation heatmap end up nearly identical, what does that
say about hidden-layer width?**

It would mean the layer has more neurons than the problem needed at that point in
training — two units doing the same job is wasted capacity, functionally 3 useful
neurons wearing a 4-neuron costume. It's worth contrasting with Part 5's actual result,
where all 4 trained neurons ended up *distinct* (`OverallQual`: -0.75, `TotalBsmtSF`:
-0.95, `OverallQual`: +0.88, `GrLivArea`: +0.73) — even Neurons 1 and 3, which both
tracked `OverallQual`, did so with opposite sign and very different output weights
(`-2.415` vs `+1.541`), so they're not actually redundant, just correlated with the same
raw feature. True redundancy would need near-identical correlation *and* near-identical
`W2` rows — that combination is what would justify shrinking the layer.
