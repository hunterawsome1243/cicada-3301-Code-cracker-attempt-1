"""The beam interrupt decoder (spec section 2.4 ``beam(scorer, width)``; Phase 2).

The rigid decoder spends one key symbol per rune, so the first F-interrupter or anti-repeat
key skip throws every later rune out of step with the key, and a correct key scores like noise
(CLAUDE.md: a planted key scores -6.835 rigid vs -4.170 beam). This decoder follows the
forward model of ``runeforge.runner.pipeline.encrypt``, position by position:

* **interrupt** -- allowed only where the canonical rune is F: the plaintext is F and the key
  does not advance; prior ``interrupt_prob``. A plaintext F that is enciphered instead pays
  ``1 - interrupt_prob``.
* **decode with s skips** (s = 0 .. ``max_skip``; s > 0 only for the anti-repeat model, never
  at position 0): key symbols j .. j+s-1 were each dropped by the filter, and j+s enciphered
  the rune. The plaintext is ``x = combine^-1(view symbol, k[j+s])``; each dropped symbol must
  have produced a canonical repeat of the previous rune with that same ``x`` -- an exact test
  on the key, not a guess -- and pays ``1 - p_keep``. A rune that does repeat the previous
  canonical rune survived the filter and pays ``p_keep``.

The canonical runes are fixed by the ciphertext (``pipeline.unview``), so the interrupt and
repeat positions are known; only the plaintext and the key position are hidden. A hypothesis is
(key position, the scorer's n-gram history). Each step every hypothesis expands into its
options; candidates that reach the same state are merged keeping the best (Viterbi: they have
identical futures); the best ``width`` survive. The objective is the scorer's log2-probability
plus the log2 transition priors; the decoder returns the plaintext of the best path, which the
lane then scores with the scorer alone, exactly as it scores a rigid decode.

Ties are broken by candidate index everywhere, so the batched numpy decoder and the scalar
reference ``decode_reference`` agree path for path (``tests/test_beam.py``).

Key budget: the decoder reads every key symbol it is given and no more (``k`` must hold at
least as many symbols as the cipher has runes). Every caller that compares a decode with a
null -- control plants, decoys and ceiling, ``runeforge null``, the sweep, ``runeforge score``
-- passes exactly the window length, so they all decode under the same budget. A path that has
used its last symbol (more skips than interrupts so far) continues with the fixed, key-free
fill ``combine^-1(view symbol, 0)`` (noise for any cipher) and is marked in the record; a
planted key under the anti-repeat model loses its last few runes that way (about 1.8 % of the
window), which costs power, never adds any.

The scorer must expose ``order`` and ``tables`` (``runeforge.scoring.ngram.NGramScorer``):
``tables[i]`` is log2 P(x | i-symbol history) with shape (29**i, 29).
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass, field

import numpy as np

from runeforge.gematria import N

F = 0
COMBINES = ("vigenere", "variant-beaufort", "beaufort")
VIEWS = ("raw", "atbash", "first-difference", "chain-increment")
# op codes in a decode record: 0..max_skip = enciphered after that many skips
OP_INTERRUPT = 100
OP_FILL = 101


@dataclass(frozen=True)
class BeamModel:
    """The decoder's transition model. ``p_keep=None`` disables the anti-repeat skips;
    ``interrupt_prob=0`` disables the interrupts (the decoder is then rigid with fill)."""

    combine: str = "vigenere"
    view: str = "raw"
    width: int = 8
    interrupt_prob: float = 15 / 16
    p_keep: float | None = None
    max_skip: int = 2

    def __post_init__(self):
        if self.combine not in COMBINES:
            raise ValueError(f"unknown combine {self.combine!r}")
        if self.view not in VIEWS:
            raise ValueError(f"unknown ciphertext view {self.view!r}")
        if self.width < 1:
            raise ValueError("beam width must be >= 1")
        if not 0 <= self.interrupt_prob <= 1:
            raise ValueError("interrupt_prob is a probability")
        if self.p_keep is not None and not 0 <= self.p_keep <= 1:
            raise ValueError("p_keep is a probability")
        if self.max_skip < 0:
            raise ValueError("max_skip must be >= 0")

    @property
    def n_skips(self) -> int:
        return self.max_skip if self.p_keep is not None else 0


def _log2(p: float) -> float:
    return math.log2(p) if p > 0 else -math.inf


# --------------------------------------------------------------------------- arithmetic


def decrypt_sym(combine: str, d, k):
    """The plaintext of view symbol ``d`` under key ``k`` (arrays or ints)."""
    if combine == "vigenere":
        return (d - k) % N
    if combine == "variant-beaufort":
        return (d + k) % N
    return (k - d) % N


def repeat_key(combine: str, x, d_rep):
    """The key symbol that enciphers plaintext ``x`` to view symbol ``d_rep``."""
    if combine == "vigenere":
        return (d_rep - x) % N
    if combine == "variant-beaufort":
        return (x - d_rep) % N
    return (d_rep + x) % N


def canonical(d: np.ndarray, view: str) -> np.ndarray:
    """Canonical runes of view symbols, row by row (``pipeline.unview``, c_{-1} = 0)."""
    d = np.asarray(d, dtype=np.int64)
    if view == "raw":
        return d.copy()
    if view == "atbash":
        return (N - 1) - d
    if view == "first-difference":
        return np.cumsum(d, axis=-1) % N
    return np.cumsum(d + 1, axis=-1) % N  # chain-increment


def repeat_symbol(c_prev: np.ndarray, view: str) -> np.ndarray:
    """The view symbol that would repeat canonical rune ``c_prev`` (``_view1(c, c)``)."""
    c_prev = np.asarray(c_prev, dtype=np.int64)
    if view == "raw":
        return c_prev.copy()
    if view == "atbash":
        return (N - 1) - c_prev
    if view == "first-difference":
        return np.zeros_like(c_prev)
    return np.full_like(c_prev, N - 1)  # chain-increment: (c - c - 1) mod 29


def _tables(scorer) -> list[np.ndarray]:
    cached = getattr(scorer, "_beam_tables64", None)
    if cached is None or len(cached) != len(scorer.tables):
        cached = [np.ascontiguousarray(t, dtype=np.float64) for t in scorer.tables]
        with contextlib.suppress(AttributeError):  # a slotted scorer just recomputes them
            scorer._beam_tables64 = cached
    return cached


@dataclass
class _Priors:
    interrupt: float
    f_kept: float  # a plaintext F that is enciphered
    skip: float
    keep_repeat: float


def _priors(model: BeamModel) -> _Priors:
    q = model.interrupt_prob
    on = model.p_keep is not None
    return _Priors(
        interrupt=_log2(q),
        f_kept=_log2(1 - q) if q > 0 else 0.0,
        skip=_log2(1 - model.p_keep) if on else -math.inf,
        keep_repeat=_log2(model.p_keep) if on else 0.0,
    )


# --------------------------------------------------------------------------- batched decoder


@dataclass
class BeamResult:
    plain: np.ndarray  # (B, L)
    ops: np.ndarray  # (B, L) int16: skips taken (0..max_skip), OP_INTERRUPT or OP_FILL
    objective: np.ndarray  # (B,) log2 P of the best path, scorer + priors
    keys_used: np.ndarray  # (B,) key symbols consumed (skipped ones included)


def decode_batch(cipher, keys, scorer, model: BeamModel) -> BeamResult:
    """Beam-decode one cipher (L,) / (1, L), or one cipher per key (B, L), under keys (B, K),
    K >= L. Rows are independent: a row decodes identically alone or in any batch."""
    d = np.atleast_2d(np.asarray(cipher, dtype=np.int64))
    k = np.atleast_2d(np.asarray(keys, dtype=np.int64))
    bc, length = d.shape
    b, kn = k.shape
    if bc not in (1, b):
        raise ValueError(f"{bc} ciphers for {b} keys: pass one cipher, or one per key")
    if kn < length:
        raise ValueError(f"the beam needs >= {length} key symbols per row, got {kn}")
    if length == 0:
        z = np.zeros((b, 0), dtype=np.int64)
        return BeamResult(z, z.astype(np.int16), np.zeros(b), np.zeros(b, dtype=np.int64))
    tables = _tables(scorer)
    kmax = scorer.order - 1
    hist_mod = N**kmax
    pri = _priors(model)
    w = model.width
    n_skips = model.n_skips
    n_dec = n_skips + 1
    use_int = model.interrupt_prob > 0
    canon_c = canonical(d, model.view)
    prev_c = np.concatenate([np.zeros((bc, 1), dtype=np.int64), canon_c[:, :-1]], axis=1)
    d_rep = repeat_symbol(prev_c, model.view)
    is_rep = canon_c == prev_c
    is_rep[:, 0] = False  # the filter never acts on the first rune

    j = np.zeros((b, w), dtype=np.int64)
    h = np.zeros((b, w), dtype=np.int64)
    score = np.full((b, w), -np.inf)
    score[:, 0] = 0.0
    back_parent = np.empty((length, b, w), dtype=np.int32)
    back_x = np.empty((length, b, w), dtype=np.int8)
    back_op = np.empty((length, b, w), dtype=np.int16)
    rows = np.arange(b)[:, None]
    k_last = kn - 1

    for i in range(length):
        tab = tables[min(i, kmax)]
        di = d[:, i : i + 1]  # (bc, 1) broadcasts over (b, w)
        alive = score > -np.inf
        rep_i = is_rep[:, i : i + 1]
        drep_i = d_rep[:, i : i + 1]
        base = score + np.where(rep_i, pri.keep_repeat, 0.0)
        opt_score, opt_x, opt_j, opt_op = [], [], [], []
        for s in range(n_dec):
            jj = j + s
            has_key = jj <= k_last
            kk = np.take_along_axis(k, np.minimum(jj, k_last), axis=1)
            x = decrypt_sym(model.combine, di, kk)
            if s == 0:
                # an exhausted path continues with the key-free fill
                x = np.where(has_key, x, decrypt_sym(model.combine, di, 0))
                op = np.where(has_key, 0, OP_FILL)
                ok = alive
                sc = base
            else:
                ok = alive & has_key & (i > 0)
                need = repeat_key(model.combine, x, drep_i)
                for t in range(s):
                    kt = np.take_along_axis(k, np.minimum(j + t, k_last), axis=1)
                    ok = ok & (kt == need)
                op = np.full((b, w), s)
                sc = base + s * pri.skip
            if use_int:
                sc = sc + np.where(x == F, pri.f_kept, 0.0)
            sc = np.where(ok, sc + tab[h, x], -np.inf)
            opt_score.append(sc)
            opt_x.append(np.broadcast_to(x, (b, w)))
            opt_j.append(np.where(op == OP_FILL, jj, jj + 1))
            opt_op.append(np.broadcast_to(op, (b, w)))
        if use_int:
            f_here = canon_c[:, i : i + 1] == F
            if f_here.any():
                sc = np.where(alive & f_here, score + pri.interrupt + tab[h, F], -np.inf)
                opt_score.append(sc)
                opt_x.append(np.zeros((b, w), dtype=np.int64))
                opt_j.append(j)
                opt_op.append(np.full((b, w), OP_INTERRUPT))
        c_score = np.concatenate(opt_score, axis=1)  # candidate m = option * w + parent
        c_x = np.concatenate(opt_x, axis=1)
        c_j = np.concatenate(opt_j, axis=1)
        c_op = np.concatenate(opt_op, axis=1)
        c_h = np.tile(h, (1, len(opt_score)))
        c_h = (c_h * N + c_x) % hist_mod if i >= kmax else c_h * N + c_x
        state = np.where(c_score > -np.inf, c_j * hist_mod + c_h, -1)
        # merge equal states (keep the best; ties -> lowest candidate index), then top-w
        by_score = np.argsort(-c_score, axis=1, kind="stable")
        st_sorted = np.take_along_axis(state, by_score, axis=1)
        by_state = np.argsort(st_sorted, axis=1, kind="stable")
        st2 = np.take_along_axis(st_sorted, by_state, axis=1)
        dup2 = np.zeros_like(st2, dtype=bool)
        dup2[:, 1:] = (st2[:, 1:] == st2[:, :-1]) & (st2[:, 1:] >= 0)
        dup_sorted = np.empty_like(dup2)
        np.put_along_axis(dup_sorted, by_state, dup2, axis=1)
        keep_order = np.argsort(dup_sorted, axis=1, kind="stable")[:, :w]
        pick = np.take_along_axis(by_score, keep_order, axis=1)  # (b, w) candidate indices
        picked_dup = np.take_along_axis(dup_sorted, keep_order, axis=1)
        if pick.shape[1] < w:  # fewer candidates than slots (width > options * width never)
            raise AssertionError("beam has fewer candidates than slots")
        score = np.where(picked_dup, -np.inf, np.take_along_axis(c_score, pick, axis=1))
        j = np.take_along_axis(c_j, pick, axis=1)
        h = np.take_along_axis(c_h, pick, axis=1)
        back_parent[i] = pick % w
        back_x[i] = np.take_along_axis(c_x, pick, axis=1)
        back_op[i] = np.take_along_axis(c_op, pick, axis=1)

    best = np.argmax(score, axis=1)  # first max: ties -> lowest slot
    objective = score[np.arange(b), best]
    keys_used = j[np.arange(b), best]
    plain = np.empty((b, length), dtype=np.int64)
    ops = np.empty((b, length), dtype=np.int16)
    slot = best
    r = rows[:, 0]
    for i in range(length - 1, -1, -1):
        plain[:, i] = back_x[i, r, slot]
        ops[:, i] = back_op[i, r, slot]
        slot = back_parent[i, r, slot]
    return BeamResult(plain, ops, objective, keys_used)


MAX_ROWS = 2048  # rows per decode_batch call: the backpointers take L x rows x width x 7 bytes


def decode(cipher, keys, scorer, model: BeamModel, max_rows: int = MAX_ROWS) -> np.ndarray:
    """Plaintext only, shaped like ``pipeline.decrypt``: (L,) for one cipher and one key,
    else (B, L). Decoded ``max_rows`` keys at a time; rows are independent, so the result
    does not depend on ``max_rows``."""
    d = np.atleast_2d(np.asarray(cipher, dtype=np.int64))
    k = np.atleast_2d(np.asarray(keys, dtype=np.int64))
    if d.shape[0] not in (1, k.shape[0]):
        raise ValueError(f"{d.shape[0]} ciphers for {k.shape[0]} keys: pass one, or one per key")
    parts = []
    for a in range(0, k.shape[0], max_rows):
        dc = d if d.shape[0] == 1 else d[a : a + max_rows]
        parts.append(decode_batch(dc, k[a : a + max_rows], scorer, model).plain)
    plain = np.concatenate(parts) if parts else np.zeros((0, d.shape[1]), dtype=np.int64)
    if np.ndim(cipher) == 1 and np.ndim(keys) == 1:
        return plain[0]
    return plain


# --------------------------------------------------------------------------- one decode


@dataclass
class DecodeRecord:
    """One path, in the form ``crosser.reencipher_forward`` replays: interrupt positions,
    ``skips[i] = s`` where the filter dropped s key symbols before the one kept, and fill
    positions (key budget used up: not a forward-model step, so never re-enciphers)."""

    plain: list[int]
    interrupts: list[int] = field(default_factory=list)
    skips: dict[int, int] = field(default_factory=dict)
    fill: list[int] = field(default_factory=list)
    objective: float = float("nan")
    keys_used: int = 0
    model: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "plain": self.plain,
            "interrupts": self.interrupts,
            "skips": {str(i): s for i, s in self.skips.items()},
            "fill": self.fill,
            "objective": self.objective,
            "keys_used": self.keys_used,
            "model": self.model,
        }


def record_from(res: BeamResult, row: int, model: BeamModel) -> DecodeRecord:
    ops = res.ops[row]
    return DecodeRecord(
        plain=[int(x) for x in res.plain[row]],
        interrupts=[int(i) for i in np.flatnonzero(ops == OP_INTERRUPT)],
        skips={int(i): int(ops[i]) for i in np.flatnonzero((ops > 0) & (ops < OP_INTERRUPT))},
        fill=[int(i) for i in np.flatnonzero(ops == OP_FILL)],
        objective=float(res.objective[row]),
        keys_used=int(res.keys_used[row]),
        model=model_dict(model),
    )


def decode_record(cipher, key, scorer, model: BeamModel) -> DecodeRecord:
    res = decode_batch(np.asarray(cipher)[None, :], np.asarray(key)[None, :], scorer, model)
    return record_from(res, 0, model)


def model_dict(model: BeamModel) -> dict:
    return {
        "combine": model.combine,
        "view": model.view,
        "width": model.width,
        "interrupt_prob": model.interrupt_prob,
        "p_keep": model.p_keep,
        "max_skip": model.max_skip,
    }


# --------------------------------------------------------------------------- reference


def decode_reference(cipher, key, scorer, model: BeamModel) -> DecodeRecord:
    """The same algorithm, one key, plain Python: the parity reference for ``decode_batch``
    (same candidate order, same merge and tie rules, same float expression order)."""
    d = [int(x) for x in np.asarray(cipher, dtype=np.int64)]
    k = [int(x) for x in np.asarray(key, dtype=np.int64)]
    length, kn = len(d), len(k)
    if kn < length:
        raise ValueError(f"the beam needs >= {length} key symbols, got {kn}")
    tables = _tables(scorer)
    kmax = scorer.order - 1
    hist_mod = N**kmax
    pri = _priors(model)
    w = model.width
    n_dec = model.n_skips + 1
    use_int = model.interrupt_prob > 0
    canon_c = [int(x) for x in canonical(np.array(d), model.view)]
    # slot -> (score, j, h, path); path = list of (x, op)
    beam: list[tuple[float, int, int, list]] = [(0.0, 0, 0, [])]
    for i in range(length):
        tab = tables[min(i, kmax)]
        prev = canon_c[i - 1] if i > 0 else 0
        rep = i > 0 and canon_c[i] == prev
        drep = int(repeat_symbol(np.array(prev), model.view))
        cands = []  # (score, m, j', h', x, op, path)
        n_opt = n_dec + (1 if use_int and canon_c[i] == F else 0)
        for opt in range(n_opt):
            for slot in range(w):
                if slot >= len(beam):
                    continue
                score, j, h, path = beam[slot]
                if score == -math.inf:
                    continue
                m = opt * w + slot
                base = score + (pri.keep_repeat if rep else 0.0)
                if opt < n_dec:
                    s = opt
                    jj = j + s
                    if s == 0:
                        if jj < kn:
                            x, op, j2 = decrypt_sym(model.combine, d[i], k[jj]), 0, jj + 1
                        else:
                            x, op, j2 = decrypt_sym(model.combine, d[i], 0), OP_FILL, jj
                        sc = base
                    else:
                        if jj >= kn or i == 0:
                            continue
                        x = decrypt_sym(model.combine, d[i], k[jj])
                        need = repeat_key(model.combine, x, drep)
                        if any(k[j + t] != need for t in range(s)):
                            continue
                        op, j2 = s, jj + 1
                        sc = base + s * pri.skip
                    if use_int:
                        sc = sc + (pri.f_kept if x == F else 0.0)
                else:
                    x, op, j2 = F, OP_INTERRUPT, j
                    sc = score + pri.interrupt
                lm = float(tab[h, x])
                sc = sc + lm
                if sc == -math.inf:
                    continue
                h2 = (h * N + x) % hist_mod if i >= kmax else h * N + x
                cands.append((sc, m, j2, h2, x, op, path))
        cands.sort(key=lambda c: (-c[0], c[1]))
        seen, nxt = set(), []
        for sc, _m, j2, h2, x, op, path in cands:
            if (j2, h2) in seen:
                continue
            seen.add((j2, h2))
            nxt.append((sc, j2, h2, [*path, (x, op)]))
            if len(nxt) == w:
                break
        beam = nxt
    best = max(range(len(beam)), key=lambda s: (beam[s][0], -s))
    score, j, _h, path = beam[best]
    ops = [op for _x, op in path]
    return DecodeRecord(
        plain=[x for x, _op in path],
        interrupts=[i for i, op in enumerate(ops) if op == OP_INTERRUPT],
        skips={i: op for i, op in enumerate(ops) if 0 < op < OP_INTERRUPT},
        fill=[i for i, op in enumerate(ops) if op == OP_FILL],
        objective=score,
        keys_used=j,
        model=model_dict(model),
    )
