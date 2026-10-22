"""The generator contract shared by every CPU reference keystream.

A generator maps ``(seed, n)`` to ``n`` key symbols in 0..28, deterministically, and
``keystream(seed, n)`` is always a prefix of ``keystream(seed, n + k)``: the lane runtime
slices ``key_offset`` symbols off the front, and every GPU kernel is checked against these
streams on 10^4 seeds before a benchmark counts (spec section 4.2, ``.claude/rules/gpu.md``).
So the CPU reference *is* the definition of the stream, not a model of it. Seeds outside
``0 .. 2**seed_bits - 1`` are refused rather than folded, so a sweep's stated coverage is
never silently aliased.
"""

from __future__ import annotations

import dataclasses
import operator
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from typing import ClassVar

import numpy as np

CHUNK = 2048  # seeds per _batch call: bounds the temporaries, keeps them cache-sized


class Generator(ABC):
    """Base for the frozen-dataclass generators; ``spec()`` lists the constructor params."""

    name: ClassVar[str]
    seed_bits: int

    def check_seed(self, seed) -> int:
        if isinstance(seed, bool):
            raise TypeError(f"{self.name}: a bool seed is almost certainly a bug")
        s = operator.index(seed)
        if not 0 <= s < 1 << self.seed_bits:
            raise ValueError(f"{self.name}: seed {s} outside 0 .. 2**{self.seed_bits} - 1")
        return s

    def keystream(self, seed: int, n: int) -> np.ndarray:
        """The first ``n`` key symbols of ``seed``'s stream, int64 in 0..28."""
        return self.batch([seed], n)[0]

    def batch(self, seeds: Iterable[int], n: int) -> np.ndarray:
        """``keystream`` for each seed, stacked to shape ``(len(seeds), n)``."""
        ss = [self.check_seed(s) for s in seeds]
        n = operator.index(n)
        if n < 0:
            raise ValueError("n must be >= 0")
        out = np.zeros((len(ss), n), dtype=np.int64)
        if n:
            for i in range(0, len(ss), CHUNK):
                out[i : i + CHUNK] = self._batch(ss[i : i + CHUNK], n)
        return out

    @abstractmethod
    def _batch(self, seeds: list[int], n: int) -> np.ndarray:
        """Validated seeds (Python ints) and n >= 1 -> int64 array ``(len(seeds), n)``."""

    def spec(self) -> dict:
        """JSON-able; ``generators.get(**g.spec())`` rebuilds an equal generator."""
        return {"name": self.name, **dataclasses.asdict(self)}


def take_accepted(
    seeds: list[int],
    n: int,
    draw: Callable[[list[int], int], tuple[np.ndarray, np.ndarray]],
    m: int,
) -> np.ndarray:
    """Row-wise rejection sampling: the first ``n`` accepted values of each seed's stream.

    ``draw(seeds, m)`` returns ``(values, accepted)``, both of shape ``(len(seeds), w)``,
    for the first ``m`` draw units of each stream (``w`` grows with ``m``; a larger ``m``
    must extend, never change, the smaller one). Rows that accept fewer than ``n`` are
    redrawn with ``2m`` -- rare when ``m`` carries a few standard deviations of margin.
    """
    out = np.empty((len(seeds), n), dtype=np.int64)
    todo = np.arange(len(seeds))
    while todo.size:
        vals, ok = draw([seeds[i] for i in todo], m)
        full = ok.sum(axis=1) >= n
        sel = ok & (np.cumsum(ok, axis=1) <= n) & full[:, None]
        out[todo[full]] = vals[sel].reshape(-1, n)
        todo, m = todo[~full], 2 * m
    return out
