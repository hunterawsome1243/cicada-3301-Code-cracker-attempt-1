"""One lane's cipher model, shared by gate, control, sweep and crosser replay.

The same functions encipher synthetic plants (forward model, with the anti-repeat filter
and F-interrupts) and decode candidates (the preset's decoder: rigid or beam), so the control
exercises exactly the code path the sweep runs (Rule 2: "through the *same* pipeline").

Conventions (mod 29):
* ``combine``: vigenere c = p + k, variant-beaufort c = p - k, beaufort c = k - p.
* ``ciphertext_view`` is applied to the canonical runes before decoding:
  raw; atbash 28 - c; first-difference d_i = c_i - c_{i-1}; chain-increment d_i - 1
  (a chain c_i = c_{i-1} + s_i with s_i in 1..28 maps to 0..27), with c_{-1} = 0.
* The forward model works on the CANONICAL runes, whatever the view: the anti-repeat
  filter (a canonical rune that would repeat the previous canonical rune survives with
  probability ``p_keep``; otherwise one key symbol is skipped and the rune re-enciphered)
  is a fact about LP2's doublets, and an interrupter is an unencrypted canonical F (CLAUDE.md).
  The view symbol of each canonical rune follows from it and the previous canonical rune.
  The rigid decoder cannot follow skips or interrupters, so such lanes fail a rigid control
  (INCONCLUSIVE (power)); the beam decoders (``runeforge.beam``, presets ``<scorer>:beam``
  for interrupters, ``<scorer>:beam-skip`` for interrupters and skips) follow this model.
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


def draw_seeds(rng: np.random.Generator, lo: int, hi: int, size: int) -> list[int]:
    """``size`` seeds uniform in [lo, hi) as Python ints; seed spaces up to 2**64 wide and
    anywhere above int64 (numpy's ``integers(lo, hi)`` stops at int64)."""
    span = hi - lo
    if span <= 2**63:
        return [lo + int(x) for x in rng.integers(0, span, size, dtype=np.int64)]
    if span <= 2**64:
        return [lo + int(x) for x in rng.integers(0, span, size, dtype=np.uint64)]
    raise ValueError("seed ranges wider than 2**64 are not supported")


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


def beam_model(lane: LaneSpec):
    """The lane's beam transition model (``runeforge.beam.BeamModel``), None when rigid."""
    from runeforge.scoring import presets

    return presets.beam_model(
        presets.split_preset(lane.preset)[1], lane.combine, lane.ciphertext_view
    )


def decrypt(lane: LaneSpec, cipher, k) -> np.ndarray:
    """Decode with the lane's decoder (the ``:<decoder>`` of its preset).

    Rigid broadcasts a (L,) cipher against (B, L) keys. The beam decoders take the same
    arguments and return the same shape, so the control, the nulls, the sweep and the crosser
    replay all reach them through this one function; they read every key symbol given (at
    least L; every caller passes exactly L for the scored window)."""
    model = beam_model(lane)
    if model is not None:
        from runeforge import beam
        from runeforge.scoring import presets

        scorer = presets.get(presets.split_preset(lane.preset)[0])
        return beam.decode(cipher, k, scorer, model)
    return rigid_decrypt(lane, cipher, k)


def rigid_decrypt(lane: LaneSpec, cipher, k) -> np.ndarray:
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


def _canon1(name: str, v: int, prev: int) -> int:
    """The canonical rune whose view symbol is ``v``, given the previous canonical rune."""
    if name == "raw":
        return v
    if name == "atbash":
        return (N - 1) - v
    if name == "first-difference":
        return (prev + v) % N
    return (prev + v + 1) % N  # chain-increment


def _view1(name: str, c: int, prev: int) -> int:
    """The view symbol of canonical rune ``c``, given the previous canonical rune."""
    if name == "raw":
        return c
    if name == "atbash":
        return (N - 1) - c
    if name == "first-difference":
        return (c - prev) % N
    return (c - prev - 1) % N  # chain-increment


def encrypt(lane: LaneSpec, plain, k, rng: np.random.Generator) -> tuple[np.ndarray, int]:
    """Forward model. Returns (cipher in the lane's view, key symbols consumed).

    The filter and the interrupters act on the canonical runes (``unview`` of the result);
    the combine acts in the view, which is what the lane's decoder inverts. ``k`` must be
    long enough for the skips (2x the plaintext is ample).
    """
    p = np.asarray(plain, dtype=np.int64)
    k = np.asarray(k, dtype=np.int64)
    out = np.empty(p.size, dtype=np.int64)
    name = lane.ciphertext_view
    j, prev = 0, 0  # prev: the previous canonical rune (c_{-1} = 0, as view() assumes)
    use_filter = lane.filter_model == "anti-repeat"
    for i, x in enumerate(p.tolist()):
        if x == F and lane.interrupt_prob and rng.random() < lane.interrupt_prob:
            out[i] = _view1(name, F, prev)  # unencrypted canonical F; the key does not advance
            prev = F
            continue
        v = _enc1(lane.combine, x, int(k[j]))
        j += 1
        c = _canon1(name, v, prev)
        while use_filter and i > 0 and c == prev and rng.random() >= lane.p_keep:
            v = _enc1(lane.combine, x, int(k[j]))
            j += 1
            c = _canon1(name, v, prev)
        out[i] = v
        prev = c
    return out, j


def score_batch(scorer, plains) -> np.ndarray:
    return scorer.score_batch(np.atleast_2d(plains))
