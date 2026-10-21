"""Gematria Primus table and transliteration rules (spec section 2.2)."""

from __future__ import annotations

import re

import numpy as np
import pytest

from runeforge import canon
from runeforge import gematria as gm
from runeforge.paths import RAW_DIR
from runeforge.primes import first_primes, is_prime


def test_table_shape():
    assert gm.N == 29
    assert [r.idx for r in gm.TABLE] == list(range(29))
    assert len(set(gm.RUNES)) == 29
    assert list(gm.PRIMES) == first_primes(29).tolist()
    assert gm.PRIMES[0] == 2 and gm.PRIMES[-1] == 109


def test_index_order_of_the_last_three_runes():
    # The spec's draft table mis-printed these glyphs; every source agrees on this order.
    assert (gm.idx_to_rune(26), gm.idx_to_latin(26)) == ("ᚣ", "Y")
    assert (gm.idx_to_rune(27), gm.idx_to_latin(27)) == ("ᛡ", "IA")
    assert (gm.idx_to_rune(28), gm.idx_to_latin(28)) == ("ᛠ", "EA")


def test_conversions_round_trip():
    for i in range(29):
        r = gm.idx_to_rune(i)
        assert gm.rune_to_idx(r) == i
        assert gm.idx_to_prime(i) == gm.PRIMES[i]
    assert gm.rune_to_idx("ᛂ") == 11  # U+16C2 variant of GER/J
    with pytest.raises(ValueError):
        gm.rune_to_idx("A")
    with pytest.raises(ValueError):
        gm.idx_to_rune(29)


@pytest.mark.raw
def test_table_matches_cicada_tools():
    """Source: yo-yo-yo-jbo/cicada_tools core.py RuneUtils (_RUNES, _LATIN, _GP_PRIMES)."""
    from runeforge.sources import cicada_tools_alphabet

    ct = cicada_tools_alphabet()
    assert "".join(ct["_RUNES"]) == gm.RUNES
    assert ct["_GP_PRIMES"] == list(gm.PRIMES)
    # cicada_tools writes index 1 as V; it is the same rune (U/V).
    assert [("U" if x == "V" else x) for x in ct["_LATIN"]] == list(gm.LATIN)


@pytest.mark.raw
def test_table_matches_dukotah_problem():
    """Source: Dukotah/cicada3301 liber-primus/PROBLEM.json alphabet.index_to_transliteration."""
    from runeforge.sources import parse_dukotah_problem

    alpha = parse_dukotah_problem()["problem"]["alphabet"]
    assert alpha["size"] == 29
    assert alpha["index_to_transliteration"] == list(gm.LATIN)


@pytest.mark.raw
def test_table_matches_scream314_a_warning():
    """Source: scream314/cicada3301 liber_primus.md, '## Runes - 01.jpg'. Their runes,
    read with our table and Atbash-decoded (which depends on the index order), must spell
    their published English 'A WARNING / BELIEVE NOTHING FROM THIS BOOK / ...'."""
    from runeforge.transforms import Atbash

    text = (RAW_DIR / "scream314-cicada3301" / "liber_primus.md").read_text(encoding="utf-8")
    section = text[text.index("## Runes - 01.jpg") : text.index("## Intus - 02.jpg")]
    runes = "".join(
        ln
        for ln in section.splitlines()
        if ln.startswith("    ") and any(gm.is_rune(c) for c in ln)
    )
    english_start = section.index("to each letter/rune yields:")
    english = section[english_start:].split("\n\n", 2)[1]
    assert english.split("\n")[0].strip() == "A WARNING"
    decoded = Atbash().decrypt(gm.runes_to_indices(runes))
    assert decoded.tolist() == gm.transliterate_english(english)
    assert np.array_equal(gm.runes_to_indices(runes), canon.load_lp1().page(1).runes)


def test_primes():
    assert [n for n in range(30) if is_prime(n)] == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    assert is_prime(3301) and is_prime(1033) and not is_prime(3301 * 1033)
    assert first_primes(1000)[-1] == 7919


@pytest.mark.parametrize(
    ("english", "latin"),
    [
        ("BOOK", "BOOC"),  # K -> C
        ("KNOW", "CNOW"),
        ("QUESTION", "CWESTIAN"),  # QU -> CW, IO -> IA rune
        ("THINGS", "THNGS"),  # ING -> NG rune
        ("FUNCTION", "FUNCTIAN"),
        ("YOU", "YOU"),
        ("DIVINITY", "DIUINITY"),  # V -> U
        ("ZERO", "SERO"),  # Z -> S
        ("WARNING", "WARNNG"),
        ("DEATH", "DEATH"),
    ],
)
def test_transliteration_rules(english, latin):
    assert gm.indices_to_latin(gm.transliterate_english(english)) == latin


def test_transliteration_never_crosses_word_boundaries():
    assert gm.transliterate_words("AT HOME") == [[24, 16], [8, 3, 19, 18]]  # not A TH OME
    assert gm.transliterate_english("THE") == [2, 18]
    assert gm.transliterate_english("DIVINITY") == [23, 10, 1, 10, 9, 10, 16, 26]


def test_rules_are_data_driven():
    no_ing = gm.TransliterationRules(
        gm.DEFAULT_RULES.substitutions,
        tuple(g for g in gm.DEFAULT_RULES.graphemes if g[0] != "ING"),
    )
    assert gm.indices_to_latin(gm.transliterate_english("THING", no_ing)) == "THING"
    assert gm.indices_to_latin(gm.transliterate_english("THING")) == "THNG"


def test_gp_sum():
    assert gm.gp_sum([]) == 0
    assert gm.gp_sum(gm.transliterate_english("NOTHING")) == 29 + 7 + 5 + 79
    assert gm.gp_sum(np.arange(29)) == sum(gm.PRIMES)


A_WARNING_ENGLISH = """A WARNING. BELIEVE NOTHING FROM THIS BOOK. EXCEPT WHAT YOU KNOW TO BE
TRUE. TEST THE KNOWLEDGE. FIND YOUR TRUTH. EXPERIENCE YOUR DEATH. DO NOT EDIT OR CHANGE THIS
BOOK. OR THE MESSAGE CONTAINED WITHIN. EITHER THE WORDS OR THEIR NUMBERS. FOR ALL IS SACRED."""


def test_english_spelling_reproduces_a_warning_exactly():
    plain = canon.solved_section("a-warning").plain
    assert gm.transliterate_english(A_WARNING_ENGLISH) == plain.tolist()


@pytest.mark.raw
def test_english_spelling_reproduces_the_solved_pages():
    """rtkd's English translation, spelled with DEFAULT_RULES, must give the decoded runes
    of every solved section except a short, explained list of differences."""
    import difflib

    text = (
        RAW_DIR / "rtkd-iddqd/liber-primus__translation/liber-primus__translation.txt"
    ).read_text(encoding="utf-8")
    blocks = re.split(r"^\+\+\n\+ (0\.\d+)\n\+\n", text, flags=re.M)
    english = {}
    for key, body in zip(blocks[1::2], blocks[2::2], strict=True):
        lines = [
            ln.split("\t", 1)[-1] for ln in body.splitlines() if re.match(r"^0\.\d+\.\d+\.\d+", ln)
        ]
        english[key] = re.sub(r"[0-9]+", " ", " ".join(lines))
    groups = {
        "0.0": ["a-warning"],
        "0.1": ["welcome", "some-wisdom"],
        "0.2": ["a-koan-1"],
        "0.3": ["the-loss-of-divinity"],
        "0.4": ["a-koan-2", "an-instruction"],
        "0.13": ["an-end"],
        "0.14": ["parable"],
    }
    diffs = {}
    for key, ids in groups.items():
        ours = gm.indices_to_runes(gm.transliterate_english(english[key]))
        plain = gm.indices_to_runes(np.concatenate([canon.solved_section(s).plain for s in ids]))
        sm = difflib.SequenceMatcher(None, ours, plain, autojunk=False)
        diffs[key] = [
            (
                op,
                gm.indices_to_latin(gm.runes_to_indices(ours[i1:i2])),
                gm.indices_to_latin(gm.runes_to_indices(plain[j1:j2])),
            )
            for op, i1, i2, j1, j2 in sm.get_opcodes()
            if op != "equal"
        ]
    square = "SHADOWSAETHEREALBUFFERSUOIDCARNALOBSCURAFORMMOBIUSANALOGUOIDMOURNFULAETHEREALCABAL"
    assert diffs == {
        "0.0": [],
        # Cicada's own transposition WIDSOM; the KNOW THIS square words are not in the translation.
        "0.1": [("insert", "", "D"), ("delete", "D", ""), ("insert", "", square)],
        "0.2": [],
        # rtkd's translation has the typo FOLLWING; the page reads FOLLOWNG.
        "0.3": [("insert", "", "O")],
        "0.4": [],
        "0.13": [],
        "0.14": [],
    }
