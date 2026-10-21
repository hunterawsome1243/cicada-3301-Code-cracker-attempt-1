"""Rule 2 -- plant before you claim: the control harness itself."""

from __future__ import annotations

import numpy as np

from runeforge import canon
from runeforge.controls import control_plaintext, run_control, synthetic_page
from runeforge.interrupts import decode_rigid, decode_skip_known
from runeforge.transforms import TotientPrimeStream, Vigenere

DIVINITY = [23, 10, 1, 10, 9, 10, 16, 26]


def test_control_plaintext_is_the_solved_register():
    p = control_plaintext()
    assert p.size == sum(s.plain.size for s in canon.load_solved_sections())
    assert control_plaintext(exclude=["a-koan-1"]).size == p.size - 778


def test_planted_divinity_key_on_a_synthetic_welcome_page():
    """Plant DIVINITY with Welcome-like interrupts on held-out plaintext: the skip-aware
    decoder recovers it exactly; the rigid decoder does not (that gap is why Phase 2
    needs a beam decoder for unknown interrupts)."""
    plain = canon.solved_section("a-koan-1").plain[:515]
    page = synthetic_page(plain, Vigenere(DIVINITY), interrupt_prob=11 / 25, seed=7)
    assert len(page.interrupts) > 0
    t = Vigenere(DIVINITY)
    good = run_control("skip_known", page, lambda c: decode_skip_known(c, t, page.interrupts))
    bad = run_control("rigid", page, lambda c: decode_rigid(c, t))
    assert good.recovered and good.status == "passed" and good.accuracy == 1.0
    assert not bad.recovered
    first = page.interrupts[0]
    after = decode_rigid(page.cipher, t)[first:] == page.plain[first:]
    assert after.mean() < 0.5  # out of step from the first interrupter on


def test_control_on_an_aperiodic_stream():
    plain = canon.solved_section("the-loss-of-divinity").plain
    page = synthetic_page(plain, TotientPrimeStream(), interrupt_prob=0.2, seed=11)
    t = TotientPrimeStream()
    res = run_control("totient", page, lambda c: decode_skip_known(c, t, page.interrupts))
    assert res.recovered
    assert res.details["n_interrupts"] == len(page.interrupts)


def test_control_rejects_length_changes():
    plain = control_plaintext()[:100]
    page = synthetic_page(plain, Vigenere("KEY"), interrupt_prob=0)
    res = run_control("broken", page, lambda c: c[:-1])
    assert not res.recovered and res.accuracy == 0.0
    assert np.array_equal(Vigenere("KEY").decrypt(page.cipher), plain)
