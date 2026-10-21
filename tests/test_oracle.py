"""Rule 3 -- hits must survive the oracle."""

from __future__ import annotations

import numpy as np
import pytest

from runeforge import canon, oracle
from runeforge.scoring import NGramScorer, fit_gumbel_from_maxima, gaussian_max_bar, gumbel_bar
from runeforge.transforms import StreamSubtract, Vigenere


@pytest.fixture(scope="module")
def scorer():
    return NGramScorer(3).fit([s.plain for s in canon.load_solved_sections() if s.id != "a-koan-1"])


def test_regression_gate_passes():
    assert oracle.regression_failures() == []


def test_selftest_accepts_planted_key_and_rejects_wrong_key():
    r = oracle.selftest()
    assert r["passed"]
    assert r["correct"].status == "hit-verified"
    assert r["wrong"].status == "negative"
    assert not r["wrong"].criteria["familywise_bar"]


def test_fragments_and_single_pages_are_rejected(scorer):
    bad_page = oracle.Claim("frag", Vigenere("DIVINITY").spec(), pages=[50, 51])  # 50 is runeless
    v = oracle.verify(bad_page, scorer)
    assert v.status == "rejected" and not v.criteria["full_pages"]
    one = oracle.Claim("one", Vigenere("DIVINITY").spec(), pages=[0])
    v = oracle.verify(one, scorer)
    assert not v.passed and not v.criteria["min_pages"]


def test_random_key_on_real_pages_is_negative(scorer):
    key = np.random.default_rng(5).integers(0, 29, 300)
    v = oracle.verify(
        oracle.Claim("rnd", StreamSubtract(key).spec(), pages=[0, 1, 2], n_trials=2**32), scorer
    )
    assert v.status == "negative"
    assert all(r["n_runes"] == canon.load_lp2().page(r["page"]).n_runes for r in v.pages)


def test_bar_rises_with_trial_count():
    assert gaussian_max_bar(-7.4, 0.17, 2**32) > gaussian_max_bar(-7.4, 0.17, 10**3) > -7.4
    assert gumbel_bar(-7.25, 0.0725, 10**9) > gumbel_bar(-7.25, 0.0725, 10**3)
    # Dukotah benchmark/null.py: maxima -6.826 at n=200 and -6.185 at n=1,385,600
    mu, beta = fit_gumbel_from_maxima(200, -6.826, 1_385_600, -6.185)
    assert round(beta, 4) == 0.0725 and round(mu, 2) == -7.25


def test_continuous_key_scope(scorer):
    pages = {0: np.arange(10) % 29, 1: np.arange(10, 20) % 29}
    t = StreamSubtract(np.arange(40) % 29)
    claim = oracle.Claim("c", t.spec(), pages=[0, 1], key_scope="continuous")
    out = oracle.decode_claim(claim, pages)
    assert np.array_equal(out[1], (pages[1] - np.arange(10, 20)) % 29)
