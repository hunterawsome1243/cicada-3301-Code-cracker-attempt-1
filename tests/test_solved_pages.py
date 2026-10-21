"""Rule 1 -- reproduce before you attack.

All nine solved sections must re-derive exactly from the canon runes, through the same
transforms and interrupt decoder that every attack uses. The expected plaintext is
cicada_tools' own decode (data/reference/), never ours.
"""

from __future__ import annotations

import json
import re

import numpy as np
import pytest

from runeforge import canon
from runeforge import gematria as gm
from runeforge.interrupts import decode_rigid, decode_skip_known, f_positions
from runeforge.paths import REFERENCE_DIR
from runeforge.primes import is_prime
from runeforge.transforms import Vigenere, from_method

SOLVED_IDS = [
    "a-warning",
    "welcome",
    "some-wisdom",
    "a-koan-1",
    "the-loss-of-divinity",
    "a-koan-2",
    "an-instruction",
    "an-end",
    "parable",
]

# Spec section 2.5, verbatim.
DIVINITY = [23, 10, 1, 10, 9, 10, 16, 26]
FIRFUMFERENFE = [0, 10, 4, 0, 1, 19, 0, 18, 4, 18, 9, 0, 18]
WELCOME_INTERRUPTS = [48, 74, 84, 132, 159, 160, 250, 421, 443, 465, 514]


def decode(section_id: str) -> np.ndarray:
    s = canon.solved_section(section_id)
    return decode_skip_known(s.cipher, from_method(s.method), s.interrupts)


def latin(section_id: str) -> str:
    return gm.indices_to_latin(decode(section_id))


def test_nine_sections():
    assert [s.id for s in canon.load_solved_sections()] == SOLVED_IDS


@pytest.mark.parametrize("section_id", SOLVED_IDS)
def test_section_reproduces_exactly(section_id):
    s = canon.solved_section(section_id)
    out = decode(section_id)
    assert out.shape == s.cipher.shape
    assert np.array_equal(
        out, s.plain
    ), f"{section_id}: first mismatch at {np.argmax(out != s.plain)}"


@pytest.mark.parametrize("section_id", SOLVED_IDS)
def test_encrypt_inverts_decode(section_id):
    from runeforge.interrupts import encrypt_with_interrupts

    s = canon.solved_section(section_id)
    assert np.array_equal(
        encrypt_with_interrupts(s.plain, from_method(s.method), s.interrupts), s.cipher
    )


def test_methods_keys_and_interrupts_match_the_spec():
    m = {s.id: s for s in canon.load_solved_sections()}
    assert m["a-warning"].method["steps"] == [{"type": "atbash"}]
    assert m["welcome"].method["steps"] == [{"type": "vigenere", "key": DIVINITY}]
    assert list(m["welcome"].interrupts) == WELCOME_INTERRUPTS
    assert m["a-koan-1"].method["steps"] == [
        {"type": "atbash"},
        {"type": "shift", "n": -3},
    ]  # Atbash -> +3
    assert m["a-koan-2"].method["steps"] == [{"type": "vigenere", "key": FIRFUMFERENFE}]
    assert list(m["a-koan-2"].interrupts) == [49, 58]
    assert m["an-end"].method["steps"] == [{"type": "totient_prime_stream"}]
    assert list(m["an-end"].interrupts) == [56]
    for pid in ("some-wisdom", "the-loss-of-divinity", "an-instruction", "parable"):
        assert m[pid].method["steps"] == [] and not m[pid].interrupts
    assert gm.transliterate_english("DIVINITY") == DIVINITY
    assert gm.indices_to_latin(FIRFUMFERENFE) == "FIRFUMFERENFE"


@pytest.mark.parametrize(
    ("section_id", "n_f", "n_interrupts"),
    [("welcome", 25, 11), ("a-koan-2", 5, 2), ("an-end", 5, 1)],
)
def test_not_every_f_is_an_interrupter(section_id, n_f, n_interrupts):
    s = canon.solved_section(section_id)
    assert f_positions(s.cipher).size == n_f
    assert len(s.interrupts) == n_interrupts
    assert set(s.interrupts) <= set(f_positions(s.cipher).tolist())


@pytest.mark.parametrize("section_id", ["welcome", "a-koan-2", "an-end"])
def test_rigid_decoding_rejects_the_correct_key(section_id):
    s = canon.solved_section(section_id)
    rigid = decode_rigid(s.cipher, from_method(s.method))
    first = s.interrupts[0]
    assert np.array_equal(rigid[:first], s.plain[:first])  # identical up to the first interrupt
    assert (rigid[first:] != s.plain[first:]).mean() > 0.8  # then the key is out of step for good


def test_koan2_key_runs_across_the_page_boundary():
    s = canon.solved_section("a-koan-2")
    lp1 = canon.load_lp1()
    n14 = lp1.page(14).n_runes
    tail = s.cipher[n14:]
    tail_interrupts = [i - n14 for i in s.interrupts if i >= n14]
    restarted = decode_skip_known(tail, Vigenere(FIRFUMFERENFE), tail_interrupts)
    assert not np.array_equal(restarted, s.plain[n14:])
    assert np.array_equal(decode("a-koan-2")[n14:], s.plain[n14:])


def test_pipeline_matches_cicada_tools_reference():
    """Our transforms on cicada_tools' own ciphertext give cicada_tools' plaintext, rune
    for rune -- for all nine sections, including the one whose transcription differs."""
    ref = json.loads((REFERENCE_DIR / "cicada_tools_solved.json").read_text(encoding="utf-8"))
    ours = {s.id: s for s in canon.load_solved_sections()}
    assert len(ref["sections"]) == 9
    for sid, r in zip(SOLVED_IDS, ref["sections"], strict=True):
        s = ours[sid]
        c = gm.runes_to_indices(r["cipher"])
        out = decode_skip_known(c, from_method(s.method), s.interrupts)
        assert gm.indices_to_runes(out) == r["plain"], sid
        if sid != "the-loss-of-divinity":  # DV-05: one transposed rune in a plaintext page
            assert np.array_equal(c, s.cipher), sid


@pytest.mark.parametrize(
    ("section_id", "anchor"),
    [
        ("a-warning", "AWARNNGBELIEUENOTHNGFROMTHISBOOC"),
        ("welcome", "WELCOMEWELCOMEPILGRIMTOTHEGREATJOURNEYTOWARDTHEENDOFALLTHNGS"),
        ("welcome", "LICETHEINSTARITISONLYTHROUGHGONGWITHINTHATWEMAYEMERGE"),
        ("some-wisdom", "THEPRIMESARESACREDTHETOTIENTFUNCTIANISSACRED"),
        ("a-koan-1", "THATISNOTWHOYOUARE"),
        ("a-koan-1", "THATISWHATYOUDONOTWHOYOUARE"),
        ("the-loss-of-divinity", "THECIRCUMFERENCEPRACTICESTHREEBEHAUIARS"),
        ("a-koan-2", "THEIISTHEUOICEOFTHECIRCUMFERENCE"),
        ("an-instruction", "CWESTIANALLTHNGS"),
        ("parable", "FINDTHEDIUINITYWITHINANDEMERGE"),
    ],
)
def test_published_plaintext_anchors(section_id, anchor):
    assert anchor in latin(section_id)


def test_dv03_koan_reading():
    """DV-03: scream314's 'ᚹᛋ' for canon 'ᛠ' would make the koan say 'NOT WHAT YOU ARE'."""
    s = canon.solved_section("a-koan-1")
    lp1 = canon.load_lp1()
    start = sum(lp1.page(n).n_runes for n in (1, 3, 4, 5))  # koan starts after pages 1, 3-5
    assert start == 856
    alt = s.cipher.tolist()
    for off in sorted((998 - start, 1134 - start), reverse=True):
        assert alt[off] == 28
        alt[off : off + 1] = [7, 15]  # ᚹᛋ
    out = gm.indices_to_latin(from_method(s.method).decrypt(np.array(alt)))
    assert "THATISNOTWHATYOUARE" in out
    assert "THATISNOTWHOYOUARE" in latin("a-koan-1")


def test_an_end_full_plaintext():
    """The whole page, not a prefix (Dukotah CONFLICTS-B C-05)."""
    assert latin("an-end") == (
        "ANENDWITHINTHEDEEPWEBTHEREEXISTSAPAGETHATHASHESTO"
        "ITISTHEDUTYOFEUERYPILGRIMTOSEECOUTTHISPAGE"
    )
    assert "36367763ab73783c7af284446c" in canon.solved_section("an-end").plain_text


def _sentences(section_id: str) -> list[list[int]]:
    s = canon.solved_section(section_id)
    out, cur, k = [], [], 0
    for ch in s.template:
        if gm.is_rune(ch):
            cur.append(int(s.plain[k]))
            k += 1
        elif ch == "." and cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def test_a_warning_sentences_have_prime_gp_sums():
    sums = [gm.gp_sum(x) for x in _sentences("a-warning")]
    assert gm.indices_to_latin(_sentences("a-warning")[0]) == "AWARNNG"
    assert sums[1:] == [757, 1009, 691, 353, 769, 911, 1051, 859, 677]
    assert all(is_prime(v) for v in sums[1:])


def _square(section_id: str, page_part: str, page: int) -> np.ndarray:
    raw = canon.load_lp1().page(page).raw if page_part == "LP1" else canon.load_lp2().page(page).raw
    lines = [ln.strip().rstrip("/") for ln in raw.split("\n")]
    rows = []
    for ln in lines:
        toks = ln.split("-")
        if len(toks) == 5 and any(t.isdigit() for t in toks):
            rows.append(
                [int(t) if t.isdigit() else gm.gp_sum(gm.runes_to_indices(t)) for t in toks]
            )
    return np.array(rows)


@pytest.mark.parametrize(("page", "total"), [(5, 1033), (16, 3301)])
def test_know_this_squares_are_magic(page, total):
    sq = _square("", "LP1", page)
    assert sq.shape == (5, 5)
    assert set(sq.sum(axis=0)) == {total}
    assert set(sq.sum(axis=1)) == {total}
    assert np.trace(sq) == total and np.trace(np.fliplr(sq)) == total


def test_solved_text_is_rendered_from_the_canon_template():
    s = canon.solved_section("an-instruction")
    assert s.plain_text.startswith(
        "AN INSTRUCTIAN. CWESTIAN ALL THNGS. DISCOUER TRUTH INSIDE YOURSELF."
    )
    assert re.search(r"CNOW THIS\. 434 1311 312 278 966", s.plain_text)
