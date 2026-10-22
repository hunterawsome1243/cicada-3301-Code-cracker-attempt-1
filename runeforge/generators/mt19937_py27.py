"""CPython 2.7 ``random.seed(<int>)`` + Mersenne Twister, byte-exact, with 2.7's reducers.

The 2012 author, if they used a PRNG at all, ran ``python2.7``. This is the stream such a
script produced, reduced to runes the four ways Dukotah's round19/G3 ``gen_py27.py`` defines
(and their round27 ``grind27.c`` swept), so our sweeps and theirs cover the same object:

* ``random29``  ``int(random()*29)``; in 2.7 also ``randrange(29)``, ``randint(0,28)`` and
  ``choice(range(29))`` (measured identical on real 2.7.3, their gate V5). 2 words/rune.
* ``grb5_mod``  ``getrandbits(5) % 29``; 1 word/rune, biased (0, 1, 2 at double weight).
* ``grb5_rej``  ``getrandbits(5)``, rejecting 29..31; variable words/rune.
* ``shuffle29`` concatenated 2.7 ``shuffle(range(29))`` blocks
  (``j = int(random()*(i+1))`` for i = 28..1); 56 words per 29 runes.

Int seeds only: 2.7 seeds ``abs(seed)`` split into 32-bit words for ``init_by_array``. The
``str``/``float`` hash path and ``jumpahead`` are not here (``gen_py27`` has them); a
Python-2 string seed on amd64 *is* its unsigned 64-bit ``hash()`` image, which is why
``seed_bits=64`` exists. Seeds are 0 .. 2**seed_bits - 1 (default 32, Dukotah's R27 lanes).

Implementation choice: the C implementation, not a port. CPython 3's ``random.Random(int)``
runs the same ``init_by_array`` over the same 32-bit chunks of ``abs(seed)`` (a single
``[0]`` word for seed 0), and the same ``genrand_int32``; ``getrandbits(32*m)`` returns the
first ``m`` words least-significant first. ``genrand_res53`` and the four reducers are then
re-done in numpy on those words -- never via Python 3's ``randrange``/``shuffle``, which use
``_randbelow`` and differ from 2.7. The proof is ``tests/test_generators.py``: equality with
``gen_py27`` on 260 seeds x 4 modes (seed 0, 2**31, 2**32 - 1, and 64-bit seeds up to
2**64 - 1), on streams that cross several MT twists, and with the real-CPython-2.7.3 vectors
pinned in round19/G3 ``validation.json`` (64-bit hash images). Because a future interpreter
could change this, ``_check_interpreter`` re-checks two pinned 2.7.3 vectors once per
process and refuses to run if they drift.

Speed (n = 240, one CPU core, Python 3.13 / numpy 2.5, 2026-10-22, best of 5 x 20,000 seeds
through ``keystream_batch``): random29 38k, grb5_mod 57k, grb5_rej 45k, shuffle29 30k seeds/s;
``gen_py27`` (pure Python) about 800 seeds/s in every mode. About 9 us of each seed is
``random.Random(seed)`` itself. ``tests/test_generators.py::test_mt_speed`` prints the rate.
"""

from __future__ import annotations

import functools
import random
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from runeforge.generators.base import Generator, take_accepted

MODES = ("random29", "grb5_mod", "grb5_rej", "shuffle29")
K = 29

# (seed, mode, first 16 symbols). The first two were measured on real CPython 2.7.3 and
# 2.7.18 (round19/G3 validation.json, "CICADA3301": hash 8810433306790406628, init_by_array
# key [2961385956, 2051338857]). The last two are gen_py27's int-seed 3301 streams; their
# gate V4 matched int seed 3301 against real 2.7.3 (int_3301).
_CICADA = 8810433306790406628
_PINNED = (
    (_CICADA, "random29", (0, 17, 2, 22, 9, 22, 27, 11, 10, 13, 27, 11, 28, 5, 26, 22)),
    (_CICADA, "grb5_rej", (1, 28, 18, 23, 2, 25, 24, 10, 10, 25, 2, 21, 12, 16, 11, 20)),
    (3301, "random29", (6, 6, 13, 12, 13, 17, 25, 23, 11, 17, 21, 15, 14, 25, 4, 19)),
    (3301, "shuffle29", (1, 27, 3, 5, 7, 19, 16, 0, 24, 15, 10, 18, 4, 21, 2, 23)),
)


def _words(seeds: list[int], m: int) -> np.ndarray:
    """The first ``m`` genrand_int32 outputs of each seed, shape (len(seeds), m) uint32."""
    buf = b"".join(random.Random(s).getrandbits(32 * m).to_bytes(4 * m, "little") for s in seeds)
    return np.frombuffer(buf, dtype="<u4").reshape(len(seeds), m)


def _res53(w: np.ndarray) -> np.ndarray:
    """genrand_res53 on consecutive word pairs: (a*2**26 + b) / 2**53, exact in float64."""
    a = (w[:, 0::2] >> 5).astype(np.float64)
    b = (w[:, 1::2] >> 6).astype(np.float64)
    return (a * 67108864.0 + b) * (1.0 / 9007199254740992.0)


def _grb5(seeds: list[int], m: int) -> tuple[np.ndarray, np.ndarray]:
    v = (_words(seeds, m) >> 27).astype(np.int64)
    return v, v < K


def _shuffle29(seeds: list[int], n: int) -> np.ndarray:
    blocks = -(-n // K)
    u = _res53(_words(seeds, 2 * (K - 1) * blocks)).reshape(len(seeds), blocks, K - 1)
    rows = np.arange(len(seeds))
    out = np.empty((len(seeds), blocks * K), dtype=np.int64)
    for b in range(blocks):
        pool = np.tile(np.arange(K, dtype=np.int64), (len(seeds), 1))
        for t, i in enumerate(range(K - 1, 0, -1)):
            j = (u[:, b, t] * (i + 1)).astype(np.int64)
            pi = pool[:, i].copy()
            pool[:, i] = pool[rows, j]
            pool[rows, j] = pi
        out[:, b * K : (b + 1) * K] = pool
    return out[:, :n]


def _reduce(mode: str, seeds: list[int], n: int) -> np.ndarray:
    if mode == "random29":
        return (_res53(_words(seeds, 2 * n)) * K).astype(np.int64)
    if mode == "grb5_mod":
        return (_words(seeds, n) >> 27).astype(np.int64) % K
    if mode == "grb5_rej":
        return take_accepted(seeds, n, _grb5, n + n // 8 + 4 * int(n**0.5) + 8)
    if mode == "shuffle29":
        return _shuffle29(seeds, n)
    raise ValueError(f"mt19937-py27: unknown mode {mode!r}")


@functools.cache
def _check_interpreter() -> None:
    for seed, mode, want in _PINNED:
        got = tuple(int(x) for x in _reduce(mode, [seed], len(want))[0])
        if got != want:
            raise RuntimeError(
                "this interpreter's random.Random no longer reproduces CPython 2.7's "
                f"MT19937 (seed {seed}, {mode}): got {got}, want {want}"
            )


@dataclass(frozen=True)
class MT19937Py27(Generator):
    name: ClassVar[str] = "mt19937-py27"
    mode: str = "random29"
    seed_bits: int = 32

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mt19937-py27: mode must be one of {MODES}, got {self.mode!r}")
        if self.seed_bits not in (32, 64):
            raise ValueError("mt19937-py27: seed_bits must be 32 or 64")

    def _batch(self, seeds: list[int], n: int) -> np.ndarray:
        _check_interpreter()
        return _reduce(self.mode, seeds, n)
