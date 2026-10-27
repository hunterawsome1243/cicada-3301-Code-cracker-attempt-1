"""Word-start masks for the word-boundary (wb) Kneser-Ney presets.

Decodes arrive as pure (B, L) rune arrays; where the words start is a property of the
cipher window (``canon.Page.words()``: 2,928 LP2 words, mean length 4.42, max 14) or of the
corpus stream a plant was cut from, never inferred from a decode (docs/kn-scorer-design.md
section 2.5). A mask is ``bool[L]``, True where a word begins; a window that cuts into a
word has ``starts[0] = False``.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def _page_word_lengths(pages: Sequence[int]) -> np.ndarray:
    from runeforge import canon

    lp2 = canon.load_lp2()
    return np.array([len(w) for n in pages for w in lp2.page(n).words()], dtype=np.int64)


def lp2_word_lengths(pages: Sequence[int] | None = None) -> np.ndarray:
    """Lengths of the words on the LP2 pages (0-55 by default), in reading order."""
    from runeforge import canon

    return _page_word_lengths(canon.UNSOLVED_LP2_PAGES if pages is None else pages)


def window_starts(pages: Sequence[int], window: int, offset: int = 0) -> np.ndarray:
    """Word-start mask of ``window`` runes of the stream of ``pages`` (in that order) from
    rune ``offset``: ``starts[i]`` is True iff stream rune ``offset + i`` begins a word."""
    lengths = _page_word_lengths(pages)
    total = int(lengths.sum())
    if offset < 0 or window < 0 or offset + window > total:
        raise ValueError(f"window [{offset}, {offset + window}) is outside the {total}-rune stream")
    starts = np.zeros(total, dtype=bool)
    starts[np.cumsum(lengths[:-1])] = True
    if total:
        starts[0] = True
    return starts[offset : offset + window].copy()


def corpus_starts(word_ids, prev_word_id: int | None = None) -> np.ndarray:
    """Word-start mask of a corpus stream from its word ids: True where the id changes.
    The first rune starts a word unless ``prev_word_id`` (the id of the rune before the
    cut) equals its own id."""
    w = np.asarray(word_ids, dtype=np.int64).ravel()
    starts = np.zeros(w.size, dtype=bool)
    if w.size:
        starts[1:] = w[1:] != w[:-1]
        starts[0] = prev_word_id is None or int(w[0]) != int(prev_word_id)
    return starts


def sample_starts(rng: np.random.Generator, length: int, lengths) -> np.ndarray:
    """A mask of ``length`` positions with word lengths drawn (with replacement) from
    ``lengths`` (LP2's word-length histogram via ``lp2_word_lengths``); the window begins a
    word and its last word may be cut. One vectorised draw of ``length`` word lengths (every
    length is >= 1, so their running sum passes ``length`` within ``length`` words)."""
    pool = np.asarray(lengths, dtype=np.int64).ravel()
    if pool.size == 0 or pool.min() < 1:
        raise ValueError("word lengths must be >= 1")
    starts = np.zeros(length, dtype=bool)
    if length == 0:
        return starts
    ends = np.cumsum(rng.choice(pool, size=length))  # where each drawn word ends
    starts[ends[ends < length]] = True  # the next word starts there
    starts[0] = True
    return starts
