"""One lane's cipher model, shared by gate, control, sweep and crosser replay.

The same functions encipher synthetic plants (forward model, with the anti-repeat filter
and F-interrupts) and decode candidates (rigid), so the control exercises exactly the code
path the sweep runs (Rule 2: "through the *same* pipeline").

Conventions (mod 29):
* ``combine``: vigenere c = p + k, variant-beaufort c = p - k, beaufort c = k - p.
* ``ciphertext_view`` is applied to the canonical runes before decoding:
  raw; atbash 28 - c; first-difference d_i = c_i - c_{i-1}; chain-increment d_i - 1
  (a chain c_i = c_{i-1} + s_i with s_i in 1..28 maps to 0..27), with c_{-1} = 0.
* The anti-repeat filter (encipher side): when a rune would repeat the previous cipher
  rune, it survives with probability ``p_keep``; otherwise one key symbol is skipped and
  the rune re-enciphered. The rigid decoder cannot follow those skips -- the Phase 2
  beam can -- so filter lanes fail their control until then (INCONCLUSIVE (power)).
"""

from __future__ import annotations

import numpy as np

from runeforge import canon, generators
from runeforge.gematria import N
from runeforge.lanes import LaneSpec

F = 0


def view(cipher: np.ndarray, name: str) -> np.ndarray:
    c = np.asarray(cipher, dtype=np.int64)
    if name == "raw":
        return c.copy()
    if name == "atbash":
        return (N - 1) - c
    prev = np.concatenate(([0], c[:-1]))
    if name == "first-difference":
        return (c - prev) % N
    if name == "chain-increment":
        return (c - prev - 1) % N
    raise ValueError(f"unknown ciphertext view {name!r}")


def unview(model_cipher: np.ndarray, name: str) -> np.ndarray:
    """The canonical-rune stream whose ``view`` is ``model_cipher`` (for synthetic plants)."""
    d = np.asarray(model_cipher, dtype=np.int64)
    if name == "raw":
        return d.copy()
    if name == "atbash":
        return (N - 1) - d
    if name == "first-difference":
        return np.cumsum(d) % N
    if name == "chain-increment":
        return np.cumsum(d + 1) % N
    raise ValueError(f"unknown ciphertext view {name!r}")


def lane_cipher(lane: LaneSpec) -> np.ndarray:
    """The lane's selected unsolved pages (continuous), with its view applied."""
    lp2 = canon.load_lp2()
    bad = [n for n in lane.pages if n not in canon.UNSOLVED_LP2_PAGES]
    if bad:
        raise ValueError(f"lane pages must be unsolved LP2 pages 0-55, got {bad}")
    return view(lp2.stream(lane.pages), lane.ciphertext_view)


def generator(lane: LaneSpec):
    return generators.get(lane.generator, **lane.generator_params)


def keys(lane: LaneSpec, seed: int, n: int) -> np.ndarray:
    return generator(lane).keystream(int(seed), lane.key_offset + n)[lane.key_offset :]


def keys_batch(lane: LaneSpec, seeds, n: int) -> np.ndarray:
    k = generators.keystream_batch(generator(lane), [int(s) for s in seeds], lane.key_offset + n)
    return k[:, lane.key_offset :]


def decrypt(lane: LaneSpec, cipher, k) -> np.ndarray:
    """Rigid decode; broadcasts a (L,) cipher against (B, L) keys."""
    c, k = np.asarray(cipher, dtype=np.int64), np.asarray(k, dtype=np.int64)
    if lane.combine == "vigenere":
        return (c - k) % N
    if lane.combine == "variant-beaufort":
        return (c + k) % N
    return (k - c) % N


def _enc1(combine: str, p: int, k: int) -> int:
    if combine == "vigenere":
        return (p + k) % N
    if combine == "variant-beaufort":
        return (p - k) % N
    return (k - p) % N


def encrypt(lane: LaneSpec, plain, k, rng: np.random.Generator) -> tuple[np.ndarray, int]:
    """Forward model in the lane's view. Returns (cipher, key symbols consumed).

    ``k`` must be long enough for the skips (2x the plaintext is ample).
    """
    p = np.asarray(plain, dtype=np.int64)
    k = np.asarray(k, dtype=np.int64)
    out = np.empty(p.size, dtype=np.int64)
    j, prev = 0, -1
    use_filter = lane.filter_model == "anti-repeat"
    for i, x in enumerate(p.tolist()):
        if x == F and lane.interrupt_prob and rng.random() < lane.interrupt_prob:
            out[i] = prev = F  # unencrypted interrupter; the key does not advance
            continue
        c = _enc1(lane.combine, x, int(k[j]))
        j += 1
        while use_filter and c == prev and rng.random() >= lane.p_keep:
            c = _enc1(lane.combine, x, int(k[j]))
            j += 1
        out[i] = prev = c
    return out, j


def score_batch(scorer, plains) -> np.ndarray:
    return scorer.score_batch(np.atleast_2d(plains))
