"""The beam decoder as a CUDA kernel: one thread per key (Phase 3).

A faster copy of ``runeforge.beam.decode_batch``, nothing more (.claude/rules/gpu.md). One
plain-Python function, ``_beam_row``, holds the whole algorithm. It is compiled twice:

* as a CUDA device function, called by ``_kernel`` (one thread decodes one key row and writes
  its score); under ``NUMBA_ENABLE_CUDASIM=1`` the same kernel runs on the CPU simulator;
* as a CPU ``numba.njit`` twin (``score_cpu``), parallel over rows.

Both must agree with the numpy reference (``beam.decode_batch`` followed by the scorer's
``score_batch``) to the rules' tolerance: the same candidate order (``m = option * width +
slot``, with the interrupt option after every skip option), the same float expression order
for each candidate, the same merge of equal states (keep the best; ties to the lowest
candidate index) and the same top-``width`` selection. The kernel does not trace the path
back: it carries each hypothesis's scorer-only log-probability along with its objective, and
the best hypothesis's sum divided by L is the score the lane would compute from the decoded
plaintext (summed in another order, so equal to ~1e-13, inside the 1e-6 parity tolerance).
Survivors and crossers are re-decoded on the CPU for their plaintext and record, as the rules
require of anything a kernel reports.

Limits: one cipher per launch (the sweep and the nulls decode one window under many keys);
``width <= W_MAX`` and ``max_skip <= S_MAX`` (the presets use 8 and 6).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numba import cuda, njit, prange

from runeforge import beam

F = 0
N = 29
W_MAX = 16
S_MAX = 6
M_MAX = W_MAX * (S_MAX + 2)  # candidates per step: every skip option and the interrupt
NEG_INF = -math.inf
COMBINES = {"vigenere": 0, "variant-beaufort": 1, "beaufort": 2}


def _beam_row(
    d, canon, drep, isrep, k, tables, tab_off, kmax, hist_mod, comb, width, n_skips, use_int,
    pri_int, pri_fkept, pri_skip, pri_keep,
    j, h, sc, lm, cj, ch, csc, clm, cm, cstate, used,
):  # fmt: skip
    """Decode one key row; return (score, objective). Scratch arrays are the caller's."""
    length = d.shape[0]
    kn = k.shape[0]
    for w in range(width):
        j[w] = 0
        h[w] = 0
        sc[w] = NEG_INF
        lm[w] = 0.0
    sc[0] = 0.0
    nalive = 1
    for i in range(length):
        lev = i if i < kmax else kmax
        off = tab_off[lev]
        di = d[i]
        dr = drep[i]
        keep = pri_keep if isrep[i] else 0.0
        n = 0
        for s in range(n_skips + 1):
            if s > 0 and i == 0:
                break  # the filter never acts on the first rune
            for w in range(nalive):
                if sc[w] == NEG_INF:
                    continue
                jw = j[w]
                base = sc[w] + keep
                if s == 0:
                    kk = k[jw % kn]  # wraps round once the key is used up
                    c = base
                else:
                    if jw + s > kn - 1:
                        continue
                    k0 = k[jw]
                    run = True
                    for t in range(1, s):
                        if k[jw + t] != k0:
                            run = False
                            break
                    if not run:
                        continue
                    kk = k[jw + s]
                    # combine^-1 (vigenere, variant-beaufort, beaufort), then the key that
                    # re-enciphers x to the canonical repeat: every dropped symbol must be it
                    if comb == 0:
                        x = (di - kk) % 29
                        need = (dr - x) % 29
                    elif comb == 1:
                        x = (di + kk) % 29
                        need = (x - dr) % 29
                    else:
                        x = (kk - di) % 29
                        need = (dr + x) % 29
                    if k0 != need:
                        continue
                    c = base + s * pri_skip
                if s == 0:
                    if comb == 0:
                        x = (di - kk) % 29
                    elif comb == 1:
                        x = (di + kk) % 29
                    else:
                        x = (kk - di) % 29
                if use_int:
                    c = c + (pri_fkept if x == F else 0.0)
                inc = tables[off + h[w] * 29 + x]
                c = c + inc
                if c == NEG_INF:
                    continue
                hh = h[w] * 29 + x
                if i >= kmax:
                    hh = hh % hist_mod
                cj[n] = jw + s + 1
                ch[n] = hh
                csc[n] = c
                clm[n] = lm[w] + inc
                cm[n] = s * width + w
                cstate[n] = (jw + s + 1) * hist_mod + hh
                n += 1
        if use_int and canon[i] == F:
            for w in range(nalive):
                if sc[w] == NEG_INF:
                    continue
                inc = tables[off + h[w] * 29 + F]
                c = sc[w] + pri_int + inc
                if c == NEG_INF:
                    continue
                hh = h[w] * 29 + F
                if i >= kmax:
                    hh = hh % hist_mod
                cj[n] = j[w]
                ch[n] = hh
                csc[n] = c
                clm[n] = lm[w] + inc
                cm[n] = (n_skips + 1) * width + w
                cstate[n] = j[w] * hist_mod + hh
                n += 1
        if n == 0:
            return math.nan, math.nan  # no live path (the presets' priors never allow it)
        # merge equal states and keep the best `width`: repeatedly take the best remaining
        # candidate (highest objective, ties to the lowest index) and retire its state
        for c in range(n):
            used[c] = 0
        nsel = 0
        while nsel < width:
            best = -1
            for c in range(n):
                if used[c] == 1:
                    continue
                if best < 0 or csc[c] > csc[best] or (csc[c] == csc[best] and cm[c] < cm[best]):
                    best = c
            if best < 0:
                break
            st = cstate[best]
            for c in range(n):
                if used[c] == 0 and cstate[c] == st:
                    used[c] = 1
            j[nsel] = cj[best]
            h[nsel] = ch[best]
            sc[nsel] = csc[best]
            lm[nsel] = clm[best]
            nsel += 1
        for w in range(nsel, width):
            sc[w] = NEG_INF
        nalive = nsel
    bi = 0
    for w in range(1, width):
        if sc[w] > sc[bi]:
            bi = w
    return lm[bi] / length, sc[bi]


_row_cpu = njit(cache=False)(_beam_row)
_row_dev = cuda.jit(device=True)(_beam_row)


@njit(parallel=True, cache=False)
def _score_cpu(d, canon, drep, isrep, keys, tables, tab_off, kmax, hist_mod, comb, width,
               n_skips, use_int, pri_int, pri_fkept, pri_skip, pri_keep, out, obj):  # fmt: skip
    for r in prange(keys.shape[0]):
        j = np.empty(W_MAX, np.int64)
        h = np.empty(W_MAX, np.int64)
        sc = np.empty(W_MAX, np.float64)
        lm = np.empty(W_MAX, np.float64)
        cj = np.empty(M_MAX, np.int64)
        ch = np.empty(M_MAX, np.int64)
        csc = np.empty(M_MAX, np.float64)
        clm = np.empty(M_MAX, np.float64)
        cm = np.empty(M_MAX, np.int64)
        cstate = np.empty(M_MAX, np.int64)
        used = np.empty(M_MAX, np.int8)
        s, o = _row_cpu(
            d, canon, drep, isrep, keys[r], tables, tab_off, kmax, hist_mod, comb, width,
            n_skips, use_int, pri_int, pri_fkept, pri_skip, pri_keep,
            j, h, sc, lm, cj, ch, csc, clm, cm, cstate, used,
        )  # fmt: skip
        out[r] = s
        obj[r] = o


@cuda.jit
def _kernel(d, canon, drep, isrep, keys, tables, tab_off, kmax, hist_mod, comb, width,
            n_skips, use_int, pri_int, pri_fkept, pri_skip, pri_keep, out, obj):  # fmt: skip
    r = cuda.grid(1)
    if r >= keys.shape[0]:
        return
    j = cuda.local.array(W_MAX, np.int64)
    h = cuda.local.array(W_MAX, np.int64)
    sc = cuda.local.array(W_MAX, np.float64)
    lm = cuda.local.array(W_MAX, np.float64)
    cj = cuda.local.array(M_MAX, np.int64)
    ch = cuda.local.array(M_MAX, np.int64)
    csc = cuda.local.array(M_MAX, np.float64)
    clm = cuda.local.array(M_MAX, np.float64)
    cm = cuda.local.array(M_MAX, np.int64)
    cstate = cuda.local.array(M_MAX, np.int64)
    used = cuda.local.array(M_MAX, np.int8)
    s, o = _row_dev(
        d, canon, drep, isrep, keys[r], tables, tab_off, kmax, hist_mod, comb, width,
        n_skips, use_int, pri_int, pri_fkept, pri_skip, pri_keep,
        j, h, sc, lm, cj, ch, csc, clm, cm, cstate, used,
    )  # fmt: skip
    out[r] = s
    obj[r] = o


# --------------------------------------------------------------------------- host side


@dataclass
class Prepared:
    """One cipher, scorer and model, laid out for the kernel (host arrays)."""

    args: tuple  # (d, canon, drep, isrep) then, after the keys, the scalar and table args
    rest: tuple
    length: int


def prepare(cipher, scorer, model: beam.BeamModel) -> Prepared:
    if model.width > W_MAX or model.n_skips > S_MAX:
        raise ValueError(f"the kernel holds width <= {W_MAX} and max_skip <= {S_MAX}")
    d = np.ascontiguousarray(np.asarray(cipher, dtype=np.int64).ravel())
    if d.size == 0:
        raise ValueError("empty cipher")
    canon = beam.canonical(d[None, :], model.view)[0]
    prev = np.concatenate([[0], canon[:-1]])
    drep = beam.repeat_symbol(prev, model.view)
    isrep = (canon == prev).astype(np.int8)
    isrep[0] = 0
    tabs = beam._tables(scorer)
    flat = np.ascontiguousarray(np.concatenate([t.ravel() for t in tabs]))
    tab_off = np.cumsum([0, *[t.size for t in tabs[:-1]]]).astype(np.int64)
    kmax = scorer.order - 1
    pri = beam._priors(model)
    rest = (
        flat,
        tab_off,
        kmax,
        N**kmax,
        COMBINES[model.combine],
        model.width,
        model.n_skips,
        model.interrupt_prob > 0,
        pri.interrupt,
        pri.f_kept,
        pri.skip,
        pri.keep_repeat,
    )
    return Prepared((d, canon, drep, isrep), rest, int(d.size))


def _check_keys(keys, length: int) -> np.ndarray:
    k = np.ascontiguousarray(np.atleast_2d(np.asarray(keys, dtype=np.int64)))
    if k.shape[1] < length:
        raise ValueError(f"the beam needs >= {length} key symbols per row, got {k.shape[1]}")
    return k


def score_cpu(cipher, keys, scorer, model: beam.BeamModel) -> tuple[np.ndarray, np.ndarray]:
    """(scores, objectives) from the njit twin of the kernel."""
    p = prepare(cipher, scorer, model)
    k = _check_keys(keys, p.length)
    out = np.empty(k.shape[0])
    obj = np.empty(k.shape[0])
    _score_cpu(*p.args, k, *p.rest, out, obj)
    return out, obj


def available() -> bool:
    """A CUDA device, or the numba simulator (NUMBA_ENABLE_CUDASIM=1)."""
    return bool(cuda.is_available())


def simulated() -> bool:
    from numba import config

    return bool(getattr(config, "ENABLE_CUDASIM", 0))


def score_gpu(
    cipher, keys, scorer, model: beam.BeamModel, threads: int = 128
) -> tuple[np.ndarray, np.ndarray]:
    """(scores, objectives) from the CUDA kernel (or its simulator)."""
    if not available():
        raise RuntimeError("no CUDA device (set NUMBA_ENABLE_CUDASIM=1 to use the simulator)")
    p = prepare(cipher, scorer, model)
    k = _check_keys(keys, p.length)
    dev = [cuda.to_device(a) for a in p.args]
    dk = cuda.to_device(k)
    flat, tab_off, *scalars = p.rest
    dflat, doff = cuda.to_device(flat), cuda.to_device(tab_off)
    out = cuda.device_array(k.shape[0], dtype=np.float64)
    obj = cuda.device_array(k.shape[0], dtype=np.float64)
    blocks = (k.shape[0] + threads - 1) // threads
    _kernel[blocks, threads](*dev, dk, dflat, doff, *scalars, out, obj)
    return out.copy_to_host(), obj.copy_to_host()


def score_reference(cipher, keys, scorer, model: beam.BeamModel):
    """(scores, objectives) from the numpy reference the kernel must match."""
    res = beam.decode_batch(cipher, keys, scorer, model)
    return scorer.score_batch(res.plain), res.objective
