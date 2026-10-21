"""Transform primitives and the interrupt decoders (spec sections 2.3, 2.4)."""

from __future__ import annotations

import numpy as np
import pytest

from runeforge import transforms as T
from runeforge.interrupts import decode_rigid, decode_skip_known, encrypt_with_interrupts
from runeforge.stats import doublet_count

RNG = np.random.default_rng(3301)
PLAIN = RNG.integers(0, 29, 500)

ALL = [
    T.Identity(),
    T.Atbash(),
    T.Shift(3),
    T.Shift(-11),
    T.Vigenere("DIVINITY"),
    T.Vigenere([0, 10, 4, 0, 1, 19, 0, 18, 4, 18, 9, 0, 18]),
    T.Beaufort("CIRCUMFERENCE"),
    T.StreamSubtract(RNG.integers(0, 29, 600)),
    T.TotientPrimeStream(),
    T.TotientPrimeStream(start=100),
    T.RunningKey(RNG.integers(0, 29, 2000), offset=37, direction="reverse"),
    T.Chain(),
    T.Chain(T.TotientPrimeStream(), c0=5),
    T.Compose([T.Atbash(), T.Shift(-3)]),
    T.Compose([T.Vigenere("DIVINITY"), T.Atbash(), T.Chain(T.Vigenere("KEY"))]),
]


@pytest.mark.parametrize("t", ALL, ids=lambda t: t.spec()["type"])
def test_round_trip(t):
    c = t.encrypt(PLAIN)
    assert c.dtype == np.int64 and c.min() >= 0 and c.max() <= 28
    assert np.array_equal(t.decrypt(c), PLAIN)


@pytest.mark.parametrize("t", ALL, ids=lambda t: t.spec()["type"])
def test_spec_round_trip(t):
    t2 = T.from_spec(t.spec())
    assert t2.spec() == t.spec()
    assert np.array_equal(t2.decrypt(PLAIN), t.decrypt(PLAIN))


def test_atbash_and_beaufort_are_involutions():
    assert np.array_equal(T.Atbash().decrypt(T.Atbash().decrypt(PLAIN)), PLAIN)
    b = T.Beaufort("KEY")
    assert np.array_equal(b.encrypt(PLAIN), b.decrypt(PLAIN))
    assert T.Atbash().decrypt([0, 28, 14]).tolist() == [28, 0, 14]


def test_shift_convention():
    # encrypt c = p + n; A KOAN's published "Atbash then +3" decode is shift n = -3.
    assert T.Shift(3).encrypt([27]).tolist() == [1]
    assert T.Compose([T.Atbash(), T.Shift(-3)]).decrypt([28]).tolist() == [3]


def test_totient_stream_values():
    # phi(p) = p - 1 for p = 2, 3, 5, 7, 11, 13, ... reduced mod 29
    assert T.TotientPrimeStream().keystream(8).tolist() == [1, 2, 4, 6, 10, 12, 16, 18]
    assert T.TotientPrimeStream().keystream(11).tolist()[-1] == (31 - 1) % 29


def test_vigenere_accepts_runes_latin_and_indices():
    a, b, c = (
        T.Vigenere("ᛞᛁᚢᛁᚾᛁᛏᚣ"),
        T.Vigenere("DIVINITY"),
        T.Vigenere([23, 10, 1, 10, 9, 10, 16, 26]),
    )
    assert a.key == b.key == c.key


def test_chain_cipher_suppresses_doublets():
    """c_i = c_{i-1} + p_i + k_i makes a doublet iff p_i + k_i = 0 -- with k = 1 and p
    never 28, no doublets at all (the published mechanism matching the LP2 deficit)."""
    p = RNG.integers(0, 28, 3000)
    c = T.Chain(T.StreamSubtract(np.ones(3000, dtype=int))).encrypt(p)
    assert doublet_count(c) == 0
    c_vig = T.Vigenere("DIVINITY").encrypt(p)
    assert doublet_count(c_vig) > 50


def test_running_key_bounds():
    with pytest.raises(ValueError):
        T.RunningKey([1, 2, 3], offset=2).keystream(5)
    with pytest.raises(ValueError):
        T.RunningKey([1, 2, 3], direction="sideways")


def test_invalid_input():
    with pytest.raises(ValueError):
        T.Atbash().decrypt([29])
    with pytest.raises(ValueError):
        T.Vigenere([])
    with pytest.raises(ValueError):
        T.from_spec({"type": "enigma"})


# --------------------------------------------------------------------------- interrupts


def test_skip_known_does_not_advance_the_key():
    t = T.Vigenere("DIVINITY")
    plain = np.array([5, 0, 7, 0, 9, 11, 0, 4])
    interrupts = [1, 6]
    c = encrypt_with_interrupts(plain, t, interrupts)
    assert c[1] == 0 and c[6] == 0  # unencrypted F
    # the 3rd plaintext rune uses the 2nd key symbol, not the 3rd
    assert c[2] == (plain[2] + t.key[1]) % 29
    assert np.array_equal(decode_skip_known(c, t, interrupts), plain)
    assert not np.array_equal(decode_rigid(c, t), plain)


def test_interrupts_must_be_f():
    t = T.Vigenere("KEY")
    with pytest.raises(ValueError):
        decode_skip_known(np.array([1, 2, 3]), t, [1])
    with pytest.raises(ValueError):
        encrypt_with_interrupts(np.array([1, 2, 3]), t, [1])
    with pytest.raises(ValueError):
        decode_skip_known(np.array([0, 2, 3]), t, [7])
