"""scripts/build_corpus.py and runeforge.corpus: pinned sources in, deterministic rune corpora out.

The raw-marked tests build every corpus once per session into a tmp dir (shared with
tests/test_fingerprint.py), so a fresh checkout needs no manual step. ``lp-solved`` needs only
the canon, so its tests and the loader's run on any checkout.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pytest

from runeforge import canon, corpus, stats
from runeforge import gematria as gm

ROOT = Path(__file__).resolve().parents[1]
ALL = [
    "cicada-english",
    "english-general",
    "latin",
    "lp-solved",
    "old-english",
    "vowel-dropped-english",
]


def _builder():
    if "build_corpus" in sys.modules:
        return sys.modules["build_corpus"]
    spec = importlib.util.spec_from_file_location("build_corpus", ROOT / "scripts/build_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_corpus"] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


bc = _builder()


@pytest.fixture(scope="session")
def corpora_dir(tmp_path_factory) -> Path:
    """Every corpus, built once per session from data/raw (shared with test_fingerprint.py)."""
    d = tmp_path_factory.getbasetemp() / "corpora"
    if not (d / "index.json").exists():
        try:
            bc.build(out_dir=d)
        except bc.BuildError as e:
            if os.environ.get("RUNEFORGE_REQUIRE_RAW") == "1":
                raise
            pytest.skip(f"corpus sources missing ({e}); run scripts/fetch_raw.sh")
    return d


def words_of(c: corpus.Corpus, k: int) -> list[str]:
    """The first k words of a corpus, in Latin letters."""
    starts = [*np.flatnonzero(np.diff(c.word_ids, prepend=-1))[: k + 1].tolist(), len(c)]
    return [gm.indices_to_latin(c.runes[a:b]) for a, b in itertools.pairwise(starts[: k + 1])]


def tr(text: str) -> list[int]:
    return gm.transliterate_english(text)


# --------------------------------------------------------------------------- no raw needed


def test_lp_solved_builds_from_the_canon_alone(tmp_path):
    index = bc.build(["lp-solved"], out_dir=tmp_path)
    c = corpus.load("lp-solved", tmp_path)
    sections = canon.load_solved_sections()
    assert np.array_equal(c.runes, np.concatenate([s.plain for s in sections]))
    assert len(c) == 2977 and c.n_words == 739
    assert words_of(c, 6) == ["A", "WARNNG", "BELIEUE", "NOTHNG", "FROM", "THIS"]
    # AN END's hash and SOME WISDOM's numbers are not runes and are skipped
    meta = index["corpora"]["lp-solved"]
    assert meta == c.meta and meta["numbering"] == "LP2-0-57"
    assert meta["sources"][0]["sha256"] == canon.read_pins()[canon.SOLVED_FILE].sha256
    assert meta["sources"][0]["sections"] == [s.id for s in sections]
    assert corpus.names(tmp_path) == ["lp-solved"]
    assert json.loads((tmp_path / "index.json").read_text())["numbering"] == "LP2-0-57"


def test_missing_corpus_says_how_to_build(tmp_path):
    with pytest.raises(corpus.CorpusMissingError, match=r"scripts/build_corpus\.py"):
        corpus.load("cicada-english", tmp_path)
    assert corpus.names(tmp_path / "absent") == []


def test_english_stream(tmp_path):
    bc.build(["lp-solved"], out_dir=tmp_path)
    full = corpus.load("lp-solved", tmp_path)
    r, w = corpus.english_stream(100, "lp-solved", offset=50, corpora_dir=tmp_path)
    assert r.size == w.size == 100 and r.dtype == w.dtype == np.int64
    assert np.array_equal(r, full.runes[50:150]) and w[0] == 0
    assert np.array_equal(w, full.word_ids[50:150] - full.word_ids[50])
    r[:] = 0  # a writable copy: the cached corpus is untouched
    assert not np.array_equal(full.runes[50:150], r)
    assert not full.runes.flags.writeable
    assert corpus.english_stream(2977, "lp-solved", corpora_dir=tmp_path)[0].size == 2977
    for n, off in ((2978, 0), (2977, 1), (0, 0)):
        with pytest.raises(ValueError):
            corpus.english_stream(n, "lp-solved", offset=off, corpora_dir=tmp_path)


def test_transliterate_is_gematria_transliterate_words():
    text = bc.normalize("Quaesiveris extra! THING'S--kings; Æthelred þā Cæsar's œuvre, ǣr Ēadgār.")
    assert text == "Quaesiveris extra! THING'S--kings; AEthelred tha Caesar's oeuvre, aer Eadgar."
    assert bc.transliterate(text) == gm.transliterate_words(text)
    assert bc.transliterate("Hwaet") == [[8, 7, 25, 16]]  # H W AE T


def test_extract_body_rules():
    t = bc.Text("x", "0" * 64, start="BEGIN", end="END", drop=(("[a", "a]"),))
    body = bc.extract_body("head BEGIN one [a two a] three END tail END", t)
    assert body == "BEGIN one a] three "
    with pytest.raises(bc.BuildError, match="start marker"):
        bc.extract_body("BEGIN BEGIN END", t)
    with pytest.raises(bc.BuildError, match="end marker"):
        bc.extract_body("BEGIN [a a] no end", t)
    with pytest.raises(bc.BuildError, match="drop span"):
        bc.extract_body("BEGIN no span END", t)


def test_drop_vowels_rule():
    words = [tr("A"), tr("EYE"), tr("GREAT"), tr("THING"), tr("LOVE")]
    runes = np.array([i for w in words for i in w])
    ids = np.repeat(np.arange(len(words)), [len(w) for w in words])
    r, w = bc.drop_vowels(runes, ids)
    got = [gm.indices_to_latin(r[w == k]) for k in range(len(words))]
    assert got == ["A", "E", "GRT", "THNG", "L"]  # first rune kept; EA, Y and U(=V) dropped
    assert set(bc.VOWEL_RUNES) == {gm.LATIN.index(v) for v in bc.VOWELS}


def test_pinned_sha256_mismatch_is_a_hard_error(tmp_path):
    raw = tmp_path / "raw"
    for t in bc.SPECS["cicada-english"].texts:
        (raw / t.path).parent.mkdir(parents=True, exist_ok=True)
        (raw / t.path).write_text("I.\nHISTORY\nnot the pinned text Next Volume", encoding="utf-8")
    with pytest.raises(bc.BuildError, match="sha256"):
        bc.build(["cicada-english"], out_dir=tmp_path / "out", raw_dir=raw)
    with pytest.raises(bc.BuildError, match="missing"):
        bc.build(["latin"], out_dir=tmp_path / "out", raw_dir=tmp_path / "empty")
    assert not (tmp_path / "out" / "cicada-english.npz").exists()


def test_fetch_raw_sparse_list_has_every_source():
    sh = (ROOT / "scripts" / "fetch_raw.sh").read_text(encoding="utf-8")
    block = re.search(r"\n\s*dukotah\) printf .*?;;", sh, re.S).group(0)
    for spec in bc.SOURCES:
        for t in spec.texts:
            assert t.path.startswith("dukotah/")
            assert "/" + t.path.removeprefix("dukotah/") in block.split(), t.path


# --------------------------------------------------------------------------- built from data/raw


@pytest.mark.raw
def test_every_corpus_builds_with_its_index_entry(corpora_dir):
    assert corpus.names(corpora_dir) == ALL == sorted(bc.SPECS)
    index = json.loads((corpora_dir / "index.json").read_text(encoding="utf-8"))
    assert index["numbering"] == "LP2-0-57"
    for name in ALL:
        c = corpus.load(name, corpora_dir)
        m = index["corpora"][name]
        assert c.meta == m and c.name == name
        for key in ("register", "language", "n_runes", "n_words", "sources", "rules"):
            assert key in m, (name, key)
        assert m["n_runes"] == len(c) and m["n_words"] == int(c.word_ids[-1]) + 1
        assert m["indices_sha256"] == canon.indices_sha256(c.runes)
        assert all(len(s["sha256"]) == 64 and s["path"] for s in m["sources"])
        assert m["rules"]["transliteration"] == "runeforge.gematria.DEFAULT_RULES"
    sizes = {n: index["corpora"][n]["n_runes"] for n in ALL}
    assert sizes["english-general"] > 800_000 and sizes["cicada-english"] > 300_000
    assert sizes["latin"] > 100_000 and sizes["old-english"] > 80_000


@pytest.mark.raw
def test_corpus_bodies_start_where_the_rules_say(corpora_dir):
    first = {n: words_of(corpus.load(n, corpora_dir), 5) for n in ALL}
    assert first["cicada-english"] == ["SELF", "RELIANCE", "NE", "TE", "CWAESIUERIS"]
    assert first["english-general"] == ["CHAPTER", "LOOMNGS", "CALL", "ME", "ISHMAEL"]
    assert first["latin"] == ["C", "IULI", "CAESARIS", "DE", "BELLO"]
    assert first["old-english"] == ["HWAET", "WE", "GAR", "DENA", "IN"]  # fitt headings dropped
    assert first["vowel-dropped-english"] == ["CHPTR", "LMNGS", "CLL", "M", "ISHML"]


@pytest.mark.raw
def test_self_reliance_is_not_trained_on_twice(corpora_dir):
    c = corpus.load("cicada-english", corpora_dir)
    phrase = np.array(tr("trust thyself every heart vibrates to that iron string"), np.int8)
    hay = c.runes.astype(np.int8).tobytes()
    assert hay.count(phrase.tobytes()) == 1
    emerson = c.meta["sources"][1]
    assert emerson["drop"] == [["II.\nSELF-RELIANCE\n", "III.\nCOMPENSATION\n"]]


@pytest.mark.raw
def test_vowel_dropped_is_derived_from_english_general(corpora_dir):
    base = corpus.load("english-general", corpora_dir)
    vd = corpus.load("vowel-dropped-english", corpora_dir)
    r, w = bc.drop_vowels(base.runes, base.word_ids)
    assert np.array_equal(vd.runes, r) and np.array_equal(vd.word_ids, w)
    assert vd.n_words == base.n_words
    assert vd.meta["derived_from_indices_sha256"] == base.meta["indices_sha256"]
    inner = np.ones(len(vd), bool)
    inner[np.flatnonzero(np.diff(vd.word_ids, prepend=-1))] = False
    assert not np.isin(vd.runes[inner], bc.VOWEL_RUNES).any()


@pytest.mark.raw
def test_build_is_deterministic(corpora_dir, tmp_path):
    index = bc.build(["latin", "old-english"], out_dir=tmp_path)
    for name in ("latin", "old-english"):
        again = corpus.load(name, tmp_path)
        assert index["corpora"][name] == corpus.load(name, corpora_dir).meta
        assert np.array_equal(again.runes, corpus.load(name, corpora_dir).runes)


@pytest.mark.raw
@pytest.mark.parametrize("name", ["cicada-english", "english-general"])
def test_lp2_sized_streams_for_the_gate(corpora_dir, name):
    r, w = corpus.english_stream(12956, name, corpora_dir=corpora_dir)
    assert r.size == 12956 and w[0] == 0
    assert 1.6 < stats.ioc_norm(r) < 1.9  # English in runes, not cipher-flat
