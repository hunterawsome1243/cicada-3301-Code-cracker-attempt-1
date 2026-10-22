"""`runeforge null`, the gate's key minimum and the control replay (`--out`)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
import yaml

from runeforge.lanes import load_lane
from runeforge.paths import REPO_ROOT
from runeforge.runner import gate, null


def _lane(tmp_path, **over):
    spec = {
        "lane_id": "TOOLS-TOY",
        "hypothesis": "toy",
        "family": "prng",
        "generator": "numpy-pcg64",
        "seed_range": [0, 300],
        "pages": [0, 1],
        "preset": "lp-ngram3-heldout:rigid",
        "interrupt_prob": 0.0,
        "control": {"planted_seed": 1, "synthetic_page": "solved:a-koan-1", "decoys": 199},
        **over,
    }
    path = tmp_path / "lane.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return path


def test_null_reports_both_nulls_at_the_lanes_trial_count(tmp_path):
    lane = load_lane(_lane(tmp_path))
    rep = null.run_null(lane, n=200, trials=None)
    assert rep["trials_per_replicate"] == 300 and rep["same_trial_count"]
    for key in ("null1_shuffle", "null2_sha256"):
        x = rep[key]
        assert x["n"] == 200 and x["max"] >= x["mean"] > -10 and x["sd"] > 0
    assert rep["numbering"] == "LP2-0-57"
    with pytest.raises(ValueError, match=">= 200"):
        null.run_null(lane, n=50)


def test_the_gate_needs_twelve_keys(tmp_path):
    with pytest.raises(ValueError, match=">= 12"):
        gate.run_gate(load_lane(_lane(tmp_path)), seeds=3)


def test_a_control_replay_touches_neither_the_lane_nor_the_ledger(tmp_path):
    env = dict(os.environ)
    env.update(
        RUNEFORGE_LANES=str(tmp_path / "lanes"),
        RUNEFORGE_LEDGER=str(tmp_path / "ledger.jsonl"),
        RUNEFORGE_RUNS=str(tmp_path / "runs"),
    )
    lane = _lane(tmp_path, seed_range=[0, 30_000])
    out = tmp_path / "replay"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "runeforge.cli",
            "control",
            str(lane),
            "--seed",
            "7",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert r.returncode in (0, 1), r.stderr
    report = json.loads((out / "control.json").read_text())
    assert report["seed"] == 7
    assert not (tmp_path / "lanes").exists() and not (tmp_path / "ledger.jsonl").exists()
    assert not (tmp_path / "runs").exists()


def test_seed_ranges_above_int64_work(tmp_path):
    """numpy-pcg64 takes 64-bit seeds; the gate, the control and the null draw them."""
    from runeforge.runner import pipeline

    rng = __import__("numpy").random.default_rng(0)
    lo = 2**63
    seeds = pipeline.draw_seeds(rng, lo, 2**64, 1000)
    assert all(lo <= s < 2**64 for s in seeds) and len(set(seeds)) == 1000
    lane = load_lane(_lane(tmp_path, seed_range=[2**63, 2**63 + 1000]))
    assert gate.run_gate(lane).verdict_line.startswith("GATE")
