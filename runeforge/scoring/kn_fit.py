"""Fitting the Phase 2 Kneser-Ney scorer: pure functions over rune sequences.

Everything here follows docs/kn-scorer-design.md section 2 (model) and section 4 (the hash
layout of the export). ``estimate`` turns sequences into the per-level arrays a
``runeforge.scoring.kn.KNScorer`` is built from; nothing here scores.

Keys: a k-gram packs as ``sum_j x[i-k+1+j] * B**(k-1-j)`` (oldest most significant, newest
least significant). Packing runs in ``np.int64`` (30**8 < 2**40) and the stored key arrays are
``np.uint64`` (the hash layout needs the EMPTY sentinel 2**64 - 1); the two dtypes never meet in
one expression (numpy would promote the pair to float64).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np

HASH_MULT = 0x9E3779B97F4A7C15
EMPTY_KEY = 0xFFFFFFFFFFFFFFFF
DISCOUNT_FLOOR = 0.05
DISCOUNT_SOURCES = (
    "modified-kn",
    "partial:D2<-D1",
    "partial:D3<-D2",
    "partial:D2<-D1,D3<-D2",
    "fallback-0.5",
    "pinned",
)


# --------------------------------------------------------------------------- counts


def pack_grams(seq: np.ndarray, k: int, base: int) -> np.ndarray:
    """Packed k-gram keys of one sequence (int64, one per position i >= k-1)."""
    s = np.asarray(seq, dtype=np.int64)
    if s.size < k:
        return np.zeros(0, dtype=np.int64)
    out = np.zeros(s.size - k + 1, dtype=np.int64)
    for j in range(k):
        out = out * base + s[j : s.size - k + 1 + j]
    return out


def collect_counts(
    sequences: Iterable[Sequence[int]], order: int, base: int
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Raw counts per level k = 1..order: ``(keys int64 ascending, counts int64)``. N-grams
    never cross a sequence join and there is no start symbol."""
    seqs = [np.asarray(s, dtype=np.int64) for s in sequences]
    for s in seqs:
        if s.size and (s.min() < 0 or s.max() >= base):
            raise ValueError(f"symbol outside 0..{base - 1}")
    out = []
    for k in range(1, order + 1):
        parts = [pack_grams(s, k, base) for s in seqs if s.size >= k]
        allk = np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)
        keys, counts = np.unique(allk, return_counts=True)
        out.append((keys.astype(np.int64), counts.astype(np.int64)))
    return out


def continuation_counts(next_keys: np.ndarray, k: int, base: int) -> tuple[np.ndarray, np.ndarray]:
    """N1+(. g) for every k-gram g that is the suffix of a distinct (k+1)-gram: the number of
    distinct (k+1)-grams whose suffix is g. Returns ``(suffix keys ascending, counts)``."""
    suffix = np.asarray(next_keys, dtype=np.int64) % np.int64(base**k)
    keys, counts = np.unique(suffix, return_counts=True)
    return keys.astype(np.int64), counts.astype(np.int64)


def counts_of_counts(counts: np.ndarray) -> list[int]:
    """[n1, n2, n3, n4]: how many grams have effective count exactly 1, 2, 3, 4."""
    c = np.asarray(counts, dtype=np.int64)
    return [int((c == r).sum()) for r in (1, 2, 3, 4)]


# --------------------------------------------------------------------------- discounts


def discounts(n1: int, n2: int, n3: int, n4: int) -> tuple[np.ndarray, str]:
    """Modified Kneser-Ney discounts (Chen & Goodman 1998) with the fixed fallback rule of
    docs/kn-scorer-design.md section 2.3: D1 undefined (n1 == 0 or n2 == 0) -> every discount
    of the level 0.5 (``discount_source`` has no word for a mixed level); otherwise D2
    undefined (n3 == 0) -> D2 = D1; D3+ undefined (n3 == 0 or n4 == 0) -> D3+ = D2; then each
    D_r is clipped to [0.05, r]. Returns ``(float64[3], discount_source)``."""
    if n1 == 0 or n2 == 0:
        d = np.array([0.5, 0.5, 0.5], dtype=np.float64)
        source = "fallback-0.5"
    else:
        y = n1 / (n1 + 2 * n2)
        d1 = 1.0 - 2.0 * y * n2 / n1
        fell = []
        if n3 == 0:
            d2 = d1
            fell.append("D2<-D1")
        else:
            d2 = 2.0 - 3.0 * y * n3 / n2
        if n3 == 0 or n4 == 0:
            d3 = d2
            fell.append("D3<-D2")
        else:
            d3 = 3.0 - 4.0 * y * n4 / n3
        d = np.array([d1, d2, d3], dtype=np.float64)
        source = "modified-kn" if not fell else "partial:" + ",".join(fell)
    d = np.minimum(np.maximum(d, DISCOUNT_FLOOR), np.array([1.0, 2.0, 3.0]))
    return d.astype(np.float64), source


def discount_of(counts: np.ndarray, d: np.ndarray) -> np.ndarray:
    """D(c) per gram: D1 for c == 1, D2 for c == 2, D3+ for c >= 3, 0 for c == 0 (float64)."""
    c = np.asarray(counts, dtype=np.int64)
    out = np.zeros(c.shape, dtype=np.float64)
    out[c == 1] = d[0]
    out[c == 2] = d[1]
    out[c >= 3] = d[2]
    return out


# --------------------------------------------------------------------------- estimate


@dataclass
class SparseLevel:
    """One sparse level k > D: entries for every raw-seen k-gram, keys ascending."""

    keys: np.ndarray  # uint64[M]
    lp: np.ndarray  # float32[M], log2 P_k(gram)
    bow: np.ndarray  # float32[M], log2 gamma_{k+1}(gram as a history); 0.0 unseen / at k = n
    lp64: np.ndarray | None = None  # the float64 values before the cast (fitted models only)
    bow64: np.ndarray | None = None
    p64: np.ndarray | None = None  # float64 P while the level above is being fitted


@dataclass
class Estimate:
    """The per-level arrays of one fit (``KNScorer.from_estimate`` wraps them)."""

    order: int
    base: int
    dense_levels: int
    boundary: int | None
    dense_lp: list[np.ndarray]  # float32[B**k], k = 1..D
    dense_bow: np.ndarray | None  # float32[B**D] iff D < n
    sparse: list[SparseLevel]  # levels D+1..n
    discounts: np.ndarray  # float64[n, 3]
    discount_source: list[str]
    counts_of_counts: list[list[int]]
    count_type: list[str]  # "continuation" | "raw" per level
    n_runes: int
    dense_lp64: list[np.ndarray] = field(default_factory=list)  # log2 P in float64, per level
    dense_bow64: np.ndarray | None = None


def _history_stats(keys: np.ndarray, counts: np.ndarray, base: int, d: np.ndarray):
    """Per distinct history of a level: ``(hist keys ascending, cc(h), gamma(h))`` where
    cc(h) = sum of the effective counts under h and gamma(h) = sum_r D_r N_r(h.) / cc(h).
    Histories whose grams all have count 0 are left out (unseen as a history)."""
    hist = np.asarray(keys, dtype=np.int64) // np.int64(base)
    c = np.asarray(counts, dtype=np.int64)
    hk, inv = np.unique(hist, return_inverse=True)
    cc_h = np.zeros(hk.size, dtype=np.int64)
    np.add.at(cc_h, inv, c)
    disc = np.zeros(hk.size, dtype=np.float64)
    np.add.at(disc, inv, discount_of(c, d))
    seen = cc_h > 0
    gamma = np.ones(hk.size, dtype=np.float64)
    gamma[seen] = disc[seen] / cc_h[seen]
    return hk[seen], cc_h[seen], gamma[seen]


def _find(keys: np.ndarray, query: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``(position, found)`` of every query in ``keys`` (int64 ascending); the position of a
    missing query is clipped into range so it can index safely."""
    if keys.size == 0:
        return np.zeros(query.shape, dtype=np.int64), np.zeros(query.shape, dtype=bool)
    pos = np.minimum(np.searchsorted(keys, query), keys.size - 1)
    return pos, keys[pos] == query


def _lookup_sorted(keys: np.ndarray, values: np.ndarray, query: np.ndarray, what: str):
    """Values of ``query`` keys, every one of which must be present in ``keys``."""
    pos, found = _find(keys, query)
    if not np.all(found):
        raise AssertionError(f"{what} of a seen gram is not a seen gram")
    return values[pos]


def estimate(
    sequences: Iterable[Sequence[int]],
    order: int,
    base: int = 29,
    dense_levels: int = 4,
    boundary: int | None = None,
    pinned_discounts: Sequence[Sequence[float]] | None = None,
    row_check_samples: int = 2_000,
    seed: int = 0,
) -> Estimate:
    """Fit the interpolated modified Kneser-Ney model of docs/kn-scorer-design.md section 2.3.

    Effective counts are continuation counts below the top level and raw counts at the top;
    every level's discounts come from its own counts-of-counts (or ``pinned_discounts``);
    probabilities are built lowest level first in float64, each level's lower-order term read
    back from the finished level below, and cast to float32 once at the end.
    """
    if not 1 <= order <= 8:
        raise ValueError("order must be 1..8")
    if not 1 <= dense_levels <= min(order, 5):
        raise ValueError("dense_levels must be 1..min(order, 5)")
    if boundary is not None and boundary != base - 1:
        raise ValueError("the boundary symbol is the last symbol of the alphabet")
    n, bb, dd = order, base, dense_levels
    seqs = [np.asarray(s, dtype=np.int64) for s in sequences]
    raw = collect_counts(seqs, n, bb)
    n_runes = int(sum(s.size for s in seqs))

    # effective counts per level, on the raw key set U_k (a key seen only at a sequence
    # start has continuation count 0)
    eff: list[np.ndarray] = []
    count_type: list[str] = []
    for k in range(1, n + 1):
        keys, counts = raw[k - 1]
        if k == n:
            eff.append(counts.copy())
            count_type.append("raw")
        else:
            ck, cc = continuation_counts(raw[k][0], k, bb)
            e = np.zeros(keys.size, dtype=np.int64)
            pos, found = _find(keys, ck)
            if not np.all(found):
                raise AssertionError("a suffix of a seen gram is not a seen gram")
            e[pos] = cc
            eff.append(e)
            count_type.append("continuation")

    coc = [counts_of_counts(e) for e in eff]
    disc = np.zeros((n, 3), dtype=np.float64)
    source: list[str] = []
    for k in range(n):
        if pinned_discounts is not None:
            disc[k] = np.asarray(pinned_discounts[k], dtype=np.float64)
            source.append("pinned")
        else:
            disc[k], src = discounts(*coc[k])
            source.append(src)

    rng = np.random.default_rng(seed)
    dense64: list[np.ndarray] = []
    dense_bow64: np.ndarray | None = None
    sparse: list[SparseLevel] = []
    # gamma of every seen history at the level above, stored as bow on this level's entries
    for k in range(1, n + 1):
        keys, counts = raw[k - 1][0], eff[k - 1]
        d = disc[k - 1]
        if k == 1:
            c_tot = int(counts.sum())
            p = np.zeros(bb, dtype=np.float64)
            if c_tot > 0:
                gamma1 = float(discount_of(counts, d).sum()) / c_tot
                p[keys] = np.maximum(counts - discount_of(counts, d), 0.0) / c_tot
            else:
                gamma1 = 1.0
            p += gamma1 / bb
            _check_rows(p[None, :], 1)
            dense64.append(p)
            continue
        hk, cc_h, gamma_h = _history_stats(keys, counts, bb, d)
        hist = keys // np.int64(bb)
        sym = keys % np.int64(bb)
        h_pos, h_seen = _find(hk, hist)
        # P_k(gram) = max(cc - D, 0) / cc(h) + gamma(h) * P_{k-1}(suffix), seen h; else the
        # lower term alone (gamma = 1)
        disc_g = np.maximum(counts - discount_of(counts, d), 0.0)
        cc_of_h = np.where(h_seen, cc_h[h_pos] if hk.size else 1, 1)
        gamma_g = np.where(h_seen, gamma_h[h_pos] if hk.size else 1.0, 1.0)
        own = np.where(h_seen, disc_g / cc_of_h, 0.0)
        lower_mod = np.int64(bb ** (k - 2))
        if k <= dd:
            # the complete level: lower broadcast over every history, seen ones scaled by
            # gamma(h), seen grams overwritten
            lower_tab = dense64[k - 2]  # float64[B**(k-1)]
            n_hist = bb ** (k - 1)
            h_all = np.arange(n_hist, dtype=np.int64)
            lower = lower_tab[(h_all % lower_mod)[:, None] * bb + np.arange(bb)]
            scale = np.ones(n_hist, dtype=np.float64)
            scale[hk] = gamma_h
            p = lower * scale[:, None]
            p[hist, sym] = own + gamma_g * lower_tab[(hist % lower_mod) * bb + sym]
            _check_rows(p, k, rng, row_check_samples)
            dense64.append(p.ravel())
        else:
            # sparse level: one entry per raw-seen gram; the lower term by the model's own
            # lookup on the finished level below (dense gather or sorted search)
            suffix = keys % np.int64(bb ** (k - 1))
            if k - 1 <= dd:
                gram_lower = dense64[k - 2][suffix]
            else:
                below = sparse[-1]
                gram_lower = _lookup_sorted(raw[k - 2][0], below.p64, suffix, "the suffix")
                below.p64 = None
            val = own + gamma_g * gram_lower
            if not np.all(np.isfinite(val)) or (val.size and (val.min() <= 0 or val.max() > 1)):
                raise AssertionError(f"level {k}: a probability outside (0, 1]")
            sparse.append(
                SparseLevel(
                    keys=keys.astype(np.uint64),
                    lp=np.empty(0, dtype=np.float32),
                    bow=np.empty(0, dtype=np.float32),
                    lp64=np.log2(val),
                    bow64=np.zeros(keys.size, dtype=np.float64),
                    p64=val,
                )
            )
        # bow = log2 gamma_k(h) of every seen history, stored on level k-1's entry for h
        log_gamma = np.log2(gamma_h)
        if k - 1 == dd:
            dense_bow64 = np.zeros(bb**dd, dtype=np.float64)
            dense_bow64[hk] = log_gamma
        elif k - 1 > dd:
            below = sparse[k - 1 - dd - 1]
            pos, found = _find(raw[k - 2][0], hk)
            if not np.all(found):
                raise AssertionError("the history of a seen gram is not a seen gram")
            below.bow64[pos] = log_gamma

    dense_lp, dense_lp64 = [], []
    for tab in dense64:
        lp64 = np.log2(tab)
        lp = lp64.astype(np.float32)
        if not np.all(np.isfinite(lp)) or lp.max() > 0:
            raise AssertionError("dense level: a log-probability outside (-inf, 0]")
        dense_lp.append(lp)
        dense_lp64.append(lp64)
    dense_bow = None
    if dd < n:
        assert dense_bow64 is not None
        dense_bow = dense_bow64.astype(np.float32)
        if not np.all(np.isfinite(dense_bow)) or dense_bow.max() > 0:
            raise AssertionError("dense bow: a value outside (-inf, 0]")
    for lev in sparse:
        lev.lp = lev.lp64.astype(np.float32)
        lev.bow = lev.bow64.astype(np.float32)
        if not np.all(np.isfinite(lev.lp)) or lev.lp.max(initial=0.0) > 0:
            raise AssertionError("sparse level: a log-probability outside (-inf, 0]")
        if not np.all(np.isfinite(lev.bow)) or lev.bow.max(initial=0.0) > 0:
            raise AssertionError("sparse bow: a value outside (-inf, 0]")
        lev.p64 = None
    return Estimate(
        order=n,
        base=bb,
        dense_levels=dd,
        boundary=boundary,
        dense_lp=dense_lp,
        dense_bow=dense_bow,
        sparse=sparse,
        discounts=disc,
        discount_source=source,
        counts_of_counts=coc,
        count_type=count_type,
        n_runes=n_runes,
        dense_lp64=dense_lp64,
        dense_bow64=dense_bow64,
    )


def _check_rows(p: np.ndarray, level: int, rng=None, samples: int = 2_000) -> None:
    """Every (sampled) history's distribution sums to 1 within 1e-9, before the float32 cast
    (raise, never clamp)."""
    if not np.all(np.isfinite(p)) or p.min() <= 0:
        raise AssertionError(f"level {level}: a probability outside (0, 1]")
    rows = p
    if rng is not None and p.shape[0] > samples:
        rows = p[rng.choice(p.shape[0], samples, replace=False)]
    err = np.abs(rows.sum(axis=1) - 1.0).max()
    if err > 1e-9:
        raise AssertionError(f"level {level}: a history's distribution sums to 1 +- {err:.3e}")


# --------------------------------------------------------------------------- hash layout


def hash_bits(n_entries: int) -> int:
    """bits with 2**bits = the next power of two >= 2 * n_entries (at least 1)."""
    bits = 1
    while (1 << bits) < 2 * n_entries:
        bits += 1
    return bits


def hash_slot0(keys: np.ndarray, bits: int) -> np.ndarray:
    """Home slot of every key: ``(key * HASH_MULT mod 2**64) >> (64 - bits)`` in uint64."""
    k = np.asarray(keys, dtype=np.uint64)
    with np.errstate(over="ignore"):
        mixed = k * np.uint64(HASH_MULT)
    return mixed >> np.uint64(64 - bits)


def build_hash(
    keys: np.ndarray, lp: np.ndarray, bow: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    """Open-addressing table (linear probing, keys inserted in ascending order) of one sparse
    level: ``(slot_keys uint64[S], slot_lp float32[S], slot_bow float32[S], bits, max_probe)``
    with EMPTY = 2**64 - 1 marking a free slot and ``max_probe`` the most slots any lookup
    visits. Deterministic: the same keys give the same table."""
    k = np.asarray(keys, dtype=np.uint64)
    if k.size > 1 and not np.all(k[1:] > k[:-1]):
        raise ValueError("keys must be strictly ascending")
    bits = hash_bits(int(k.size))
    slots = 1 << bits
    mask = slots - 1
    slot_keys = np.full(slots, EMPTY_KEY, dtype=np.uint64)
    slot_lp = np.zeros(slots, dtype=np.float32)
    slot_bow = np.zeros(slots, dtype=np.float32)
    home = hash_slot0(k, bits).tolist()
    placed = np.empty(k.size, dtype=np.int64)
    taken = bytearray(slots)
    max_probe = 0
    for i, s in enumerate(home):
        probes = 1
        while taken[s]:
            s = (s + 1) & mask
            probes += 1
        taken[s] = 1
        placed[i] = s
        if probes > max_probe:
            max_probe = probes
    slot_keys[placed] = k
    slot_lp[placed] = np.asarray(lp, dtype=np.float32)
    slot_bow[placed] = np.asarray(bow, dtype=np.float32)
    return slot_keys, slot_lp, slot_bow, bits, max_probe


def hash_lookup(slot_keys: np.ndarray, bits: int, max_probe: int, key: int) -> int:
    """Slot index of ``key`` (a Python int) or -1: the scalar probe the kernel implements."""
    mask = (1 << bits) - 1
    s = ((key * HASH_MULT) & 0xFFFFFFFFFFFFFFFF) >> (64 - bits)
    for _ in range(max_probe):
        got = int(slot_keys[s])
        if got == key:
            return s
        if got == EMPTY_KEY:
            return -1
        s = (s + 1) & mask
    return -1
