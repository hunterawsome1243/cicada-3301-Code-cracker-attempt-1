"""Family-wise bars for the beam decoders (``<scorer>:beam``, ``<scorer>:beam-skip``).

``runeforge.scoring.calib`` fits the rigid decoder's bar on uniform random strings: a wrong
key under a rigid additive decoder turns any ciphertext into exactly such a string. A wrong key
under a beam decoder does not: the beam picks the best of its interrupt and skip paths through
the wrong key, so its decodes score higher than uniform strings (on uniform ciphers at L = 240
with lp-ngram3-heldout, mean -6.83 for ``beam`` and -6.66 for ``beam-skip`` against -7.17
rigid) and need their own null. Here every draw is the preset's beam decode of a fresh uniform
random cipher under a fresh uniform random key (both of length L: the decoder's key budget
in every caller), scored by the preset's scorer. Fresh ciphers are the conservative choice: the
block maxima also carry cipher-to-cipher variation (how many canonical F's, which keys can
skip), so a bar fitted here sits at or above a fixed window's own null; ``runeforge null``
(null 2) and the control's ceiling are the out-of-sample checks on a real or planted window.

The fit is ``calib``'s: Gumbel moments of block maxima (block 1,000), checked against the
25,000-draw block maxima and the overall maximum. The record has calib's layout plus
``decoder_params`` (``presets.DECODER_PARAMS``) and the null's description, so
``calib.load`` / ``threshold_for`` read it unchanged once it is installed in
``runeforge/scoring/calib/presets/`` (frozen: Hunter installs it, TOOLBOX_REQUESTS.md).
Draws are deterministic per chunk (``default_rng([seed, chunk])``), so the result does not
depend on the number of worker processes.
"""

from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime

import numpy as np

from runeforge.gematria import N as ALPHABET
from runeforge.scoring.calib import BLOCK, CHECK_BLOCK, EULER_GAMMA, _gumbel_fit

CHUNK = 5_000


def _chunk(args) -> np.ndarray:
    scorer_name, decoder, length, seed, index, size = args
    from runeforge import beam
    from runeforge.scoring import presets

    scorer = presets.get(scorer_name)
    model = presets.beam_model(decoder)
    rng = np.random.default_rng([seed, index])
    cipher = rng.integers(0, ALPHABET, (size, length))
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
) -> np.ndarray:
    """Scores of ``draws`` beam decodes of uniform ciphers under uniform keys."""
    if draws % CHECK_BLOCK:
        raise ValueError(f"draws must be a multiple of {CHECK_BLOCK}")
    if decoder == "rigid":
        raise ValueError("the rigid decoder is calibrated by runeforge.scoring.calib")
    jobs = [
        (scorer_name, decoder, length, seed, i, min(CHUNK, draws - start))
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
    scores = measure(scorer_name, decoder, length, draws, seed, workers)
    blocks = scores.reshape(-1, BLOCK).max(axis=1)
    mu_b, beta = _gumbel_fit(blocks)
    check_blocks = scores.reshape(-1, CHECK_BLOCK).max(axis=1)
    predicted_check = mu_b + beta * (math.log(CHECK_BLOCK / BLOCK) + EULER_GAMMA)
    predicted_all = mu_b + beta * (math.log(draws / BLOCK) + EULER_GAMMA)
    return {
        "preset": f"{scorer_name}:{decoder}",
        "scorer": scorer_name,
        "decoder": decoder,
        "decoder_params": presets.DECODER_PARAMS[decoder],
        "L": length,
        "units": "mean log2-probability per rune (higher = more language-like)",
        "scorer_fingerprint": scorer.fingerprint(),
        "method": f"Gumbel MoM fit to {draws // BLOCK} block maxima of {BLOCK} beam decodes "
        f"({decoder}) of a fresh uniform cipher under a fresh uniform key, both of length L; "
        f"max of N = k*{BLOCK} is Gumbel(mu_b + beta ln k, beta)",
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
