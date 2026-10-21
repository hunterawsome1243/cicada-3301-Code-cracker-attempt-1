"""Periodicity diagnostics: periodic IoC (column coincidences) and kappa (lag coincidences).

Both are reported as z-scores against the i.i.d.-uniform null with exact variance
(see :mod:`runeforge.stats.basic`), and judged against a family-wise bar so that
scanning more periods does not manufacture peaks.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

from runeforge.gematria import N
from runeforge.stats.basic import coincidence_z


def periodic_coincidences(x, period: int) -> tuple[int, int]:
    """(coinciding pairs, total pairs) within the ``period`` columns of x."""
    a = np.asarray(x, dtype=np.int64)
    if period < 1:
        raise ValueError("period must be >= 1")
    col = np.arange(a.size) % period
    c = np.bincount(col * N + a, minlength=period * N).reshape(period, N)
    n_col = c.sum(axis=1)
    return int((c * (c - 1)).sum() // 2), int((n_col * (n_col - 1)).sum() // 2)


def periodic_ioc(x, period: int) -> dict:
    """Pooled column IoC (normalised x29) and its z for one period."""
    co, pairs = periodic_coincidences(x, period)
    return {
        "period": period,
        "ioc_norm": N * co / pairs if pairs else float("nan"),
        "pairs": pairs,
        "z": coincidence_z(co, pairs),
    }


def kappa(x, lag: int) -> dict:
    """Fraction of positions i with x[i] == x[i+lag], and its z."""
    a = np.asarray(x, dtype=np.int64)
    if not 1 <= lag < a.size:
        raise ValueError("lag out of range")
    co = int((a[lag:] == a[:-lag]).sum())
    pairs = a.size - lag
    return {"lag": lag, "kappa": co / pairs, "pairs": pairs, "z": coincidence_z(co, pairs)}


def familywise_z(n_tests: int, alpha: float = 1e-3) -> float:
    """One-sided Bonferroni bar: the z a single test must exceed so that the chance of
    any of ``n_tests`` null tests exceeding it is at most ``alpha``."""
    return NormalDist().inv_cdf(1 - alpha / n_tests)


def scan(x, max_lag: int, kind: str = "periodic", min_pairs: int = 50) -> dict:
    """Scan periods (or lags) 1..max_lag; return every z, the peak, and the family-wise bar.

    Periods with fewer than ``min_pairs`` comparable pairs carry no information and are
    skipped (they would otherwise inflate the trial count).
    """
    fn = periodic_ioc if kind == "periodic" else kappa
    rows = []
    a = np.asarray(x, dtype=np.int64)
    for d in range(1, max_lag + 1):
        if kind == "kappa" and d >= a.size:
            break
        r = fn(a, d)
        if r["pairs"] >= min_pairs and not math.isnan(r["z"]):
            rows.append(r)
    zs = np.array([r["z"] for r in rows])
    best = rows[int(np.argmax(zs))] if rows else None
    bar = familywise_z(len(rows)) if rows else float("nan")
    return {
        "kind": kind,
        "n_tests": len(rows),
        "max_z": float(zs.max()) if rows else float("nan"),
        "argmax": None if best is None else best.get("period", best.get("lag")),
        "familywise_bar": bar,
        "peak": bool(rows) and float(zs.max()) > bar,
        "rows": rows,
    }
