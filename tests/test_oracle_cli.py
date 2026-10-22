"""``python -m runeforge.oracle``: the entry point SESSION_PROMPT.md section A and
HIT_PROTOCOL.md step 5 call. Its last line is the verdict, and its exit code must agree."""

from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest

from runeforge import canon, oracle
from runeforge.gematria import N
from runeforge.paths import REPO_ROOT


def _first_pages(k: int) -> list[int]:
    lp2 = canon.load_lp2()
    return [n for n in canon.UNSOLVED_LP2_PAGES if lp2.page(n).n_runes][:k]


def _write_key_module(path, keys: np.ndarray) -> None:
    path.write_text(
        f"KEYS = {[int(x) for x in keys]}\n\ndef keystream(n):\n    return KEYS[:n]\n",
        encoding="utf-8",
    )


def test_module_entry_point_selftest_is_not_a_silent_exit():
    r = subprocess.run(
        [sys.executable, "-m", "runeforge.oracle", "--selftest"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "ORACLE SELF-TEST: PASS"


def test_regression_mode():
    assert oracle.main(["--regression"]) == 0


def test_random_key_module_fails(tmp_path, capsys):
    pages = _first_pages(2)
    lp2 = canon.load_lp2()
    need = sum(lp2.page(n).n_runes for n in pages)
    km = tmp_path / "k_random.py"
    _write_key_module(km, np.random.default_rng(1).integers(0, N, need))
    out = tmp_path / "v.json"
    code = oracle.main(["--key-module", str(km), "--pages", "2", "--json", str(out)])
    assert code == 1
    assert capsys.readouterr().out.strip().splitlines()[-1] == "ORACLE: FAIL"
    v = json.loads(out.read_text())
    assert v["verdict"] == "FAIL" and v["numbering"] == "LP2-0-57"


def test_pad_that_maps_two_pages_to_english_passes_the_mechanics(tmp_path, capsys):
    """k = c - p for English p makes any page read as English: the oracle checks the
    decode, never where the key came from. That is why HIT_PROTOCOL.md requires the key
    module to record its generator and seed, and why a hit also needs the bar at the
    lane's true N. This test only shows the PASS path and its exit code work."""
    pages = _first_pages(2)
    lp2 = canon.load_lp2()
    cipher = np.concatenate([lp2.page(n).runes for n in pages])
    plain = np.concatenate([s.plain for s in canon.load_solved_sections()])[: cipher.size]
    km = tmp_path / "k_pad.py"
    _write_key_module(km, (cipher - plain) % N)
    assert oracle.main(["--key-module", str(km), "--pages", "2"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "ORACLE: PASS"


def test_key_module_values_outside_the_alphabet_are_refused(tmp_path):
    km = tmp_path / "k_bad.py"
    km.write_text("def keystream(n):\n    return [29] * n\n", encoding="utf-8")
    with pytest.raises(SystemExit, match=r"outside 0\.\.28"):
        oracle.main(["--key-module", str(km), "--pages", "2"])


def test_short_keystream_is_refused(tmp_path):
    ks = tmp_path / "short.txt"
    ks.write_text("1 2 3", encoding="utf-8")
    with pytest.raises(SystemExit, match="the claim needs"):
        oracle.main(["--keystream", str(ks), "--pages", "2"])
