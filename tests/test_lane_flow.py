"""The documented lane procedure, end to end through the CLI (README.md "Running a lane"):
pre-register -> control (records its evidence) -> validator -> sweep (refuses until the
evidence and the frozen bar line up) -> every sweep row reproduces with `runeforge score`."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from runeforge.paths import REPO_ROOT
from runeforge.scoring import calib

N_SEEDS = 20_000


def _env(tmp_path: Path) -> dict:
    env = dict(os.environ)
    env.update(
        RUNEFORGE_LANES=str(tmp_path / "lanes"),
        RUNEFORGE_LEDGER=str(tmp_path / "ledger.jsonl"),
        RUNEFORGE_RUNS=str(tmp_path / "runs"),
    )
    return env


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "runeforge.cli", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=_env(tmp_path),
        timeout=600,
    )


def _validate(tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/validate_ledger.py"),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
            "--root",
            str(tmp_path),
            "--no-git",
        ],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def lane(tmp_path: Path) -> Path:
    bar = calib.threshold_for(N_SEEDS, "lp-ngram3-heldout:rigid", 240).bar
    spec = {
        "lane_id": "FLOW-PCG64",
        "hypothesis": "toy: pages 0-1 are numpy-pcg64 keystreams (CI fixture only)",
        "family": "prng",
        "category": "instrument",
        "generator": "numpy-pcg64",
        "seed_range": [0, N_SEEDS],
        "chunk_size": 10_000,
        "window": 240,
        "pages": [0, 1],
        "preset": "lp-ngram3-heldout:rigid",
        "interrupt_prob": 0.0,
        "claim_bar": bar - 0.3,
        "family_wise_bar": bar,
        "control": {
            "planted_seed": 3301,
            "synthetic_page": "solved:a-koan-1",
            "n_plants": 20,
            "decoys": 199,
        },
    }
    path = tmp_path / "FLOW-PCG64.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return path


@pytest.mark.raw  # the gate simulates the family on the cicada-english corpus
def test_the_documented_lane_procedure(tmp_path, lane):
    spec = yaml.safe_load(lane.read_text())
    bar = spec["family_wise_bar"]
    # no ledger row, no control: the sweep refuses
    r = _run(tmp_path, "sweep", str(lane))
    assert r.returncode == 2 and "REFUSED" in r.stderr + r.stdout

    # pre-registration with the frozen bar
    r = _run(
        tmp_path,
        "ledger",
        "append",
        "FLOW-PCG64",
        "--set",
        f"hypothesis={spec['hypothesis']}",
        "--set",
        "family=prng",
        "--set",
        f"threshold={bar!r}",
        "--set",
        "threshold_fixed_in_advance=true",
        "--set",
        "reopens_if=a non-toy lane",
    )
    assert r.returncode == 0, r.stderr

    # the control writes its committed report and records it in the ledger
    r = _run(tmp_path, "control", str(lane))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "recovered 20/20 at rank 1" in r.stdout
    reports = sorted((tmp_path / "lanes" / "FLOW-PCG64").glob("control-*.json"))
    assert len(reports) == 1 and (tmp_path / "lanes/FLOW-PCG64/control.json").exists()
    rows = [json.loads(x) for x in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert rows[-1]["positive_control"] == "passed"
    assert rows[-1]["control_detail"]["sha256"]
    v = _validate(tmp_path)
    assert v.returncode == 0 and v.stdout.strip().endswith("Unsound negatives = 0"), v.stdout

    # the gate: this toy lane (no filter) has LP2's doublet rate x 5, so the gate excludes it
    # and the sweep refuses. That is the honest state of every rigid-decoder lane today: one
    # with the anti-repeat filter passes the gate but fails its control (the rigid decoder
    # cannot follow the key skips), so the Phase 2 beam decoder is the critical path.
    r = _run(tmp_path, "gate", str(lane))
    assert r.returncode == 1 and "GATE FAIL" in r.stdout, r.stdout + r.stderr
    r = _run(tmp_path, "sweep", str(lane))
    assert r.returncode == 2 and "gate" in (r.stdout + r.stderr).lower()

    # from here the sweep mechanics, with a passing gate report standing in (a fixture, not
    # a measurement) for a lane whose family reproduces the fingerprint
    from runeforge.lanes import load_lane
    from runeforge.runner.control import lane_pipeline_sha256

    fixture = {
        "lane_id": "FLOW-PCG64",
        "numbering": "LP2-0-57",
        "verdict_line": "GATE PASS (test fixture)",
        "excluded": False,
        "n_seeds": 12,
        "lane_pipeline_sha256": lane_pipeline_sha256(load_lane(lane)),
    }
    gate_json = tmp_path / "lanes" / "FLOW-PCG64" / "gate.json"
    gate_json.write_text(json.dumps(fixture), encoding="utf-8")
    run_gate = tmp_path / "runs" / "FLOW-PCG64" / "gate.json"
    run_gate.write_text(json.dumps(fixture), encoding="utf-8")

    # the sweep runs now, and its rows reproduce with `runeforge score`
    r = _run(tmp_path, "sweep", str(lane))
    assert r.returncode == 0, r.stdout + r.stderr
    rd = tmp_path / "runs" / "FLOW-PCG64"
    st = json.loads((rd / "status.json").read_text())
    assert st["done"] and st["cursor"] == N_SEEDS
    r = _run(tmp_path, "score", str(lane), str(st["best_seed"]), "--json")
    assert r.returncode == 0, r.stderr
    rescored = json.loads(r.stdout)["top"][0]
    assert rescored["seed"] == st["best_seed"]
    assert rescored["score"] == pytest.approx(st["best_score"], abs=1e-12)
    for row in (json.loads(x) for x in (rd / "sweep.jsonl").read_text().splitlines()):
        if row["type"] in ("survivor", "crosser"):
            assert row["reproduce"].startswith("runeforge score")

    # editing the lane after its control invalidates the control
    spec["window"] = 120
    spec["claim_bar"] = calib.threshold_for(N_SEEDS, "lp-ngram3-heldout:rigid", 120).bar - 0.3
    lane.write_text(yaml.safe_dump(spec), encoding="utf-8")
    r = _run(tmp_path, "sweep", str(lane), "--no-resume")
    assert r.returncode == 2 and "re-run `runeforge control`" in r.stderr + r.stdout


def test_a_hand_set_passing_control_is_not_evidence(tmp_path, lane):
    spec = yaml.safe_load(lane.read_text())
    r = _run(
        tmp_path,
        "ledger",
        "append",
        "FLOW-PCG64",
        "--set",
        "hypothesis=h",
        "--set",
        "family=prng",
        "--set",
        "positive_control=passed",
        "--set",
        f"threshold={spec['family_wise_bar']!r}",
        "--set",
        "threshold_fixed_in_advance=true",
    )
    assert r.returncode != 0 and "must cite its evidence" in r.stdout + r.stderr
