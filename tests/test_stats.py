"""The published LP2 fingerprint (spec section 2.6), each with a positive control:
an instrument that reports "no signal" must be shown to see a planted one."""

from __future__ import annotations

import numpy as np
import pytest

from runeforge import canon, stats
from runeforge.controls import control_plaintext
from runeforge.transforms import Vigenere


@pytest.fixture(scope="module")
def unsolved():
    return canon.unsolved_stream()


@pytest.fixture(scope="module")
def sections():
    return canon.unsolved_sections()


def test_global_fingerprint(unsolved):
    s = stats.summary(unsolved)
    assert s["n"] == 12956
    assert round(s["ioc_norm"], 3) == 1.000
    assert round(s["entropy_bits"], 3) == 4.857
    assert s["doublets"] == 86  # the anomaly: 0.66 %
    assert round(100 * s["doublet_rate"], 2) == 0.66
    assert round(s["doublets_expected"]) == 447
    assert round(s["doublet_z"]) == -17
    assert abs(s["chi2_uniform"] - 28) < 4 * np.sqrt(56)


def test_every_section_is_flat_and_doublet_depleted(sections):
    for name, x in sections.items():
        s = stats.summary(x)
        assert abs(s["ioc_norm"] - 1) < 4 * stats.ioc_null_sd(s["n"]) + 0.02, name
        assert abs(s["chi2_uniform"] - 28) < 4 * np.sqrt(56), name  # chi^2 ~ df
        assert s["doublet_rate"] < 0.015, name  # every section, not just the aggregate


def test_no_periodicity_per_section(sections):
    for name, x in sections.items():
        for kind in ("periodic", "kappa"):
            r = stats.scan(x, 400, kind)
            assert not r["peak"], (name, kind, r["max_z"], r["argmax"])


@pytest.mark.slow
def test_no_periodicity_corpus_wide(unsolved):
    for kind in ("periodic", "kappa"):
        r = stats.scan(unsolved, 600, kind)
        assert r["n_tests"] == 600
        assert not r["peak"], (kind, r["max_z"], r["argmax"])
    k = stats.scan(unsolved, 400, "kappa")
    assert round(max(row["kappa"] for row in k["rows"]), 4) == 0.0398  # Leo-Y-Zhang FINDINGS


def test_periodicity_control_detects_a_planted_period():
    """Positive control: a period-13 Vigenere over real Cicada plaintext of section size."""
    plain = control_plaintext()[:1500]
    c = Vigenere([0, 10, 4, 0, 1, 19, 0, 18, 4, 18, 9, 0, 18]).encrypt(plain)
    r = stats.scan(c, 400, "periodic")
    assert r["peak"] and r["argmax"] % 13 == 0
    k = stats.scan(c, 400, "kappa")
    assert k["peak"] and k["argmax"] % 13 == 0


def test_no_shared_keystream(sections):
    """Cross-section scan over every relative shift. Judged family-wise: the raw max z
    (about 6 here) is what ~80,000 null shifts produce -- see stats/crosskey.py."""
    res = stats.shared_key_scan(sections)
    cross = stats.familywise([r for r in res if r["a"] != r["b"]])
    within = stats.familywise([r for r in res if r["a"] == r["b"]])
    assert cross["n_tests"] > 80_000
    assert cross["p_familywise"] > 0.01, cross
    assert within["p_familywise"] > 0.01, within


def test_shared_keystream_control_is_detected(sections):
    """Positive control: two sections enciphered with the SAME running key at some shift,
    embedded among the real sections, must be found at that shift and be family-wise
    significant under the same scan, at the same alpha (0.01) the null test uses. At an
    overlap of 1,100 runes of Cicada-register plaintext this lands near p_fw = 1e-3: the
    scan's power fades below ~1,000 aligned runes, so a shared key over a short overlap
    would be missed -- report that alongside the negative."""
    plain = control_plaintext()
    rng = np.random.default_rng(3301)
    key = rng.integers(0, 29, 1300)
    a = (plain[:1200] + key[100:1300]) % 29
    b = (plain[1300:2500] + key[:1200]) % 29
    planted = dict(sections)
    planted["plantA"], planted["plantB"] = a, b
    res = stats.shared_key_scan(planted)
    best = next(r for r in res if {r["a"], r["b"]} == {"plantA", "plantB"})
    assert best["shift"] in (-100, 100)
    fw = stats.familywise([r for r in res if r["a"] != r["b"]])
    assert fw["best"] == best
    assert fw["p_familywise"] < 0.01


def test_doublet_fingerprint_separates_cipher_families():
    """English under any c = p + k cipher keeps ~3.4 % doublets; LP2 shows 0.66 %."""
    plain = control_plaintext()
    rng = np.random.default_rng(1)
    otp = (plain + rng.integers(0, 29, plain.size)) % 29
    assert stats.doublet_stats(otp)["rate"] > 0.02
