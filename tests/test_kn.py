"""The Phase 2 Kneser-Ney scorer (runeforge.scoring.kn, kn_fit, boundaries, presets;
docs/kn-scorer-design.md, whose section numbers the tests cite).

What is proven here:

* the fitted model is a probability model: every conditional distribution sums to 1 (1e-12 on
  ``distribution``, 1e-5 through the float32 tables) for seen, once-seen, unseen-at-top,
  never-seen and prefix histories, in dense, sparse and word-boundary (wb) models;
* the estimate follows section 2.3 exactly: the hand-computed order-2 example on [0,1,0,1,2],
  the discounted unigram at order 1, the discount fallbacks and clamps with their
  ``discount_source``, and a brute-force ``fractions.Fraction`` re-implementation of the whole
  rule (raw counts, continuation counts, modified-KN discounts, interpolation) on random Markov
  text at orders 1..4, nb and wb, dense and sparse, computed and pinned discounts;
* ``score_batch`` is the per-row ``score`` to 1e-9 at L 1..1000, a row scores the same alone
  and in a batch of 4096, short positions use the lower-order distribution, an unseen history
  backs off with weight one and a seen history with an unseen symbol uses its stored bow;
* the ``knx-1`` export round-trips: the scalar ``reference_logprobs`` over the exported hash is
  bit-for-bit the numpy ``logprobs`` (random, held-out, all-F, max-key and longest-probe
  windows), the hash layout holds its invariants and the reloaded fingerprint equals;
* fingerprints pin the arrays, order, base and dense levels and nothing else, and the Phase 1
  ``ngram`` presets keep the fingerprints their shipped calibrations were fitted on;
* beam compatibility (section 5): dense ``tables`` are identity-stable and equal log2 of
  ``distribution``; sparse and wb models refuse ``tables``; ``split_preset`` and ``LaneSpec``
  refuse them with any beam decoder; the numpy beam replays ``score_batch`` to 1e-9 (and the
  GPU twin to 1e-6, skipped without numba); WELCOME's 11-of-25 interrupters are re-derived
  under kn4-lp-heldout;
* the held-out split is real (``check_held_out`` refusals, ``heldout_stream`` word alignment,
  a 12-gram found only in the tail), the boundary extension and its L divisor,
  ``calib.calibrate`` / ``calib.load`` on a KN preset, determinism across two processes and a
  throughput smoke (slow).

Corpus-dependent cases are marked ``raw`` and skip without ``data/corpora``. The ``_fit``,
``_load_export``, ``_manifest_of`` and ``_hex`` adapters at the top bind the tests to the entry
points section 1 names; everything else is the section 2-5 contract.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from collections import Counter
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from runeforge import beam, canon, corpus, interrupts
from runeforge.lanes import LaneSpec
from runeforge.paths import REPO_ROOT
from runeforge.scoring import calib, kn, kn_fit, presets
from runeforge.transforms import from_method

BOUNDARY = 29
MULT = 0x9E3779B97F4A7C15
EMPTY = np.uint64(0xFFFFFFFFFFFFFFFF)
PHASE1_FINGERPRINTS = {  # runeforge/scoring/calib/presets/*.json, scorer_fingerprint
    "lp-ngram3": "538474ae5abad01c1f681dc9895929deb77b488a77d8c6b52fd7599a68338e07",
    "lp-ngram3-heldout": "a144706ac65a67119a825883df063b5cac38c021818a298dc8becf07dcb58870",
    "cicada-ngram3": "621cff123ee62d090b89cab641ae3a14ebea562312adef00c81cd5e25005aaaf",
    "general-ngram3": "38000098a1f2c33765e05ee07e329e7fe467235d0f2911e8b06ce5bf311d3570",
}
KN_PRESETS = {  # name: (order, base, dense_levels, beam-compatible)  -- design section 3
    "kn4-lp-heldout": (4, 29, 4, True),
    "kn4-cicada": (4, 29, 4, True),
    "kn5-cicada": (5, 29, 5, True),
    "kn6-cicada": (6, 29, 4, False),
    "kn8-cicada": (8, 29, 4, False),
    "kn8-general": (8, 29, 4, False),
    "kn8-latin": (8, 29, 4, False),
    "kn8-old-english": (8, 29, 4, False),
    "kn8-vowel-dropped": (8, 29, 4, False),
    "kn8-cicada-wb": (8, 30, 4, False),
}
SOURCES = {
    "modified-kn",
    "partial:D2<-D1",
    "partial:D3<-D2",
    "partial:D2<-D1,D3<-D2",
    "fallback-0.5",
}


# ----------------------------------------------------------------------------- adapters


def _fit(seqs, order, base=29, dense_levels=None, discounts=None, boundary=None):
    """A KNScorer fitted on ``seqs`` (already boundary-extended for wb) through
    ``kn_fit.estimate`` (section 1: the per-level arrays; kn.py holds no fitting code)."""
    est = kn_fit.estimate(
        [np.asarray(s, dtype=np.int64) for s in seqs],
        order,
        base=base,
        dense_levels=order if dense_levels is None else dense_levels,
        boundary=boundary,
        pinned_discounts=discounts,
    )
    return kn.KNScorer.from_estimate(est)


def _load_export(path):
    return kn.KNScorer.load_export(path)


def _hex(v) -> int:
    return v if isinstance(v, int) else int(str(v), 16)


def _extend(x, starts, end_boundary: bool) -> np.ndarray:
    """Section 2.5 by hand: 29 before every True position (and at the end), one mask for
    every row; the oracle for ``KNScorer.boundary_extend``."""
    a = np.asarray(x, dtype=np.int64)
    rows = a.reshape(-1, a.shape[-1])
    out = []
    for row in rows:
        ext = []
        for v, st in zip(row.tolist(), np.asarray(starts, dtype=bool).tolist(), strict=True):
            if st:
                ext.append(BOUNDARY)
            ext.append(v)
        if end_boundary:
            ext.append(BOUNDARY)
        out.append(ext)
    return np.array(out, dtype=np.int64).reshape(*a.shape[:-1], -1)


def _manifest_of(ret, path: Path) -> dict:
    """The JSON manifest of an export: the return value of ``export`` when it is one, else the
    file next to the npz, else the copy inside the npz (section 4: both exist)."""
    if isinstance(ret, dict):
        return ret
    side = path.with_suffix(".json")
    if side.exists():
        return json.loads(side.read_text(encoding="utf-8"))
    with np.load(path, allow_pickle=False) as z:
        return json.loads(str(z["manifest"]))


def _need_corpus(name="cicada-english"):
    if name not in corpus.names():
        pytest.skip(f"corpus {name!r} not built: python scripts/build_corpus.py")


# ----------------------------------------------------------------------------- reference


def _classes(values) -> list[int]:
    """[N_1, N_2, N_3+] over effective counts (count 0 is in no class)."""
    n = [0, 0, 0]
    for c in values:
        if c >= 1:
            n[min(c, 3) - 1] += 1
    return n


def _ref_discounts(values) -> tuple[list[Fraction], str]:
    """Section 2.3 step 3 in exact arithmetic, fallback rule and clamp included."""
    n = [0] * 5
    for c in values:
        if 1 <= c <= 4:
            n[c] += 1
    n1, n2, n3, n4 = n[1:]
    if n1 == 0 or n2 == 0:
        d, src = [Fraction(1, 2)] * 3, "fallback-0.5"
    else:
        y = Fraction(n1, n1 + 2 * n2)
        d1 = 1 - 2 * y * Fraction(n2, n1)
        fell = []
        if n3 == 0:
            d2 = d1
            fell.append("D2<-D1")
        else:
            d2 = 2 - 3 * y * Fraction(n3, n2)
        if n3 == 0 or n4 == 0:
            d3 = d2
            fell.append("D3<-D2")
        else:
            d3 = 3 - 4 * y * Fraction(n4, n3)
        d, src = [d1, d2, d3], ("partial:" + ",".join(fell) if fell else "modified-kn")
    return [min(max(x, Fraction(1, 20)), r) for r, x in zip((1, 2, 3), d, strict=True)], src


class _Reference:
    """Design section 2.3, brute force, in ``Fraction``: the oracle for every fitted value."""

    def __init__(self, seqs, order, base, discounts=None):
        self.n, self.base = order, base
        raw = [Counter() for _ in range(order + 1)]
        for s in seqs:
            t = tuple(int(v) for v in s)
            for k in range(1, order + 1):
                for i in range(len(t) - k + 1):
                    raw[k][t[i : i + k]] += 1
        eff: list[dict] = [{} for _ in range(order + 1)]
        eff[order] = dict(raw[order])
        for k in range(order - 1, 0, -1):  # continuation counts from the next level's keys
            cc = dict.fromkeys(raw[k], 0)
            for g in raw[k + 1]:
                cc[g[1:]] += 1
            eff[k] = cc
        self.eff = eff
        self.D: list[list[Fraction]] = []
        self.source: list[str] = []
        for k in range(1, order + 1):
            if discounts is None:
                d, src = _ref_discounts(eff[k].values())
            else:
                d, src = [Fraction(x) for x in discounts[k - 1]], "pinned"
            self.D.append(d)
            self.source.append(src)
        self.hist: list[dict] = [{} for _ in range(order + 1)]  # h -> [cc(h), [N1, N2, N3+]]
        for k in range(2, order + 1):
            acc: dict = {}
            for g, c in eff[k].items():
                e = acc.setdefault(g[:-1], [0, [0, 0, 0]])
                e[0] += c
                if c >= 1:
                    e[1][min(c, 3) - 1] += 1
            self.hist[k] = acc
        self.C1 = sum(eff[1].values())
        self.N1 = _classes(eff[1].values())

    def _disc(self, k, c) -> Fraction:
        return self.D[k - 1][min(c, 3) - 1] if c >= 1 else Fraction(0)

    def p(self, k, h: tuple, w: int) -> Fraction:
        if k == 1:
            gamma = sum(self.D[0][j] * self.N1[j] for j in range(3)) / self.C1
            c = self.eff[1].get((w,), 0)
            return max(c - self._disc(1, c), 0) / self.C1 + gamma / self.base
        e = self.hist[k].get(h)
        if e is None or e[0] == 0:  # unseen history: weight one on the lower level
            return self.p(k - 1, h[1:], w)
        tot, cls = e
        gamma = sum(self.D[k - 1][j] * cls[j] for j in range(3)) / tot
        c = self.eff[k].get((*h, w), 0)
        return max(c - self._disc(k, c), 0) / tot + gamma * self.p(k - 1, h[1:], w)

    def gamma(self, k, h: tuple) -> Fraction:
        e = self.hist[k].get(h)
        if e is None or e[0] == 0:
            return Fraction(1)
        return sum(self.D[k - 1][j] * e[1][j] for j in range(3)) / e[0]

    def distribution(self, h) -> list[Fraction]:
        h = tuple(int(v) for v in h)
        return [self.p(len(h) + 1, h, w) for w in range(self.base)]

    def probs(self, x) -> list[Fraction]:
        """P(x_i | the longest available history) per position (section 2.4)."""
        x = [int(v) for v in x]
        out = []
        for i, w in enumerate(x):
            m = min(i, self.n - 1)
            out.append(self.p(m + 1, tuple(x[i - m : i]), w))
        return out


def _flat(rows) -> list:
    return [v for row in rows for v in row]


def _f64(fracs) -> np.ndarray:
    return np.array([float(v) for v in fracs], dtype=np.float64)


def _log2(fracs) -> np.ndarray:
    return np.array([math.log2(float(v)) for v in fracs], dtype=np.float64)


# ----------------------------------------------------------------------------- toy data


class _Chain:
    """A sparse-transition Markov source over symbols 0..symbols-1 (28 is never emitted, so a
    history ending in 28 is never seen at any level >= 2)."""

    def __init__(self, seed: int, symbols: int = 28):
        self.rng = np.random.default_rng(seed)
        t = self.rng.random((symbols, symbols)) ** 6
        self.t = t / t.sum(axis=1, keepdims=True)
        self.symbols = symbols

    def seq(self, n: int) -> np.ndarray:
        out = np.empty(n, dtype=np.int64)
        out[0] = self.rng.integers(0, self.symbols)
        for i in range(1, n):
            out[i] = self.rng.choice(self.symbols, p=self.t[out[i - 1]])
        return out

    def words(self, n_words: int) -> list[np.ndarray]:
        return [self.seq(int(self.rng.integers(1, 9))) for _ in range(n_words)]


def _wb_sequence(words) -> np.ndarray:
    """Section 2.3: concat over words ([29] + runes(word)) + [29]."""
    return np.array([v for w in words for v in (BOUNDARY, *w)] + [BOUNDARY], dtype=np.int64)


def _unextend(ext) -> tuple[np.ndarray, np.ndarray, bool]:
    """(runes, starts, end_boundary) whose boundary extension is ``ext``."""
    runes, starts, pending = [], [], False
    for s in ext:
        if s == BOUNDARY:
            assert not pending, "two boundaries in a row cannot come from a starts mask"
            pending = True
        else:
            runes.append(int(s))
            starts.append(pending)
            pending = False
    return np.array(runes, dtype=np.int64), np.array(starts, dtype=bool), pending


@pytest.fixture(scope="module")
def toy():
    """Three nb sequences, one wb sequence and their Fraction references, plus the fitted
    dense (order 3, D 3), sparse (order 4, D 2) and wb (order 3, base 30, D 2) models."""
    chain = _Chain(3301)
    nb = [chain.seq(1500), chain.seq(900), chain.seq(600)]
    wb = [_wb_sequence(chain.words(220))]
    return {
        "chain": chain,
        "nb": nb,
        "wb": wb,
        "dense": _fit(nb, 3, dense_levels=3),
        "sparse": _fit(nb, 4, dense_levels=2),
        "wb3": _fit(wb, 3, base=30, dense_levels=2, boundary=BOUNDARY),
        "ref_dense": _Reference(nb, 3, 29),
        "ref_sparse": _Reference(nb, 4, 29),
        "ref_wb3": _Reference(wb, 3, 30),
    }


MODELS = ["dense", "sparse", "wb3"]


def _histories(ref: _Reference) -> dict[str, tuple]:
    """Seen, once-seen, unseen-at-top (its suffix seen one level down), never-seen and
    prefix histories of a reference model."""
    n = ref.n
    if n == 1:
        return {"prefix0": ()}
    top = ref.hist[n]
    seen = max(top, key=lambda h: top[h][0])
    out = {"seen": seen, "never": (28,) * (n - 1)}
    once = [h for h in top if top[h][0] == 1]
    if once:
        out["once"] = once[0]
    if n >= 3:
        suffix = seen[1:]
        assert suffix in ref.hist[n - 1]
        out["unseen-at-top"] = next(
            (s, *suffix) for s in range(ref.base) if (s, *suffix) not in top
        )
    for j in range(n - 1):
        out[f"prefix{j}"] = seen[:j]
    return out


def _conditional_logprobs(scorer, h, base: int, wb: bool) -> np.ndarray:
    """log2 P(x | h) for every x through ``logprobs`` (the float32 tables): for a wb model the
    extended history is expressed as runes + starts, and x = 29 as ``end_boundary``."""
    out = np.empty(base)
    for x in range(base):
        ext = (*h, x)
        if not wb:
            out[x] = scorer.logprobs(np.array(ext, dtype=np.int64))[-1]
            continue
        if x == BOUNDARY and h and h[-1] == BOUNDARY:  # no mask writes two boundaries in a row
            out[x] = np.nan
            continue
        runes, starts, end = _unextend(ext)
        assert scorer.boundary_extend(runes, starts, end).tolist() == list(ext)
        out[x] = scorer.logprobs(runes, starts=starts, end_boundary=end)[-1]
    return out


# ----------------------------------------------------------------------------- sum to 1


@pytest.mark.parametrize("name", MODELS)
def test_every_conditional_distribution_sums_to_one(toy, name):
    scorer, ref = toy[name], toy["ref_" + name]
    for kind, h in _histories(ref).items():
        d = np.asarray(scorer.distribution(list(h)), dtype=np.float64)
        assert d.shape == (ref.base,) and d.dtype == np.float64, kind
        assert (d > 0).all(), kind  # the uniform floor reaches every symbol
        assert abs(d.sum() - 1.0) <= 1e-12, (kind, d.sum())
        lp = _conditional_logprobs(scorer, h, ref.base, wb=name == "wb3")
        lp = np.where(np.isnan(lp), np.log2(d), lp)  # the one cell no mask can express
        assert np.isfinite(lp).all() and (lp <= 0).all(), kind
        assert abs(np.exp2(lp).sum() - 1.0) <= 1e-5, (kind, np.exp2(lp).sum())
        assert np.abs(lp - np.log2(d)).max() <= 1e-4, kind  # float32 of the same values


@pytest.mark.parametrize("name", MODELS)
def test_the_fit_is_the_section_2_3_rule(toy, name):
    """Every history kind against the Fraction reference, discounts and sources included."""
    scorer, ref = toy[name], toy["ref_" + name]
    assert scorer.order == ref.n and scorer.base == ref.base
    assert np.asarray(scorer.discounts).shape == (ref.n, 3)
    assert (
        np.abs(
            np.asarray(scorer.discounts, dtype=np.float64) - _f64(_flat(ref.D)).reshape(ref.n, 3)
        ).max()
        <= 1e-12
    )
    assert list(scorer.discount_source) == ref.source
    assert set(ref.source) <= SOURCES
    for kind, h in _histories(ref).items():
        got = np.asarray(scorer.distribution(list(h)), dtype=np.float64)
        assert np.abs(got - _f64(ref.distribution(h))).max() <= 1e-10, kind


# ----------------------------------------------------------------------------- hand examples


def test_the_hand_computed_order_2_example():
    """[0,1,0,1,2]: bigrams FU 2, UF 1, UO 1 -> n1 = 2, n2 = 1 -> Y = 1/2, D1 = 1/2, D2 <- D1,
    D3 <- D2; unigram continuation counts 1, 1, 1 -> n2 = 0 -> every D = 0.5."""
    scorer = _fit([[0, 1, 0, 1, 2]], 2, dense_levels=2)
    assert np.array_equal(np.asarray(scorer.discounts), np.full((2, 3), 0.5))
    assert list(scorer.discount_source) == ["fallback-0.5", "partial:D2<-D1,D3<-D2"]
    half = Fraction(1, 2)
    gamma1 = half * 3 / 3  # (D1 N1) / C with N1 = 3, C = 3

    def p1(x):
        return (half / 3 if x in (0, 1, 2) else Fraction(0)) + gamma1 / 29

    assert p1(0) == Fraction(1, 6) + Fraction(1, 58) and p1(7) == Fraction(1, 58)
    assert sum(p1(x) for x in range(29)) == 1
    want = {
        (): [p1(x) for x in range(29)],
        (0,): [
            Fraction(3, 4) + Fraction(1, 4) * p1(1) if x == 1 else Fraction(1, 4) * p1(x)
            for x in range(29)
        ],
        (1,): [Fraction(1, 4) + half * p1(x) if x in (0, 2) else half * p1(x) for x in range(29)],
        (2,): [p1(x) for x in range(29)],  # unseen history: the unigram exactly
        (28,): [p1(x) for x in range(29)],
    }
    assert want[(0,)][1] == Fraction(3, 4) + Fraction(1, 4) * p1(1)
    assert want[(1,)][0] == Fraction(1, 4) + half * p1(0) and want[(1,)][5] == half * p1(5)
    for h, row in want.items():
        assert sum(row) == 1
        got = np.asarray(scorer.distribution(list(h)), dtype=np.float64)
        assert np.abs(got - _f64(row)).max() <= 1e-12, h
    # the stored float32 tables and the per-position log-probs are the same numbers
    assert scorer.tables[0].shape == (1, 29) and scorer.tables[1].shape == (29, 29)
    assert abs(scorer.tables[1][0, 1] - math.log2(float(want[(0,)][1]))) <= 1e-6
    assert abs(scorer.tables[1][1, 5] - math.log2(float(half * p1(5)))) <= 1e-6
    lp = scorer.logprobs(np.array([0, 1, 0, 1, 2]))
    exp = _log2([p1(0), want[(0,)][1], want[(1,)][0], want[(0,)][1], want[(1,)][2]])
    assert np.abs(lp - exp).max() <= 1e-5
    assert abs(scorer.score([0, 1, 0, 1, 2]) - lp.sum() / 5) <= 1e-9


def test_order_1_is_the_discounted_unigram():
    """Counts 1,1,1,2,2,3,4,5 -> n1 = 3, n2 = 2, n3 = 1, n4 = 1: Y = 3/7, D1 = 3/7, D2 = 19/14,
    D3+ = 9/7 (no fallback, nothing clamped)."""
    counts = {0: 1, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 5}
    seq = [s for s, c in counts.items() for _ in range(c)]
    scorer = _fit([seq], 1, dense_levels=1)
    d = [Fraction(3, 7), Fraction(19, 14), Fraction(9, 7)]
    assert np.abs(np.asarray(scorer.discounts) - _f64(d).reshape(1, 3)).max() <= 1e-12
    assert list(scorer.discount_source) == ["modified-kn"]
    total = 19
    gamma = (d[0] * 3 + d[1] * 2 + d[2] * 3) / total

    def p(x):
        c = counts.get(x, 0)
        disc = d[min(c, 3) - 1] if c else Fraction(0)
        return max(c - disc, 0) / total + gamma / 29

    assert sum(p(x) for x in range(29)) == 1
    got = np.asarray(scorer.distribution([]), dtype=np.float64)
    assert np.abs(got - _f64([p(x) for x in range(29)])).max() <= 1e-12
    assert scorer.tables[0].shape == (1, 29)
    assert np.abs(scorer.logprobs(np.arange(29)) - _log2([p(x) for x in range(29)])).max() <= 1e-5


@pytest.mark.parametrize(
    "counts,want,source",
    [
        # n1 = 10, n2 = 1, n3 = 1, n4 = 2: D1 = 5/6, D2 = -1/2 and D3+ = -11/3 clamp to 0.05
        (
            {**{s: 1 for s in range(10)}, 10: 2, 11: 3, 12: 4, 13: 4},
            [Fraction(5, 6), Fraction(1, 20), Fraction(1, 20)],
            "modified-kn",
        ),
        # n1 = 2, n2 = 1, n3 = 1, n4 = 0: D3+ undefined -> D2
        (
            {0: 1, 1: 1, 2: 2, 3: 3},
            [Fraction(1, 2), Fraction(1, 2), Fraction(1, 2)],
            "partial:D3<-D2",
        ),
        # n1 = 2, n2 = 1, n3 = 0: D2 <- D1, D3+ <- D2
        ({0: 1, 1: 1, 2: 2}, [Fraction(1, 2)] * 3, "partial:D2<-D1,D3<-D2"),
        # n2 = 0: D1 undefined -> every D = 0.5
        ({0: 1, 1: 1, 2: 1, 3: 3}, [Fraction(1, 2)] * 3, "fallback-0.5"),
        # n1 = 0: D1 undefined too
        ({0: 2, 1: 2, 2: 3}, [Fraction(1, 2)] * 3, "fallback-0.5"),
    ],
)
def test_discount_fallbacks_and_clamps_are_recorded(counts, want, source):
    seq = [s for s, c in counts.items() for _ in range(c)]
    assert _ref_discounts(counts.values()) == (want, source)  # the reference agrees first
    scorer = _fit([seq], 1, dense_levels=1)
    assert np.abs(np.asarray(scorer.discounts)[0] - _f64(want)).max() <= 1e-12
    assert list(scorer.discount_source) == [source]
    assert (np.asarray(scorer.discounts) >= 0.05).all()
    assert abs(float(np.asarray(scorer.distribution([])).sum()) - 1) <= 1e-12


def test_pinned_discounts_are_used_as_given(toy):
    pinned = [[0.3, 0.6, 0.9], [0.4, 0.8, 1.2], [0.5, 1.0, 1.5]]
    scorer = _fit(toy["nb"], 3, dense_levels=2, discounts=pinned)
    ref = _Reference(toy["nb"], 3, 29, discounts=pinned)
    assert np.array_equal(np.asarray(scorer.discounts, dtype=np.float64), np.array(pinned))
    for kind, h in _histories(ref).items():
        got = np.asarray(scorer.distribution(list(h)), dtype=np.float64)
        assert np.abs(got - _f64(ref.distribution(h))).max() <= 1e-10, kind


@pytest.mark.parametrize(
    "order,dense_levels,wb,pinned",
    [
        (1, 1, False, False),
        (2, 2, False, False),
        (3, 2, False, False),
        (4, 2, False, False),
        (4, 4, False, False),
        (3, 1, True, False),
        (4, 2, False, True),
        (3, 3, True, True),
    ],
)
def test_continuation_counts_and_interpolation_by_brute_force(order, dense_levels, wb, pinned):
    """Short sequences over 8 symbols (so the counts-of-counts are small and the fallbacks
    fire), compared with the Fraction reference at every position of three windows."""
    chain = _Chain(order * 10 + dense_levels + wb, symbols=8)
    if wb:
        seqs = [_wb_sequence(chain.words(40))]
    else:
        seqs = [chain.seq(200), chain.seq(120), chain.seq(80)]
    base = 30 if wb else 29
    discounts = [[0.25 * k, 0.5 * k, 0.75 * k] for k in range(1, order + 1)] if pinned else None
    scorer = _fit(
        seqs,
        order,
        base=base,
        dense_levels=dense_levels,
        discounts=discounts,
        boundary=BOUNDARY if wb else None,
    )
    ref = _Reference(seqs, order, base, discounts=discounts)
    assert (
        np.abs(
            np.asarray(scorer.discounts, dtype=np.float64) - _f64(_flat(ref.D)).reshape(order, 3)
        ).max()
        <= 1e-12
    )
    if not pinned:
        assert list(scorer.discount_source) == ref.source
    rng = np.random.default_rng(order)
    windows = [chain.seq(40), rng.integers(0, 29, 40), np.full(40, 28)]
    for x in windows:
        probs = ref.probs(x)
        if wb:
            starts = rng.random(40) < 0.25
            starts[0] = False
            ext = _extend(x, starts, False)
            probs = ref.probs(ext)
            lp = scorer.logprobs(x, starts=starts)
            assert lp.shape == ext.shape
            score = scorer.score(x, starts=starts)
        else:
            lp = scorer.logprobs(x)
            score = scorer.score(x)
        assert np.abs(lp - _log2(probs)).max() <= 1e-4
        assert abs(score - lp.sum() / 40) <= 1e-9
    for h in _histories(ref).values():
        got = np.asarray(scorer.distribution(list(h)), dtype=np.float64)
        assert np.abs(got - _f64(ref.distribution(h))).max() <= 1e-10


# ----------------------------------------------------------------------------- scoring


def _rows(rng, b: int, length: int) -> np.ndarray:
    x = rng.integers(0, 29, (b, length))
    x[0, :] = 0  # the all-F row
    return x


@pytest.mark.parametrize("length", [1, 3, 7, 50, 240, 1000])
@pytest.mark.parametrize("name", MODELS)
def test_score_batch_is_the_per_row_score(toy, name, length):
    scorer = toy[name]
    rng = np.random.default_rng(length)
    x = _rows(rng, 6, length)
    kw = {}
    if name == "wb3":
        starts = rng.random(length) < 0.25
        starts[0] = False
        kw = {"starts": starts}
    batch = scorer.score_batch(x, **kw)
    assert batch.shape == (6,) and batch.dtype == np.float64 and np.isfinite(batch).all()
    for r in range(6):
        single = scorer.score(x[r], **kw)
        lp = scorer.logprobs(x[r], **kw)
        assert abs(batch[r] - single) <= 1e-9
        assert abs(single - np.sum(lp, dtype=np.float64) / length) <= 1e-9  # L = cipher runes
        assert abs(batch[r] - scorer.score_batch(x[r : r + 1], **kw)[0]) <= 1e-9


def test_a_row_scores_the_same_alone_and_in_a_batch_of_4096(toy):
    scorer = toy["sparse"]
    x = _rows(np.random.default_rng(4096), 4096, 50)
    whole = scorer.score_batch(x)
    assert whole.shape == (4096,)
    for r in (0, 1, 1234, 4095):
        assert abs(whole[r] - scorer.score(x[r])) <= 1e-9
        assert abs(whole[r] - scorer.score_batch(x[r : r + 1])[0]) <= 1e-9
    assert np.abs(whole[100:300] - scorer.score_batch(x[100:300])).max() <= 1e-9


def test_short_positions_use_the_lower_order_distribution(toy):
    scorer = toy["sparse"]  # order 4: positions 0, 1, 2 see 0, 1, 2 history symbols
    x = np.array([5, 7, 5, 9, 2, 5, 7])
    lp = scorer.logprobs(x)
    assert lp.shape == (7,)
    for i in range(3):
        d = np.asarray(scorer.distribution(x[:i].tolist()), dtype=np.float64)
        assert abs(lp[i] - math.log2(d[x[i]])) <= 1e-4, i
    d3 = np.asarray(scorer.distribution(x[3:6].tolist()), dtype=np.float64)
    assert abs(lp[6] - math.log2(d3[x[6]])) <= 1e-4


def test_an_unseen_history_backs_off_with_weight_one(toy):
    scorer, ref = toy["sparse"], toy["ref_sparse"]
    hs = _histories(ref)
    never, unseen = hs["never"], hs["unseen-at-top"]
    for h in (never, unseen):
        full = np.asarray(scorer.distribution(list(h)), dtype=np.float64)
        lower = np.asarray(scorer.distribution(list(h[1:])), dtype=np.float64)
        assert ref.gamma(ref.n, h) == 1
        assert np.abs(full - lower).max() <= 1e-12, h
    # a seen history with an unseen symbol: the stored bow scales the lower distribution
    seen = hs["seen"]
    full = np.asarray(scorer.distribution(list(seen)), dtype=np.float64)
    lower = np.asarray(scorer.distribution(list(seen[1:])), dtype=np.float64)
    missing = [w for w in range(29) if (*seen, w) not in ref.eff[ref.n]]
    assert missing, "pick a seen history with an unseen follower"
    gamma = float(ref.gamma(ref.n, seen))
    assert 0 < gamma < 1
    ratios = full[missing] / lower[missing]
    assert np.abs(ratios - gamma).max() <= 1e-10
    present = [w for w in range(29) if w not in missing]
    assert (full[present] / lower[present] > gamma).all()


# ----------------------------------------------------------------------------- export


def _probe(slots: np.ndarray, key: np.uint64, bits: int) -> tuple[int, int]:
    """(slot, probes) of ``key`` in one level's open-addressing table (section 4)."""
    s = (int(key) * MULT % 2**64) >> (64 - bits)
    n = 1
    while slots[s] != key:
        assert slots[s] != EMPTY, f"key {int(key)} is not in the hash"
        s = (s + 1) % slots.size
        n += 1
    return s, n


def _unpack(key: int, base: int, k: int) -> list[int]:
    """The k symbols of a packed key, oldest first (section 2.1)."""
    out = []
    for _ in range(k):
        out.append(key % base)
        key //= base
    return out[::-1]


def _sparse_levels(manifest: dict) -> list[dict]:
    per_level = next(
        v
        for v in manifest.values()
        if isinstance(v, list) and v and isinstance(v[0], dict) and "kind" in v[0]
    )
    return [e for e in per_level if str(e["kind"]).lower().startswith("sparse")]


def _check_export(scorer, path: Path, manifest: dict, windows: list) -> None:
    """Layout invariants, longest-probe windows and bit-for-bit ``reference_logprobs``."""
    n, base, dense = scorer.order, scorer.base, scorer.dense_levels
    assert manifest["version"] == "knx-1" and manifest["numbering"] == "LP2-0-57"
    assert manifest["order"] == n and manifest["base"] == base
    assert manifest["dense_levels"] == dense
    assert manifest["fingerprint"] == scorer.fingerprint()
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    assert "manifest" in arrays
    assert arrays["dense_lp"].dtype == np.float32
    assert arrays["dense_lp"].size == sum(base**k for k in range(1, dense + 1))
    assert (arrays["dense_lp"] <= 0).all() and np.isfinite(arrays["dense_lp"]).all()
    if dense < n:
        assert arrays["dense_bow"].shape == (base**dense,) and (arrays["dense_bow"] <= 0).all()
    assert arrays["discounts"].ndim == 1 and arrays["discounts"].size == 3 * n  # all 1-D
    assert np.array_equal(
        arrays["discounts"].reshape(n, 3), np.asarray(scorer.discounts, dtype=np.float64)
    )
    levels = _sparse_levels(manifest)
    assert len(levels) == n - dense
    assert arrays["hash_keys"].dtype == arrays["sorted_keys"].dtype == np.uint64
    off_h = off_s = 0
    for e in levels:
        m, slots, bits = int(e["n_entries"]), int(e["slots"]), int(e["bits"])
        assert m > 0 and slots == 2**bits and slots >= 2 * m and slots // 2 < 2 * m
        assert _hex(e["empty_key"]) == int(EMPTY) and _hex(e["mult"]) == MULT
        assert int(e["shift"]) == 64 - bits
        assert int(e["offset"]) == off_h and int(e.get("sorted_offset", off_s)) == off_s
        keys = arrays["sorted_keys"][off_s : off_s + m]
        lp = arrays["sorted_lp"][off_s : off_s + m]
        bow = arrays["sorted_bow"][off_s : off_s + m]
        hk = arrays["hash_keys"][off_h : off_h + slots]
        hlp = arrays["hash_lp"][off_h : off_h + slots]
        hbow = arrays["hash_bow"][off_h : off_h + slots]
        assert (np.diff(keys.astype(np.int64)) > 0).all()  # ascending, no duplicates
        assert int((hk != EMPTY).sum()) == m
        assert np.array_equal(np.sort(hk[hk != EMPTY]), keys)
        longest = (0, 0)
        for i in range(m):
            s, probes = _probe(hk, keys[i], bits)
            assert probes <= int(e["max_probe"])
            assert hlp[s] == lp[i] and hbow[s] == bow[i]
            if probes > longest[0]:
                longest = (probes, int(keys[i]))
        assert longest[0] == int(e["max_probe"])
        windows.append(np.array(_unpack(longest[1], base, levels.index(e) + dense + 1)))
        off_h += slots
        off_s += m
    assert off_h == arrays["hash_keys"].size and off_s == arrays["sorted_keys"].size
    loaded = _load_export(path)
    assert loaded.fingerprint() == scorer.fingerprint()
    assert loaded.order == n and loaded.base == base and loaded.dense_levels == dense
    for w in windows:
        if base == 30:  # wb: a window is runes + starts, section 2.5
            runes, starts, end = _unextend(w)
            if runes.size == 0:
                continue
            kw = {"starts": starts, "end_boundary": end}
        else:
            runes, kw = np.asarray(w, dtype=np.int64), {}
        want = scorer.logprobs(runes, **kw)
        assert np.array_equal(loaded.logprobs(runes, **kw), want)
        assert np.array_equal(loaded.reference_logprobs(runes, **kw), want)
        assert np.array_equal(scorer.reference_logprobs(runes, **kw), want)


@pytest.mark.parametrize("name", MODELS)
def test_export_round_trips_bit_for_bit(toy, name, tmp_path):
    scorer, chain = toy[name], toy["chain"]
    path = tmp_path / f"{name}.npz"
    manifest = _manifest_of(scorer.export(path), path)
    rng = np.random.default_rng(len(name))
    windows = [rng.integers(0, 29, 40) for _ in range(500)]  # random
    windows += [chain.seq(40) for _ in range(100)]  # held out: same source, never fitted
    windows += [np.zeros(40, dtype=np.int64), np.full(40, 28)]  # all-F, max key
    if name == "wb3":
        windows = [_extend(w, rng.random(40) < 0.25, False) for w in windows]
    _check_export(scorer, path, manifest, windows)


def test_an_export_names_its_training_and_lookup_rule(toy, tmp_path):
    path = tmp_path / "sparse.npz"
    manifest = _manifest_of(toy["sparse"].export(path), path)
    assert manifest["key_packing"] and manifest["score_rule"]
    assert "training" in manifest and "fingerprint" in manifest
    for e in _sparse_levels(manifest):
        assert e["discount_source"] in SOURCES and e["count_type"]
        assert len(e["discounts"]) == 3 and len(e["counts_of_counts"]) >= 4


# ----------------------------------------------------------------------------- fingerprint


def test_fingerprint_pins_the_arrays_order_base_and_dense_levels(toy):
    nb = toy["nb"]
    a, b = _fit(nb, 3, dense_levels=3), _fit(nb, 3, dense_levels=3)
    assert a.fingerprint() == b.fingerprint() == toy["dense"].fingerprint()
    assert len(a.fingerprint()) == 64 and int(a.fingerprint(), 16) >= 0
    changed = [s.copy() for s in nb]
    changed[1][7] = (changed[1][7] + 1) % 28
    assert _fit(changed, 3, dense_levels=3).fingerprint() != a.fingerprint()
    assert _fit(nb, 4, dense_levels=4).fingerprint() != a.fingerprint()  # order
    assert _fit(nb, 4, dense_levels=2).fingerprint() != _fit(nb, 4, dense_levels=4).fingerprint()
    assert _fit(nb, 3, base=30, dense_levels=3).fingerprint() != a.fingerprint()  # base
    assert _fit(nb, 3, dense_levels=3, discounts=[[0.5, 0.5, 0.5]] * 3).fingerprint() != (
        a.fingerprint()
    )


@pytest.mark.parametrize("name", ["lp-ngram3", "lp-ngram3-heldout"])
def test_phase_1_fingerprints_are_unchanged(name):
    """The ``model: ngram`` entries stay byte-identical: their shipped calibrations are pinned
    to these fingerprints (runeforge/scoring/calib/presets/)."""
    spec = presets.PRESETS[name]
    assert spec.get("model", "ngram") == "ngram" and spec["order"] == 3
    assert presets.get(name).fingerprint() == PHASE1_FINGERPRINTS[name]
    for length in (120, 240):
        rec = calib.load(f"{name}:rigid", length)
        assert rec["scorer_fingerprint"] == PHASE1_FINGERPRINTS[name]


@pytest.mark.raw
@pytest.mark.parametrize("name", ["cicada-ngram3", "general-ngram3"])
def test_phase_1_corpus_fingerprints_are_unchanged(name):
    _need_corpus(presets.PRESETS[name]["train"][0])
    assert presets.get(name).fingerprint() == PHASE1_FINGERPRINTS[name]
    assert calib.load(f"{name}:rigid", 240)["scorer_fingerprint"] == PHASE1_FINGERPRINTS[name]


# ----------------------------------------------------------------------------- beam tables


def test_dense_tables_are_identity_stable_and_equal_log2_distribution(toy):
    scorer = toy["dense"]
    t = scorer.tables
    assert t is scorer.tables and isinstance(t, list) and len(t) == 3
    for i, tab in enumerate(t):
        assert tab.shape == (29**i, 29) and tab.dtype == np.float32
        assert np.isfinite(tab).all() and (tab <= 0).all()
        assert np.abs(np.exp2(tab.astype(np.float64)).sum(axis=1) - 1).max() <= 1e-5
    rng = np.random.default_rng(1)
    for h in [[], [3], [0, 28], [28, 28], [5, 7], [4, 4], *rng.integers(0, 29, (20, 2)).tolist()]:
        row = 0
        for s in h:
            row = row * 29 + s
        d = np.log2(np.asarray(scorer.distribution(h), dtype=np.float64))
        assert np.abs(t[len(h)][row] - d).max() <= 1e-5, h
    assert beam._tables(scorer) is beam._tables(scorer)  # cached by list identity


@pytest.mark.parametrize("name", ["sparse", "wb3"])
def test_sparse_and_wb_models_refuse_tables(toy, name):
    with pytest.raises(AttributeError, match="rigid decoder"):
        _ = toy[name].tables


def test_presets_table_follows_the_design():
    for name, (order, base, dense, compatible) in KN_PRESETS.items():
        spec = presets.PRESETS[name]
        assert spec["model"] == "kn" and spec["order"] == order, name
        assert spec.get("dense_levels", order) == dense, name
        assert (spec.get("boundary") == BOUNDARY) == (base == 30), name
        assert presets.beam_compatible(name) is compatible, name
        assert name in presets.names()
    assert presets.beam_compatible("lp-ngram3-heldout")  # the Phase 1 tables stay beam-ready
    assert presets.PRESETS["kn4-lp-heldout"]["train"] == ["lp-solved"]
    assert set(presets.PRESETS["kn4-lp-heldout"]["exclude"]) == {"a-koan-1", "the-loss-of-divinity"}
    assert presets.PRESETS["kn4-cicada"]["train"] == ["cicada-english"]
    assert presets.PRESETS["kn8-general"]["train"] == ["english-general"]
    assert presets.PRESETS["kn8-vowel-dropped"]["train"] == ["vowel-dropped-english"]
    assert presets.PRESETS["kn8-cicada-wb"]["train"] == ["cicada-english"]
    assert presets.DECODERS == ("rigid", "beam", "beam-skip", "beam-skip-int")


def test_split_preset_refuses_sparse_and_wb_scorers_with_a_beam_decoder():
    dense = "kn4-lp-heldout"
    assert presets.split_preset(f"{dense}:beam-skip-int") == (dense, "beam-skip-int")
    assert presets.split_preset("kn4-cicada:beam") == ("kn4-cicada", "beam")
    assert presets.split_preset("kn5-cicada:beam-skip") == ("kn5-cicada", "beam-skip")
    assert presets.split_preset("kn8-cicada") == ("kn8-cicada", "rigid")
    assert presets.split_preset("kn8-cicada:rigid") == ("kn8-cicada", "rigid")
    for bad in ("kn8-cicada:beam", "kn6-cicada:beam-skip", "kn8-general:beam-skip-int"):
        with pytest.raises(KeyError, match="kn4-cicada"):
            presets.split_preset(bad)
    for bad in ("kn8-cicada-wb", "kn8-cicada-wb:rigid", "kn8-cicada-wb:beam"):
        with pytest.raises(KeyError):
            presets.split_preset(bad)


def _lane(**over) -> LaneSpec:
    spec = {
        "lane_id": "KN-TOY",
        "hypothesis": "toy KN lane (test fixture)",
        "family": "prng",
        "generator": "numpy-pcg64",
        "seed_range": [0, 2**32],
        "window": 240,
        "pages": [0, 1, 2, 3, 4, 5],
        "preset": "kn4-lp-heldout:beam-skip-int",
        "filter_model": "anti-repeat",
        "interrupt_prob": 1.0,
        "control": {"planted_seed": 3301, "synthetic_page": "solved:a-koan-1", "decoys": 199},
    }
    spec.update(over)
    return LaneSpec(**spec)


def test_lane_spec_refuses_the_same_presets():
    assert _lane().decoder_problems() == []
    assert _lane(preset="kn8-cicada:rigid").decoder_problems() == []
    for bad in ("kn8-cicada:beam", "kn8-cicada-wb:rigid", "kn8-cicada-wb:beam-skip"):
        with pytest.raises(ValidationError):
            _lane(preset=bad)
    # belt and braces: a spec that got past validation is still refused by decoder_problems
    sneaked = _lane().model_copy(update={"preset": "kn8-cicada:beam"})
    problems = sneaked.decoder_problems()
    assert problems and any("kn8-cicada" in p for p in problems)


# ----------------------------------------------------------------------------- beam replay


def _beam_case() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(29)
    c = rng.integers(0, 29, 120)
    c[10:40:3] = 0  # canonical F's
    return c, rng.integers(0, 29, (16, 120))


def _beam_parity(scorer):
    assert scorer.order == 4 and len(scorer.tables) == 4
    c, keys = _beam_case()
    # the scorer-only beam (no interrupters, no skips) sums exactly what score_batch sums
    res = beam.decode_batch(c, keys, scorer, beam.BeamModel(interrupt_prob=0.0, p_keep=None))
    assert np.array_equal(res.plain, (c[None, :] - keys) % 29)
    assert np.abs(res.objective - scorer.score_batch(res.plain) * 120).max() <= 1e-9
    # the numpy decoder and the scalar reference agree path for path under every decoder
    for decoder in ("beam", "beam-skip", "beam-skip-int"):
        model = presets.beam_model(decoder)
        res = beam.decode_batch(c, keys[:4], scorer, model)
        for row in range(4):
            ref = beam.decode_reference(c, keys[row], scorer, model)
            assert ref.plain == res.plain[row].tolist(), decoder
            assert ref.objective == res.objective[row], decoder
            got = beam.record_from(res, row, model)
            assert (got.interrupts, got.skips, got.fill) == (ref.interrupts, ref.skips, ref.fill)


def _gpu_twin(scorer):
    pytest.importorskip("numba")
    from runeforge.gpu import beam_kernel as bk

    c, keys = _beam_case()
    model = presets.beam_model("beam-skip-int")
    (rs, ro), (ks, ko) = bk.score_reference(c, keys, scorer, model), bk.score_cpu(
        c, keys, scorer, model
    )
    assert np.array_equal(np.isnan(rs), np.isnan(ks))
    ok = ~np.isnan(rs)
    assert np.abs(rs[ok] - ks[ok]).max() <= 1e-6 and np.abs(ro[ok] - ko[ok]).max() <= 1e-6


def test_beam_replay_parity_under_kn4_lp_heldout():
    scorer = presets.get("kn4-lp-heldout")
    assert isinstance(scorer, kn.KNScorer) and scorer.base == 29 and scorer.dense_levels == 4
    _beam_parity(scorer)


def test_gpu_twin_parity_under_kn4_lp_heldout():
    _gpu_twin(presets.get("kn4-lp-heldout"))


@pytest.mark.raw
def test_beam_replay_parity_under_kn4_cicada():
    _need_corpus()
    _beam_parity(presets.get("kn4-cicada"))


@pytest.mark.raw
def test_gpu_twin_parity_under_kn4_cicada():
    _need_corpus()
    _gpu_twin(presets.get("kn4-cicada"))


@pytest.mark.parametrize("sid", ["welcome", "a-koan-2", "an-end"])
def test_welcome_interrupters_are_rederived_under_kn4_lp_heldout(sid):
    """11 of WELCOME's 25 ciphertext F's (2 of 5, 1 of 5 on the other keyed sections) from
    the key alone; the scorer trained on these pages, so this is mechanics, not power."""
    s = next(x for x in canon.load_solved_sections() if x.id == sid)
    scorer = presets.get("kn4-lp-heldout")
    plain, chosen = interrupts.decode_beam(s.cipher, from_method(s.method), scorer)
    assert chosen == sorted(s.interrupts)
    assert np.array_equal(plain, s.plain)
    if sid == "welcome":
        assert len(chosen) == 11 and int((s.cipher == interrupts.F).sum()) == 25
        assert (
            scorer.score(plain)
            > -5.0
            > scorer.score(interrupts.decode_rigid(s.cipher, from_method(s.method)))
        )


# ----------------------------------------------------------------------------- held out


def test_held_out_refusals_on_the_canon_trained_preset():
    presets.check_held_out("kn4-lp-heldout", "solved:a-koan-1")
    presets.check_held_out("kn4-lp-heldout", "solved:the-loss-of-divinity")
    for src in ("solved", "solved:welcome", "solved:a-koan-2"):
        with pytest.raises(ValueError, match="training data"):
            presets.check_held_out("kn4-lp-heldout", src)
    with pytest.raises(ValueError):
        presets.check_held_out("kn4-lp-heldout", "file:./lp-solved")


@pytest.mark.raw
def test_held_out_refusals_follow_derived_corpora():
    _need_corpus()
    _need_corpus("vowel-dropped-english")
    with pytest.raises(ValueError, match="training"):  # 90 % trained is still trained
        presets.check_held_out("kn4-cicada", "corpus:cicada-english")
    with pytest.raises(ValueError):
        presets.check_held_out("kn8-general", "corpus:vowel-dropped-english")
    with pytest.raises(ValueError):
        presets.check_held_out("kn8-vowel-dropped", "corpus:english-general")
    with pytest.raises(ValueError):
        presets.check_held_out("kn8-cicada-wb", "corpus:cicada-english")
    presets.check_held_out("kn8-general", "corpus:latin")
    presets.check_held_out("kn4-cicada", "solved:welcome")  # lp-solved is a lane control
    presets.check_held_out("kn4-cicada", "corpus:english-general")
    with pytest.raises(ValueError, match="unknown corpus"):
        presets.check_held_out("kn4-cicada", "corpus:./cicada-english")


def _packed(x: np.ndarray, k: int) -> np.ndarray:
    """Packed k-gram keys of a rune stream (29**12 < 2**64)."""
    keys = np.zeros(x.size - k + 1, dtype=np.uint64)
    for j in range(k):
        keys = keys * np.uint64(29) + x[j : x.size - k + 1 + j].astype(np.uint64)
    return keys


@pytest.mark.raw
def test_heldout_stream_is_the_word_aligned_tail():
    _need_corpus()
    c = corpus.load("cicada-english")
    train = presets.training_slice("cicada-english")
    train = np.asarray(train[0] if isinstance(train, tuple) else train, dtype=np.int64)
    tail, ids = presets.heldout_stream("cicada-english")
    tail, ids = np.asarray(tail, dtype=np.int64), np.asarray(ids, dtype=np.int64)
    n_train = math.floor(Fraction(9, 10) * c.n_words)
    assert n_train == 67322
    cut = int(np.searchsorted(c.word_ids, n_train))  # the first rune of word n_train
    assert train.size == cut and tail.size == len(c) - cut
    assert np.array_equal(np.concatenate([train, tail]), c.runes)
    assert c.word_ids[cut] == n_train and c.word_ids[cut - 1] == n_train - 1
    assert ids[0] == 0 and (np.diff(ids) >= 0).all()
    assert np.array_equal(ids, c.word_ids[cut:] - n_train)
    presets.get("kn4-cicada")  # fills and checks the split against the built corpus
    split = presets.PRESETS["kn4-cicada"]["split"]
    assert split["train_words"] == n_train and split["n_words"] == c.n_words
    assert split["indices_sha256"] == c.meta["indices_sha256"]
    assert "0.9" in split["rule"]
    # a 12-gram found only in the tail: the held-out text is not a copy of the training text
    seen = set(_packed(train, 12).tolist())
    tail_keys = _packed(tail[:5000], 12)
    only = [i for i, k in enumerate(tail_keys.tolist()) if k not in seen]
    assert only, "the first 5,000 tail runes repeat the training text 12-gram for 12-gram"
    assert tail_keys[only[0]] in set(_packed(c.runes, 12).tolist())  # the whole corpus has it


@pytest.mark.raw
def test_a_moved_split_is_refused_not_refit(monkeypatch):
    _need_corpus()
    presets.get("kn4-cicada")
    split = presets.PRESETS["kn4-cicada"]["split"]
    monkeypatch.setitem(split, "train_words", split["train_words"] - 1)
    presets.get.cache_clear()
    try:
        with pytest.raises((ValueError, RuntimeError)):
            presets.get("kn4-cicada")
    finally:
        presets.get.cache_clear()


# ----------------------------------------------------------------------------- boundaries


def test_boundary_extension_inserts_29_before_every_start(toy):
    wb, nb = toy["wb3"], toy["dense"]
    x = np.array([3, 4, 5, 6])
    starts = np.array([True, False, True, False])
    assert wb.boundary_extend(x, starts, False).tolist() == [29, 3, 4, 29, 5, 6]
    assert wb.boundary_extend(x, starts, True).tolist() == [29, 3, 4, 29, 5, 6, 29]
    cut = starts.copy()
    cut[0] = False  # a window that cuts into a word
    assert wb.boundary_extend(x, cut, False).tolist() == [3, 4, 29, 5, 6]
    rows = np.array([[3, 4, 5, 6], [7, 8, 9, 10]])
    ext = wb.boundary_extend(rows, starts, True)
    assert ext.shape == (2, 7) and ext[1].tolist() == [29, 7, 8, 29, 9, 10, 29]
    assert wb.boundary_extend(x, np.zeros(4, dtype=bool), False).tolist() == [3, 4, 5, 6]
    rng = np.random.default_rng(2)
    for _ in range(20):
        r = rng.integers(0, 29, (3, 30))
        m = rng.random(30) < 0.3
        assert np.array_equal(wb.boundary_extend(r, m, True), _extend(r, m, True))
        assert np.array_equal(wb.boundary_extend(r[0], m, False), _extend(r[0], m, False))
    with pytest.raises(ValueError):
        wb.boundary_extend(x, starts[:3], False)
    with pytest.raises(ValueError):  # an nb model has no boundary symbol
        nb.boundary_extend(x, starts, False)
    with pytest.raises(ValueError):
        nb.score_batch(rows, starts=starts)


def test_wb_scores_divide_by_the_cipher_runes(toy):
    scorer = toy["wb3"]
    rng = np.random.default_rng(5)
    x = rng.integers(0, 29, (3, 60))
    starts = rng.random(60) < 0.3
    starts[0] = True
    ext = _extend(x, starts, True)
    assert ext.shape == (3, 60 + int(starts.sum()) + 1)
    lp = scorer.logprobs(x[0], starts=starts, end_boundary=True)
    assert lp.shape == (ext.shape[1],)
    assert abs(scorer.score(x[0], starts=starts, end_boundary=True) - lp.sum() / 60) <= 1e-9
    batch = scorer.score_batch(x, starts=starts, end_boundary=True)
    assert abs(batch[0] - lp.sum() / 60) <= 1e-9
    plain = scorer.score_batch(x, starts=starts)
    assert not np.array_equal(plain, batch)  # the trailing boundary is scored
    with pytest.raises(ValueError):
        scorer.score_batch(x)
    with pytest.raises(ValueError):
        scorer.score(x[0])


def test_window_starts_come_from_the_canon_words():
    from runeforge.scoring import boundaries

    lengths = np.asarray(boundaries.lp2_word_lengths())
    assert lengths.size == 2928 and lengths.max() == 14 and lengths.min() >= 1
    assert abs(lengths.mean() - 4.42) < 0.01
    lp2 = canon.load_lp2()
    words = [len(w) for p in (0, 1) for w in lp2.page(p).words()]
    starts = boundaries.window_starts([0, 1], 240)
    assert starts.dtype == bool and starts.shape == (240,) and starts[0]
    want = np.zeros(240, dtype=bool)
    for pos in np.cumsum([0, *words[:-1]]):
        if pos < 240:
            want[pos] = True
    assert np.array_equal(starts, want)
    full = np.zeros(sum(words), dtype=bool)
    full[np.cumsum([0, *words[:-1]])] = True
    assert sum(words) >= 243 and np.array_equal(starts, full[:240])
    off = boundaries.window_starts([0, 1], 240, offset=3)
    assert np.array_equal(off, full[3:243]) and off[0] == full[3]
    with pytest.raises(ValueError):
        boundaries.window_starts([0, 1], 240, offset=sum(words) - 239)
    ids = np.array([0, 0, 1, 1, 1, 2])
    assert boundaries.corpus_starts(ids).tolist() == [True, False, True, False, False, True]
    rng = np.random.default_rng(1)
    sampled = boundaries.sample_starts(rng, 240, lengths)
    assert sampled.dtype == bool and sampled.shape == (240,)
    gaps = np.diff(np.flatnonzero(sampled))
    assert gaps.size and gaps.min() >= 1 and gaps.max() <= 14
    again = boundaries.sample_starts(np.random.default_rng(1), 240, lengths)
    assert np.array_equal(sampled, again)


# ----------------------------------------------------------------------------- calibration


def test_calib_calibrate_and_load_on_a_kn_preset(monkeypatch, tmp_path):
    scorer = presets.get("kn4-lp-heldout")
    rec = calib.calibrate(scorer, "kn4-lp-heldout", "rigid", 120, draws=25_000)
    assert rec["preset"] == "kn4-lp-heldout:rigid" and rec["L"] == 120
    assert rec["scorer_fingerprint"] == scorer.fingerprint()
    assert rec["fit"]["beta"] > 0 and math.isfinite(rec["null"]["mean"])
    assert rec["null"]["mean"] < -5.0  # uniform noise sits below the English band
    assert rec["check"]["max_error"] < 3 * rec["fit"]["beta"], rec["check"]
    monkeypatch.setattr(calib, "CALIB_DIR", tmp_path)
    calib.path_for("kn4-lp-heldout:rigid", 120).write_text(json.dumps(rec), encoding="utf-8")
    assert calib.load("kn4-lp-heldout:rigid", 120)["fit"] == rec["fit"]
    t = calib.threshold_for(10**6, "kn4-lp-heldout:rigid", 120)
    assert t.regime == "gumbel" and t.bar > rec["null"]["mean"] and t.expected_false_positives < 1
    calib.path_for("kn4-lp-heldout:rigid", 240).write_text(
        json.dumps({**rec, "L": 240, "scorer_fingerprint": "0" * 64}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="refit"):
        calib.load("kn4-lp-heldout:rigid", 240)


# ----------------------------------------------------------------------------- determinism


def test_the_fit_is_deterministic_across_processes():
    code = (
        "from runeforge.scoring import presets; "
        "print(presets.get('kn4-lp-heldout').fingerprint())"
    )
    outs = []
    for _ in range(2):
        r = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True
        )
        assert r.returncode == 0, r.stderr[-2000:]
        outs.append(r.stdout.strip())
    assert outs[0] == outs[1] == presets.get("kn4-lp-heldout").fingerprint()


# ----------------------------------------------------------------------------- corpus presets


@pytest.mark.raw
def test_kn8_cicada_separates_held_out_text_from_noise():
    """Not a bar: a sanity band. Uniform noise at order 8 is expected around -7..-8 (section
    2.4); held-out Cicada-register text scores well above it under the same scorer."""
    _need_corpus()
    scorer = presets.get("kn8-cicada")
    assert scorer.order == 8 and scorer.dense_levels == 4 and scorer.base == 29
    rng = np.random.default_rng(8)
    noise = scorer.score_batch(rng.integers(0, 29, (2000, 240)))
    assert -9.5 < noise.mean() < -6.0
    tail, _ = presets.heldout_stream("cicada-english")
    offs = rng.integers(0, tail.size - 240, 200)
    text = scorer.score_batch(np.stack([tail[o : o + 240] for o in offs]))
    assert text.mean() > noise.mean() + 2.0 and text.min() > noise.max()
    with pytest.raises(AttributeError, match="rigid decoder"):
        _ = scorer.tables


@pytest.mark.raw
def test_kn8_cicada_wb_scores_with_the_windows_mask():
    from runeforge.scoring import boundaries

    _need_corpus()
    scorer = presets.get("kn8-cicada-wb")
    assert scorer.base == 30 and scorer.boundary == BOUNDARY and scorer.dense_levels == 4
    tail, ids = presets.heldout_stream("cicada-english")
    starts = boundaries.corpus_starts(ids[1000:1240])
    rows = np.stack([tail[1000:1240], np.random.default_rng(0).integers(0, 29, 240)])
    scores = scorer.score_batch(rows, starts=starts)
    assert np.isfinite(scores).all() and scores[0] > scores[1] + 2.0
    with pytest.raises(ValueError):
        scorer.score_batch(rows)
    with pytest.raises(AttributeError, match="rigid decoder"):
        _ = scorer.tables


@pytest.mark.raw
@pytest.mark.slow
def test_kn8_cicada_export_round_trips(tmp_path):
    _need_corpus()
    scorer = presets.get("kn8-cicada")
    path = tmp_path / "kn8-cicada.npz"
    manifest = _manifest_of(scorer.export(path), path)
    rng = np.random.default_rng(88)
    tail, _ = presets.heldout_stream("cicada-english")
    windows = [rng.integers(0, 29, 240) for _ in range(500)]
    windows += [tail[o : o + 240] for o in rng.integers(0, tail.size - 240, 100)]
    windows += [np.zeros(240, dtype=np.int64), np.full(240, 28)]
    _check_export(scorer, path, manifest, windows)


@pytest.mark.raw
@pytest.mark.slow
def test_throughput_smoke():
    _need_corpus()
    rng = np.random.default_rng(0)
    for name in ("kn4-cicada", "kn8-cicada"):
        scorer = presets.get(name)
        x = rng.integers(0, 29, (20_000, 240))
        scorer.score_batch(x[:100])  # warm
        t0 = time.perf_counter()
        s = scorer.score_batch(x)
        dt = time.perf_counter() - t0
        assert np.isfinite(s).all()
        print(f"{name}: {20_000 / dt:,.0f} keys/s at L=240 ({dt:.2f} s for 20,000 rows)")


# ------------------------------------------------------------------ review fixes (2026-10-27)


def test_load_export_tolerates_null_counts_of_counts(toy, tmp_path):
    """A KNScorer built directly (no counts_of_counts / count_type) exports them as null per
    level; load_export rebuilds it instead of raising."""
    est = kn_fit.estimate(toy["nb"], 3, base=29, dense_levels=1)
    m = kn.KNScorer(
        est.order, est.base, est.dense_levels, None, est.dense_lp, est.dense_bow, est.sparse,
        est.discounts, est.discount_source,
    )  # fmt: skip
    assert m.counts_of_counts is None and m.count_type is None
    path = tmp_path / "bare.npz"
    man = m.export(path)
    assert all(
        lev["counts_of_counts"] is None and lev["count_type"] is None for lev in man["levels"]
    )
    r = _load_export(path)
    assert r.counts_of_counts is None and r.count_type is None
    assert r.fingerprint() == m.fingerprint()
    x = toy["chain"].seq(60)
    assert np.array_equal(r.logprobs(x), m.logprobs(x))


def test_export_embeds_the_side_files_exact_text(toy, tmp_path):
    """runeforge/gpu/kernels/README.md: the ``manifest`` array is the side file's text."""
    path = tmp_path / "sparse.npz"
    toy["sparse"].export(path)
    with np.load(path, allow_pickle=False) as z:
        embedded = str(z["manifest"])
    side = path.with_suffix(".json").read_text(encoding="utf-8")
    assert embedded == side and side.endswith("\n") and json.loads(side)["version"] == "knx-1"


@pytest.mark.parametrize("name", ["dense", "sparse", "wb3"])
def test_row_chunking_changes_no_number(toy, name, monkeypatch):
    """score_batch / _logprobs_rows work on row chunks (kn.ROW_CHUNK_POSITIONS): the same
    bits whatever the chunk size, since a row's sum is its own np.sum."""
    scorer = toy[name]
    rng = np.random.default_rng(5)
    x = rng.integers(0, 29, (37, 53))
    kw = {"starts": rng.random(53) < 0.2} if name == "wb3" else {}
    want = scorer.score_batch(x, **kw)
    want_lp = scorer._logprobs_rows(scorer._prepare(x, kw.get("starts"), False)[0])
    for positions in (1, 53, 100, 53 * 7, 10**9):
        monkeypatch.setattr(kn, "ROW_CHUNK_POSITIONS", positions)
        assert np.array_equal(scorer.score_batch(x, **kw), want), positions
        got = scorer._logprobs_rows(scorer._prepare(x, kw.get("starts"), False)[0])
        assert np.array_equal(got, want_lp), positions
    monkeypatch.setattr(kn, "ROW_CHUNK_POSITIONS", 1)
    assert scorer._row_chunks(5, 7) == [(i, i + 1) for i in range(5)]
    monkeypatch.setattr(kn, "ROW_CHUNK_POSITIONS", 2_000_000)
    assert scorer._row_chunks(50_000, 1000) == [(a, a + 2000) for a in range(0, 50_000, 2000)]


def test_a_wb_model_refuses_rune_29_in_a_decode(toy):
    """Decodes are rune rows (0..28); the boundary symbol is inserted by boundary_extend,
    never supplied, so 29 in a row is an error for a wb model as it is for an nb model."""
    wb, nb = toy["wb3"], toy["dense"]
    starts = np.zeros(5, dtype=bool)
    with pytest.raises(ValueError, match=r"rune outside 0\.\.28"):
        wb.score_batch(np.full((1, 5), 29), starts=starts)
    with pytest.raises(ValueError, match=r"rune outside 0\.\.28"):
        wb.score(np.array([1, 2, 29, 4, 5]), starts=starts)
    with pytest.raises(ValueError, match=r"rune outside 0\.\.28"):
        nb.score_batch(np.full((1, 5), 29))
    assert np.isfinite(wb.score_batch(np.full((1, 5), 28), starts=starts)).all()
    with pytest.raises(ValueError):
        wb.score_batch(np.full((1, 5), -1), starts=starts)


def test_a_zero_length_window_scores_nan_as_documented(toy):
    sp, wb = toy["sparse"], toy["wb3"]
    assert math.isnan(sp.score(np.zeros(0, dtype=np.int64)))
    assert np.isnan(sp.score_batch(np.zeros((3, 0), dtype=np.int64))).all()
    empty = np.zeros(0, dtype=np.int64)
    lp = wb.logprobs(empty, starts=np.zeros(0, dtype=bool), end_boundary=True)
    assert lp.shape == (1,) and np.isfinite(lp).all()  # the one boundary symbol is scored
    assert math.isnan(wb.score(empty, starts=np.zeros(0, dtype=bool), end_boundary=True))
    assert "NaN" in kn.KNScorer.score.__doc__ and "NaN" in kn.KNScorer.score_batch.__doc__


@pytest.mark.raw
def test_heldout_plant_source_is_refused_for_a_preset_without_a_split():
    """TR-9: the 90/10 tail is held out of a KN preset with a pinned split, and is training
    text for a Phase 1 ngram preset that trains on the whole corpus (or its derived family)."""
    _need_corpus()
    _need_corpus("english-general")
    _need_corpus("vowel-dropped-english")
    presets.check_held_out("kn4-cicada", "heldout:cicada-english")
    presets.check_held_out("kn8-general", "heldout:vowel-dropped-english")
    presets.check_held_out("kn8-latin", "heldout:cicada-english")
    presets.check_held_out("lp-ngram3-heldout", "heldout:cicada-english")
    for scorer, src in (
        ("cicada-ngram3", "heldout:cicada-english"),
        ("general-ngram3", "heldout:english-general"),
        ("general-ngram3", "heldout:vowel-dropped-english"),
    ):
        assert presets.PRESETS[scorer].get("split") is None
        with pytest.raises(ValueError, match="no 90/10 split"):
            presets.check_held_out(scorer, src)
    with pytest.raises(ValueError, match="unknown corpus"):
        presets.check_held_out("kn4-cicada", "heldout:./cicada-english")


def test_a_preset_export_pins_its_training_block(tmp_path):
    """Section 4: the manifest's ``training`` block (corpora, exclude, split, n_runes,
    indices_sha256s) is filled by presets.get, so a preset export carries it."""
    scorer = presets.get("kn4-lp-heldout")
    man = scorer.export(tmp_path / "kn4-lp-heldout.npz")
    t = man["training"]
    assert t["preset"] == "kn4-lp-heldout" and t["corpora"] == ["lp-solved"]
    assert sorted(t["exclude"]) == ["a-koan-1", "the-loss-of-divinity"]
    assert t["n_runes"] > 0 and t["n_sequences"] == 7 and t["split"] is None
    assert t["indices_sha256s"] == {}
    assert _load_export(tmp_path / "kn4-lp-heldout.npz").training == t


@pytest.mark.raw
def test_a_corpus_preset_export_pins_its_split_and_corpus_sha(tmp_path):
    _need_corpus()
    scorer = presets.get("kn4-cicada")
    man = scorer.export(tmp_path / "kn4-cicada.npz")
    t = man["training"]
    assert t["corpora"] == ["cicada-english"] and t["exclude"] == []
    assert t["split"] == presets.SPLITS["cicada-english"]
    assert t["split"]["train_words"] == 67322 and "0.9" in t["split"]["rule"]
    c = corpus.load("cicada-english")
    assert t["indices_sha256s"] == {"cicada-english": c.meta["indices_sha256"]}
    assert 0 < t["n_runes"] < len(c)
    assert _load_export(tmp_path / "kn4-cicada.npz").training == t


def test_sample_starts_is_one_vectorised_draw_of_word_lengths():
    from runeforge.scoring import boundaries

    pool = np.array([3, 5, 7])
    for seed in range(20):
        starts = boundaries.sample_starts(np.random.default_rng(seed), 100, pool)
        assert starts[0]
        gaps = np.diff(np.flatnonzero(starts))
        assert set(gaps.tolist()) <= {3, 5, 7}
        # the mask is the running sum of the same draw
        ends = np.cumsum(np.random.default_rng(seed).choice(pool, size=100))
        want = np.zeros(100, dtype=bool)
        want[ends[ends < 100]] = True
        want[0] = True
        assert np.array_equal(starts, want)
    assert boundaries.sample_starts(np.random.default_rng(0), 0, pool).shape == (0,)
    with pytest.raises(ValueError):
        boundaries.sample_starts(np.random.default_rng(0), 10, np.array([0, 2]))
