"""Baseline rune-native n-gram scorer (Witten-Bell interpolation over 29 symbols).

This is the Phase 1 stand-in that lets the oracle and its self-test run. The Phase 2
scorer (6-8-gram Kneser-Ney with a word-boundary symbol, trained on the corpora in
``data/corpora``) replaces it behind the same interface: ``score(plain) -> float``,
higher = more language-like.

Scores are mean log2-probability per rune: uniform noise is about -log2(29) = -4.86.
The full conditional table is materialised as ``float32[29**(order-1), 29]`` -- the
flat layout a CUDA kernel can load into constant/texture memory.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

from runeforge.gematria import N


class NGramScorer:
    def __init__(self, order: int = 3):
        if not 1 <= order <= 5:
            raise ValueError("order must be 1..5 for the dense baseline table")
        self.order = order
        self.tables: list[np.ndarray] = []  # tables[k]: log2 P(x | k-symbol history), (29**k, 29)

    def fit(self, sequences: Iterable[Sequence[int]]) -> NGramScorer:
        seqs = [np.asarray(s, dtype=np.int64) for s in sequences]
        counts = [np.zeros((N**k, N)) for k in range(self.order)]
        for s in seqs:
            for k in range(self.order):
                if s.size <= k:
                    continue
                h = np.zeros(s.size - k, dtype=np.int64)
                for j in range(k):
                    h = h * N + s[j : s.size - k + j]
                np.add.at(counts[k], (h, s[k:]), 1.0)
        prev = np.full((1, N), 1.0 / N)  # order-0 base: uniform
        probs: list[np.ndarray] = []
        for k in range(self.order):
            c = counts[k]
            tot = c.sum(axis=1, keepdims=True)
            types = (c > 0).sum(axis=1, keepdims=True)
            lam = np.divide(tot, tot + types, out=np.zeros_like(tot), where=(tot + types) > 0)
            ml = np.divide(c, tot, out=np.zeros_like(c), where=tot > 0)
            lower = prev[np.arange(N**k) % prev.shape[0]]  # back off to the last k-1 symbols
            p = lam * ml + (1 - lam) * lower
            probs.append(p)
            prev = p
        self.tables = [np.log2(p).astype(np.float32) for p in probs]
        return self

    def logprobs(self, plain) -> np.ndarray:
        """log2 P(x_i | history) for every position, using the longest available history."""
        if not self.tables:
            raise RuntimeError("scorer is not fitted")
        x = np.asarray(plain, dtype=np.int64)
        out = np.empty(x.size, dtype=np.float64)
        k_max = self.order - 1
        for i in range(min(k_max, x.size)):
            h = 0
            for j in range(i):
                h = h * N + int(x[j])
            out[i] = self.tables[i][h, x[i]]
        if x.size > k_max:
            h = np.zeros(x.size - k_max, dtype=np.int64)
            for j in range(k_max):
                h = h * N + x[j : x.size - k_max + j]
            out[k_max:] = self.tables[k_max][h, x[k_max:]]
        return out

    def score(self, plain) -> float:
        """Mean log2-probability per rune (higher = more language-like)."""
        lp = self.logprobs(plain)
        return float(lp.mean()) if lp.size else float("nan")

    def __call__(self, plain) -> float:
        return self.score(plain)
