"""Family-wise bars calibrated from observed MAXIMA, per scorer/decoder preset and length.

A sweep over N wrong keys reports the maximum of N null scores, and that maximum climbs
with N, so the bar must too (CLAUDE.md, Doctrine: "Thresholds scale with N"). Following
Dukotah's benchmark/null.py lesson, the bar comes from extreme values, never from the null's
bulk SD (for a skewed score the bulk SD misstates the tail by ~2.5x):

1. Score M uniform random rune strings of length L. A wrong key under any additive
   decoder turns the ciphertext into exactly such a string, whatever the ciphertext is.
2. Cut them into blocks of b = 1,000 and fit a Gumbel (mu_b, beta) to the block maxima.
   The max of N = k * b draws is then Gumbel(mu_b + beta ln k, beta).
3. Check out of sample: the mean of the 30,000-draw block maxima and the single
   M-draw maximum must land where the fit predicts (recorded as ``check``).

Calibrations live in ``presets/<scorer>__<decoder>__L<L>.json`` and are pinned to the
scorer's fingerprint; a scorer that changed needs a refit (``scripts/calibrate.py``).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from runeforge.gematria import N as ALPHABET

EULER_GAMMA = 0.5772156649015329
CALIB_DIR = Path(__file__).resolve().parent / "presets"
BLOCK = 1_000
CHECK_BLOCK = 25_000


def _gumbel_fit(maxima: np.ndarray) -> tuple[float, float]:
    """Method-of-moments Gumbel fit: beta = sd * sqrt(6) / pi, mu = mean - gamma * beta."""
    beta = float(np.std(maxima, ddof=1)) * math.sqrt(6) / math.pi
    return float(np.mean(maxima)) - EULER_GAMMA * beta, beta


def measure(scorer, length: int, draws: int = 1_000_000, seed: int = 3301, chunk: int = 50_000):
    """Score ``draws`` uniform random strings of ``length``; return the score array."""
    if draws % CHECK_BLOCK:
        raise ValueError(f"draws must be a multiple of {CHECK_BLOCK}")
    rng = np.random.default_rng(seed)
    out = np.empty(draws, dtype=np.float64)
    for start in range(0, draws, chunk):
        stop = min(start + chunk, draws)
        out[start:stop] = scorer.score_batch(rng.integers(0, ALPHABET, (stop - start, length)))
    return out


def calibrate(scorer, scorer_name: str, decoder: str, length: int, draws: int = 1_000_000):
    """Fit and return a calibration record (not yet written)."""
    scores = measure(scorer, length, draws)
    blocks = scores.reshape(-1, BLOCK).max(axis=1)
    mu_b, beta = _gumbel_fit(blocks)
    check_blocks = scores.reshape(-1, CHECK_BLOCK).max(axis=1)
    k_check = CHECK_BLOCK / BLOCK
    predicted_check = mu_b + beta * (math.log(k_check) + EULER_GAMMA)
    predicted_all = mu_b + beta * (math.log(draws / BLOCK) + EULER_GAMMA)
    return {
        "preset": f"{scorer_name}:{decoder}",
        "scorer": scorer_name,
        "decoder": decoder,
        "L": length,
        "units": "mean log2-probability per rune (higher = more language-like)",
        "scorer_fingerprint": scorer.fingerprint(),
        "method": f"Gumbel MoM fit to {draws // BLOCK} block maxima of {BLOCK} uniform random "
        f"strings; max of N = k*{BLOCK} is Gumbel(mu_b + beta ln k, beta)",
        "draws": draws,
        "seed": 3301,
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


def path_for(preset: str, length: int) -> Path:
    scorer, _, decoder = preset.partition(":")
    return CALIB_DIR / f"{scorer}__{decoder or 'rigid'}__L{length}.json"


def available() -> list[tuple[str, int]]:
    out = []
    for p in sorted(CALIB_DIR.glob("*__L*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        out.append((rec["preset"], rec["L"]))
    return out


def load(preset: str, length: int, check_fingerprint: bool = True) -> dict:
    p = path_for(preset, length)
    if not p.exists():
        have = ", ".join(f"{a}@L{b}" for a, b in available()) or "none"
        raise FileNotFoundError(
            f"no calibration for {preset} at L={length} (have: {have}); "
            f"run scripts/calibrate.py --preset {preset} --L {length}"
        )
    rec = json.loads(p.read_text(encoding="utf-8"))
    if check_fingerprint:
        from runeforge.scoring import presets

        scorer_name, _ = presets.split_preset(preset)
        fp = presets.get(scorer_name).fingerprint()
        if fp != rec["scorer_fingerprint"]:
            raise ValueError(
                f"{p.name} was fitted on a different {scorer_name} model; refit it "
                "(scripts/calibrate.py) before using its bars"
            )
    return rec


@dataclass(frozen=True)
class Threshold:
    preset: str
    length: int
    n_trials: int
    alpha: float
    regime: str  # gumbel | small-n
    bar: float
    expected_null_max: float
    expected_false_positives: float
    note: str

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def threshold_for(
    n_trials: int,
    preset: str,
    length: int,
    alpha: float = 0.01,
    floor: float | None = None,
    null_max: float | None = None,
    null2_max: float | None = None,
) -> Threshold:
    """The family-wise bar for the best of ``n_trials`` decodes at length ``length``.

    For N >= the calibration block (1,000) the Gumbel extrapolation is used: the bar is the
    1 - alpha quantile of the max of N, so P(any null crosses) = alpha and the expected number
    of null crossers N * P(single clears) is -ln(1 - alpha) (about alpha, < 1).
    For smaller N the rule is max(floor, null_max + 0.5) with a size-matched shuffle null of
    the real runes (n >= 200), supplied as ``null_max``, raised to null2_max + 0.5 when the
    second null (a domain-separated SHA-256 stream) is given. The preset must still be
    calibrated at this length: the expected false positives N * P(clear) at that bar come from
    its Gumbel fit, and are a number, never NaN.
    """
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    rec = load(preset, length)  # an unknown preset or length is refused in both regimes
    mu_b, beta = rec["fit"]["mu_block"], rec["fit"]["beta"]
    if n_trials < BLOCK:
        if null_max is None:
            raise ValueError(
                f"N={n_trials} < {BLOCK}: small-N rule max(floor, null_max + 0.5) needs "
                "--null-max from a size-matched shuffle null (n >= 200) of the real runes"
            )
        parts = [null_max + 0.5] + ([] if null2_max is None else [null2_max + 0.5])
        bar = max(parts) if floor is None else max(floor, *parts)
        p_block = 1 - math.exp(-math.exp(-(bar - mu_b) / beta))  # P(max of 1,000 > bar)
        p_single = 1 - (1 - p_block) ** (1 / BLOCK)
        note = (
            "small N: max("
            + ("floor, " if floor is not None else "no floor, ")
            + ("null_max + 0.5" + (", null2_max + 0.5)" if null2_max is not None else ")"))
        )
        return Threshold(
            preset,
            length,
            n_trials,
            alpha,
            "small-n",
            bar,
            null_max,
            n_trials * p_single,
            f"{note}; P(clear) from {path_for(preset, length).name}",
        )
    mu_n = mu_b + beta * math.log(n_trials / BLOCK)
    bar = mu_n - beta * math.log(-math.log(1 - alpha))
    if floor is not None:
        bar = max(bar, floor)
    p_single = 1 - (1 - alpha) ** (1 / n_trials)
    return Threshold(
        preset,
        length,
        n_trials,
        alpha,
        "gumbel",
        bar,
        mu_n + beta * EULER_GAMMA,
        n_trials * p_single,
        f"Gumbel(mu_b={mu_b:.4f}, beta={beta:.4f}, block={BLOCK}) "
        f"from {path_for(preset, length).name}",
    )
