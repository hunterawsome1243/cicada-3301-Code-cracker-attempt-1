"""Unigram and adjacent-pair statistics over the 29-symbol alphabet.

Null model throughout: i.i.d. uniform symbols. Coincidence indicators of distinct
position pairs are *pairwise independent* under that model, so the variance of any
coincidence count over M distinct pairs is exactly M p (1 - p) with p = 1/29; the
z-scores below use that exact variance.
"""

from __future__ import annotations

import math

import numpy as np

from runeforge.gematria import N

P_COINCIDE = 1.0 / N


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype=np.int64)


def counts(x) -> np.ndarray:
    return np.bincount(_arr(x), minlength=N)


def ioc(x) -> float:
    """Raw index of coincidence: P(two distinct positions hold the same symbol)."""
    a = _arr(x)
    n = a.size
    if n < 2:
        return float("nan")
    c = counts(a)
    return float((c * (c - 1)).sum() / (n * (n - 1)))


def ioc_norm(x) -> float:
    """IoC x 29: 1.0 for uniform random text, ~1.7-1.8 for English in runes."""
    return ioc(x) * N


def ioc_null_sd(n: int, m: int = N) -> float:
    """SD of the normalised IoC of n i.i.d. uniform symbols: sqrt(2(m-1)) / (n-1)."""
    return math.sqrt(2 * (m - 1)) / (n - 1)


def entropy_bits(x) -> float:
    a = _arr(x)
    if a.size == 0:
        return float("nan")
    p = counts(a) / a.size
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def chi2_uniform(x) -> float:
    """Pearson chi-square of the unigram counts against uniform (df = 28)."""
    a = _arr(x)
    exp = a.size / N
    return float(((counts(a) - exp) ** 2 / exp).sum())


def doublet_count(x) -> int:
    a = _arr(x)
    return int((a[1:] == a[:-1]).sum()) if a.size > 1 else 0


def doublet_stats(x) -> dict:
    """Adjacent identical runes vs the uniform expectation (n-1)/29."""
    a = _arr(x)
    pairs = max(a.size - 1, 0)
    obs = doublet_count(a)
    exp = pairs * P_COINCIDE
    sd = math.sqrt(pairs * P_COINCIDE * (1 - P_COINCIDE)) if pairs else float("nan")
    return {
        "pairs": pairs,
        "doublets": obs,
        "rate": obs / pairs if pairs else float("nan"),
        "expected": exp,
        "z": (obs - exp) / sd if pairs else float("nan"),
    }


def coincidence_z(coincidences: int, pairs: int) -> float:
    """z of a coincidence count over ``pairs`` distinct position pairs (exact variance)."""
    if pairs <= 0:
        return float("nan")
    return (coincidences - pairs * P_COINCIDE) / math.sqrt(pairs * P_COINCIDE * (1 - P_COINCIDE))


def summary(x) -> dict:
    a = _arr(x)
    d = doublet_stats(a)
    return {
        "n": int(a.size),
        "ioc_norm": ioc_norm(a),
        "entropy_bits": entropy_bits(a),
        "chi2_uniform": chi2_uniform(a),
        "chi2_df": N - 1,
        "doublets": d["doublets"],
        "doublet_rate": d["rate"],
        "doublets_expected": d["expected"],
        "doublet_z": d["z"],
    }
