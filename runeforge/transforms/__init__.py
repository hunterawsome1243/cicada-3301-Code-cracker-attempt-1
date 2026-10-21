"""Composable, invertible cipher primitives on rune indices (mod 29)."""

from __future__ import annotations

from runeforge.transforms.base import Compose, Identity, KeystreamTransform, Transform, as_runes
from runeforge.transforms.classical import Atbash, Beaufort, Shift, Vigenere
from runeforge.transforms.stream import (
    Chain,
    RunningKey,
    StreamSubtract,
    TotientPrimeStream,
)

__all__ = [
    "Atbash",
    "Beaufort",
    "Chain",
    "Compose",
    "Identity",
    "KeystreamTransform",
    "RunningKey",
    "Shift",
    "StreamSubtract",
    "TotientPrimeStream",
    "Transform",
    "Vigenere",
    "as_runes",
    "from_method",
    "from_spec",
]


def from_spec(spec: dict) -> Transform:
    """Rebuild a transform from its ``spec()`` dictionary."""
    kind = spec["type"]
    if kind == "identity":
        return Identity()
    if kind == "atbash":
        return Atbash()
    if kind == "shift":
        return Shift(int(spec["n"]))
    if kind == "vigenere":
        return Vigenere(spec["key"])
    if kind == "beaufort":
        return Beaufort(spec["key"])
    if kind == "stream_subtract":
        return StreamSubtract(spec["stream"])
    if kind == "totient_prime_stream":
        return TotientPrimeStream(int(spec.get("start", 0)))
    if kind == "running_key":
        return RunningKey(spec["text"], spec.get("offset", 0), spec.get("direction", "forward"))
    if kind == "chain":
        inc = spec.get("increments")
        return Chain(None if inc is None else from_spec(inc), int(spec.get("c0", 0)))
    if kind == "compose":
        return Compose([from_spec(s) for s in spec["steps"]])
    raise ValueError(f"unknown transform type {kind!r}")


def from_method(method: dict) -> Transform:
    """A solved-section method ``{"steps": [...]}`` -> one decryption pipeline."""
    steps = [from_spec(s) for s in method["steps"]]
    if not steps:
        return Identity()
    return steps[0] if len(steps) == 1 else Compose(steps)
