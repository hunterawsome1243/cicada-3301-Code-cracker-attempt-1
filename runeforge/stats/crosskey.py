"""Shared-keystream scan between (and within) sections.

If two ciphertexts were made with the same additive keystream at some relative shift,
their difference at that alignment is the difference of two plaintexts -- non-uniform,
so its IoC rises above 1. This scans every relative shift with at least ``min_overlap``
aligned runes and reports z = (IoC(diff) - 1) / sd(n), sd(n) = sqrt(56) / (n - 1)
(Leo-Y-Zhang/LiberPrimusAnalysis tests5.py).

The raw maximum z is NOT a significance measure: ~80,000 shifts are tested and the
statistic has a chi-square right tail, so the null maximum is near z = 6 (confirmed on
shuffled surrogates). Judge a scan by :func:`familywise`. (Leo's published "max z 3.3"
does not reproduce with the exact null SD sqrt(56)/(n-1) that the same repository now
uses; the family-wise conclusion -- no shared keystream -- does.)

All shifts of a pair are computed at once: for each symbol pair (a, b) the number of
aligned positions with A = a and B = b is a cross-correlation of one-hot rows, done by FFT.
"""

from __future__ import annotations

import itertools
import math

import numpy as np

from runeforge.gematria import N
from runeforge.stats.basic import ioc_null_sd


def _onehot(x: np.ndarray) -> np.ndarray:
    m = np.zeros((N, x.size))
    m[x, np.arange(x.size)] = 1.0
    return m


def diff_ioc_by_shift(a, b) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For every shift s (A[i + s] aligned with B[i]) return (shifts, overlap, IoC(diff))."""
    a = np.asarray(a, dtype=np.int64)
    b = np.asarray(b, dtype=np.int64)
    na, nb = a.size, b.size
    size = 1 << int(np.ceil(np.log2(na + nb)))
    fa = np.fft.rfft(_onehot(a), size)
    fb = np.conj(np.fft.rfft(_onehot(b), size))
    # corr[x, y, s] = #{i : A[i+s] = x, B[i] = y}; negative shifts wrap to the end.
    corr = np.rint(np.fft.irfft(fa[:, None, :] * fb[None, :, :], size)).astype(np.int64)
    shifts = np.arange(-(nb - 1), na)
    corr = corr[:, :, shifts % size]
    # differences d = x - y (mod 29): sum the diagonals of the (x, y) table.
    x = np.arange(N)[:, None]
    y = np.arange(N)[None, :]
    d = (x - y) % N
    cnt = np.zeros((N, shifts.size), dtype=np.int64)
    for v in range(N):
        cnt[v] = corr[d == v].sum(axis=0)
    overlap = cnt.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ioc = (cnt * (cnt - 1)).sum(axis=0) / (overlap * (overlap - 1) / N)
    return shifts, overlap, ioc


def chi2_sf_even(x: float, df: int) -> float:
    """Exact chi-square survival function for even ``df`` (a Poisson CDF)."""
    if df % 2:
        raise ValueError("df must be even")
    if x <= 0:
        return 1.0
    lam = x / 2.0
    term = math.exp(-lam)
    total = term
    for j in range(1, df // 2):
        term *= lam / j
        total += term
    return min(1.0, total)


def z_to_p(z: float) -> float:
    """Per-shift p-value of an IoC(diff) z: (n-1)(IoC-1) + m - 1 is the chi-square
    statistic of the difference counts (df 28), whose right tail is heavier than normal."""
    return chi2_sf_even((N - 1) + z * math.sqrt(2 * (N - 1)), N - 1)


def familywise(results: list[dict]) -> dict:
    """Sidak family-wise p-value of the best z over every shift tested in ``results``."""
    if not results:
        return {"max_z": float("nan"), "n_tests": 0, "p_single": float("nan"), "p_familywise": 1.0}
    best = max(results, key=lambda r: r["z"])
    k = sum(r["n_shifts"] for r in results)
    p1 = z_to_p(best["z"])
    p_fw = -math.expm1(k * math.log1p(-p1)) if p1 < 1 else 1.0
    return {"max_z": best["z"], "best": best, "n_tests": k, "p_single": p1, "p_familywise": p_fw}


def shared_key_scan(
    sections: dict[str, np.ndarray], min_overlap: int = 300, self_min_shift: int = 2
) -> list[dict]:
    """Best shift per section pair, sorted by z descending.

    Self-pairs skip |shift| < ``self_min_shift``: at shift 1 the difference stream is the
    first difference of the ciphertext, whose depleted zero IS the doublet anomaly
    (measured separately), not evidence of a reused keystream.
    """
    names = list(sections)
    out = []
    for x, y in itertools.combinations_with_replacement(names, 2):
        shifts, overlap, ioc = diff_ioc_by_shift(sections[x], sections[y])
        ok = overlap >= min_overlap
        if x == y:
            ok &= np.abs(shifts) >= self_min_shift
        if not ok.any():
            continue
        z = (ioc - 1.0) / np.array([ioc_null_sd(int(n)) if n > 1 else np.inf for n in overlap])
        z[~ok] = -np.inf
        k = int(np.argmax(z))
        out.append(
            {
                "a": x,
                "b": y,
                "z": float(z[k]),
                "shift": int(shifts[k]),
                "overlap": int(overlap[k]),
                "n_shifts": int(ok.sum()),
            }
        )
    return sorted(out, key=lambda r: -r["z"])
