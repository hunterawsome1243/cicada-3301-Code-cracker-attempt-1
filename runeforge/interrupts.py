"""The F-interrupt rule.

House rule on the solved pages: a plaintext F is written as an unencrypted ᚠ and does
NOT advance the key -- every one of them: the keyed sections' 14 plaintext F's are all
interrupters. Not every ciphertext ᚠ is an interrupt, though (WELCOME: 11 of 25, A KOAN 2:
2 of 5, AN END: 1 of 5; the rest are enciphered runes that landed on ᚠ), so decoders have
to choose.

Because every keyed transform consumes one key symbol per *enciphered* rune, skipping
interrupt positions is the same as decrypting the subsequence that excludes them and
copying the interrupts through unchanged. That is how both directions are implemented
here, for any transform.

* ``decode_rigid``      -- no interrupts (baseline; rejects correct keys under the rule).
* ``decode_skip_known`` -- a given interrupt set (reproduces the solved pages).
* ``decode_beam``       -- every ᚠ is an interrupt-or-not choice, beam-searched with a scorer
  (spec section 2.4 ``beam(scorer, width)``; the algorithm is :mod:`runeforge.beam`). Given
  only the key, it re-derives WELCOME's 11-of-25, A KOAN 2's 2-of-5 and AN END's 1-of-5
  interrupt sets (tests/test_beam.py).
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from runeforge.transforms.base import Transform, as_runes

F = 0  # ᚠ


def f_positions(cipher) -> np.ndarray:
    """Positions of every ᚠ (candidate interrupter) in a ciphertext."""
    return np.flatnonzero(as_runes(cipher) == F)


def _mask(n: int, interrupts: Iterable[int], cipher: np.ndarray | None) -> np.ndarray:
    idx = np.array(sorted(set(int(i) for i in interrupts)), dtype=np.int64)
    if idx.size and (idx[0] < 0 or idx[-1] >= n):
        raise ValueError(f"interrupt position out of range 0..{n - 1}")
    if cipher is not None and idx.size and np.any(cipher[idx] != F):
        bad = idx[cipher[idx] != F].tolist()
        raise ValueError(f"interrupt positions must hold ᚠ in the ciphertext: {bad}")
    keep = np.ones(n, dtype=bool)
    keep[idx] = False
    return keep


def decode_rigid(cipher, transform: Transform) -> np.ndarray:
    return transform.decrypt(as_runes(cipher))


def decode_skip_known(cipher, transform: Transform, interrupts: Iterable[int]) -> np.ndarray:
    """Decrypt, passing ``interrupts`` through unchanged and not advancing the key there."""
    c = as_runes(cipher)
    keep = _mask(c.size, interrupts, c)
    out = c.copy()
    out[keep] = transform.decrypt(c[keep])
    return out


def encrypt_with_interrupts(plain, transform: Transform, interrupts: Iterable[int]) -> np.ndarray:
    """Inverse of :func:`decode_skip_known`: interrupt positions (plaintext F) are written
    as a bare ᚠ and do not consume key."""
    p = as_runes(plain)
    keep = _mask(p.size, interrupts, None)
    if np.any(p[~keep] != F):
        raise ValueError("only a plaintext F can be an interrupter")
    out = p.copy()
    out[keep] = transform.encrypt(p[keep])
    return out


def decode_beam(
    cipher, transform: Transform, scorer, width: int = 8, interrupt_prob: float = 15 / 16
) -> tuple[np.ndarray, list[int]]:
    """Decrypt with a keyed transform, choosing the interrupters by beam search.

    Returns the plaintext and the chosen interrupt positions, which
    ``decode_skip_known(cipher, transform, interrupts)`` reproduces exactly. The transform
    must be a keystream cipher (p = c - k, e.g. Vigenere, StreamSubtract, TotientPrimeStream,
    RunningKey) or Beaufort (p = k - c); other transforms have no key position to hold."""
    from runeforge import beam
    from runeforge.transforms.base import KeystreamTransform
    from runeforge.transforms.classical import Beaufort

    c = as_runes(cipher)
    if isinstance(transform, Beaufort):
        combine = "beaufort"
    elif isinstance(transform, KeystreamTransform) and (
        type(transform).decrypt is KeystreamTransform.decrypt
    ):
        combine = "vigenere"
    else:
        raise TypeError(f"the beam needs a keystream transform, got {type(transform).__name__}")
    model = beam.BeamModel(combine=combine, width=width, interrupt_prob=interrupt_prob)
    rec = beam.decode_record(c, transform.keystream(c.size), scorer, model)
    return np.asarray(rec.plain, dtype=np.int64), rec.interrupts
