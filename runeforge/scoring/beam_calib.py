"""Family-wise bars for the beam decoders (``<scorer>:beam``, ``:beam-skip``, ``:beam-skip-int``).

``runeforge.scoring.calib`` fits the rigid decoder's bar on uniform random strings: a wrong
key under a rigid additive decoder turns any ciphertext into exactly such a string. A wrong key
under a beam decoder does not: the beam picks the best of its interrupt and skip paths through
the wrong key, so its decodes score higher than uniform strings (lp-ngram3-heldout, L = 240:
wrong-key mean -6.90 ``beam``, -6.88 ``beam-skip``, -6.74 ``beam-skip-int`` against -7.17
rigid; ``scripts/beam_power.py``) and need their own null. Every draw is the preset's beam
decode of a cipher under a fresh uniform key of the cipher's length (the decoder's key budget
in every caller), scored by the preset's scorer. Under a uniform key every decoded rune is
uniform whatever the cipher symbol, so a window's null depends on the cipher only through
the choices it offers the beam (adversarial review rounds 1 and 2, 2026-10-22):

* canonical F's: every one is a free interrupt-or-not choice for ``beam`` / ``beam-skip-int``,
  so their null RISES WITH THE WINDOW'S CANONICAL F COUNT (L = 240, ``beam``: block-max mean
  -6.59 at 4 F's, -6.31 at 20). Their fits draw ciphers with exactly ``canonical_F`` canonical
  F's, the most in any lane window of this length that starts at an unsolved LP2 page and runs
  on in canonical order (L = 120: 10, page 43; L = 240: 14, page 11): conservative for every
  window holding at most that many, and ``LaneSpec.runnable_problems`` refuses one with more.
  ``beam-skip`` ignores F's.
* canonical doublets: at a repeat a one-symbol skip deciphers the same rune as no skip, so a
  doublet offers the skip decoders no new choice. LP2 has almost none (86 in 12,956), uniform
  ciphers one in 29, and a uniform-cipher fit sat 0.004 below every LP2 window's null (14
  page-start windows: offset +0.0043, spread 0.0020 against a per-window se of 0.0031). All
  fits therefore draw DOUBLET-FREE ciphers (F's never adjacent), which offer the beam at least
  the choices of any LP2 window.
* nothing else: with exhausted paths wrapping round the key (``runeforge.beam``) no cipher
  rune reaches a decode except through ``combine^-1(cipher, key)``, and the null is the same
  in every ciphertext view and combine (a repeat is ``d_i == d_rep`` in all of them).

The fit is ``calib``'s: Gumbel moments of block maxima (block 1,000), checked against the
25,000-draw block maxima and the overall maximum. The record has calib's layout plus
``decoder_params`` (``presets.DECODER_PARAMS``), ``beam_sha256`` (the SHA-256 of
``runeforge/beam.py`` it was fitted with) and ``canonical_F``; ``calib.load`` /
``threshold_for`` read it unchanged once it is installed in ``runeforge/scoring/calib/presets/``
(frozen: Hunter installs it, TOOLBOX_REQUESTS.md TR-1), and ``runnable_problems`` refuses it
when any of the three no longer matches. Draws are deterministic per chunk
(``default_rng([seed, chunk])``), so the result does not depend on the number of workers.
"""

from __future__ import annotations

import hashlib
import math
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from runeforge.gematria import N as ALPHABET
from runeforge.scoring.calib import BLOCK, CHECK_BLOCK, EULER_GAMMA, _gumbel_fit

CHUNK = 5_000
F = 0


def beam_sha256() -> str:
    """SHA-256 of runeforge/beam.py: a calibration is valid only for the decoder it measured."""
    from runeforge import beam

    return hashlib.sha256(Path(beam.__file__).read_bytes()).hexdigest()


def uses_interrupts(decoder: str) -> bool:
    from runeforge.scoring import presets

    return presets.DECODER_PARAMS[decoder].get("interrupt_prob", 0) > 0


@lru_cache(maxsize=16)
def page_start_f_counts(length: int) -> tuple[tuple[int, int], ...]:
    """(canonical F count, first page) of every window of ``length`` runes that starts at an
    unsolved LP2 page and runs on through the later pages in canonical order."""
    from runeforge import canon

    lp2 = canon.load_lp2()
    pages = [p for p in canon.UNSOLVED_LP2_PAGES if lp2.page(p).n_runes]
    out = []
    for i, p in enumerate(pages):
        s = lp2.stream(pages[i:])[:length]
        if s.size == length:
            out.append((int((s == F).sum()), p))
    return tuple(out)


def canonical_f(length: int) -> int:
    """The F count an interrupt decoder's calibration is conditioned on at this length."""
    counts = page_start_f_counts(length)
    if not counts:
        raise ValueError(f"no LP2 window of {length} runes")
    return max(c for c, _ in counts)


def _cipher(rng: np.random.Generator, size: int, length: int, n_f: int | None) -> np.ndarray:
    """Raw-view (canonical) ciphers with no doublets: uniform over the runes that differ from
    the previous one, or with exactly ``n_f`` canonical F's at random non-adjacent positions
    and the other runes uniform over 1..28 minus the previous one."""
    c = np.empty((size, length), dtype=np.int64)
    is_f = np.zeros((size, length), dtype=bool)
    if n_f is not None:
        if 2 * n_f > length + 1:
            raise ValueError(f"{n_f} non-adjacent F's do not fit in {length} runes")
        # n_f sorted slots out of length - n_f + 1, spread by their rank: never adjacent
        slots = np.sort(np.argsort(rng.random((size, length - n_f + 1)), axis=1)[:, :n_f])
        np.put_along_axis(is_f, slots + np.arange(n_f), True, axis=1)
    prev = np.full(size, -1, dtype=np.int64)
    for i in range(length):
        if n_f is None:  # any rune but the previous one
            v = rng.integers(0, ALPHABET - 1, size)
            v = np.where((prev >= 0) & (v >= prev), v + 1, v)
            v = np.where(prev < 0, rng.integers(0, ALPHABET, size), v)
        else:  # a non-F rune other than the previous one
            v = 1 + rng.integers(0, ALPHABET - 2, size)
            v = np.where((prev >= 1) & (v >= prev), v + 1, v)
            v = np.where(prev < 1, 1 + rng.integers(0, ALPHABET - 1, size), v)
            v = np.where(is_f[:, i], F, v)
        c[:, i] = v
        prev = v
    return c


def _chunk(args) -> np.ndarray:
    scorer_name, decoder, length, seed, index, size, n_f = args
    from runeforge import beam
    from runeforge.scoring import presets

    scorer = presets.get(scorer_name)
    model = presets.beam_model(decoder)
    rng = np.random.default_rng([seed, index])
    cipher = _cipher(rng, size, length, n_f)
    keys = rng.integers(0, ALPHABET, (size, length))
    plain = beam.decode_batch(cipher, keys, scorer, model).plain
    return scorer.score_batch(plain)


def measure(
    scorer_name: str,
    decoder: str,
    length: int,
    draws: int = 1_000_000,
    seed: int = 3301,
    workers: int = 1,
    n_f: int | None = None,
) -> np.ndarray:
    """Scores of ``draws`` beam decodes under uniform keys, of doublet-free ciphers
    (``_cipher``), with exactly ``n_f`` non-adjacent canonical F's when it is given."""
    if draws % CHECK_BLOCK:
        raise ValueError(f"draws must be a multiple of {CHECK_BLOCK}")
    if decoder == "rigid":
        raise ValueError("the rigid decoder is calibrated by runeforge.scoring.calib")
    jobs = [
        (scorer_name, decoder, length, seed, i, min(CHUNK, draws - start), n_f)
        for i, start in enumerate(range(0, draws, CHUNK))
    ]
    if workers <= 1:
        parts = [_chunk(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            parts = list(ex.map(_chunk, jobs))
    return np.concatenate(parts)


def calibrate(
    scorer_name: str,
    decoder: str,
    length: int,
    draws: int = 1_000_000,
    seed: int = 3301,
    workers: int = 1,
) -> dict:
    """Fit and return a beam calibration record (not yet written)."""
    from runeforge.scoring import presets

    scorer = presets.get(scorer_name)
    n_f = canonical_f(length) if uses_interrupts(decoder) else None
    scores = measure(scorer_name, decoder, length, draws, seed, workers, n_f)
    blocks = scores.reshape(-1, BLOCK).max(axis=1)
    mu_b, beta = _gumbel_fit(blocks)
    check_blocks = scores.reshape(-1, CHECK_BLOCK).max(axis=1)
    predicted_check = mu_b + beta * (math.log(CHECK_BLOCK / BLOCK) + EULER_GAMMA)
    predicted_all = mu_b + beta * (math.log(draws / BLOCK) + EULER_GAMMA)
    if n_f is None:
        cipher = "a fresh doublet-free cipher (beam-skip ignores canonical F's)"
    else:
        cipher = (
            f"a fresh doublet-free cipher with exactly {n_f} non-adjacent canonical F's (the "
            f"most in any LP2 page-start window of {length} runes; a window with more is "
            "refused)"
        )
    return {
        "preset": f"{scorer_name}:{decoder}",
        "scorer": scorer_name,
        "decoder": decoder,
        "decoder_params": presets.DECODER_PARAMS[decoder],
        "beam_sha256": beam_sha256(),
        "canonical_F": n_f,
        "doublets": "none",
        "L": length,
        "units": "mean log2-probability per rune (higher = more language-like)",
        "scorer_fingerprint": scorer.fingerprint(),
        "method": f"Gumbel MoM fit to {draws // BLOCK} block maxima of {BLOCK} beam decodes "
        f"({decoder}) of {cipher} under a fresh uniform key, both of length L; max of "
        f"N = k*{BLOCK} is Gumbel(mu_b + beta ln k, beta)",
        "null_source": "runeforge.scoring.beam_calib.measure",
        "draws": draws,
        "seed": seed,
        "null": {
            "n": int(min(draws, 10_000)),
            "mean": float(scores[:10_000].mean()),
            "sd": float(scores[:10_000].std()),
        },
        "fit": {"block": BLOCK, "mu_block": mu_b, "beta": beta, "n_blocks": int(blocks.size)},
        "check": {
            f"mean_max_{CHECK_BLOCK}": float(check_blocks.mean()),
            f"predicted_mean_max_{CHECK_BLOCK}": predicted_check,
            f"max_{draws}": float(scores.max()),
            f"predicted_mean_max_{draws}": predicted_all,
            "max_error": float(
                max(abs(check_blocks.mean() - predicted_check), abs(scores.max() - predicted_all))
            ),
        },
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def calibration_problems(preset: str, length: int, window_canonical) -> list[str]:
    """Why a beam preset's installed calibration may not give this window's bar: fitted with
    other decoder parameters or another runeforge/beam.py, or conditioned on fewer canonical
    F's than the window holds (its bar would sit below the window's own null). Empty for the
    rigid decoder and when no calibration is installed (threshold_for reports that)."""
    from runeforge.scoring import calib, presets

    _scorer, decoder = presets.split_preset(preset)
    if decoder == "rigid":
        return []
    try:
        rec = calib.load(preset, length, check_fingerprint=False)
    except (FileNotFoundError, ValueError):
        return []
    out = []
    name = calib.path_for(preset, length).name
    if rec.get("decoder_params") != presets.DECODER_PARAMS[decoder]:
        out.append(
            f"{name} was fitted with decoder parameters {rec.get('decoder_params')}, not "
            f"{presets.DECODER_PARAMS[decoder]}; refit it (scripts/calibrate.py)"
        )
    if rec.get("beam_sha256") != beam_sha256():
        out.append(f"{name} was fitted with another runeforge/beam.py; refit it")
    if uses_interrupts(decoder):
        n_f = int((np.asarray(window_canonical) == F).sum())
        cal_f = rec.get("canonical_F")
        if cal_f is None:
            out.append(f"{name} is not conditioned on a canonical F count; refit it")
        elif n_f > cal_f:
            out.append(
                f"the window holds {n_f} canonical F's, more than the {cal_f} {name} is "
                "conditioned on: an interrupt decoder's null rises with the F count, so its "
                "bar would sit below this window's own null"
            )
    return out
