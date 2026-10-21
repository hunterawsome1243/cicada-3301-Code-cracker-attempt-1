"""Transform protocol and composition.

A transform is a pure, invertible map on rune-index arrays (mod 29) with an explicit
``encrypt``/``decrypt`` pair, so the same code that decodes a page also enciphers the
synthetic pages used by the plant-and-recover controls.

Keyed transforms consume one key symbol per enciphered rune, in order. That is what
makes the F-interrupt rule (an unencrypted F does not advance the key) a property of
the *decoder* rather than of each cipher: see :mod:`runeforge.interrupts`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from runeforge.gematria import N


def as_runes(x) -> np.ndarray:
    arr = np.asarray(x, dtype=np.int64)
    if arr.ndim != 1:
        raise ValueError("expected a 1-D sequence of rune indices")
    if arr.size and (arr.min() < 0 or arr.max() >= N):
        raise ValueError("rune index out of range 0..28")
    return arr


class Transform(ABC):
    """An invertible cipher primitive on rune indices."""

    type_name: str = ""

    @abstractmethod
    def encrypt(self, plain) -> np.ndarray: ...

    @abstractmethod
    def decrypt(self, cipher) -> np.ndarray: ...

    @abstractmethod
    def spec(self) -> dict:
        """JSON-serialisable description, round-trippable through ``from_spec``."""

    def __call__(self, cipher) -> np.ndarray:
        return self.decrypt(cipher)


class KeystreamTransform(Transform):
    """c_i = combine(p_i, k_i) for a keystream k consumed one symbol per rune."""

    @abstractmethod
    def keystream(self, n: int) -> np.ndarray:
        """The first ``n`` key symbols, reduced mod 29."""

    def encrypt(self, plain) -> np.ndarray:
        p = as_runes(plain)
        return (p + self.keystream(p.size)) % N

    def decrypt(self, cipher) -> np.ndarray:
        c = as_runes(cipher)
        return (c - self.keystream(c.size)) % N


@dataclass(frozen=True)
class Compose(Transform):
    """Decryption applies ``steps`` in order; encryption applies their inverses in reverse."""

    steps: tuple[Transform, ...]
    type_name = "compose"

    def __init__(self, steps: Sequence[Transform]):
        object.__setattr__(self, "steps", tuple(steps))

    def decrypt(self, cipher) -> np.ndarray:
        x = as_runes(cipher)
        for t in self.steps:
            x = t.decrypt(x)
        return x

    def encrypt(self, plain) -> np.ndarray:
        x = as_runes(plain)
        for t in reversed(self.steps):
            x = t.encrypt(x)
        return x

    def spec(self) -> dict:
        return {"type": self.type_name, "steps": [t.spec() for t in self.steps]}


@dataclass(frozen=True)
class Identity(Transform):
    type_name = "identity"

    def encrypt(self, plain) -> np.ndarray:
        return as_runes(plain).copy()

    def decrypt(self, cipher) -> np.ndarray:
        return as_runes(cipher).copy()

    def spec(self) -> dict:
        return {"type": self.type_name}
