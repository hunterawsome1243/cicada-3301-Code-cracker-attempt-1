"""Language-agnostic statistics of one decode (CLAUDE.md, Doctrine).

Persisted for every survivor, crosser and chunk best, so a sweep can be re-read under a
different register or adjudicator later without re-running it:

* ``ioc_n``            index of coincidence x 29 (1.0 = uniform, English ~1.7-1.8)
* ``min_distinct_32``  fewest distinct runes in any 32-rune window (a stuck key shows here)
* ``order2_entropy``   H(X_i | X_{i-1}) in bits, from bigram and unigram counts
* ``zlib_ratio``       zlib level-9 compressed size / length (one byte per rune)
* ``best_non_english`` the best of the non-English register scorers, by name and score
"""

from __future__ import annotations

import zlib

import numpy as np

from runeforge.gematria import N

# registers other than English with a calibrated-or-not n-gram preset; Phase 2 adds more
NON_ENGLISH_PRESETS = ("latin-ngram3", "old-english-ngram3")


def ioc_n(x: np.ndarray) -> float:
    n = x.size
    if n < 2:
        return float("nan")
    f = np.bincount(x, minlength=N)
    return float((f * (f - 1)).sum() / (n * (n - 1)) * N)


def min_distinct(x: np.ndarray, w: int = 32) -> int:
    if x.size < w:
        return len(set(x.tolist()))
    win = np.lib.stride_tricks.sliding_window_view(x, w)
    return int(min(len(np.unique(r)) for r in win))


def order2_entropy(x: np.ndarray) -> float:
    if x.size < 2:
        return float("nan")
    pairs = np.bincount(x[:-1] * N + x[1:], minlength=N * N).astype(np.float64)
    first = np.bincount(x[:-1], minlength=N).astype(np.float64)
    p2 = pairs[pairs > 0] / pairs.sum()
    p1 = first[first > 0] / first.sum()
    return float(-(p2 * np.log2(p2)).sum() + (p1 * np.log2(p1)).sum())


def zlib_ratio(x: np.ndarray) -> float:
    b = bytes(np.asarray(x, dtype=np.uint8).tolist())
    return len(zlib.compress(b, 9)) / max(len(b), 1)


def best_non_english(x: np.ndarray) -> dict:
    """The best non-English register score of the decode; ``None`` when no such corpus is
    built (the scorers train on data/corpora, scripts/build_corpus.py)."""
    from runeforge.corpus import CorpusMissingError
    from runeforge.scoring import presets

    best = None
    for name in NON_ENGLISH_PRESETS:
        try:
            s = float(presets.get(name).score(x))
        except (CorpusMissingError, FileNotFoundError, KeyError):
            continue
        if best is None or s > best["score"]:
            best = {"register": name, "score": s}
    return best or {"register": None, "score": None, "note": "no non-English corpus built"}


def decode_stats(plain) -> dict:
    x = np.asarray(plain, dtype=np.int64)
    return {
        "ioc_n": ioc_n(x),
        "min_distinct_32": min_distinct(x),
        "order2_entropy": order2_entropy(x),
        "zlib_ratio": zlib_ratio(x),
        "best_non_english": best_non_english(x),
    }
