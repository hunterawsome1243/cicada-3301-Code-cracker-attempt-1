"""Aperiodic keystream primitives: generic stream subtraction, the page-56 totient
stream, running keys, and the chain cipher."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from runeforge.gematria import N, as_indices
from runeforge.primes import first_primes
from runeforge.transforms.base import KeystreamTransform, Transform, as_runes


@dataclass(frozen=True)
class StreamSubtract(KeystreamTransform):
    """Decrypt p = c - k with an explicit keystream (totient, PRNG, running key...)."""

    stream: tuple[int, ...]
    type_name = "stream_subtract"

    def __init__(self, stream):
        object.__setattr__(self, "stream", tuple(int(v) % N for v in np.asarray(stream).ravel()))

    def keystream(self, n: int) -> np.ndarray:
        if n > len(self.stream):
            raise ValueError(f"keystream has {len(self.stream)} symbols, {n} needed")
        return np.array(self.stream[:n], dtype=np.int64)

    def spec(self) -> dict:
        return {"type": self.type_name, "stream": list(self.stream)}


@dataclass(frozen=True)
class TotientPrimeStream(KeystreamTransform):
    """k_n = phi(p_n) = p_n - 1 (mod 29) over the primes 2, 3, 5, ... -- the AN END method.

    ``start`` skips that many primes (0 = start at 2).
    """

    start: int = 0
    type_name = "totient_prime_stream"

    def keystream(self, n: int) -> np.ndarray:
        return (first_primes(self.start + n)[self.start :] - 1) % N

    def spec(self) -> dict:
        return {"type": self.type_name, "start": int(self.start)}


@dataclass(frozen=True)
class RunningKey(KeystreamTransform):
    """Keystream taken from a text (rune indices), from ``offset``, read forward or reversed."""

    text: tuple[int, ...]
    offset: int = 0
    direction: str = "forward"
    type_name = "running_key"

    def __init__(self, text, offset: int = 0, direction: str = "forward"):
        if direction not in ("forward", "reverse"):
            raise ValueError("direction must be 'forward' or 'reverse'")
        object.__setattr__(self, "text", tuple(int(i) for i in as_indices(text)))
        object.__setattr__(self, "offset", int(offset))
        object.__setattr__(self, "direction", direction)

    def keystream(self, n: int) -> np.ndarray:
        src = np.array(self.text, dtype=np.int64)
        if self.direction == "reverse":
            src = src[::-1]
        if self.offset < 0 or self.offset + n > src.size:
            raise ValueError(f"running key too short: offset {self.offset} + {n} > {src.size}")
        return src[self.offset : self.offset + n]

    def spec(self) -> dict:
        return {
            "type": self.type_name,
            "text": list(self.text),
            "offset": self.offset,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class Chain(Transform):
    """Chain cipher c_i = c_{i-1} + p_i + k_i (mod 29), c_{-1} = ``c0``.

    The increments come from ``increments`` (any keystream transform; None = all zero).
    This is the only published mechanism that reproduces the LP2 doublet deficit.
    """

    increments: KeystreamTransform | None = None
    c0: int = 0
    type_name = "chain"

    def _k(self, n: int) -> np.ndarray:
        if self.increments is None:
            return np.zeros(n, dtype=np.int64)
        return self.increments.keystream(n) % N

    def encrypt(self, plain) -> np.ndarray:
        p = as_runes(plain)
        # c_i = c0 + sum_{j<=i} (p_j + k_j)
        return (self.c0 + np.cumsum(p + self._k(p.size))) % N

    def decrypt(self, cipher) -> np.ndarray:
        c = as_runes(cipher)
        prev = np.concatenate(([self.c0], c[:-1])) if c.size else c
        return (c - prev - self._k(c.size)) % N

    def spec(self) -> dict:
        return {
            "type": self.type_name,
            "increments": None if self.increments is None else self.increments.spec(),
            "c0": int(self.c0),
        }
