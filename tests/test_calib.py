"""Family-wise bars from observed maxima (scripts/threshold_for.py)."""

from __future__ import annotations

import json
import math
import subprocess
import sys

import numpy as np
import pytest

from runeforge.paths import REPO_ROOT
from runeforge.scoring import calib, presets


def _needs_corpus(preset: str) -> bool:
    return presets.PRESETS[presets.split_preset(preset)[0]]["train"] != ["lp-solved"]


def _check(preset: str, length: int) -> None:
    rec = calib.load(preset, length)  # raises if the scorer drifted from the fit
    assert rec["fit"]["beta"] > 0
    assert rec["check"]["max_error"] < 3 * rec["fit"]["beta"], rec["check"]


def test_shipped_calibrations_match_the_current_scorer():
    """The canon-trained presets: no corpus build needed, so this holds on any checkout."""
    have = calib.available()
    assert ("lp-ngram3:rigid", 240) in have and ("lp-ngram3:rigid", 120) in have
    for preset, length in have:
        if not _needs_corpus(preset):
            _check(preset, length)


@pytest.mark.raw
def test_shipped_corpus_calibrations_match_the_current_scorer():
    """The corpus-trained presets need scripts/build_corpus.py (CI runs it before the tests;
    with RUNEFORGE_REQUIRE_RAW=1 a missing corpus is a failure, locally a skip)."""
    import os

    from runeforge.corpus import CorpusMissingError

    have = [(p, n) for p, n in calib.available() if _needs_corpus(p)]
    assert have, "no corpus-trained calibration is shipped"
    try:
        for preset, length in have:
            _check(preset, length)
    except CorpusMissingError:
        if os.environ.get("RUNEFORGE_REQUIRE_RAW") == "1":
            raise
        pytest.skip("corpora not built: python scripts/build_corpus.py")


def test_bar_rises_with_n_and_expected_false_positives_stay_below_one():
    bars = [calib.threshold_for(n, "lp-ngram3:rigid", 240).bar for n in (10**3, 10**6, 2**32)]
    assert bars[0] < bars[1] < bars[2]
    t = calib.threshold_for(2**32, "lp-ngram3:rigid", 240)
    assert t.regime == "gumbel"
    assert t.expected_false_positives == pytest.approx(-math.log(1 - 0.01), rel=1e-3)
    assert t.bar > t.expected_null_max


def test_small_n_rule_needs_a_real_shuffle_null():
    with pytest.raises(ValueError, match="null_max"):
        calib.threshold_for(300, "lp-ngram3:rigid", 240)
    t = calib.threshold_for(300, "lp-ngram3:rigid", 240, floor=-5.0, null_max=-6.9)
    assert t.regime == "small-n" and t.bar == -5.0
    t = calib.threshold_for(300, "lp-ngram3:rigid", 240, null_max=-6.9)
    assert t.bar == pytest.approx(-6.4)
    # the expected false positives are a number (from the preset's fit), never NaN
    assert math.isfinite(t.expected_false_positives) and t.expected_false_positives < 1
    t2 = calib.threshold_for(300, "lp-ngram3:rigid", 240, null_max=-6.9, null2_max=-6.5)
    assert t2.bar == pytest.approx(-6.0)
    with pytest.raises(FileNotFoundError):  # an uncalibrated preset gets no bar either
        calib.threshold_for(300, "nonexistent:rigid", 999, null_max=-6.9)


def test_unknown_length_is_refused_not_interpolated():
    with pytest.raises(FileNotFoundError, match=r"calibrate\.py"):
        calib.threshold_for(10**6, "lp-ngram3:rigid", 241)


def test_bar_is_empirically_family_wise():
    """Out-of-sample check of the fit: over fresh nulls the max of N = 1e4 crosses the
    alpha = 0.05 bar about 5 % of the time (not 0 %, not 50 %)."""
    scorer = presets.get("lp-ngram3")
    bar = calib.threshold_for(10_000, "lp-ngram3:rigid", 120, alpha=0.05).bar
    rng = np.random.default_rng(7)
    crossed = 0
    reps = 60
    for _ in range(reps):
        s = scorer.score_batch(rng.integers(0, 29, (10_000, 120)))
        crossed += bool(s.max() > bar)
    assert crossed / reps < 0.2


def test_threshold_for_cli():
    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/threshold_for.py"),
            "--n",
            "4294967296",
            "--preset",
            "lp-ngram3:rigid",
            "--L",
            "240",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["n_trials"] == 2**32 and out["expected_false_positives"] < 1
    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/threshold_for.py"),
            "--n",
            "50",
            "--preset",
            "lp-ngram3:rigid",
            "--L",
            "240",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2 and "small-N" in r.stderr
