"""Lane runtime: pipeline views, the planted control, the detached sweep (forced kill and
resume) and crosser replay -- on a toy lane small enough for CI."""

from __future__ import annotations

import itertools
import json
import os
import signal
import time
from pathlib import Path

import numpy as np
import pytest
import yaml

from runeforge.lanes import load_lane
from runeforge.ledger import Ledger
from runeforge.runner import control, crosser, jobs, pipeline, sweep
from runeforge.scoring import calib, presets

N_SEEDS = 30_000


def _lane(tmp_path: Path, **over) -> Path:
    bar = calib.threshold_for(N_SEEDS, "lp-ngram3-heldout:rigid", 240).bar
    spec = {
        "lane_id": "TOY-PCG64",
        "hypothesis": "toy: the first two pages are numpy-pcg64 keystreams (CI fixture only)",
        "family": "prng",
        "category": "instrument",
        "generator": "numpy-pcg64",
        "seed_range": [0, N_SEEDS],
        "chunk_size": 5_000,
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
    spec.update(over)
    path = tmp_path / f"{spec['lane_id']}.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return path


@pytest.mark.parametrize("name", ["raw", "atbash", "first-difference", "chain-increment"])
def test_views_invert(name):
    c = np.random.default_rng(1).integers(0, 29, 500)
    assert np.array_equal(pipeline.view(pipeline.unview(c, name), name), c)
    assert np.array_equal(pipeline.unview(pipeline.view(c, name), name), c)


@pytest.mark.parametrize("combine", ["vigenere", "variant-beaufort", "beaufort"])
def test_encrypt_then_rigid_decrypt(tmp_path, combine):
    lane = load_lane(_lane(tmp_path, combine=combine))
    p = np.random.default_rng(2).integers(0, 29, 300)
    k = pipeline.keys(lane, 42, 600)
    c, used = pipeline.encrypt(lane, p, k, np.random.default_rng(0))
    assert used == 300
    assert np.array_equal(pipeline.decrypt(lane, c, k[:300]), p)


def test_anti_repeat_filter_suppresses_doublets(tmp_path):
    lane = load_lane(_lane(tmp_path, filter_model="anti-repeat", p_keep=0.17))
    p = np.random.default_rng(3).integers(0, 29, 6000)
    c, used = pipeline.encrypt(lane, p, pipeline.keys(lane, 7, 20_000), np.random.default_rng(0))
    rate = float((c[1:] == c[:-1]).mean())
    assert 0.003 < rate < 0.012  # LP2: 0.66 %; unfiltered: 3.4 %
    assert used > 6000  # skips consumed extra key symbols


def test_control_passes_on_a_recoverable_lane(tmp_path):
    rep = control.run_control(load_lane(_lane(tmp_path)))
    assert rep.status == "passed", rep.reasons
    assert rep.identified == rep.n_plants == 20
    assert rep.gap_nats > 0.25 and rep.floor > rep.bar
    assert "recovered 20/20 at rank 1" in rep.summary()


def test_control_is_inconclusive_when_the_decoder_cannot_follow_the_filter(tmp_path):
    """The rigid decoder cannot follow anti-repeat key skips (the Phase 2 beam can); the
    control must say so instead of letting a filter lane report a negative."""
    rep = control.run_control(load_lane(_lane(tmp_path, filter_model="anti-repeat")))
    assert rep.status == "failed"
    assert rep.verdict_if_failed == "INCONCLUSIVE (power)"


def test_control_refuses_plants_from_the_training_data(tmp_path):
    lane = load_lane(
        _lane(tmp_path, control={"planted_seed": 1, "synthetic_page": "solved:welcome"})
    )
    with pytest.raises(ValueError, match="training data"):
        control.run_control(lane)


def test_sweep_preflight_refusals(tmp_path):
    led = tmp_path / "ledger.jsonl"
    lane = load_lane(_lane(tmp_path))
    probs = sweep.preflight(lane, led, smoke=False, base=tmp_path / "runs")
    assert any("no ledger row" in p for p in probs)
    Ledger(led).new(lane.lane_id, lane.hypothesis, lane.family)
    probs = sweep.preflight(lane, led, smoke=False, base=tmp_path / "runs")
    assert any("Rule 2" in p for p in probs)
    Ledger(led).update(lane.lane_id, positive_control="passed")
    assert sweep.preflight(lane, led, smoke=False, base=tmp_path / "runs") == []
    uncal = load_lane(_lane(tmp_path, claim_bar=None, family_wise_bar=None))
    assert any("calibrated" in p for p in sweep.preflight(uncal, led, True, tmp_path / "runs"))


def _rows(rd: Path) -> list[dict]:
    return [json.loads(x) for x in (rd / "sweep.jsonl").read_text().splitlines() if x.strip()]


def test_detached_sweep_survives_a_forced_kill_and_resumes_exactly(tmp_path):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path)
    lane = load_lane(lane_path)
    rd = base / lane.lane_id
    assert sweep.launch_detached(lane_path, smoke=True, base=base) == 0
    pid = int((rd / "sweep.pid").read_text())
    assert jobs.pid_alive_runeforge(pid)
    # wait for at least one checkpointed chunk, then SIGKILL (no chance to clean up)
    t0 = time.time()
    while time.time() - t0 < 120:
        st = json.loads((rd / "status.json").read_text()) if (rd / "status.json").exists() else {}
        if st.get("cursor", 0) >= 5_000 or st.get("done"):
            break
        time.sleep(0.2)
    os.kill(pid, signal.SIGKILL)
    for _ in range(50):
        if not jobs.pid_alive_runeforge(pid):
            break
        time.sleep(0.1)
    assert not jobs.pid_alive_runeforge(pid)
    st = json.loads((rd / "status.json").read_text())
    killed_at = st["cursor"]
    assert 5_000 <= killed_at <= N_SEEDS
    # resume in the foreground to completion
    assert sweep.run(lane_path, resume=True, smoke=True, base=base) == 0
    st = json.loads((rd / "status.json").read_text())
    assert st["done"] is True and st["cursor"] == N_SEEDS
    ckpt = json.loads((rd / "checkpoint.json").read_text())
    assert ckpt["seeds_done"] == N_SEEDS  # no gap, no double count
    chunks = [r for r in _rows(rd) if r["type"] == "chunk"]
    spans = sorted((c["lo"], c["hi"]) for c in chunks)
    assert spans[0][0] == 0 and spans[-1][1] == N_SEEDS
    assert all(a[1] == b[0] for a, b in itertools.pairwise(spans))
    assert all("reproduce" in r for r in _rows(rd))
    # the best score equals a direct recomputation
    scorer = presets.get("lp-ngram3-heldout")
    cipher = pipeline.lane_cipher(lane)[:240]
    best_seed = st["best_seed"]
    direct = scorer.score(pipeline.decrypt(lane, cipher, pipeline.keys(lane, best_seed, 240)))
    assert direct == pytest.approx(st["best_score"], abs=1e-9)


def test_crossers_are_flagged_and_replay_with_parity(tmp_path):
    """Set the bar just under the 3rd-best score so exactly three crossers appear."""
    base = tmp_path / "runs"
    lane0 = load_lane(_lane(tmp_path))
    cipher = pipeline.lane_cipher(lane0)[:240]
    seeds = np.arange(0, 3000)
    scores = presets.get("lp-ngram3-heldout").score_batch(
        pipeline.decrypt(lane0, cipher[None, :], pipeline.keys_batch(lane0, seeds, 240))
    )
    third = float(np.sort(scores)[-3])
    lane_path = _lane(
        tmp_path,
        lane_id="TOY-CROSS",
        seed_range=[0, 3000],
        claim_bar=third - 1e-9,
        family_wise_bar=third - 1e-9,
    )
    assert sweep.run(lane_path, resume=False, smoke=True, base=base) == 0
    pend = sorted((base / "TOY-CROSS" / "crossers").glob("*.pending"))
    assert len(pend) == 3
    kid = pend[0].stem
    rec = json.loads(pend[0].read_text())
    assert rec["status"] == "FLAGGED-FOR-ORACLE" and rec["numbering"] == "LP2-0-57"
    assert crosser.replay(kid, base=base)["verdict"] == "PARITY-OK"
    assert crosser.reencipher(kid, base=base)["verdict"] == "passes step 6"
    esc = crosser.escalate(kid, base=base, n_null=300)
    assert [r["length"] for r in esc["rows"]][:2] == [240, 480]
    assert esc["verdict"] == "NOISE-CROSSER"  # a wrong key regresses toward the null
    md = pend[0].with_suffix(".md").read_text()
    assert "PARITY-OK" in md and "reproduce" in md


def test_no_resume_archives_the_previous_run(tmp_path):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path, lane_id="TOY-RERUN", seed_range=[0, 6000], chunk_size=3000)
    assert sweep.run(lane_path, resume=True, smoke=True, base=base) == 0
    rd = base / "TOY-RERUN"
    first = _rows(rd)
    assert sweep.run(lane_path, resume=False, smoke=True, base=base) == 0
    prev = sorted(rd.glob("previous-*"))
    assert len(prev) == 1 and (prev[0] / "sweep.jsonl").exists()
    assert _rows(prev[0]) == first
    spans = [(r["lo"], r["hi"]) for r in _rows(rd) if r["type"] == "chunk"]
    assert spans == [(0, 3000), (3000, 6000)]  # one contiguous run, no rows from the first


def test_detached_launch_passes_max_seeds_and_an_absolute_lane_path(tmp_path, monkeypatch):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path, lane_id="TOY-DETACH-CAP")
    monkeypatch.chdir(tmp_path)  # a relative path must still resolve in the child
    assert sweep.launch_detached(Path(lane_path.name), smoke=True, base=base, max_seeds=4096) == 0
    rd = base / "TOY-DETACH-CAP"
    pid = int((rd / "sweep.pid").read_text())
    t0 = time.time()
    while time.time() - t0 < 120 and jobs.pid_alive_runeforge(pid):
        time.sleep(0.2)
    st = json.loads((rd / "status.json").read_text())
    assert st["done"] is True and st["seed_range"] == [0, 4096] and st["cursor"] == 4096


def test_status_heartbeats_inside_a_long_chunk(tmp_path, monkeypatch):
    """overnight.sh kills a live job whose status.json is older than STALE_MIN; a healthy
    sweep with one long chunk must keep it fresh. ``cursor`` stays the resume point."""
    monkeypatch.setattr(sweep, "HEARTBEAT_S", 0)
    writes = []
    real = sweep._atomic_json

    def spy(path, data):
        if path.name == "status.json":
            writes.append(dict(data))
        real(path, data)

    monkeypatch.setattr(sweep, "_atomic_json", spy)
    lane_path = _lane(tmp_path, lane_id="TOY-BEAT", seed_range=[0, 20_000], chunk_size=20_000)
    assert sweep.run(lane_path, smoke=True, base=tmp_path / "runs") == 0
    inside = [w for w in writes if w["cursor"] == 0 and w["scoring_at"] > 0]
    assert inside, "no heartbeat inside the chunk"
    assert writes[-1]["done"] and writes[-1]["cursor"] == writes[-1]["scoring_at"] == 20_000
