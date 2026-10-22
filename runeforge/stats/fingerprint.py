"""The LP2 fingerprint (murphy's constraints C1-C6) for any rune stream, the coarse gate
against LP2, and the gate simulator ``runeforge gate`` runs (SESSION_PROMPT.md §C3 step 1).

Why: a cipher family that cannot reproduce LP2's measured surface -- flat IoC, the doublet
deficit with its 63 within-word / 23 cross-word split, a flat conditional IoC, doublets
uniform in position, repeated cipher words at chance -- is not worth a key-space sweep.
Simulating the family on English with >= 12 random keys and grading each ciphertext here
costs seconds. A majority FAIL is ``EXCLUDED (gate)``: it excludes the typical key, not the
family. The bands are deliberately coarse and scaled to the stream's size, so simulate about
as many runes as LP2 has (12,956).

    f = fingerprint(runes, word_ids, line_ids, page_ids)
    for row in gate(f): print(row)          # GateRow(id, value, lp2, band, verdict)
    gate_cipher(encrypt).verdict_line       # GATE PASS | GATE PASS (marginal: ..) | GATE FAIL: ..

Numpy port of murphy ``toolbox/fingerprint.py`` and ``jobs/hypothesis-gate/tools/gate_sim.py``:
same keys, constraints, bands and majority rule; pinned on LP2 in tests/test_fingerprint.py.
Two deliberate differences: the C3 shuffle null draws from numpy's PCG64 instead of Python's
``random`` (same definition, different draws); and the gate's LP2 column shows what this
module measures on LP2 (C3: 15 repeated words, C4: z = -0.81) where murphy printed round one's
16 and +0.9, whose definitions were not recorded.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

from runeforge import canon
from runeforge import corpus as corpora
from runeforge import gematria as gm
from runeforge.gematria import N
from runeforge.stats.basic import ioc_norm

CHI2_001 = {2: 10.83, 3: 13.82, 4: 16.27, 5: 18.47, 6: 20.52, 7: 22.46, 8: 24.32}  # df k-1
# LP2 pages 0-55 as this module measures them (tests/test_fingerprint.py re-derives each).
LP2: dict[str, Any] = {
    "n": 12956,
    "ioc": 1.000,
    "doublets": 86,
    "doublets_within": 63,
    "doublets_cross": 23,
    "doublet_residues_mod5": (18, 21, 16, 11, 20),  # murphy: position = second rune's index
    "cond_ioc": 1.026,
    "lag5_hits": 104,
    "lag5_pairs": 2105,
    "lag5_straddle": (32, 460),
    "repeated_words": 15,  # distinct >= 3-rune words seen twice or more (round one said 16)
    "wordlen_z": -0.81,  # (CONSTRAINTS.md's +0.9 is round one's, definition not recorded)
    "n_words": 2896,
}
HARD = ("C1", "C2", "C2b", "C2c", "C3", "C6")  # C4 (layout) and C5 (soft) do not decide
SYNTH_LINE = 22  # LP2 lines average 21.8 runes
SYNTH_PAGE = 235  # LP2 pages average 235.6 runes
_LP2_SEPARATORS = "-.&$§"  # murphy lpdata: word id += 1
_LP2_IGNORED = set("\n0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


class GateRow(NamedTuple):
    id: str  # "C2b conditional IoC"; the constraint is the first word
    value: Any
    lp2: Any
    band: str
    verdict: str  # PASS | FAIL | INFO | FAIL(soft)

    @property
    def constraint(self) -> str:
        return self.id.split()[0]


@dataclass
class GateResult:
    verdict_line: str
    per_seed_rows: list[list[GateRow]]
    fails_per_constraint: dict[str, int]
    fingerprints: list[dict] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict_line.startswith("GATE PASS")


# --------------------------------------------------------------------------- LP2 streams


def lp2_streams(canon_dir: Path | None = None) -> tuple[np.ndarray, ...]:
    """(runes, word_ids, line_ids, page_ids) of the 12,956-rune unsolved stream (pages 0-55).

    Segmentation follows murphy's ``lp/lpdata.py`` on each page's raw rtkd text: the word id
    advances on ``- . & $ §``; ``/`` advances the line id but does not break a word; a page
    break advances the page and line ids but does not break a word either; digits, newlines
    and the letters of the page-49/51 number grid are ignored. Page ids are LP2 page numbers.
    """
    lp2 = canon.load_lp2(canon_dir)
    r: list[int] = []
    w: list[int] = []
    li: list[int] = []
    pg: list[int] = []
    wid = lid = 0
    for k, n in enumerate(canon.UNSOLVED_LP2_PAGES):
        if k:
            lid += 1
        for c in gm.normalize_glyphs(lp2.page(n).raw):
            if gm.is_rune(c):
                r.append(gm.rune_to_idx(c))
                w.append(wid)
                li.append(lid)
                pg.append(n)
            elif c in _LP2_SEPARATORS:
                wid += 1
            elif c == "/":
                lid += 1
            elif c not in _LP2_IGNORED:
                raise ValueError(f"LP2 page {n}: unexpected character {c!r} in raw text")
    runes = np.array(r, dtype=np.int64)
    if not np.array_equal(runes, canon.unsolved_stream(canon_dir)):
        raise canon.CanonIntegrityError("lp2_streams does not reproduce canon.unsolved_stream()")
    return runes, np.array(w, np.int64), np.array(li, np.int64), np.array(pg, np.int64)


# --------------------------------------------------------------------------- fingerprint


def doublet_positions(runes) -> np.ndarray:
    """Index i of every doublet runes[i] == runes[i-1] (murphy's convention: the second rune)."""
    r = np.asarray(runes, dtype=np.int64)
    return np.flatnonzero(r[1:] == r[:-1]) + 1


def residue_chi2(positions: np.ndarray, k: int) -> float:
    """Pearson chi-square of positions mod k against uniform (df k-1); 0.0 if there are none."""
    if positions.size == 0:
        return 0.0
    c = np.bincount(positions % k, minlength=k)
    e = positions.size / k
    return float(((c - e) ** 2 / e).sum())


def _cond_ioc(r: np.ndarray, page: np.ndarray) -> float:
    """29 x P(two transitions out of the same rune agree), over pairs on one page."""
    same = page[1:] == page[:-1]
    tab = np.bincount(r[:-1][same] * N + r[1:][same], minlength=N * N).reshape(N, N)
    rows = tab.sum(axis=1)
    den = int((rows * (rows - 1)).sum())
    return N * int((tab * (tab - 1)).sum()) / den if den else 0.0


def _word_spans(w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Starts and lengths of maximal runs of equal word id (murphy's ``_words``)."""
    starts = np.concatenate(([0], np.flatnonzero(w[1:] != w[:-1]) + 1))
    return starts, np.diff(np.append(starts, w.size))


def _repeated(r: np.ndarray, starts: np.ndarray, lens: np.ndarray) -> int:
    """Distinct words of >= 3 runes that occur at least twice."""
    b = r.astype(np.int8)
    keep = lens >= 3
    c = Counter(b[s : s + n].tobytes() for s, n in zip(starts[keep], lens[keep], strict=True))
    return sum(1 for v in c.values() if v >= 2)


def fingerprint(
    runes,
    word_ids,
    line_ids=None,
    page_ids=None,
    null_shuffles: int = 5,
    seed: int = 3301,
) -> dict:
    """murphy's fingerprint dict for a rune stream with a word id per rune.

    ``line_ids`` enables ``lag5_straddle``; ``page_ids`` restricts the conditional IoC to
    transitions within a page (None: one page). The C3 null shuffles the runes across the
    whole stream ``null_shuffles`` times and refills the same word lengths.
    """
    r = np.asarray(runes, dtype=np.int64)
    w = np.asarray(word_ids, dtype=np.int64)
    n = r.size
    if w.shape != r.shape or r.ndim != 1:
        raise ValueError("runes and word_ids must be 1-D and the same length")
    if n < 6:
        raise ValueError("need at least 6 runes")
    if null_shuffles < 1:
        raise ValueError("null_shuffles must be >= 1")
    page = np.zeros(n, np.int64) if page_ids is None else np.asarray(page_ids, dtype=np.int64)

    eq = r[1:] == r[:-1]
    same_word = w[1:] == w[:-1]
    d_in = int((eq & same_word).sum())
    d_x = int((eq & ~same_word).sum())

    pair5 = w[:-5] == w[5:]  # within-word pairs at distance 5
    hit5 = pair5 & (r[:-5] == r[5:])
    pairs, hits = int(pair5.sum()), int(hit5.sum())
    straddle = None
    if line_ids is not None:
        line = np.asarray(line_ids, dtype=np.int64)
        cross = line[:-5] != line[5:]
        straddle = (int((hit5 & cross).sum()), int((pair5 & cross).sum()))

    dpos = doublet_positions(r)
    resid = {k: residue_chi2(dpos, k) for k in range(2, 9)}

    starts, lens = _word_spans(w)
    rep = _repeated(r, starts, lens)
    rng = np.random.default_rng(seed)
    rnull = np.array([_repeated(rng.permutation(r), starts, lens) for _ in range(null_shuffles)])

    lf = lens.astype(np.float64)
    mu = lf.mean()
    var = ((lf - mu) ** 2).mean()
    r1 = 0.0
    if var and lf.size > 1:
        r1 = float(((lf[:-1] - mu) * (lf[1:] - mu)).sum() / ((lf.size - 1) * var))
    e = pairs / N
    return {
        "n": int(n),
        "ioc": ioc_norm(r),
        "doublets": d_in + d_x,
        "doublets_within": d_in,
        "doublets_cross": d_x,
        "doublet_rate": (d_in + d_x) / max(1, n - 1),
        "doublet_residue_chi2": resid,
        "cond_ioc": _cond_ioc(r, page),
        "lag5_hits": hits,
        "lag5_pairs": pairs,
        "lag5_rate": hits / max(1, pairs),
        "lag5_z": (hits - e) / math.sqrt(e * (N - 1) / N) if pairs else 0.0,
        "lag5_straddle": straddle,
        "repeated_words": rep,
        "repeated_words_null": (float(rnull.mean()), float(rnull.std())),
        "wordlen_r1": r1,
        "wordlen_z": r1 * math.sqrt(lf.size),
        "n_words": int(lens.size),
    }


# --------------------------------------------------------------------------- gate


def gate(f: dict) -> list[GateRow]:
    """Coarse consistency with LP2, scaled to f's size (accepts a JSON round-tripped f)."""
    k = (f["n"] - 1) / (LP2["n"] - 1)
    sd_ioc = math.sqrt(2 * (N - 1)) / f["n"]
    rows = [
        GateRow(
            "C1 IoC",
            round(f["ioc"], 4),
            LP2["ioc"],
            f"1.000 +- {4 * sd_ioc:.3f}",
            "PASS" if abs(f["ioc"] - 1) <= 4 * sd_ioc + 0.005 else "FAIL",
        )
    ]
    lo, hi = 0.004, 0.010
    rows.append(
        GateRow(
            "C2 doublet rate",
            round(f["doublet_rate"], 5),
            round(LP2["doublets"] / (LP2["n"] - 1), 5),
            f"[{lo:.3f}, {hi:.3f}]",
            "PASS" if lo <= f["doublet_rate"] <= hi else "FAIL",
        )
    )
    rows.append(
        GateRow(
            "C2b conditional IoC",
            round(f["cond_ioc"], 4),
            LP2["cond_ioc"],
            "[0.98, 1.08]",
            "PASS" if 0.98 <= f["cond_ioc"] <= 1.08 else "FAIL",
        )
    )
    resid = {int(m): v for m, v in f["doublet_residue_chi2"].items()}
    worst = max(CHI2_001, key=lambda m: resid[m] / CHI2_001[m])
    ratio = resid[worst] / CHI2_001[worst]
    rows.append(
        GateRow(
            "C2c doublet positions mod 2..8",
            f"mod{worst} chi2 {resid[worst]:.1f}",
            "uniform",
            "every chi2 < its p=0.001 value",
            "INFO" if f["doublets"] < 20 else ("PASS" if ratio < 1 else "FAIL"),
        )
    )
    mu, sd = f["repeated_words_null"]
    z3 = (f["repeated_words"] - mu) / max(sd, 1.0)
    rows.append(
        GateRow(
            "C3 repeated words >=3",
            f["repeated_words"],
            LP2["repeated_words"],
            f"within 3 sd of own shuffle null ({mu:.1f} +- {sd:.1f})",
            "PASS" if z3 <= 3 else "FAIL",
        )
    )
    rows.append(
        GateRow(
            "C4 adjacent word-length z",
            round(f["wordlen_z"], 2),
            LP2["wordlen_z"],
            "|z| < 3 (layout, not cipher)",
            "PASS" if abs(f["wordlen_z"]) < 3 else "INFO",
        )
    )
    rows.append(
        GateRow(
            "C5 within-word lag-5 rate",
            round(f["lag5_rate"], 4),
            round(LP2["lag5_hits"] / LP2["lag5_pairs"], 4),
            "[0.039, 0.060] (soft)",
            "PASS" if 0.039 <= f["lag5_rate"] <= 0.060 else "FAIL(soft)",
        )
    )
    xd = f["doublets_cross"] / k
    rows.append(
        GateRow(
            "C6 cross-word doublets (LP2-size)",
            round(xd, 1),
            LP2["doublets_cross"],
            "[12, 35]",
            "PASS" if 12 <= xd <= 35 else "FAIL",
        )
    )
    return rows


Encrypt = Callable[[np.ndarray, np.ndarray, np.random.Generator], np.ndarray]


def gate_cipher(
    encrypt: Encrypt,
    n: int = 12956,
    seeds: int = 12,
    corpus: str = "cicada-english",
    offset: int = 0,
    corpora_dir: Path | None = None,
) -> GateResult:
    """Simulate a cipher family on ``n`` runes of a corpus and grade it against LP2.

    ``encrypt(plain, word_ids, rng) -> ciphertext`` (one rune 0..28 per plaintext rune); seed
    s draws its key from ``np.random.default_rng(1000 + s)``, so seeds sample the family's own
    key-to-key spread. Synthetic layout: line id i // 22, page id i // 235 (LP2 averages).
    murphy's majority rule: a HARD constraint failing on more than half the seeds fails the
    gate; failing on half or fewer makes the pass marginal.
    """
    if seeds < 1:
        raise ValueError("seeds must be >= 1")
    plain, words = corpora.english_stream(n, corpus, offset, corpora_dir=corpora_dir)
    idx = np.arange(n)
    lines, pages = idx // SYNTH_LINE, idx // SYNTH_PAGE
    fails: dict[str, int] = {}
    per_seed: list[list[GateRow]] = []
    fps: list[dict] = []
    for s in range(seeds):
        c = np.asarray(encrypt(plain.copy(), words.copy(), np.random.default_rng(1000 + s)))
        if c.shape != plain.shape or not np.issubdtype(c.dtype, np.integer):
            raise ValueError("encrypt must return one integer rune per plaintext rune")
        if c.min() < 0 or c.max() >= N:
            raise ValueError("encrypt returned a rune index outside 0..28")
        f = fingerprint(c, words, lines, pages, seed=s)
        rows = gate(f)
        for row in rows:
            if row.constraint in HARD and row.verdict == "FAIL":
                fails[row.constraint] = fails.get(row.constraint, 0) + 1
        per_seed.append(rows)
        fps.append(f)
    hard = sorted(c for c, v in fails.items() if v > seeds / 2)
    marginal = sorted(c for c, v in fails.items() if v <= seeds / 2)
    if hard:
        line = "GATE FAIL: " + " ".join(hard)
    else:
        line = "GATE PASS" + (f" (marginal: {' '.join(marginal)})" if marginal else "")
    return GateResult(line, per_seed, {c: fails[c] for c in HARD if c in fails}, fps)


def _show(f: dict) -> None:
    for k, v in f.items():
        print(f"  {k:22} {v}")
    for row in gate(f):
        print(f"  {row.id:36} {row.value!s:12} LP2 {row.lp2!s:8} band {row.band:46} {row.verdict}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:  # python -m runeforge.stats.fingerprint <corpus>
        name = sys.argv[1]
        r, w = corpora.english_stream(LP2["n"], name)
        print(f"{name}, first {LP2['n']:,} runes:")
        _show(fingerprint(r, w))
    else:
        print("LP2 pages 0-55 (numbering: LP2-0-57):")
        _show(fingerprint(*lp2_streams()))
