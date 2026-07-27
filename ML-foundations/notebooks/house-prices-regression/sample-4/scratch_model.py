"""Linear regression "by hand": gradient descent on plain numpy arrays, no
sklearn estimator classes involved. Mirrors sklearn's Estimator API
(fit/predict, .coef_/.intercept_ after fitting) purely so scripts/train_*.py
can treat both training paths the same way — the fitting algorithm itself is
implemented from scratch below.

Why Adam and not plain SGD: this problem has 175 features on a mix of scales
— standardized numeric columns (variance 1) next to one-hot dummy columns
(variance close to 0 for rare categories, e.g. a neighborhood with 5 houses
out of 1,400). That mix is ill-conditioned: a learning rate large enough to
move quickly along the well-scaled directions overshoots and diverges along
the near-flat ones, while a learning rate small enough to stay stable takes
tens of thousands of iterations to converge along the steep ones. Plain
full-batch gradient descent plateaus around R^2 ~ 0.87 on this dataset even
after 40k iterations. Adam's per-parameter adaptive step size — normalizing
each coordinate's update by its own running gradient magnitude — handles
that heterogeneity directly and reaches sklearn's closed-form R^2 (~0.89) in
about 20k iterations.
"""

from __future__ import annotations

import numpy as np


class LinearRegressionScratch:
    """Ordinary least squares fit via the Adam optimizer, implemented from
    scratch (no autograd, no optimizer library — just the closed-form
    gradient of mean squared error and Adam's moment-tracking update rule).
    """

    def __init__(
        self,
        learning_rate: float = 0.03,
        n_iters: int = 20_000,
        beta1: float = 0.9,
        beta2: float = 0.999,
        eps: float = 1e-8,
        verbose_every: int = 0,
    ):
        self.learning_rate = learning_rate
        self.n_iters = n_iters
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.verbose_every = verbose_every
        self.coef_: np.ndarray | None = None
        self.intercept_: float = 0.0
        self.loss_history_: list[float] = []

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LinearRegressionScratch":
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        n_samples, n_features = X.shape

        w = np.zeros(n_features)
        b = 0.0
        # First and second moment estimates (Adam's running mean/variance of
        # the gradient), one per parameter, initialized to zero.
        m_w, v_w = np.zeros(n_features), np.zeros(n_features)
        m_b, v_b = 0.0, 0.0
        history = []

        for t in range(1, self.n_iters + 1):
            y_pred = X @ w + b
            error = y_pred - y
            grad_w = (X.T @ error) / n_samples
            grad_b = error.mean()

            m_w = self.beta1 * m_w + (1 - self.beta1) * grad_w
            v_w = self.beta2 * v_w + (1 - self.beta2) * grad_w**2
            m_b = self.beta1 * m_b + (1 - self.beta1) * grad_b
            v_b = self.beta2 * v_b + (1 - self.beta2) * grad_b**2

            # Bias correction: without it, m/v are biased toward zero during
            # the first few steps since they start at zero.
            m_w_hat = m_w / (1 - self.beta1**t)
            v_w_hat = v_w / (1 - self.beta2**t)
            m_b_hat = m_b / (1 - self.beta1**t)
            v_b_hat = v_b / (1 - self.beta2**t)

            w -= self.learning_rate * m_w_hat / (np.sqrt(v_w_hat) + self.eps)
            b -= self.learning_rate * m_b_hat / (np.sqrt(v_b_hat) + self.eps)

            loss = float(np.mean(error**2))
            history.append(loss)
            if self.verbose_every and (t % self.verbose_every == 0 or t == self.n_iters):
                print(f"iter {t:6d} | MSE (log target): {loss:.5f}")

        self.coef_ = w
        self.intercept_ = float(b)
        self.loss_history_ = history
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.coef_ is None:
            raise RuntimeError("call fit() before predict()")
        return np.asarray(X, dtype=np.float64) @ self.coef_ + self.intercept_
