"""The canon: structure, numbering, pinned hashes, and the three-way cross-check."""

from __future__ import annotations

import shutil
import subprocess
import sys

import numpy as np
import pytest

from runeforge import canon
from runeforge.paths import CANON_DIR, REPO_ROOT

# Dukotah/cicada3301 liber-primus/PROBLEM.json ciphertext_identity
DUKOTAH_UNSOLVED_SHA256 = "023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585"


def test_counts_and_numbering():
    lp2 = canon.load_lp2()
    assert lp2.numbering == "LP2-0-57"
    assert [p.page for p in lp2.pages] == list(range(58))
    assert [p.book_page for p in lp2.pages] == list(range(17, 75))  # LP2 page 56 = book page 73
    assert lp2.stream().size == 13136
    assert canon.unsolved_stream().size == 12956
    assert lp2.page(50).n_runes == 0 and lp2.page(50).status == "runeless"
    assert {p.status for p in lp2.pages[56:]} == {"solved"}
    assert sum(p.status == "unsolved" for p in lp2.pages) == 55

    lp1 = canon.load_lp1()
    assert lp1.numbering == "LP1-0-16"
    assert [p.page for p in lp1.pages] == list(range(17))
    assert lp1.page(0).n_runes == 0 and lp1.page(2).n_runes == 0
    assert lp1.stream().size == 2797


def test_unsolved_stream_is_dukotahs_problem():
    u = canon.unsolved_stream()
    assert canon.indices_sha256(u) == DUKOTAH_UNSOLVED_SHA256
    first_24 = [15, 8, 18, 3, 6, 19, 27, 0, 15, 26, 18, 21, 5, 2, 11, 6, 25, 0, 11, 22, 3, 9, 2, 9]
    assert u[:24].tolist() == first_24  # PROBLEM.json first_24_indices


def test_unsolved_sections():
    secs = canon.unsolved_sections()
    names = ["p0-2", "p3-7", "p8-14", "p15-22", "p23-26", "p27-32", "p33-39", "p40-53", "p54-55"]
    assert list(secs) == names
    assert [v.size for v in secs.values()] == [729, 1145, 1729, 1903, 1021, 1433, 1680, 3008, 308]
    assert np.array_equal(np.concatenate(list(secs.values())), canon.unsolved_stream())


def test_page_structure():
    lp2 = canon.load_lp2()
    p0 = lp2.page(0)
    assert len(p0.lines) == len(p0.line_continues)
    words = p0.words()
    assert words[0] == [15, 8, 18, 3, 6, 19, 27, 0]  # ᛋᚻᛖᚩᚷᛗᛡᚠ
    assert sum(len(w) for w in words) == p0.n_runes
    # A WARNING line 3 ends "...ᚣᛁ-ᛞ/" and the word continues as "ᛗᚫᛝᚻᛁᚳᛟᛁ" on line 4.
    warning = canon.load_lp1().page(1)
    assert warning.line_continues[2] is True
    assert [23, 19, 25, 21, 8, 10, 5, 22, 10] in warning.words()


def test_pins_are_enforced(tmp_path):
    d = tmp_path / "canon"
    shutil.copytree(CANON_DIR, d)
    canon.load_lp2(d)  # an untouched copy verifies
    text = (d / canon.LP2_FILE).read_text(encoding="utf-8")
    (d / canon.LP2_FILE).write_text(text.replace('"page":3,', '"page":3, ', 1), encoding="utf-8")
    canon._load.cache_clear()
    with pytest.raises(canon.CanonIntegrityError):
        canon.load_lp2(d)
    canon._load.cache_clear()


def test_render():
    s = canon.solved_section("parable")
    assert s.plain_text == (
        "PARABLE. LICE THE INSTAR TUNNELNG TO THE SURFACE. WE MUST SHED OUR OWN "
        "CIRCUMFERENCES. FIND THE DIUINITY WITHIN AND EMERGE."
    )


@pytest.mark.raw
def test_build_canon_cross_check_and_freshness():
    """Rebuild from data/raw: the rtkd parse must agree with cicada_tools, scream314 and
    Dukotah up to exactly the documented divergences, and reproduce data/canon byte-for-byte."""
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_canon.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "7 edits observed, all documented" in r.stdout
