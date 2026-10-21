"""Classical primitives. Implemented as regression tests and building blocks only --
these families are closed on the unsolved pages."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from runeforge.gematria import N, as_indices
from runeforge.transforms.base import KeystreamTransform, Transform, as_runes


@dataclass(frozen=True)
class Atbash(Transform):
    """p = 28 - c (self-inverse)."""

    type_name = "atbash"

    def encrypt(self, plain) -> np.ndarray:
        return (N - 1) - as_runes(plain)

    def decrypt(self, cipher) -> np.ndarray:
        return (N - 1) - as_runes(cipher)

    def spec(self) -> dict:
        return {"type": self.type_name}


@dataclass(frozen=True)
class Shift(Transform):
    """Caesar shift: encrypt c = p + n, decrypt p = c - n (mod 29)."""

    n: int
    type_name = "shift"

    def encrypt(self, plain) -> np.ndarray:
        return (as_runes(plain) + self.n) % N

    def decrypt(self, cipher) -> np.ndarray:
        return (as_runes(cipher) - self.n) % N

    def spec(self) -> dict:
        return {"type": self.type_name, "n": int(self.n)}


@dataclass(frozen=True)
class Vigenere(KeystreamTransform):
    """Periodic key: c = p + k (mod 29). ``key`` may be indices, runes or a Latin word."""

    key: tuple[int, ...]
    type_name = "vigenere"

    def __init__(self, key):
        k = tuple(int(i) for i in as_indices(key))
        if not k:
            raise ValueError("empty key")
        object.__setattr__(self, "key", k)

    def keystream(self, n: int) -> np.ndarray:
        return np.resize(np.array(self.key, dtype=np.int64), n)

    def spec(self) -> dict:
        return {"type": self.type_name, "key": list(self.key)}


@dataclass(frozen=True)
class Beaufort(KeystreamTransform):
    """c = k - p (mod 29); self-reciprocal."""

    key: tuple[int, ...]
    type_name = "beaufort"

    def __init__(self, key):
        k = tuple(int(i) for i in as_indices(key))
        if not k:
            raise ValueError("empty key")
        object.__setattr__(self, "key", k)

    def keystream(self, n: int) -> np.ndarray:
        return np.resize(np.array(self.key, dtype=np.int64), n)

    def encrypt(self, plain) -> np.ndarray:
        p = as_runes(plain)
        return (self.keystream(p.size) - p) % N

    def decrypt(self, cipher) -> np.ndarray:
        c = as_runes(cipher)
        return (self.keystream(c.size) - c) % N

    def spec(self) -> dict:
        return {"type": self.type_name, "key": list(self.key)}
