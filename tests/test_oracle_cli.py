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
from runeforge.transforms import StreamSubtract


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
    code = oracle.main(
        ["--key-module", str(km), "--pages", "2", "--n-trials", "1000000", "--json", str(out)]
    )
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
    assert oracle.main(["--key-module", str(km), "--pages", "2", "--n-trials", "1000"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "ORACLE: PASS"


def test_key_module_values_outside_the_alphabet_are_refused(tmp_path):
    km = tmp_path / "k_bad.py"
    km.write_text("def keystream(n):\n    return [29] * n\n", encoding="utf-8")
    with pytest.raises(SystemExit, match=r"outside 0\.\.28"):
        oracle.main(["--key-module", str(km), "--pages", "2", "--n-trials", "1000"])


def test_short_keystream_is_refused(tmp_path):
    ks = tmp_path / "short.txt"
    ks.write_text("1 2 3", encoding="utf-8")
    with pytest.raises(SystemExit, match="the claim needs"):
        oracle.main(["--keystream", str(ks), "--pages", "2", "--n-trials", "1000"])


def test_n_trials_is_required_without_a_lane(tmp_path, capsys):
    ks = tmp_path / "k.txt"
    ks.write_text(" ".join(["1"] * 5000), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        oracle.main(["--keystream", str(ks), "--pages", "2"])
    assert e.value.code == 2 and "--n-trials is required" in capsys.readouterr().err


def _lane_file(tmp_path, **over) -> str:
    import yaml

    spec = {
        "lane_id": "ORACLE-LANE",
        "hypothesis": "oracle --lane fixture",
        "family": "prng",
        "generator": "numpy-pcg64",
        "seed_range": [0, 1000],
        "pages": [3, 4],
        "combine": "beaufort",
        "ciphertext_view": "first-difference",
        "key_offset": 7,
        "control": {"planted_seed": 1, "synthetic_page": "solved:a-koan-1"},
    }
    spec.update(over)
    path = tmp_path / "lane.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("combine", ["vigenere", "variant-beaufort", "beaufort"])
@pytest.mark.parametrize("view", ["raw", "atbash", "first-difference", "chain-increment"])
def test_lane_decode_is_the_sweep_decode(tmp_path, combine, view):
    """--lane decodes exactly as runeforge.runner.pipeline does for the sweep."""
    import argparse

    from runeforge.lanes import load_lane
    from runeforge.runner import pipeline

    path = _lane_file(tmp_path, combine=combine, ciphertext_view=view)
    lane = load_lane(path)
    a = argparse.Namespace(lane=path, pages=None, n_trials=None)
    pages, cipher_pages, n_trials, to_subtract, offset = oracle._lane_claim(a)
    assert pages == [3, 4] and n_trials == 1000 and offset == 7
    raw = np.random.default_rng(9).integers(0, N, offset + 2000)
    keys = raw[offset : offset + sum(c.size for c in cipher_pages.values())]
    claim = oracle.Claim(
        "x", StreamSubtract(to_subtract(keys)).spec(), pages, key_scope="continuous"
    )
    got = np.concatenate(list(oracle.decode_claim(claim, cipher_pages).values()))
    want = pipeline.decrypt(lane, pipeline.lane_cipher(lane), keys)
    assert np.array_equal(got, want)


def test_lane_claim_on_non_leading_pages_passes_with_its_own_decode(tmp_path, capsys):
    """A beaufort / first-difference lane over pages 3-4 (not the first pages): a key that
    decodes them to English under the lane's own decode passes; the same key judged as
    p = c - k on the raw runes does not."""
    from runeforge.lanes import load_lane
    from runeforge.runner import pipeline

    path = _lane_file(tmp_path)
    lane = load_lane(path)
    cipher = pipeline.lane_cipher(lane)
    plain = np.concatenate([s.plain for s in canon.load_solved_sections()])[: cipher.size]
    pad = (plain + cipher) % N  # beaufort: p = k - c'
    km = tmp_path / "k_lane.py"
    filler = np.zeros(lane.key_offset, dtype=int)
    _write_key_module(km, np.concatenate([filler, pad, np.zeros(1000, dtype=int)]))
    assert oracle.main(["--key-module", str(km), "--lane", path]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "ORACLE: PASS"
    code = oracle.main(["--key-module", str(km), "--pages", "2", "--n-trials", "1000"])
    assert code == 1
