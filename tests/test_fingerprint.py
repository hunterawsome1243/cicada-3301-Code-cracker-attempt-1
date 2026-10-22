"""runeforge.stats.fingerprint: murphy's LP2 fingerprint and gate (C1-C6), pinned on LP2, and the
gate simulator on murphy's three fixture ciphers (jobs/hypothesis-gate/data/fixture).

The pins are murphy's own asserts (toolbox/fingerprint.py __main__) plus CONSTRAINTS.md's C2c and
C3 figures. They reproduce exactly from the canon with murphy's lpdata segmentation; nothing here
is loosened. A reference copy of murphy's pure-Python loops checks the numpy port on random
streams, so a pin that happens to match cannot hide a wrong formula.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from runeforge import canon
from runeforge.stats import fingerprint as fp

ROOT = Path(__file__).resolve().parents[1]
LP2_SHA = "023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585"
MURPHY_KEYS = [
    "n",
    "ioc",
    "doublets",
    "doublets_within",
    "doublets_cross",
    "doublet_rate",
    "doublet_residue_chi2",
    "cond_ioc",
    "lag5_hits",
    "lag5_pairs",
    "lag5_rate",
    "lag5_z",
    "lag5_straddle",
    "repeated_words",
    "repeated_words_null",
    "wordlen_r1",
    "wordlen_z",
    "n_words",
]


@pytest.fixture(scope="module")
def lp2():
    return fp.lp2_streams()


@pytest.fixture(scope="module")
def lp2_f(lp2):
    return fp.fingerprint(*lp2)


# --------------------------------------------------------------------------- LP2 pins


def test_lp2_streams_reproduce_the_canon(lp2):
    r, w, li, pg = lp2
    assert r.size == 12956
    assert np.array_equal(r, canon.unsolved_stream())
    assert canon.indices_sha256(r) == LP2_SHA
    for ids in (w, li, pg):
        assert ids.shape == r.shape and (np.diff(ids) >= 0).all()
    assert sorted(set(pg.tolist())) == [n for n in range(56) if n != 50]  # 50 carries no runes
    # murphy's lpdata: a page break does not break a word (page 0 ends "-ᚫ", page 1 opens "ᚪᛁᛗᛋᚾ-")
    first_p1 = int(np.argmax(pg == 1))
    assert w[first_p1] == w[first_p1 - 1] and li[first_p1] != li[first_p1 - 1]


def test_lp2_pins(lp2_f):
    f = lp2_f
    assert list(f) == MURPHY_KEYS
    assert f["n"] == 12956
    assert (f["doublets"], f["doublets_within"], f["doublets_cross"]) == (86, 63, 23)
    assert (f["lag5_hits"], f["lag5_pairs"]) == (104, 2105)
    assert f["lag5_straddle"] == (32, 460)
    assert abs(f["cond_ioc"] - 1.026) < 0.002
    assert f["repeated_words"] == 15  # CONSTRAINTS.md C3: fingerprint.py counts 15
    assert f["n_words"] == 2896
    assert round(f["ioc"], 3) == 1.000
    assert round(f["lag5_z"], 2) == 3.75  # CONSTRAINTS.md C5: z +3.75 raw


def test_lp2_doublet_positions_c2c(lp2):
    r, _w, _li, pg = lp2
    d = fp.doublet_positions(r)
    assert d.size == 86 and (r[d] == r[d - 1]).all()
    # CONSTRAINTS.md C2c: 18, 21, 16, 11, 20 -- the index of the doublet's *second* rune, mod 5
    assert tuple(np.bincount(d % 5, minlength=5).tolist()) == (18, 21, 16, 11, 20)
    assert tuple(np.bincount((d - 1) % 5, minlength=5).tolist()) == (21, 16, 11, 20, 18)
    glob = {k: fp.residue_chi2(d, k) for k in range(2, 9)}
    assert max(glob, key=glob.get) == 8 and round(glob[8], 1) == 7.6
    # "largest chi-square 11.3 vs 24.3": that figure is the within-page index, also mod 8
    pages, first = np.unique(pg, return_index=True)
    within = d - first[np.searchsorted(pages, pg[d])]
    wp = {k: fp.residue_chi2(within, k) for k in range(2, 9)}
    assert max(wp, key=wp.get) == 8 and round(wp[8], 1) == 11.3
    for chi2 in (glob, wp):
        assert all(v < fp.CHI2_001[k] for k, v in chi2.items())


def test_lp2_constants_are_what_this_module_measures(lp2, lp2_f):
    f, pins = lp2_f, fp.LP2
    for key in ("n", "doublets", "doublets_within", "doublets_cross", "lag5_hits"):
        assert f[key] == pins[key], key
    for key in ("lag5_pairs", "lag5_straddle", "repeated_words", "n_words"):
        assert f[key] == pins[key], key
    assert round(f["ioc"], 3) == pins["ioc"]
    assert round(f["cond_ioc"], 3) == pins["cond_ioc"]
    assert round(f["wordlen_z"], 2) == pins["wordlen_z"]
    mod5 = np.bincount(fp.doublet_positions(lp2[0]) % 5, minlength=5)
    assert tuple(mod5.tolist()) == pins["doublet_residues_mod5"]


def test_lp2_passes_its_own_gate(lp2_f):
    rows = fp.gate(lp2_f)
    assert [r.constraint for r in rows] == ["C1", "C2", "C2b", "C2c", "C3", "C4", "C5", "C6"]
    assert [r.verdict for r in rows] == ["PASS"] * 8
    assert rows[5].lp2 == -0.81 and rows[4].lp2 == 15


def test_gate_accepts_a_json_round_tripped_fingerprint(lp2_f):
    assert fp.gate(json.loads(json.dumps(lp2_f))) == fp.gate(lp2_f)


# --------------------------------------------------------------------------- port fidelity


def murphy_reference(runes, word, line, page) -> dict:
    """murphy toolbox/fingerprint.py's loops, transcribed (everything but the shuffle null)."""
    runes, word, line, page = (list(map(int, x)) for x in (runes, word, line, page))
    n = len(runes)
    d_in = d_x = 0
    for i in range(1, n):
        if runes[i] == runes[i - 1]:
            if word[i] == word[i - 1]:
                d_in += 1
            else:
                d_x += 1
    hits = pairs = s_hits = s_pairs = 0
    for a in range(n - 5):
        if word[a] == word[a + 5]:
            pairs += 1
            m = runes[a] == runes[a + 5]
            hits += m
            if line[a] != line[a + 5]:
                s_pairs += 1
                s_hits += m
    tab: Counter = Counter()
    for i in range(1, n):
        if page[i] == page[i - 1]:
            tab[(runes[i - 1], runes[i])] += 1
    rows: Counter = Counter()
    for (a, _b), v in tab.items():
        rows[a] += v
    num = sum(v * (v - 1) for v in tab.values())
    den = sum(v * (v - 1) for v in rows.values())
    dpos = [i for i in range(1, n) if runes[i] == runes[i - 1]]
    resid = {}
    for k in range(2, 9):
        cnt = [0] * k
        for x in dpos:
            cnt[x % k] += 1
        e = len(dpos) / k
        resid[k] = sum((c - e) ** 2 / e for c in cnt) if dpos else 0.0
    words, cur, last = [], [], None
    for r, w in zip(runes, word, strict=True):
        if w != last and cur:
            words.append(tuple(cur))
            cur = []
        cur.append(r)
        last = w
    if cur:
        words.append(tuple(cur))
    c = Counter(w for w in words if len(w) >= 3)
    lens = [len(w) for w in words]
    mu = sum(lens) / len(lens)
    var = sum((x - mu) ** 2 for x in lens) / len(lens)
    r1 = (
        sum((lens[i] - mu) * (lens[i + 1] - mu) for i in range(len(lens) - 1))
        / ((len(lens) - 1) * var)
        if var
        else 0
    )
    cc = Counter(runes)
    return {
        "ioc": 29 * sum(v * (v - 1) for v in cc.values()) / (n * (n - 1)),
        "doublets_within": d_in,
        "doublets_cross": d_x,
        "doublet_residue_chi2": resid,
        "cond_ioc": 29 * num / den if den else 0.0,
        "lag5_hits": hits,
        "lag5_pairs": pairs,
        "lag5_straddle": (s_hits, s_pairs),
        "repeated_words": sum(1 for v in c.values() if v >= 2),
        "wordlen_r1": r1,
        "wordlen_z": r1 * math.sqrt(len(lens)),
        "n_words": len(words),
    }


def _random_layout(rng, n, alphabet):
    runes = rng.integers(0, alphabet, n)
    word = np.cumsum(rng.random(n) < 0.25)
    line = np.cumsum(rng.random(n) < 1 / 22)
    page = np.cumsum(rng.random(n) < 1 / 235)
    return runes, word, line, page


@pytest.mark.parametrize("alphabet", [3, 29])
@pytest.mark.parametrize("seed", [1, 2])
def test_port_matches_murphys_loops(seed, alphabet):
    stream = _random_layout(np.random.default_rng(seed), 3000, alphabet)
    got, ref = fp.fingerprint(*stream), murphy_reference(*stream)
    for key, want in ref.items():
        if key == "doublet_residue_chi2":
            assert got[key].keys() == want.keys()
            assert all(math.isclose(got[key][k], want[k], abs_tol=1e-9) for k in want)
        elif isinstance(want, float):
            assert math.isclose(got[key], want, rel_tol=1e-12, abs_tol=1e-12), key
        else:
            assert got[key] == want, key


def test_hand_built_stream():
    # words [5 5 7] [7 9] [1 2 3 4 5 1 7]; doublets 5-5 (within) and 7-7 (across a word break)
    runes = [5, 5, 7, 7, 9, 1, 2, 3, 4, 5, 1, 7]
    word = [0, 0, 0, 1, 1, 2, 2, 2, 2, 2, 2, 2]
    line = [0] * 8 + [1] * 4
    f = fp.fingerprint(runes, word, line)
    assert (f["doublets"], f["doublets_within"], f["doublets_cross"]) == (2, 1, 1)
    assert fp.doublet_positions(runes).tolist() == [1, 3]
    assert (f["lag5_hits"], f["lag5_pairs"]) == (1, 2)  # 1..1 at distance 5 in the third word
    assert f["lag5_straddle"] == (1, 2)
    assert (f["n_words"], f["repeated_words"]) == (3, 0)
    assert fp.fingerprint(runes, word)["lag5_straddle"] is None
    with pytest.raises(ValueError):
        fp.fingerprint(runes, word[:-1])


def test_shuffle_null_is_seeded():
    stream = _random_layout(np.random.default_rng(7), 2000, 4)
    a, b = fp.fingerprint(*stream, seed=11), fp.fingerprint(*stream, seed=11)
    assert a["repeated_words_null"] == b["repeated_words_null"]
    assert a["repeated_words"] > 0  # a 4-symbol stream repeats words


# --------------------------------------------------------------------------- gate simulator


def vigenere7(plain, words, rng):
    """murphy fixture vigenere7.py: c_i = p_i + k_(i mod 7). Must fail C1 and C2."""
    key = rng.integers(0, 29, 7)
    return (plain + key[np.arange(plain.size) % 7]) % 29


def norepeat(plain, words, rng):
    """murphy fixture norepeat.py: random key, redraw until c differs from the previous rune."""
    key = rng.integers(0, 29, 3 * plain.size + 10).tolist()
    out = np.empty_like(plain)
    j, prev = 0, -1
    for i, p in enumerate(plain.tolist()):
        c = (p + key[j]) % 29
        j += 1
        while c == prev:
            c = (p + key[j]) % 29
            j += 1
        out[i] = prev = c
    return out


def otp_dodge5(plain, words, rng):
    """murphy fixture otp_dodge5.py: dodge a repeat (consume the next key value) except when the
    key clock j is at phase 0 mod 5, so repeats survive about 1 time in 5."""
    key = rng.integers(0, 29, 3 * plain.size + 10).tolist()
    out = np.empty_like(plain)
    j, prev = 0, -1
    for i, p in enumerate(plain.tolist()):
        c = (p + key[j]) % 29
        if c == prev and j % 5 != 0:
            j += 1
            c = (p + key[j]) % 29
        out[i] = prev = c
        j += 1
    return out


def otp(plain, words, rng):
    """Not a murphy fixture: an i.i.d. additive keystream, the textbook C2 exclusion."""
    return (plain + rng.integers(0, 29, plain.size)) % 29


FIXTURES = {"vigenere7": vigenere7, "norepeat": norepeat, "otp_dodge5": otp_dodge5, "otp": otp}
# jobs/hypothesis-gate/data/fixture/expected.md (murphy, Moby-Dick), reproduced at 12 seeds.
# murphy measured with --seeds 2 and Python's random; at our seeds=2 vigenere7's second key
# (numpy seed 1001: mod-7 chi2 20.2 < 22.46) passes C2c, so that line reads "C1 C2 C2b C3 C6".
MURPHY_EXPECTED = {
    "otp_dodge5": "GATE PASS",
    "vigenere7": "GATE FAIL: C1 C2 C2b C2c C3 C6",
    "norepeat": "GATE FAIL: C2 C6",
    "otp": "GATE FAIL: C2 C6",
}
# Measured here on cicada-english (Self-Reliance), 12 seeds: otp_dodge5's drifting clock leaves
# its doublet phases overdispersed, so 2 of 12 keys fail C2c (mod 6 chi2 21.7, mod 2 11.2).
CICADA_MEASURED = {
    "otp_dodge5": "GATE PASS (marginal: C2c)",
    "vigenere7": "GATE FAIL: C1 C2 C2b C2c C3 C6",
    "norepeat": "GATE FAIL: C2 C6",
    "otp": "GATE FAIL: C2 C6",
}


def _builder():
    if "build_corpus" in sys.modules:
        return sys.modules["build_corpus"]
    spec = importlib.util.spec_from_file_location("build_corpus", ROOT / "scripts/build_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_corpus"] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def corpora_dir(tmp_path_factory) -> Path:
    """Every corpus, built once per session from data/raw into a tmp dir (shared with
    tests/test_corpus.py), so a fresh checkout needs no manual build step."""
    d = tmp_path_factory.getbasetemp() / "corpora"
    if not (d / "index.json").exists():
        bc = _builder()
        try:
            bc.build(out_dir=d)
        except bc.BuildError as e:
            if os.environ.get("RUNEFORGE_REQUIRE_RAW") == "1":
                raise
            pytest.skip(f"corpus sources missing ({e}); run scripts/fetch_raw.sh")
    return d


@pytest.mark.raw
@pytest.mark.parametrize(
    ("corpus", "expected"),
    [("english-general", MURPHY_EXPECTED), ("cicada-english", CICADA_MEASURED)],
)
@pytest.mark.parametrize("cipher", list(FIXTURES))
def test_gate_on_fixture_ciphers(corpora_dir, corpus, expected, cipher):
    res = fp.gate_cipher(FIXTURES[cipher], corpus=corpus, corpora_dir=corpora_dir)
    assert res.verdict_line == expected[cipher]
    assert len(res.per_seed_rows) == len(res.fingerprints) == 12
    assert set(res.fails_per_constraint) <= set(fp.HARD)
    assert res.passed == expected[cipher].startswith("GATE PASS")
    if cipher == "norepeat":
        assert all(f["doublets"] == 0 for f in res.fingerprints)
        assert {rows[3].verdict for rows in res.per_seed_rows} == {"INFO"}  # C2c: < 20 doublets
    if cipher == "otp_dodge5":
        rates = [f["doublet_rate"] for f in res.fingerprints]
        assert 0.006 < np.mean(rates) < 0.009  # expected.md: about 0.86 %


def test_gate_cipher_plumbing_without_raw(tmp_path):
    """lp-solved builds from the canon alone, so the simulator's checks run on any checkout."""
    _builder().build(["lp-solved"], out_dir=tmp_path)
    kw = {"n": 2900, "seeds": 3, "corpus": "lp-solved", "corpora_dir": tmp_path}
    res = fp.gate_cipher(otp, **kw)
    assert res.verdict_line == "GATE FAIL: C2 C6"
    assert res.fails_per_constraint == {"C2": 3, "C6": 3}
    with pytest.raises(ValueError, match="one integer rune"):
        fp.gate_cipher(lambda p, w, rng: p[:-1], **kw)
    with pytest.raises(ValueError, match=r"outside 0\.\.28"):
        fp.gate_cipher(lambda p, w, rng: p + 29, **kw)
    with pytest.raises(ValueError, match="does not fit"):
        fp.gate_cipher(otp, n=5000, corpus="lp-solved", corpora_dir=tmp_path)
