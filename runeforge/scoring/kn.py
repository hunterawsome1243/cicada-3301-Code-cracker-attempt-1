"""The Phase 2 Kneser-Ney scorer (docs/kn-scorer-design.md): the model object, no fitting.

``KNScorer`` holds per-level arrays fitted by ``runeforge.scoring.kn_fit.estimate``: complete
float32 tables for levels 1..D (``dense_lp``, plus ``dense_bow`` when D < n) and, for levels
D+1..n, sorted packed ``uint64`` keys with a log2-probability and a back-off weight each.
Scores are mean log2-probability per cipher rune, higher = more language-like, the same
units as ``runeforge.scoring.ngram.NGramScorer``; uniform noise under the fitted order-8
``kn8-cicada`` preset lands around -6.5 (the measured bands live in reports/scorer_power.md,
never here). A window of 0 cipher runes has no score: ``score`` and ``score_batch`` return NaN
for it, as ``NGramScorer`` does.

The scoring chain (section 2.4), per position with symbol x and (n-1)-history H::

    acc = 0
    for k = m+1 down to D+1:                   # sparse levels, m = history symbols available
        hk = H mod B**(k-1)
        if k-1 > D: (hit_h, bow) = lookup(level k-1, hk); if not hit_h: continue
        else:       bow = dense_bow[hk]
        (hit_g, lp) = lookup(level k, hk*B + x)
        if hit_g: return acc + lp
        acc += bow
    kd = min(m+1, D)
    return acc + dense_lp[kd-1][(H mod B**(kd-1))*B + x]

``logprobs`` / ``score_batch`` run it vectorised with ``np.searchsorted`` on the live subset
of positions per level; ``reference_logprobs`` is the scalar version probing the exported
open-addressing hash (section 4), and the two agree bit for bit per position.

Dense presets (D == n, B == 29) expose ``tables`` for ``runeforge.beam``; a sparse or
word-boundary model raises ``AttributeError`` there (section 5).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from runeforge.scoring import kn_fit
from runeforge.scoring.kn_fit import EMPTY_KEY, HASH_MULT, Estimate, SparseLevel

VERSION = "knx-1"
NUMBERING = "LP2-0-57"
KEY_PACKING = (
    "k-gram key = sum_j x[i-k+1+j] * B**(k-1-j): oldest symbol most significant, newest least;"
    " history of a gram = key // B; suffix = key mod B**(k-1); rolling (n-1)-history"
    " H <- (H*B + x) mod B**(n-1)"
)
SCORE_RULE = (
    "window score = sum over positions of log2 P(x_i | history) / L, L = cipher runes"
    " (word-boundary symbols are scored but not counted in L)"
)
LOOKUP_ALGORITHM = (
    "per position (x, H, m = min(i, n-1)): acc = 0; for k = m+1 down to D+1: hk = H mod"
    " B**(k-1); if k-1 > D: probe level k-1 for hk, skip the level when absent, bow = its bow;"
    " else bow = dense_bow[hk]; probe level k for hk*B + x: present -> return acc + lp;"
    " else acc += bow. Then kd = min(m+1, D); return acc + dense_lp[level kd][(H mod"
    " B**(kd-1))*B + x]. Hash probe: slot = (key * 0x9E3779B97F4A7C15 mod 2**64) >>"
    " (64 - bits); linear probing up to max_probe slots; EMPTY = 2**64-1 ends the probe."
)
# score_batch / _logprobs_rows work on row chunks of at most this many positions: the chain
# materialises ~100 bytes of temporaries per position, so an unchunked 50,000 x 1000 batch
# (calib.measure's default chunk) peaked near 6 GB. Chunking changes no number: every row's
# sum is its own ``np.sum`` over that row. Tests shrink it to exercise the boundaries.
ROW_CHUNK_POSITIONS = 2_000_000
_NOT_DENSE = (
    "this Kneser-Ney scorer has no dense n-gram tables: a sparse (D < n) or word-boundary "
    "model pairs with the rigid decoder only; the beam decoders take the dense presets "
    "(presets.beam_compatible)"
)


class _Values:
    """The arrays one scoring pass reads (float32 as shipped, or the fitted float64)."""

    __slots__ = ("dense_bow", "dense_flat", "dense_off", "sparse_bow", "sparse_lp")

    def __init__(self, dense_lp, dense_bow, sparse_lp, sparse_bow):
        self.dense_flat = np.concatenate([np.asarray(t).ravel() for t in dense_lp])
        self.dense_off = np.cumsum([0, *[t.size for t in dense_lp]]).astype(np.int64)
        self.dense_bow = dense_bow
        self.sparse_lp = list(sparse_lp)
        self.sparse_bow = list(sparse_bow)


class KNScorer:
    """Interpolated modified Kneser-Ney over rune indices (docs/kn-scorer-design.md)."""

    def __init__(
        self,
        order: int,
        base: int,
        dense_levels: int,
        boundary: int | None,
        dense_lp: Sequence[np.ndarray],
        dense_bow: np.ndarray | None,
        sparse: Sequence[SparseLevel],
        discounts: np.ndarray,
        discount_source: Sequence[str],
        counts_of_counts: Sequence[Sequence[int]] | None = None,
        count_type: Sequence[str] | None = None,
        training: dict | None = None,
        dense_lp64: Sequence[np.ndarray] | None = None,
        dense_bow64: np.ndarray | None = None,
    ):
        if not 1 <= dense_levels <= min(order, 5):
            raise ValueError("dense_levels must be 1..min(order, 5)")
        if len(dense_lp) != dense_levels or len(sparse) != order - dense_levels:
            raise ValueError("level arrays do not match order / dense_levels")
        if (dense_bow is None) != (dense_levels == order):
            raise ValueError("dense_bow is present exactly when D < n")
        if boundary is not None and boundary != base - 1:
            raise ValueError("the boundary symbol is the last symbol of the alphabet")
        self.order = int(order)
        self.base = int(base)
        self.dense_levels = int(dense_levels)
        self.boundary = None if boundary is None else int(boundary)
        self.version = VERSION
        self.dense_lp = [np.ascontiguousarray(t, dtype=np.float32).ravel() for t in dense_lp]
        for k, t in enumerate(self.dense_lp, 1):
            if t.size != self.base**k:
                raise ValueError(f"dense level {k} has {t.size} entries, not {self.base**k}")
        self.dense_bow = (
            None if dense_bow is None else np.ascontiguousarray(dense_bow, dtype=np.float32)
        )
        self.sparse = [
            SparseLevel(
                keys=np.ascontiguousarray(s.keys, dtype=np.uint64),
                lp=np.ascontiguousarray(s.lp, dtype=np.float32),
                bow=np.ascontiguousarray(s.bow, dtype=np.float32),
                lp64=s.lp64,
                bow64=s.bow64,
            )
            for s in sparse
        ]
        self.discounts = np.ascontiguousarray(discounts, dtype=np.float64).reshape(order, 3)
        self.discount_source = list(discount_source)
        self.counts_of_counts = (
            None if counts_of_counts is None else [list(map(int, c)) for c in counts_of_counts]
        )
        self.count_type = None if count_type is None else list(count_type)
        self.training = dict(training or {})
        self._hist_mod = self.base ** (self.order - 1)
        self._f32 = _Values(
            self.dense_lp, self.dense_bow, [s.lp for s in self.sparse], [s.bow for s in self.sparse]
        )
        self._f64: _Values | None = None
        if dense_lp64 is not None and all(s.lp64 is not None for s in self.sparse):
            self._f64 = _Values(
                [np.asarray(t, dtype=np.float64) for t in dense_lp64],
                None if dense_bow64 is None else np.asarray(dense_bow64, dtype=np.float64),
                [s.lp64 for s in self.sparse],
                [s.bow64 for s in self.sparse],
            )
        self._tables: list[np.ndarray] | None = None
        if self.beam_compatible:
            # the same list object every call: runeforge.beam._tables caches by identity
            self._tables = [
                self.dense_lp[i].reshape(self.base**i, self.base) for i in range(self.order)
            ]
        self._hash: list[tuple[np.ndarray, np.ndarray, np.ndarray, int, int]] | None = None

    @classmethod
    def from_estimate(cls, est: Estimate, training: dict | None = None) -> KNScorer:
        return cls(
            est.order,
            est.base,
            est.dense_levels,
            est.boundary,
            est.dense_lp,
            est.dense_bow,
            est.sparse,
            est.discounts,
            est.discount_source,
            est.counts_of_counts,
            est.count_type,
            training,
            est.dense_lp64,
            est.dense_bow64,
        )

    # ------------------------------------------------------------------ properties

    @property
    def beam_compatible(self) -> bool:
        """B == 29 and every level dense (section 5)."""
        return self.base == 29 and self.dense_levels == self.order

    @property
    def tables(self) -> list[np.ndarray]:
        """``tables[i]``: log2 P(x | i-symbol history), float32 (29**i, 29) views of the dense
        levels, for ``runeforge.beam`` (dense presets only; identity-stable)."""
        if self._tables is None:
            raise AttributeError(_NOT_DENSE)
        return self._tables

    def __repr__(self) -> str:
        kind = "wb" if self.boundary is not None else "nb"
        return (
            f"KNScorer(order={self.order}, base={self.base}, dense_levels={self.dense_levels}, "
            f"{kind}, sparse={[int(s.keys.size) for s in self.sparse]})"
        )

    # ------------------------------------------------------------------ boundaries

    def boundary_extend(self, x, starts, end_boundary: bool = False) -> np.ndarray:
        """Insert the boundary symbol before every True position of ``starts`` (and at the end
        when ``end_boundary``); rows of a (B, L) batch share the one mask."""
        if self.boundary is None:
            raise ValueError("this model has no word-boundary symbol")
        a = np.asarray(x, dtype=np.int64)
        s = np.asarray(starts, dtype=bool).ravel()
        if s.size != a.shape[-1]:
            raise ValueError(f"starts has {s.size} entries for {a.shape[-1]} runes")
        total = a.shape[-1] + int(s.sum()) + int(bool(end_boundary))
        # output index of every rune: its position plus the boundaries inserted before it
        pos = np.arange(a.shape[-1]) + np.cumsum(s)
        out = np.full((*a.shape[:-1], total), self.boundary, dtype=np.int64)
        out[..., pos] = a
        return out

    # ------------------------------------------------------------------ scoring

    def _check_symbols(self, x: np.ndarray) -> None:
        if x.size and (x.min() < 0 or x.max() >= self.base):
            raise ValueError(f"symbol outside 0..{self.base - 1}")

    def _check_runes(self, x: np.ndarray) -> None:
        """Rune rows hold runes only (0..28): the boundary symbol of a wb model is inserted
        by ``boundary_extend``, never supplied in a decode."""
        top = self.base - 1 if self.boundary is None else self.boundary - 1
        if x.size and (x.min() < 0 or x.max() > top):
            raise ValueError(f"rune outside 0..{top}")

    def _prepare(self, plains, starts, end_boundary) -> tuple[np.ndarray, int]:
        """(rows, L) as the scorer sees them: int64 (R, L') after boundary extension, and the
        divisor L = cipher runes."""
        x = np.asarray(plains, dtype=np.int64)
        if x.ndim != 2:
            raise ValueError("expected a 2-D (batch, length) array")
        length = x.shape[1]
        self._check_runes(x)
        if self.boundary is not None:
            if starts is None:
                raise ValueError(
                    "a word-boundary model needs the window's word-start mask (starts=); the "
                    "cipher's word starts are window data, never inferred from a decode"
                )
            x = self.boundary_extend(x, starts, end_boundary)
        elif starts is not None:
            raise ValueError("this model has no word-boundary symbol: do not pass starts")
        self._check_symbols(x)
        return x, length

    def _histories(self, x: np.ndarray) -> np.ndarray:
        """uint64 (R, L): the packed up-to-(n-1)-symbol history before every position."""
        xu = x.astype(np.uint64)
        r, length = xu.shape
        h = np.zeros((r, length), dtype=np.uint64)
        for j in range(1, self.order):
            if j >= length:
                break
            h[:, j:] += xu[:, : length - j] * np.uint64(self.base ** (j - 1))
        return h

    def _chain(self, h: np.ndarray, x: np.ndarray, i: np.ndarray, vals: _Values) -> np.ndarray:
        """The section 2.4 chain over flat position arrays: ``h`` uint64 histories, ``x``
        uint64 symbols, ``i`` the position index (history symbols available = min(i, n-1)).
        Float64 accumulation in the scalar reference's order; every level works on the live
        subset of positions only (compaction)."""
        n, bb, dd = self.order, np.uint64(self.base), self.dense_levels
        size = h.size
        acc = np.zeros(size, dtype=np.float64)
        out = np.empty(size, dtype=np.float64)
        pending = np.ones(size, dtype=bool)
        for k in range(n, dd, -1):
            live = np.flatnonzero(pending & (i >= k - 1))
            if live.size == 0:
                continue
            hk = h[live] % np.uint64(self.base ** (k - 1))
            if k - 1 > dd:
                j = k - 1 - dd - 1  # the sparse level holding the (k-1)-gram histories
                pos, hit = _probe(self.sparse[j].keys, hk)
                live, hk = live[hit], hk[hit]
                bow = vals.sparse_bow[j][pos[hit]]
                if live.size == 0:
                    continue
            else:
                bow = vals.dense_bow[hk]
            j = k - dd - 1
            pos, hit = _probe(self.sparse[j].keys, hk * bb + x[live])
            done = live[hit]
            out[done] = acc[done] + vals.sparse_lp[j][pos[hit]].astype(np.float64)
            pending[done] = False
            miss = live[~hit]
            acc[miss] += bow[~hit].astype(np.float64)
        rest = np.flatnonzero(pending)
        kd1 = np.minimum(i[rest], dd - 1).astype(np.uint64)  # kd - 1 = min(m + 1, D) - 1
        hist_mod = np.array([self.base**j for j in range(dd)], dtype=np.uint64)
        idx = vals.dense_off.astype(np.uint64)[kd1] + (h[rest] % hist_mod[kd1]) * bb + x[rest]
        out[rest] = acc[rest] + vals.dense_flat[idx].astype(np.float64)
        return out

    @staticmethod
    def _row_chunks(rows: int, length: int) -> list[tuple[int, int]]:
        """(start, stop) row slices of at most ROW_CHUNK_POSITIONS positions each."""
        step = max(ROW_CHUNK_POSITIONS // max(length, 1), 1)
        return [(a, min(a + step, rows)) for a in range(0, rows, step)]

    def _logprobs_chunk(self, x: np.ndarray, vals: _Values) -> np.ndarray:
        r, length = x.shape
        h = self._histories(x)
        i = np.broadcast_to(np.arange(length, dtype=np.int64), (r, length)).ravel()
        return self._chain(h.ravel(), x.astype(np.uint64).ravel(), i, vals).reshape(r, length)

    def _logprobs_rows(self, x: np.ndarray, vals: _Values | None = None) -> np.ndarray:
        """float64 (R, L') log2 P per position of every row of an extended int64 batch,
        computed in row chunks (ROW_CHUNK_POSITIONS) so the working set stays bounded."""
        vals = vals or self._f32
        r, length = x.shape
        if length == 0:
            return np.zeros((r, 0), dtype=np.float64)
        out = np.empty((r, length), dtype=np.float64)
        for a, b in self._row_chunks(r, length):
            out[a:b] = self._logprobs_chunk(x[a:b], vals)
        return out

    @staticmethod
    def _sum_rows(lp: np.ndarray) -> np.ndarray:
        """The one summation ``score`` and ``score_batch`` share (replay parity to 1e-9)."""
        return np.sum(lp, axis=1, dtype=np.float64)

    def logprobs(self, plain, starts=None, end_boundary: bool = False) -> np.ndarray:
        """log2 P(x_i | history) per position (boundary symbols included for a wb model)."""
        x, _ = self._prepare(np.asarray(plain, dtype=np.int64)[None, :], starts, end_boundary)
        return self._logprobs_rows(x)[0]

    def score(self, plain, starts=None, end_boundary: bool = False) -> float:
        """Mean log2-probability per cipher rune (higher = more language-like); NaN for a
        window of 0 cipher runes (there is nothing to divide by, as in ``NGramScorer``), even
        when ``end_boundary`` scored one boundary symbol."""
        x, length = self._prepare(np.asarray(plain, dtype=np.int64)[None, :], starts, end_boundary)
        if length == 0:
            return float("nan")
        return float(self._sum_rows(self._logprobs_rows(x))[0] / length)

    def score_batch(self, plains, starts=None, end_boundary: bool = False) -> np.ndarray:
        """Scores of every row of a (B, L) array, vectorised (the sweep's inner loop); NaN
        for every row when L == 0. Rows are scored in chunks of ROW_CHUNK_POSITIONS positions
        (one row's sum never depends on the chunk it sits in)."""
        x, length = self._prepare(plains, starts, end_boundary)
        if length == 0:
            return np.full(x.shape[0], np.nan)
        out = np.empty(x.shape[0], dtype=np.float64)
        for a, b in self._row_chunks(x.shape[0], x.shape[1]):
            out[a:b] = self._sum_rows(self._logprobs_rows(x[a:b]))
        return out / length

    def __call__(self, plain) -> float:
        return self.score(plain)

    def distribution(self, history) -> np.ndarray:
        """float64[B]: P(x | history) for every symbol, from the fitted float64 values when
        the model was fitted in this process (sum to 1 within 1e-12), else from the float32
        tables (1e-5). ``history`` is the preceding symbols, at most n-1 (a shorter one is a
        prefix history; a longer one is cut to its last n-1 symbols)."""
        hseq = np.asarray(history, dtype=np.int64).ravel()
        hseq = hseq[hseq.size - min(hseq.size, self.order - 1) :]
        self._check_symbols(hseq)
        m = hseq.size
        h = np.uint64(0)
        for s in hseq:
            h = h * np.uint64(self.base) + np.uint64(int(s))
        hs = np.full(self.base, h, dtype=np.uint64)
        xs = np.arange(self.base, dtype=np.uint64)
        i = np.full(self.base, m, dtype=np.int64)
        lp = self._chain(hs, xs, i, self._f64 or self._f32)
        return np.exp2(lp)

    # ------------------------------------------------------------------ fingerprint

    def fingerprint(self) -> str:
        """SHA-256 of order, base, dense_levels, discounts and every array: a rename, a commit
        or a timestamp never changes it; one changed training rune does."""
        hsh = hashlib.sha256(f"kn/{self.order}/{self.base}/{self.dense_levels}".encode())
        hsh.update(np.ascontiguousarray(self.discounts).tobytes())
        for t in self.dense_lp:
            hsh.update(t.tobytes())
        if self.dense_bow is not None:
            hsh.update(self.dense_bow.tobytes())
        for s in self.sparse:
            hsh.update(s.keys.tobytes())
            hsh.update(s.lp.tobytes())
            hsh.update(s.bow.tobytes())
        return hsh.hexdigest()

    # ------------------------------------------------------------------ export (knx-1)

    def hash_layout(self) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, int, int]]:
        """Per sparse level ``(slot_keys, slot_lp, slot_bow, bits, max_probe)``: the
        open-addressing layout of the export, built once and cached."""
        if self._hash is None:
            self._hash = [kn_fit.build_hash(s.keys, s.lp, s.bow) for s in self.sparse]
        return self._hash

    def manifest(self) -> dict:
        levels = []
        off = 0
        for k, t in enumerate(self.dense_lp, 1):
            levels.append(
                {
                    "level": k,
                    "kind": "dense",
                    "n_entries": int(t.size),
                    "offset": off,
                    "discounts": self.discounts[k - 1].tolist(),
                    "counts_of_counts": self._coc(k),
                    "count_type": self._ctype(k),
                    "discount_source": self.discount_source[k - 1],
                }
            )
            off += int(t.size)
        hoff = soff = 0
        for j, (s, (slot_keys, _, _, bits, max_probe)) in enumerate(
            zip(self.sparse, self.hash_layout(), strict=True)
        ):
            k = self.dense_levels + 1 + j
            levels.append(
                {
                    "level": k,
                    "kind": "sparse",
                    "n_entries": int(s.keys.size),
                    "offset": hoff,
                    "sorted_offset": soff,
                    "slots": int(slot_keys.size),
                    "bits": int(bits),
                    "mult": f"0x{HASH_MULT:016X}",
                    "shift": 64 - int(bits),
                    "max_probe": int(max_probe),
                    "empty_key": f"0x{EMPTY_KEY:016X}",
                    "discounts": self.discounts[k - 1].tolist(),
                    "counts_of_counts": self._coc(k),
                    "count_type": self._ctype(k),
                    "discount_source": self.discount_source[k - 1],
                }
            )
            hoff += int(slot_keys.size)
            soff += int(s.keys.size)
        return {
            "version": self.version,
            "order": self.order,
            "base": self.base,
            "boundary_symbol": self.boundary,
            "dense_levels": self.dense_levels,
            "key_packing": KEY_PACKING,
            "levels": levels,
            "score_rule": SCORE_RULE,
            "lookup": LOOKUP_ALGORITHM,
            "training": self.training,
            "fingerprint": self.fingerprint(),
            "numbering": NUMBERING,
        }

    def _coc(self, k: int):
        return None if self.counts_of_counts is None else self.counts_of_counts[k - 1]

    def _ctype(self, k: int):
        return None if self.count_type is None else self.count_type[k - 1]

    def export(self, path: Path | str) -> dict:
        """Write the ``knx-1`` ``.npz`` (uncompressed, 1-D little-endian arrays) and its JSON
        manifest beside it (``<stem>.json``); returns the manifest."""
        path = Path(path)
        man = self.manifest()
        text = json.dumps(man, indent=2, sort_keys=True) + "\n"  # one text, both copies
        hl = self.hash_layout()
        arrays = {
            "dense_lp": self._f32.dense_flat,
            "hash_keys": _cat([h[0] for h in hl], np.uint64),
            "hash_lp": _cat([h[1] for h in hl], np.float32),
            "hash_bow": _cat([h[2] for h in hl], np.float32),
            "sorted_keys": _cat([s.keys for s in self.sparse], np.uint64),
            "sorted_lp": _cat([s.lp for s in self.sparse], np.float32),
            "sorted_bow": _cat([s.bow for s in self.sparse], np.float32),
            "discounts": self.discounts.ravel(),
            "manifest": np.array(text),
        }
        if self.dense_bow is not None:
            arrays["dense_bow"] = self.dense_bow
        arrays = {
            k: v if k == "manifest" else np.ascontiguousarray(v, dtype=v.dtype.newbyteorder("<"))
            for k, v in arrays.items()
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            np.savez(fh, **arrays)
        path.with_suffix(".json").write_text(text, encoding="utf-8")
        return man

    @classmethod
    def load_export(cls, path: Path | str) -> KNScorer:
        """Rebuild a scorer from a ``knx-1`` export (no refit); its fingerprint must equal the
        manifest's."""
        with np.load(Path(path), allow_pickle=False) as z:
            man = json.loads(str(z["manifest"]))
            if man.get("version") != VERSION:
                raise ValueError(f"export version {man.get('version')!r} is not {VERSION}")
            n, bb, dd = man["order"], man["base"], man["dense_levels"]
            dense_flat = z["dense_lp"].astype(np.float32)
            dense_lp = []
            off = 0
            for k in range(1, dd + 1):
                dense_lp.append(dense_flat[off : off + bb**k])
                off += bb**k
            dense_bow = z["dense_bow"].astype(np.float32) if dd < n else None
            sk = z["sorted_keys"].astype(np.uint64)
            slp = z["sorted_lp"].astype(np.float32)
            sbow = z["sorted_bow"].astype(np.float32)
            hk = z["hash_keys"].astype(np.uint64)
            hlp = z["hash_lp"].astype(np.float32)
            hbow = z["hash_bow"].astype(np.float32)
            sparse, hashes = [], []
            for lev in man["levels"]:
                if lev["kind"] != "sparse":
                    continue
                a, m = lev["sorted_offset"], lev["n_entries"]
                sparse.append(SparseLevel(sk[a : a + m], slp[a : a + m], sbow[a : a + m]))
                b, s = lev["offset"], lev["slots"]
                hashes.append(
                    (hk[b : b + s], hlp[b : b + s], hbow[b : b + s], lev["bits"], lev["max_probe"])
                )
            disc = z["discounts"].astype(np.float64).reshape(n, 3)
        levels = man["levels"]
        # a scorer built without counts_of_counts / count_type exports them as null per level
        coc = [lev.get("counts_of_counts") for lev in levels]
        ctype = [lev.get("count_type") for lev in levels]
        sc = cls(
            n,
            bb,
            dd,
            man.get("boundary_symbol"),
            dense_lp,
            dense_bow,
            sparse,
            disc,
            [lev["discount_source"] for lev in levels],
            None if all(c is None for c in coc) else coc,
            None if all(c is None for c in ctype) else ctype,
            man.get("training"),
        )
        sc._hash = hashes
        if sc.fingerprint() != man["fingerprint"]:
            raise ValueError(f"{path}: the arrays do not match the manifest's fingerprint")
        return sc

    # ------------------------------------------------------------------ scalar reference

    def reference_logprobs(self, plain, starts=None, end_boundary: bool = False) -> np.ndarray:
        """The scalar section 2.4 recursion over the exported arrays, probing the hash layout:
        the lookup a CUDA kernel implements, bit-for-bit equal per position to ``logprobs``."""
        x, _ = self._prepare(np.asarray(plain, dtype=np.int64)[None, :], starts, end_boundary)
        seq = [int(v) for v in x[0]]
        n, bb, dd = self.order, self.base, self.dense_levels
        hl = self.hash_layout()
        dense = [np.asarray(t) for t in self.dense_lp]
        dense_bow = self.dense_bow
        hist_mod = bb ** (n - 1)
        out = np.empty(len(seq), dtype=np.float64)
        h = 0
        for i, sym in enumerate(seq):
            m = min(i, n - 1)
            acc = np.float64(0.0)
            result = None
            for k in range(m + 1, dd, -1):
                hk = h % bb ** (k - 1)
                if k - 1 > dd:
                    slot_keys, _, slot_bow, bits, max_probe = hl[k - 1 - dd - 1]
                    s = kn_fit.hash_lookup(slot_keys, bits, max_probe, hk)
                    if s < 0:
                        continue
                    bow = np.float64(slot_bow[s])
                else:
                    bow = np.float64(dense_bow[hk])
                slot_keys, slot_lp, _, bits, max_probe = hl[k - dd - 1]
                s = kn_fit.hash_lookup(slot_keys, bits, max_probe, hk * bb + sym)
                if s >= 0:
                    result = acc + np.float64(slot_lp[s])
                    break
                acc = acc + bow
            if result is None:
                kd = min(m + 1, dd)
                result = acc + np.float64(dense[kd - 1][(h % bb ** (kd - 1)) * bb + sym])
            out[i] = result
            h = (h * bb + sym) % hist_mod
        return out


def _probe(keys: np.ndarray, query: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``(position, hit)`` of every uint64 query in the ascending uint64 ``keys``."""
    if keys.size == 0:
        return np.zeros(query.shape, dtype=np.int64), np.zeros(query.shape, dtype=bool)
    pos = np.minimum(np.searchsorted(keys, query), keys.size - 1)
    return pos, keys[pos] == query


def _cat(parts: list[np.ndarray], dtype) -> np.ndarray:
    return np.concatenate([np.asarray(p, dtype=dtype) for p in parts] or [np.zeros(0, dtype)])
