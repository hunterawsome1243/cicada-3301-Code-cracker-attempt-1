"""Null distributions and family-wise score bars.

The maximum of N null scores grows with N, so a fixed bar is meaningless at sweep
scale. Scores here are higher-is-better (mean log-probability per rune).

* ``gaussian_max_bar``: mu + sd * sqrt(2 ln N), the Gaussian extreme-value rule of thumb
  (the spec's ``bar(N) = mu - sd * sqrt(2 ln N)`` written for a lower-is-better score).
* ``gumbel_bar``: mu + beta * (ln N - ln(-ln(1 - alpha))), with (mu, beta) fitted from
  observed *maxima* (``fit_gumbel_from_maxima``). Dukotah's benchmark/null.py shows the
  bulk SD can misstate the upper tail of a skewed score by ~2.5x; prefer this form once
  order statistics exist.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

EULER_GAMMA = 0.5772156649015329


def gaussian_max_bar(mu: float, sd: float, n_trials: int) -> float:
    if n_trials < 2:
        return mu
    return mu + sd * math.sqrt(2 * math.log(n_trials))


def gumbel_bar(mu: float, beta: float, n_trials: int, alpha: float = 0.01) -> float:
    """Family-wise bar at level ``alpha`` for the max of ``n_trials`` Gumbel(mu, beta) draws."""
    if n_trials < 2:
        return mu
    return mu + beta * (math.log(n_trials) - math.log(-math.log(1 - alpha)))


def fit_gumbel_from_maxima(n1: int, max1: float, n2: int, max2: float) -> tuple[float, float]:
    """(mu, beta) from two observed maxima at different trial counts:
    E[max_N] = mu + beta * (ln N + gamma)."""
    if n1 == n2:
        raise ValueError("need two different trial counts")
    beta = (max2 - max1) / (math.log(n2) - math.log(n1))
    mu = max1 - beta * (math.log(n1) + EULER_GAMMA)
    return mu, beta


def null_scores(
    score: Callable[[np.ndarray], float], length: int, n: int = 10_000, seed: int = 3301
) -> np.ndarray:
    """Scores of ``n`` uniform random rune strings of ``length``."""
    rng = np.random.default_rng(seed)
    return np.array([score(rng.integers(0, 29, length)) for _ in range(n)])


def shuffle_null(
    score: Callable[[np.ndarray], float], seq, n: int = 200, seed: int = 3301
) -> np.ndarray:
    """Histogram-preserving, order-destroying null for one candidate decode."""
    rng = np.random.default_rng(seed)
    a = np.asarray(seq)
    return np.array([score(rng.permutation(a)) for _ in range(n)])
