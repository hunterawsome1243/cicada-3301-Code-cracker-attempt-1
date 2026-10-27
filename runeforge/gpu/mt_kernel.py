"""The ``mt19937-py27`` keystream as a CUDA kernel: one thread per seed (Phase 3).

A faster copy of ``runeforge.generators.mt19937_py27.MT19937Py27`` (the CPU reference, which
is the definition of the stream: ``runeforge/generators/base.py``), nothing more. One
plain-Python function, ``_mt_row``, holds everything: CPython's ``random.seed(<int>)``
(``init_by_array`` over the 32-bit words of the seed, one word for seeds below 2**32, two up
to 2**64 - 1), ``genrand_int32`` with its twist, and the four 2.7 reducers (``random29``:
``genrand_res53`` on word pairs times 29; ``grb5_mod``; ``grb5_rej``; ``shuffle29``). It is
compiled twice, as the beam kernel is (``runeforge/gpu/beam_kernel.py``):

* as a CUDA device function, called by ``_kernel`` (a thread seeds its own 624-word state in
  local memory and writes its row of symbols); under ``NUMBA_ENABLE_CUDASIM=1`` the same
  kernel runs on the CPU simulator;
* as a CPU ``numba.njit`` twin (``keys_cpu``), parallel over seeds.

Both must equal ``generators.keystream_batch`` symbol for symbol (.claude/rules/gpu.md), which
``runeforge.gpu.parity`` records per lane on >= 10^4 of the lane's seeds and
``tests/test_gpu_mt.py`` checks per mode, on both seed widths and across several twists. The
arithmetic is int64 with explicit masks (every intermediate of the C code fits), so no
unsigned/signed promotion can differ between the two compilations; ``random29`` and
``shuffle29`` use the reference's own float64 expressions (``a * 2**26 + b`` is exact, so a
fused multiply-add on the device changes nothing).

``keys_device`` leaves the rows on the device for ``beam_kernel.score_gpu``, so a sweep's
keys never cross the PCIe bus; the sweep re-generates every row it reports with the CPU
generator before believing it. Seeds are passed as two int64 words (low, high) because a
64-bit seed does not fit a signed int64. The 624-word state is int64 (5 KB of local memory
per thread): the first thing to shrink if the device number disappoints.
"""

from __future__ import annotations

import numpy as np
from numba import cuda, njit, prange

from runeforge.generators import Generator
from runeforge.generators.mt19937_py27 import MT19937Py27

N_MT = 624
M_MT = 397
MASK32 = 0xFFFFFFFF
UPPER = 0x80000000
LOWER = 0x7FFFFFFF
MATRIX_A = 0x9908B0DF
K = 29
MODES = {"random29": 0, "grb5_mod": 1, "grb5_rej": 2, "shuffle29": 3}
TWO26 = 67108864.0
INV53 = 1.0 / 9007199254740992.0


def _mt_row(seed_lo, seed_hi, mode, off, n, mt, pool, out):
    """Symbols ``off .. off + n - 1`` of one seed's stream into ``out[0:n]``. ``mt`` is the
    624-word scratch state, ``pool`` the 29-word shuffle scratch; both the caller's."""
    # random_seed: init_by_array(key = the 32-bit words of abs(seed), least significant first)
    mt[0] = 19650218
    for i in range(1, N_MT):
        p = mt[i - 1]
        mt[i] = (1812433253 * (p ^ (p >> 30)) + i) & MASK32
    nkey = 2 if seed_hi != 0 else 1
    i = 1
    j = 0
    for _ in range(N_MT):  # k = max(N, key_length) = N
        p = mt[i - 1]
        kj = seed_lo if j == 0 else seed_hi
        mt[i] = ((mt[i] ^ ((p ^ (p >> 30)) * 1664525)) + kj + j) & MASK32
        i += 1
        j += 1
        if i >= N_MT:
            mt[0] = mt[N_MT - 1]
            i = 1
        if j >= nkey:
            j = 0
    for _ in range(N_MT - 1):
        p = mt[i - 1]
        mt[i] = ((mt[i] ^ ((p ^ (p >> 30)) * 1566083941)) - i) & MASK32
        i += 1
        if i >= N_MT:
            mt[0] = mt[N_MT - 1]
            i = 1
    mt[0] = UPPER
    mti = N_MT  # the first genrand_int32 twists
    end = off + n
    pos = 0
    have_a = False
    a = 0.0
    si = K - 1  # shuffle29: the next Fisher-Yates index, 28 down to 1
    for t in range(K):
        pool[t] = t
    while pos < end:
        if mti >= N_MT:
            for kk in range(N_MT - M_MT):
                y = (mt[kk] & UPPER) | (mt[kk + 1] & LOWER)
                mt[kk] = mt[kk + M_MT] ^ (y >> 1) ^ ((y & 1) * MATRIX_A)
            for kk in range(N_MT - M_MT, N_MT - 1):
                y = (mt[kk] & UPPER) | (mt[kk + 1] & LOWER)
                mt[kk] = mt[kk + M_MT - N_MT] ^ (y >> 1) ^ ((y & 1) * MATRIX_A)
            y = (mt[N_MT - 1] & UPPER) | (mt[0] & LOWER)
            mt[N_MT - 1] = mt[M_MT - 1] ^ (y >> 1) ^ ((y & 1) * MATRIX_A)
            mti = 0
        y = mt[mti]
        mti += 1
        y ^= y >> 11
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        y ^= y >> 18
        if mode == 1:
            sym = (y >> 27) % K
        elif mode == 2:
            sym = y >> 27
            if sym >= K:
                continue
        else:
            if not have_a:
                a = np.float64(y >> 5)
                have_a = True
                continue
            have_a = False
            u = (a * TWO26 + np.float64(y >> 6)) * INV53
            if mode == 0:
                sym = np.int64(u * 29.0)
            else:
                jj = np.int64(u * np.float64(si + 1))
                tmp = pool[si]
                pool[si] = pool[jj]
                pool[jj] = tmp
                si -= 1
                if si > 0:
                    continue
                for t in range(K):
                    if pos >= off and pos < end:
                        out[pos - off] = pool[t]
                    pos += 1
                for t in range(K):
                    pool[t] = t
                si = K - 1
                continue
        if pos >= off:
            out[pos - off] = sym
        pos += 1
    return 0


_row_cpu = njit(_mt_row)
_row_dev = cuda.jit(device=True)(_mt_row)


@njit(parallel=True)
def _keys_cpu(lo, hi, mode, off, n, out):
    for r in prange(lo.shape[0]):
        mt = np.empty(N_MT, np.int64)
        pool = np.empty(K, np.int64)
        _row_cpu(lo[r], hi[r], mode, off, n, mt, pool, out[r])


@cuda.jit
def _kernel(lo, hi, mode, off, n, out):
    r = cuda.grid(1)
    if r >= lo.shape[0]:
        return
    mt = cuda.local.array(N_MT, np.int64)
    pool = cuda.local.array(K, np.int64)
    _row_dev(lo[r], hi[r], mode, off, n, mt, pool, out[r])


# --------------------------------------------------------------------------- host side


def supports(gen: Generator) -> bool:
    """Whether this kernel generates ``gen``'s family (the CPU generator stays the reference)."""
    return isinstance(gen, MT19937Py27)


def seed_words(gen: Generator, seeds) -> tuple[np.ndarray, np.ndarray]:
    """(low, high) 32-bit words of each seed as int64 arrays, after the generator's own
    range check (a seed outside 0 .. 2**seed_bits - 1 is refused, never folded)."""
    if not supports(gen):
        raise ValueError(f"no GPU kernel for generator {gen.name!r} (mt19937-py27 only)")
    ss = [gen.check_seed(s) for s in seeds]
    lo = np.array([s & MASK32 for s in ss], dtype=np.int64).reshape(-1)
    hi = np.array([s >> 32 for s in ss], dtype=np.int64).reshape(-1)
    return lo, hi


def _check_n(n: int, offset: int) -> None:
    if n < 0 or offset < 0:
        raise ValueError("n and offset must be >= 0")


def keys_cpu(gen: Generator, seeds, n: int, offset: int = 0) -> np.ndarray:
    """``keystream_batch(gen, seeds, offset + n)[:, offset:]`` from the njit twin."""
    _check_n(n, offset)
    lo, hi = seed_words(gen, seeds)
    out = np.zeros((lo.size, n), dtype=np.int64)
    if n and lo.size:
        _keys_cpu(lo, hi, MODES[gen.mode], offset, n, out)
    return out


def keys_device(gen: Generator, seeds, n: int, offset: int = 0, threads: int = 128):
    """The same rows as a device array (int64, shape (len(seeds), n)), for the beam kernel."""
    from runeforge.gpu import beam_kernel as bk

    if not bk.available():
        raise RuntimeError("no CUDA device (set NUMBA_ENABLE_CUDASIM=1 to use the simulator)")
    _check_n(n, offset)
    lo, hi = seed_words(gen, seeds)
    out = cuda.device_array((lo.size, n), dtype=np.int64)
    if n and lo.size:
        blocks = (lo.size + threads - 1) // threads
        _kernel[blocks, threads](
            cuda.to_device(lo), cuda.to_device(hi), MODES[gen.mode], offset, n, out
        )
    return out


def keys_gpu(gen: Generator, seeds, n: int, offset: int = 0, threads: int = 128) -> np.ndarray:
    """``keys_device`` copied back to the host."""
    return keys_device(gen, seeds, n, offset, threads).copy_to_host()
