"""Lane runtime: pipeline views, the planted control, the detached sweep (forced kill and
resume, refusals, pins, Q5, budgets, the PID contract overnight.sh relies on) and crosser
replay -- on a toy lane small enough for CI."""

from __future__ import annotations

import fcntl
import itertools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest
import yaml

from runeforge.lanes import load_lane
from runeforge.ledger import Ledger
from runeforge.paths import REPO_ROOT
from runeforge.runner import control, crosser, gate, jobs, pipeline, sweep
from runeforge.scoring import calib, presets
from runeforge.stats.decode import decode_stats

N_SEEDS = 30_000
needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="overnight.sh needs jq")
STATS = {"ioc_n", "min_distinct_32", "order2_entropy", "zlib_ratio", "best_non_english"}


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


def _scores(lane, n: int, lo: int = 0) -> np.ndarray:
    """Scores of seeds lo .. lo + n - 1 (Python ints: seeds may exceed int64)."""
    cipher = pipeline.lane_cipher(lane)[: lane.window]
    seeds = list(range(lo, lo + n))
    keys = pipeline.keys_batch(lane, seeds, cipher.size)
    return pipeline.score_batch(
        presets.get("lp-ngram3-heldout"), pipeline.decrypt(lane, cipher[None, :], keys)
    )


def _rows(rd: Path) -> list[dict]:
    return [json.loads(x) for x in (rd / "sweep.jsonl").read_text().splitlines() if x.strip()]


def _status(rd: Path) -> dict:
    return json.loads((rd / "status.json").read_text())


def _ckpt(rd: Path) -> dict:
    return json.loads((rd / "checkpoint.json").read_text())


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


# ---------------------------------------------------------------- preflight: Rules 2 and 3


def _passed_control(tmp_path: Path, lane, lanes: Path) -> dict:
    rep = control.run_control(lane)
    assert rep.status == "passed", rep.reasons
    return control.write_report(rep, lane, tmp_path / "control-runs" / lane.lane_id, lanes)


def _gate(lane, lanes: Path, verdict: str = "GATE PASS", n_keys: int = 12) -> Path:
    """lanes/<id>/gate.json as `runeforge gate` writes it (gate.write_report)."""
    res = types.SimpleNamespace(
        verdict_line=verdict, per_seed_rows=[[] for _ in range(n_keys)], fails_per_constraint={}
    )
    return gate.write_report(lane, res, lanes.parent / "gate-runs" / lane.lane_id, lanes)


def test_sweep_preflight_refusals(tmp_path):
    led, lanes, base = tmp_path / "ledger.jsonl", tmp_path / "lanes", tmp_path / "runs"
    lane = load_lane(_lane(tmp_path))

    def probs(lane=lane, led=led):
        return sweep.preflight(lane, led, smoke=False, base=base, lanes_dir=lanes)

    assert any("no ledger row" in p for p in probs())
    Ledger(led).new(lane.lane_id, lane.hypothesis, lane.family)
    assert any("Rule 2" in p for p in probs())
    # the ledger string is not evidence: the cited control.json must exist and match
    fake = {"path": f"lanes/{lane.lane_id}/control-000000000000.json", "sha256": "0" * 64}
    Ledger(led).update(lane.lane_id, positive_control="passed", control_detail=fake)
    assert any("Rule 2: no" in p and "control.json" in p for p in probs())
    detail = _passed_control(tmp_path, lane, lanes)
    assert any("does not cite" in p for p in probs())
    Ledger(led).update(lane.lane_id, control_detail=detail)
    p = probs()
    assert not any("Rule 2" in x for x in p)
    assert any("Rule 3" in x and "not fixed in advance" in x for x in p)
    # a lane edited after its control ran has no control
    edited = load_lane(_lane(tmp_path, window=241))
    assert any("lane spec changed" in x for x in probs(lane=edited))
    # the PREREG threshold must be the bar the sweep flags crossers at
    led2 = tmp_path / "ledger2.jsonl"
    Ledger(led2).new(
        lane.lane_id,
        lane.hypothesis,
        lane.family,
        positive_control="passed",
        control_detail=detail,
        threshold=lane.family_wise_bar + 0.5,
        threshold_fixed_in_advance=True,
    )
    assert any("Rule 3" in x and "family_wise_bar" in x for x in probs(led=led2))
    Ledger(led).update(
        lane.lane_id, threshold=lane.family_wise_bar, threshold_fixed_in_advance=True
    )
    # the fingerprint gate: present, passed, >= 12 keys, on this lane spec
    assert probs() == [
        f"no gate.json for {lane.lane_id} (lanes/<id>/ or runs/<id>/): run `runeforge gate`"
    ]
    _gate(lane, lanes, verdict="GATE FAIL: C3 doublets")
    assert any("the gate did not pass" in x for x in probs())
    _gate(lane, lanes, n_keys=8)
    assert any("8 keys, fewer than 12" in x for x in probs())
    _gate(edited, lanes)  # same lane id, another spec
    assert any("since its gate ran" in x for x in probs())
    _gate(lane, lanes)
    assert probs() == []
    # concluded ground is not re-run
    Ledger(led).update(lane.lane_id, status="inconclusive", verdict="INCONCLUSIVE (power)")
    assert any("concluded ground" in x for x in probs())
    uncal = load_lane(_lane(tmp_path, claim_bar=None, family_wise_bar=None))
    assert any("calibrated" in p for p in sweep.preflight(uncal, led, True, base))


def test_a_real_run_needs_the_cited_control_and_writes_rescoring_reproduce_lines(tmp_path, capsys):
    base, led, lanes = tmp_path / "runs", tmp_path / "ledger.jsonl", tmp_path / "lanes"
    lane_path = _lane(tmp_path, lane_id="TOY-REAL")
    lane = load_lane(lane_path)
    rd = base / "TOY-REAL"
    fake = {"path": "lanes/TOY-REAL/control-000000000000.json", "sha256": "0" * 64}
    Ledger(led).new(
        lane.lane_id,
        lane.hypothesis,
        lane.family,
        positive_control="passed",
        control_detail=fake,
        threshold=lane.family_wise_bar,
        threshold_fixed_in_advance=True,
    )
    _gate(lane, lanes)
    assert sweep.run(lane_path, ledger_path=led, base=base, lanes_dir=lanes) == 2
    assert "Rule 2" in capsys.readouterr().err
    assert not (rd / "checkpoint.json").exists() and not (rd / "sweep.pid").exists()
    Ledger(led).update(lane.lane_id, control_detail=_passed_control(tmp_path, lane, lanes))
    assert sweep.run(lane_path, ledger_path=led, base=base, lanes_dir=lanes, max_seeds=10_000) == 0
    st, ck, rows = _status(rd), _ckpt(rd), _rows(rd)
    assert st["smoke"] is False and ck["smoke"] is False
    assert all(r["smoke"] is False for r in rows)
    assert st["done"] and st["seed_range"] == [0, 10_000]
    ref = str(lane_path.resolve())  # a lane outside the repo is named by its absolute path
    chunks = [r for r in rows if r["type"] == "chunk"]
    assert [c["reproduce"] for c in chunks] == [
        f"runeforge score {ref} 0:5000",
        f"runeforge score {ref} 5000:10000",
    ]
    # each chunk carries the language-agnostic stats of its own best decode
    for c in chunks:
        assert set(c["stats"]) == STATS and c["lo"] <= c["chunk_best_seed"] < c["hi"]
    assert max(c["chunk_best_score"] for c in chunks) == pytest.approx(st["best_score"])
    for r in rows:
        if r["type"] in ("survivor", "crosser"):
            assert r["reproduce"] == f"runeforge score {ref} {r['seed']}"
    assert rows[-1]["type"] == "done"
    assert (
        rows[-1]["reproduce"] == f"runeforge sweep {ref} --resume --max-seeds 10000 --ledger {led}"
    )


# ---------------------------------------------------------------- smoke


def test_smoke_is_refused_into_the_repository_runs_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(sweep.SMOKE_OK_ENV, raising=False)
    lane_path = _lane(tmp_path, lane_id="TOY-SMOKE-GUARD")
    lane = load_lane(lane_path)
    repo_runs = REPO_ROOT / "runs"
    existed = repo_runs.exists()
    assert any("--smoke" in p for p in sweep.preflight(lane, None, True, repo_runs))
    assert sweep.run(lane_path, smoke=True, base=repo_runs) == 2
    assert sweep.launch_detached(lane_path, smoke=True, base=repo_runs) == 2
    assert "--smoke" in capsys.readouterr().err
    assert not (repo_runs / "TOY-SMOKE-GUARD").exists() and repo_runs.exists() == existed
    monkeypatch.setenv(sweep.SMOKE_OK_ENV, "1")  # test harnesses only
    assert not any("--smoke" in p for p in sweep.preflight(lane, None, True, repo_runs))
    # and `runeforge sweep` never exposes it
    from runeforge import cli

    with pytest.raises(SystemExit):
        cli.main(["sweep", str(lane_path), "--smoke"])


# ---------------------------------------------------------------- detached runs


def test_detached_sweep_survives_a_forced_kill_and_resumes_exactly(tmp_path):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path)
    lane = load_lane(lane_path)
    rd = base / lane.lane_id
    assert sweep.launch_detached(lane_path, smoke=True, base=base) == 0
    st = _status(rd)  # the launcher returns once the child wrote it
    pid = st["pid"]
    assert jobs.pid_alive_runeforge(pid, st) or st["done"]
    # wait for at least one checkpointed chunk, then SIGKILL (no chance to clean up)
    t0 = time.time()
    while time.time() - t0 < 120:
        st = _status(rd)
        if st.get("cursor", 0) >= 5_000 or st.get("done"):
            break
        time.sleep(0.02)
    os.kill(pid, signal.SIGKILL)
    for _ in range(50):
        if not jobs.pid_alive_runeforge(pid):
            break
        time.sleep(0.1)
    assert not jobs.pid_alive_runeforge(pid)
    st = _status(rd)
    killed_at = st["cursor"]
    assert 5_000 <= killed_at <= N_SEEDS
    # resume in the foreground to completion
    assert sweep.run(lane_path, resume=True, smoke=True, base=base) == 0
    st = _status(rd)
    assert st["done"] is True and st["cursor"] == N_SEEDS
    ckpt = _ckpt(rd)
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


def test_crossers_are_flagged_replayed_escalated_and_filed(tmp_path, monkeypatch):
    """Set the bar just under the 3rd-best score so exactly three crossers appear. A smoke
    run marks every output it writes."""
    base = tmp_path / "runs"
    third = float(np.sort(_scores(load_lane(_lane(tmp_path)), 3000))[-3])
    lane_path = _lane(
        tmp_path,
        lane_id="TOY-CROSS",
        seed_range=[0, 3000],
        claim_bar=third - 1e-9,
        family_wise_bar=third - 1e-9,
    )
    assert sweep.run(lane_path, resume=False, smoke=True, base=base) == 0
    rd = base / "TOY-CROSS"
    pend = sorted((rd / "crossers").glob("*.pending"))
    assert len(pend) == 3
    kid = pend[0].stem
    rec = json.loads(pend[0].read_text())
    assert rec["status"] == "FLAGGED-FOR-ORACLE" and rec["numbering"] == "LP2-0-57"
    assert all(json.loads(p.read_text())["smoke"] is True for p in pend)
    assert _status(rd)["smoke"] is True and _ckpt(rd)["smoke"] is True
    rows = _rows(rd)
    assert rows and all(r["smoke"] is True for r in rows)
    ref = str(lane_path.resolve())
    hits = [r for r in rows if r["type"] == "crosser"]
    assert sorted(r["seed"] for r in hits) == sorted(
        json.loads(p.read_text())["seed"] for p in pend
    )
    assert all(r["reproduce"] == f"runeforge score {ref} {r['seed']}" for r in hits)
    assert rows[-1]["reproduce"] == f"python -m runeforge.runner.sweep run {ref} --smoke"
    # per-decode stats on every crosser row and .pending file; the stats are of the window
    lane = load_lane(lane_path)
    window = pipeline.decrypt(
        lane, pipeline.lane_cipher(lane)[:240], pipeline.keys(lane, rec["seed"], 240)
    )
    assert rec["stats"] == json.loads(json.dumps(decode_stats(window)))
    assert all(set(r["stats"]) == STATS for r in hits)
    assert rec["lane_path"] == ref  # outside the repo: absolute; inside: repo-relative
    monkeypatch.chdir(tmp_path)  # crosser steps work from any cwd
    assert crosser.replay(kid, base=base)["verdict"] == "PARITY-OK"
    # step 6 cannot fail under the rigid decoder: it says so instead of "passes"
    re6 = crosser.reencipher(kid, base=base)
    assert re6["verdict"] == "NOT-INFORMATIVE (rigid decoder)" and crosser.exit_code(re6) == 0
    esc = crosser.escalate(kid, base=base, n_null=300)
    # window, end of page 0 (262 runes), 2x window, then the full LP2 0-55 stream
    assert [r["length"] for r in esc["rows"]] == [240, 262, 480, 12_956]
    assert [r["step"] for r in esc["rows"]] == ["window", "page", "2x window", "full stream"]
    assert esc["pages"] == list(range(56))
    assert esc["rows"][0]["score"] == pytest.approx(rec["score"], abs=1e-9)  # same key, no re-sync
    assert esc["verdict"] == "NOISE-CROSSER"  # a wrong key regresses toward the null
    assert crosser.exit_code(esc) == 1
    # adjudicated: renamed, status recorded inside, no longer listed as pending
    done = rd / "crossers" / f"{kid}.noise-crosser"
    assert not pend[0].exists() and json.loads(done.read_text())["status"] == "NOISE-CROSSER"
    assert crosser.pending_list(base=base) == pend[1:]
    assert crosser.resolved_list(base=base) == [done] and crosser.find(kid, base=base) == done
    md = pend[0].with_suffix(".md").read_text()
    assert "PARITY-OK" in md and "NOT-INFORMATIVE" in md and "noise-crosser" in md
    # PARITY-FAIL is filed the same way
    other = json.loads(pend[1].read_text())
    pend[1].write_text(json.dumps({**other, "score": other["score"] + 0.5}))
    assert crosser.replay(pend[1].stem, base=base)["verdict"] == "PARITY-FAIL"
    assert pend[1].with_suffix(".parity-fail").exists() and not pend[1].exists()
    # the sweep never re-opens an adjudicated crosser
    assert sweep.run(lane_path, resume=False, smoke=True, base=base) == 0
    assert sorted((rd / "crossers").glob("*.pending")) == [pend[2]]


def test_no_resume_archives_the_previous_run_but_keeps_its_crossers(tmp_path):
    base = tmp_path / "runs"
    third = float(np.sort(_scores(load_lane(_lane(tmp_path)), 6000))[-3])
    lane_path = _lane(
        tmp_path,
        lane_id="TOY-RERUN",
        seed_range=[0, 6000],
        chunk_size=3000,
        claim_bar=third - 1e-9,
        family_wise_bar=third - 1e-9,
    )
    assert sweep.run(lane_path, resume=True, smoke=True, base=base) == 0
    rd = base / "TOY-RERUN"
    first = _rows(rd)
    pend = {p.name: p.read_text() for p in (rd / "crossers").glob("*.pending")}
    assert len(pend) == 3
    assert sweep.run(lane_path, resume=False, smoke=True, base=base) == 0
    prev = sorted(rd.glob("previous-*"))
    assert len(prev) == 1
    assert sorted(p.name for p in prev[0].iterdir()) == [
        "checkpoint.json",
        "status.json",
        "sweep.jsonl",
    ]
    assert _rows(prev[0]) == first
    # the HIT_PROTOCOL work items stay where they were, untouched
    assert {p.name: p.read_text() for p in (rd / "crossers").glob("*.pending")} == pend
    spans = [(r["lo"], r["hi"]) for r in _rows(rd) if r["type"] == "chunk"]
    assert spans == [(0, 3000), (3000, 6000)]  # one contiguous run, no rows from the first
    # crossers an older runner moved into previous-*/crossers/ stay findable
    old = rd / "previous-20260101T000000-1" / "crossers"
    old.mkdir(parents=True)
    kid = "TOY-RERUN-999999"
    (old / f"{kid}.pending").write_text(next(iter(pend.values())))
    assert crosser.find(kid, base=base) == old / f"{kid}.pending"
    live = sorted((rd / "crossers").glob("*.pending"))
    assert crosser.pending_list(base=base) == [*live, old / f"{kid}.pending"]


def test_escalation_stream_lengths_and_an_incomplete_escalation(tmp_path):
    lane = load_lane(_lane(tmp_path, pages=[3, 7]))
    assert crosser.escalation_pages(lane) == [3, 7, 4, 5, 6, *range(8, 56)]
    # window 240 inside page sizes 262, 266: page step = 262; dedupe; cap at the stream
    assert crosser.escalation_lengths(240, [262, 266], 528) == {
        240: ["window"],
        262: ["page"],
        480: ["2x window"],
        528: ["full stream"],
    }
    assert crosser.escalation_lengths(76, [76], 76) == {
        76: ["window", "2x window", "page", "full stream"]
    }
    # a lane on the last page with a window of the whole page has nothing to escalate to
    base = tmp_path / "runs"
    last = _lane(tmp_path, lane_id="TOY-LAST", pages=[55], window=76)
    pend = base / "TOY-LAST" / "crossers" / "TOY-LAST-7.pending"
    pend.parent.mkdir(parents=True)
    rec = {
        "kid": "TOY-LAST-7",
        "status": "FLAGGED-FOR-ORACLE",
        "lane_path": str(last),
        "seed": 7,
        "score": 0.0,
        "window": 76,
        "preset": "lp-ngram3-heldout:rigid",
    }
    pend.write_text(json.dumps(rec))
    esc = crosser.escalate("TOY-LAST-7", base=base, n_null=50)
    assert esc["verdict"] == "INCOMPLETE" and crosser.exit_code(esc) == 1
    assert [r["length"] for r in esc["rows"]] == [76]
    assert pend.exists()  # INCOMPLETE adjudicates nothing
    assert "INCOMPLETE" in pend.with_suffix(".md").read_text()


def test_forward_reencipher_replays_a_decoders_skip_and_interrupt_record(tmp_path):
    """The mechanics a skip-aware decoder's step 6 will use (the rigid decoder's is
    NOT-INFORMATIVE)."""
    p = np.random.default_rng(5).integers(0, 29, 400)
    interrupts = np.flatnonzero(p == pipeline.F).tolist()  # every plaintext F, at prob 1
    assert interrupts
    for view in ("raw", "first-difference", "chain-increment"):
        lane = load_lane(_lane(tmp_path, interrupt_prob=1.0, ciphertext_view=view))
        k = pipeline.keys(lane, 11, 800)
        forward, _ = pipeline.encrypt(lane, p, k, np.random.default_rng(0))
        assert np.array_equal(crosser.reencipher_forward(lane, p, k, interrupts), forward), view
    lane = load_lane(_lane(tmp_path))
    # a filter skip: the kept rune used the key symbol after the skipped one
    p4, k4 = np.array([0, 3, 0, 7]), np.array([5, 9, 13, 17, 21])
    out = crosser.reencipher_forward(lane, p4, k4, interrupts=[0], skips={"3": 1})
    assert out.tolist() == [0, (3 + 5) % 29, (0 + 9) % 29, (7 + 17) % 29]


def test_lane_paths_are_repo_relative_inside_the_repo():
    inside = REPO_ROOT / "lanes" / "B04-EXAMPLE.yaml"
    assert sweep._lane_ref(inside) == "lanes/B04-EXAMPLE.yaml"
    assert crosser.lane_file({"lane_path": "lanes/B04-EXAMPLE.yaml"}) == inside
    outside = Path("/srv/elsewhere/L.yaml")
    assert sweep._lane_ref(outside) == str(outside)
    assert crosser.lane_file({"lane_path": str(outside)}) == outside


def test_detached_launch_passes_max_seeds_and_an_absolute_lane_path(tmp_path, monkeypatch):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path, lane_id="TOY-DETACH-CAP")
    monkeypatch.chdir(tmp_path)  # a relative path must still resolve in the child
    assert sweep.launch_detached(Path(lane_path.name), smoke=True, base=base, max_seeds=4096) == 0
    rd = base / "TOY-DETACH-CAP"
    pid = _status(rd)["pid"]
    t0 = time.time()
    while time.time() - t0 < 120 and jobs.pid_alive_runeforge(pid):
        time.sleep(0.05)
    st = _status(rd)
    assert st["done"] is True and st["seed_range"] == [0, 4096] and st["cursor"] == 4096
    assert not (rd / "sweep.pid").exists()  # the runner removed its own PID file


def test_detached_launch_reports_a_child_that_refuses(tmp_path, capsys):
    """The launcher's own preflight cannot see a checkpoint pin; the child refuses, and the
    launcher must say so instead of reporting a launch."""
    base = tmp_path / "runs"
    spec = {"lane_id": "TOY-CHILD-NO", "seed_range": [0, 6000], "chunk_size": 3000}
    lane_path = _lane(tmp_path, **spec)
    claim = load_lane(lane_path).claim_bar
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=3000) == 0
    _lane(tmp_path, **spec, claim_bar=claim - 0.01)  # the screening bar moved after the start
    capsys.readouterr()
    assert sweep.launch_detached(lane_path, smoke=True, base=base) == 2
    err = capsys.readouterr().err
    assert "exited with 2" in err and "checkpoint.json pins claim_bar" in err
    assert _ckpt(base / "TOY-CHILD-NO")["cursor"] == 3000


def _sweep_child(lane_path: Path, base: Path, *extra: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "runeforge.runner.sweep", "run", str(lane_path), "--smoke", *extra],
        cwd=REPO_ROOT,
        env={**os.environ, "RUNEFORGE_RUNS": str(base)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _holds_open(pid: int, path: Path) -> bool:
    try:
        fds = list(Path(f"/proc/{pid}/fd").iterdir())
    except OSError:
        return False
    for fd in fds:
        try:
            if Path(os.readlink(fd)) == path:
                return True
        except OSError:
            continue
    return False


def test_two_launches_cannot_both_pass_the_preflight(tmp_path):
    """The child's preflight, PID write and first status.json happen under an exclusive
    flock on <runs>/.sweep.lock: while it is held nothing is written; once released, one
    child runs and the other sees it alive and refuses."""
    base = tmp_path / "runs"
    base.mkdir()
    lock = base / ".sweep.lock"
    lanes = [
        _lane(tmp_path, lane_id=f"TOY-LOCK-{i}", seed_range=[0, 5_000_000], chunk_size=4096)
        for i in (1, 2)
    ]
    with open(lock, "a+b") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        procs = [_sweep_child(p, base) for p in lanes]
        t0 = time.time()
        while not all(_holds_open(p.pid, lock) for p in procs):
            assert time.time() - t0 < 30 and all(p.poll() is None for p in procs)
            time.sleep(0.02)
        time.sleep(0.3)
        assert all(p.poll() is None for p in procs)  # both wait at the lock
        assert not list(base.glob("*/sweep.pid")) and not list(base.glob("*/status.json"))
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    try:
        t0 = time.time()
        while all(p.poll() is None for p in procs):
            assert time.time() - t0 < 60
            time.sleep(0.02)
        loser = next(p for p in procs if p.poll() is not None)
        winner = next(p for p in procs if p is not loser)
        assert loser.returncode == 2
        assert "another sweep is alive" in loser.stdout.read()
        assert winner.poll() is None
        name = Path(winner.args[4]).stem
        st = _status(base / name)
        assert st["pid"] == winner.pid and jobs.pid_alive_runeforge(winner.pid, st)
        assert jobs.live_sweeps(base) == [(name, winner.pid)]
    finally:
        for p in procs:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
    assert winner.wait(timeout=60) == 143
    assert not (base / name / "sweep.pid").exists()


# ---------------------------------------------------------------- pins, Q5, budgets


def test_resume_refuses_a_checkpoint_whose_bars_or_pipeline_changed(tmp_path, capsys):
    base = tmp_path / "runs"
    spec = {"lane_id": "TOY-PIN", "seed_range": [0, 6000], "chunk_size": 3000}
    lane_path = _lane(tmp_path, **spec)
    lane = load_lane(lane_path)
    rd = base / "TOY-PIN"
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=3000) == 0
    ck = _ckpt(rd)
    assert ck["claim_bar"] == lane.claim_bar and ck["family_wise_bar"] == lane.family_wise_bar
    assert ck["lane_pipeline_sha256"] == control.lane_pipeline_sha256(lane)
    before = (rd / "checkpoint.json").read_text()
    _lane(tmp_path, **spec, family_wise_bar=lane.family_wise_bar + 0.1)
    capsys.readouterr()
    assert sweep.run(lane_path, smoke=True, base=base) == 2
    err = capsys.readouterr().err
    assert "family_wise_bar" in err and "lane_pipeline_sha256" in err and "--no-resume" in err
    assert (rd / "checkpoint.json").read_text() == before
    # a checkpoint that pins nothing (an older runner) is not trusted either
    _lane(tmp_path, **spec)
    old = {k: v for k, v in json.loads(before).items() if k not in sweep.PINNED}
    (rd / "checkpoint.json").write_text(json.dumps(old))
    assert sweep.run(lane_path, smoke=True, base=base) == 2
    assert "older runner" in capsys.readouterr().err
    # a smoke checkpoint is never resumed by a real run
    assert any("smoke run" in p for p in sweep.pin_problems(json.loads(before), lane, False))
    (rd / "checkpoint.json").write_text(before)
    assert sweep.run(lane_path, smoke=True, base=base) == 0
    assert _status(rd)["cursor"] == 6000


def test_q5_kill_is_remembered_on_resume_unless_overridden(tmp_path, capsys):
    base = tmp_path / "runs"
    third = float(np.sort(_scores(load_lane(_lane(tmp_path)), 3000))[-3])
    lane_path = _lane(
        tmp_path,
        lane_id="TOY-Q5",
        seed_range=[0, 6000],
        chunk_size=3000,
        claim_bar=third - 1e-9,
        family_wise_bar=third - 1e-9,
        kill_condition={"at_fraction": 0.1, "max_crossers": 0},
    )
    rd = base / "TOY-Q5"
    assert sweep.run(lane_path, smoke=True, base=base) == 3
    ck = _ckpt(rd)
    assert ck["kill_condition"] == "fired" and ck["cursor"] == 3000
    assert ck["kill_detail"]["crossers"] == 3 and ck["kill_detail"]["seeds_per_s"] > 0
    n_rows = len(_rows(rd))
    capsys.readouterr()
    # a plain resume does not forget it: nothing scored, status says fired, exit 3
    assert sweep.run(lane_path, smoke=True, base=base) == 3
    st = _status(rd)
    assert st["kill_condition"] == "fired" and st["cursor"] == 3000 and not st["done"]
    assert len(_rows(rd)) == n_rows
    assert "--override-q5" in capsys.readouterr().err
    assert not (rd / "sweep.pid").exists()  # removed after a stop that had written it
    assert sweep.run(lane_path, smoke=True, base=base, override_q5="  ") == 2
    # a human override is recorded and the sweep continues
    why = "Hunter 2026-10-22: three crossers are the toy bar, not the lane"
    assert sweep.run(lane_path, smoke=True, base=base, override_q5=why) == 0
    ov = [r for r in _rows(rd) if r["type"] == "override-q5"]
    assert len(ov) == 1 and ov[0]["reason"] == why and ov[0]["kill_detail"]["crossers"] == 3
    st, ck = _status(rd), _ckpt(rd)
    assert st["done"] and st["cursor"] == 6000 and st["kill_condition"] == "overridden"
    assert ck["kill_condition"] == "overridden" and ck["q5_overrides"][0]["reason"] == why


def test_wall_clock_budget_is_per_lane_not_per_launch(tmp_path):
    base = tmp_path / "runs"
    lane_path = _lane(
        tmp_path,
        lane_id="TOY-BUDGET",
        seed_range=[0, 9000],
        chunk_size=3000,
        budget={"wall_clock_hours": 1.0},
    )
    rd = base / "TOY-BUDGET"
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=3000) == 0
    ck = _ckpt(rd)
    assert 0 < ck["elapsed_s"] < 600
    # a later launch gets only what is left of the lane's hour
    ck["elapsed_s"] = 3000.0
    (rd / "checkpoint.json").write_text(json.dumps(ck))
    t0 = time.time()
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=6000) == 0
    st = _status(rd)
    assert t0 + 600 - 1 <= st["deadline_epoch"] <= time.time() + 600
    ck = _ckpt(rd)
    assert ck["elapsed_s"] >= 3000.0 and ck["cursor"] == 6000
    # nothing left: stop at once, score nothing
    ck["elapsed_s"] = 3600.0
    (rd / "checkpoint.json").write_text(json.dumps(ck))
    assert sweep.run(lane_path, smoke=True, base=base) == 1
    st = _status(rd)
    assert st["stopped_by"] == "deadline" and st["cursor"] == 6000 and not st["done"]
    last = _rows(rd)[-1]
    assert last["type"] == "stopped" and last["why"] == "deadline"


def test_max_seeds_respects_the_lane_budget(tmp_path, capsys):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path, lane_id="TOY-CAP", budget={"max_seeds": 4096})
    lane = load_lane(lane_path)
    rd = base / "TOY-CAP"
    assert any("budget.max_seeds" in p for p in sweep.preflight(lane, None, True, base, None, 5000))
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=5000) == 2
    assert "budget.max_seeds" in capsys.readouterr().err
    assert not (rd / "checkpoint.json").exists()
    assert sweep.seed_hi(lane, None) == 4096 and sweep.seed_hi(lane, 1000) == 1000
    assert sweep.run(lane_path, smoke=True, base=base) == 0
    st = _status(rd)
    assert st["seed_range"] == [0, 4096] and st["cursor"] == 4096 and st["done"]


# ---------------------------------------------------------------- PID contract


def _sweep_like(*tags: str) -> subprocess.Popen:
    """A sleeping process whose cmdline carries ``tags`` (Popen returns after exec)."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", *tags])


def _bash_fns(*names: str) -> str:
    src = (REPO_ROOT / "overnight.sh").read_text(encoding="utf-8")
    out = []
    for name in names:
        m = re.search(rf"^{name}\(\) \{{.*?^\}}", src, re.S | re.M)
        assert m, f"overnight.sh has no {name}()"
        out.append(m.group(0))
    return "\n".join(out)


def _bash_alive(pid: int, status: Path | str = "") -> bool:
    script = "set -uo pipefail\n" + _bash_fns("pid_is_runeforge") + '\npid_is_runeforge "$1" "$2"'
    return subprocess.run(["bash", "-c", script, "bash", str(pid), str(status)]).returncode == 0


@needs_jq
def test_a_job_is_alive_only_with_a_sweep_cmdline_and_its_recorded_start_time(tmp_path):
    procs = [
        _sweep_like("runeforge.runner.sweep"),
        _sweep_like("runeforge", "sweep"),
        _sweep_like("runeforge-notes"),
    ]
    gone = subprocess.Popen(["true"])
    gone.wait()
    try:
        module, cli, other = procs
        t = jobs.pid_starttime(module.pid)
        assert isinstance(t, int) and t > 0
        ok, recycled = tmp_path / "ok.json", tmp_path / "recycled.json"
        ok.write_text(json.dumps({"pid": module.pid, "pid_starttime": t}))
        recycled.write_text(json.dumps({"pid": module.pid, "pid_starttime": t + 1}))
        cases = [
            (module.pid, None, True),
            (cli.pid, None, True),
            (other.pid, None, False),  # the bare word "runeforge" is not a sweep
            (gone.pid, None, False),
            (module.pid, ok, True),
            (module.pid, recycled, False),  # same PID, another process start: not our job
        ]
        for pid, st, alive in cases:
            status = json.loads(st.read_text()) if st else None
            assert jobs.pid_alive_runeforge(pid, status) is alive, (pid, st)
            assert _bash_alive(pid, st or "") is alive, ("overnight.sh", pid, st)
        rd = tmp_path / "runs" / "L"
        rd.mkdir(parents=True)
        (rd / "sweep.pid").write_text(f"{module.pid}\n")
        assert jobs.live_sweeps(tmp_path / "runs") == [("L", module.pid)]
        shutil.copy(recycled, rd / "status.json")
        assert jobs.live_sweeps(tmp_path / "runs") == []
    finally:
        for p in procs:
            p.kill()
            p.wait()


@needs_jq
def test_overnight_watch_jobs_skips_finished_and_recycled_jobs(tmp_path):
    job = _sweep_like("runeforge.runner.sweep")
    try:
        rd = tmp_path / "runs" / "L"
        rd.mkdir(parents=True)
        (rd / "sweep.pid").write_text(f"{job.pid}\n")
        t = jobs.pid_starttime(job.pid)
        script = "\n".join(
            [
                "set -uo pipefail",
                "STALE_MIN=30",
                'log() { echo "LOG $*"; }',
                'kill_job() { echo "KILL $1 $2"; }',
                _bash_fns("pid_is_runeforge", "watch_jobs"),
                "watch_jobs",
            ]
        )

        def watch(**over) -> str:
            st = {"pid": job.pid, "pid_starttime": t, "updated_epoch": 0, "deadline_epoch": 0}
            st.update({"kill_condition": "no", "done": False, **over})
            (rd / "status.json").write_text(json.dumps(st))
            return subprocess.run(
                ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True
            ).stdout

        assert "KILL runs/L stale-status" in watch()
        assert "KILL" not in watch(done=True)  # finished: it is exiting on its own
        assert "KILL" not in watch(pid_starttime=t + 1)  # a recycled PID is not our job
        fired = watch(updated_epoch=int(time.time()), kill_condition="fired")
        assert "KILL runs/L q5-kill-condition" in fired
    finally:
        job.kill()
        job.wait()


def test_the_runner_records_its_start_time_and_removes_only_its_own_pid_file(tmp_path):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path, lane_id="TOY-PID", seed_range=[0, 3000], chunk_size=3000)
    rd = base / "TOY-PID"
    assert sweep.run(lane_path, smoke=True, base=base) == 0
    assert not (rd / "sweep.pid").exists()
    st = _status(rd)
    assert st["pid"] == os.getpid() and st["pid_starttime"] == jobs.pid_starttime(os.getpid())
    other = _sweep_like("runeforge.runner.sweep")
    try:
        (rd / "sweep.pid").write_text(f"{other.pid}\n")
        assert sweep.run(lane_path, smoke=True, base=base, resume=False) == 2
        assert (rd / "sweep.pid").read_text().strip() == str(other.pid)
    finally:
        other.kill()
        other.wait()


_SLOW_CHILD = """
import sys, time
from pathlib import Path
from runeforge.runner import pipeline, sweep
sweep.HEARTBEAT_S = 0
real = pipeline.score_batch
def slow(scorer, plains):
    time.sleep(0.25)
    return real(scorer, plains)
pipeline.score_batch = slow
sys.exit(sweep.run(Path(sys.argv[1]), smoke=True, base=Path(sys.argv[2])))
"""


def test_sigkill_mid_chunk_does_not_duplicate_survivor_or_crosser_rows(tmp_path):
    base = tmp_path / "runs"
    n = 20_000
    scores = _scores(load_lane(_lane(tmp_path)), n)
    claim = float(np.quantile(scores, 0.98))
    fw = float(np.sort(scores[:8192])[-3]) - 1e-9  # crossers inside the first two batches
    lane_path = _lane(
        tmp_path,
        lane_id="TOY-SIGKILL",
        seed_range=[0, n],
        chunk_size=n,
        claim_bar=claim,
        family_wise_bar=fw,
    )
    rd = base / "TOY-SIGKILL"
    proc = subprocess.Popen(
        [sys.executable, "-c", _SLOW_CHILD, str(lane_path), str(base)], cwd=REPO_ROOT
    )
    t0 = time.time()
    while True:
        st = _status(rd) if (rd / "status.json").exists() else {}
        if st.get("cursor") == 0 and st.get("scoring_at", 0) >= 3 * sweep.BATCH:
            break  # mid-chunk: three batches scored, nothing checkpointed
        assert proc.poll() is None and time.time() - t0 < 60
        time.sleep(0.01)
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait()
    assert len(list((rd / "crossers").glob("*.pending"))) >= 3  # written at the crossing
    assert sweep.run(lane_path, smoke=True, base=base) == 0
    rows = _rows(rd)
    seeds = [r["seed"] for r in rows if r["type"] in ("survivor", "crosser")]
    assert len(seeds) == len(set(seeds)) == int((scores > claim).sum())
    hits = sorted(r["seed"] for r in rows if r["type"] == "crosser")
    assert hits == sorted(np.flatnonzero(scores > fw).tolist())
    assert len(list((rd / "crossers").glob("*.pending"))) == len(hits)
    assert _ckpt(rd)["crossers"] == len(hits)


def test_seeds_above_int64_sweep_flag_and_replay(tmp_path):
    """numpy-pcg64 (like sha256-ctr and mt19937-py27 at 64 bits) takes seeds up to
    2**64 - 1; the sweep must not route them through int64."""
    lo = 2**63
    base = tmp_path / "runs"
    third = float(np.sort(_scores(load_lane(_lane(tmp_path)), 10_000, lo))[-3])
    lane_path = _lane(
        tmp_path,
        lane_id="TOY-HIGH",
        seed_range=[lo, lo + 10_000],
        claim_bar=third - 1e-9,
        family_wise_bar=third - 1e-9,
    )
    lane = load_lane(lane_path)
    rd = base / "TOY-HIGH"
    assert sweep.run(lane_path, smoke=True, base=base) == 0
    st, ck = _status(rd), _ckpt(rd)
    assert st["done"] and st["seed_range"] == [lo, lo + 10_000] and st["cursor"] == lo + 10_000
    assert ck["seeds_done"] == 10_000 and lo <= st["best_seed"] < lo + 10_000
    cipher = pipeline.lane_cipher(lane)[:240]
    best = presets.get("lp-ngram3-heldout").score(
        pipeline.decrypt(lane, cipher, pipeline.keys(lane, st["best_seed"], 240))
    )
    assert best == pytest.approx(st["best_score"], abs=1e-9)
    chunks = [r for r in _rows(rd) if r["type"] == "chunk"]
    assert [(c["lo"], c["hi"]) for c in chunks] == [(lo, lo + 5000), (lo + 5000, lo + 10_000)]
    hits = [r for r in _rows(rd) if r["type"] == "crosser"]
    pend = sorted((rd / "crossers").glob("*.pending"))
    assert len(hits) == len(pend) == 3 and all(r["seed"] >= lo for r in hits)
    rec = json.loads(pend[0].read_text())
    assert rec["seed"] >= lo and pend[0].stem == f"TOY-HIGH-{rec['seed']}"
    assert crosser.replay(pend[0].stem, base=base)["verdict"] == "PARITY-OK"


def test_killed_markers_move_to_history_when_a_relaunch_passes_preflight(tmp_path):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path, lane_id="TOY-KILLED", seed_range=[0, 3000], chunk_size=3000)
    rd = base / "TOY-KILLED"
    rd.mkdir(parents=True)
    (rd / "KILLED-stale-status").write_text("2026-10-22 03:00:00 stale-status\n")
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=0) == 2  # refused
    assert (rd / "KILLED-stale-status").exists()
    assert sweep.run(lane_path, smoke=True, base=base) == 0
    assert not list(rd.glob("KILLED-*"))
    hist = list((rd / "killed-history").iterdir())
    assert len(hist) == 1 and re.fullmatch(r"\d{8}T\d{6}-KILLED-stale-status", hist[0].name)
    assert "stale-status" in hist[0].read_text()


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
