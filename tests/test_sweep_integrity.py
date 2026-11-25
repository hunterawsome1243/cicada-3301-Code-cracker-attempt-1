"""The sweep's per-lane state across launches: the backend a checkpoint was written on, what
--no-resume carries over (budget, Q5), Q5 measured on the lane's slice rather than a launch's
--max-seeds cap, the Q5 check recorded whether or not it fires, and a crash that says so in
status.json. Toy lanes small enough for CI (smoke runs into tmp_path)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from runeforge.lanes import load_lane
from runeforge.runner import pipeline, sweep
from runeforge.scoring import calib, presets


def _lane(tmp_path: Path, **over) -> Path:
    bar = calib.threshold_for(30_000, "lp-ngram3-heldout:rigid", 240).bar
    spec = {
        "lane_id": "TOY-INTEGRITY",
        "hypothesis": "toy: the first two pages are numpy-pcg64 keystreams (CI fixture only)",
        "family": "prng",
        "category": "instrument",
        "generator": "numpy-pcg64",
        "seed_range": [0, 6000],
        "chunk_size": 1000,
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


def _scores(lane, n: int) -> np.ndarray:
    cipher = pipeline.lane_cipher(lane)[: lane.window]
    keys = pipeline.keys_batch(lane, list(range(n)), cipher.size)
    return pipeline.score_batch(
        presets.get("lp-ngram3-heldout"), pipeline.decrypt(lane, cipher[None, :], keys)
    )


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _rows(rd: Path) -> list[dict]:
    return [json.loads(x) for x in (rd / "sweep.jsonl").read_text().splitlines() if x.strip()]


def _crowded_lane(tmp_path: Path, **over) -> Path:
    """A lane whose Q5 (max_crossers 0) fires at its first check: three seeds cross."""
    third = float(np.sort(_scores(load_lane(_lane(tmp_path)), 6000))[-3])
    spec = {
        "claim_bar": third - 1e-9,
        "family_wise_bar": third - 1e-9,
        "kill_condition": {"at_fraction": 0.5, "max_crossers": 0},
    }
    spec.update(over)
    return _lane(tmp_path, **spec)


# ---------------------------------------------------------------- backend


def test_a_checkpoint_pins_its_backend_and_refuses_another(tmp_path, capsys):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path)
    lane = load_lane(lane_path)
    rd = base / lane.lane_id
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=2000) == 0
    ck = _json(rd / "checkpoint.json")
    assert ck["backend"] == "cpu" and sweep.pins(lane, True)["backend"] == "cpu"
    # a GPU-started checkpoint is never resumed on the CPU (the budget was set for the GPU)
    (rd / "checkpoint.json").write_text(json.dumps({**ck, "backend": "gpu"}))
    capsys.readouterr()
    assert sweep.run(lane_path, smoke=True, base=base) == 2
    err = capsys.readouterr().err
    assert "--backend gpu" in err and "PREREG addendum" in err
    assert "--no-resume" not in err  # a backend mismatch is not fixed by starting over
    assert _json(rd / "checkpoint.json")["cursor"] == 2000
    probs = sweep.pin_problems({**ck, "backend": "gpu"}, lane, True, "gpu")
    assert probs == []


def test_a_checkpoint_from_before_the_backend_pin_takes_status_jsons(tmp_path, capsys):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path)
    rd = base / load_lane(lane_path).lane_id
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=2000) == 0
    ck = _json(rd / "checkpoint.json")
    del ck["backend"]
    (rd / "checkpoint.json").write_text(json.dumps(ck))
    st = _json(rd / "status.json")
    (rd / "status.json").write_text(json.dumps({**st, "backend": "gpu"}))
    assert sweep.read_checkpoint(rd)["backend"] == "gpu"
    capsys.readouterr()
    assert sweep.run(lane_path, smoke=True, base=base) == 2
    assert "--backend gpu" in capsys.readouterr().err
    (rd / "status.json").write_text(json.dumps(st))  # it was a CPU launch: resume goes on
    assert sweep.run(lane_path, smoke=True, base=base) == 0
    assert _json(rd / "checkpoint.json")["backend"] == "cpu"


def test_a_gpu_sweeps_resume_command_names_its_backend_and_detaches(tmp_path):
    lane_path = _lane(tmp_path)
    lane = load_lane(lane_path)
    kw = {
        "resume": True,
        "ledger_path": None,
        "max_seeds": None,
        "lanes_dir": None,
        "override_q5": None,
        "stop": {"flag": False, "why": ""},
    }
    real = sweep._Sweep(lane, lane_path, tmp_path, smoke=False, backend="gpu", **kw)
    assert real.resume_cmd.endswith("--resume --backend gpu --detach")
    smoke = sweep._Sweep(lane, lane_path, tmp_path, smoke=True, backend="gpu", **kw)
    assert smoke.resume_cmd.endswith("--smoke --backend gpu")
    cpu = sweep._Sweep(lane, lane_path, tmp_path, smoke=False, backend="cpu", **kw)
    assert cpu.resume_cmd.endswith("--resume")  # unchanged: the frozen runner tests pin it


# ---------------------------------------------------------------- --no-resume


def test_no_resume_keeps_the_lanes_budget_and_a_fired_q5(tmp_path, capsys):
    base = tmp_path / "runs"
    lane_path = _crowded_lane(tmp_path, budget={"wall_clock_hours": 1.0})
    rd = base / load_lane(lane_path).lane_id
    assert sweep.run(lane_path, smoke=True, base=base) == 3
    ck = _json(rd / "checkpoint.json")
    assert ck["kill_condition"] == "fired"
    ck["elapsed_s"] = 1800.0
    (rd / "checkpoint.json").write_text(json.dumps(ck))
    capsys.readouterr()
    # archiving the run does not reset Q5: refused, nothing moved
    assert sweep.run(lane_path, resume=False, smoke=True, base=base) == 2
    assert "--no-resume does not reset Q5" in capsys.readouterr().err
    assert not list(rd.glob("previous-*")) and (rd / "checkpoint.json").exists()
    why = "toy: three crossers are the toy bar, not the lane"
    assert sweep.run(lane_path, resume=False, smoke=True, base=base, override_q5=why) == 0
    (prev,) = rd.glob("previous-*")
    new = _json(rd / "checkpoint.json")
    assert new["elapsed_s"] >= 1800.0  # the hour is per lane, not per run
    assert new["kill_condition"] == "overridden" and new["q5_overrides"][0]["reason"] == why
    assert new["restarts"][0]["archived"] == prev.name and new["restarts"][0]["cursor"] == 3000
    assert _rows(rd)[0]["type"] == "override-q5"


def test_no_resume_without_a_fired_q5_gives_the_new_run_its_own_check(tmp_path):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path, kill_condition={"at_fraction": 0.1, "min_seeds_per_s": 1})
    rd = base / load_lane(lane_path).lane_id
    assert sweep.run(lane_path, smoke=True, base=base) == 0
    assert _json(rd / "checkpoint.json")["kill_check"]["fired"] is False
    assert sweep.run(lane_path, resume=False, smoke=True, base=base) == 0
    new = _json(rd / "checkpoint.json")
    assert new["kill_check"]["cursor"] == 1000 and new["restarts"][0]["cursor"] == 6000


# ---------------------------------------------------------------- Q5 on the lane's slice


def test_a_short_launch_does_not_spend_the_lanes_q5_check(tmp_path):
    base = tmp_path / "runs"
    lane_path = _crowded_lane(tmp_path)
    rd = base / load_lane(lane_path).lane_id
    # 1,000 of 6,000 seeds is 1/6 of the lane, below at_fraction 0.5: no check yet, although
    # it is the whole of this launch's --max-seeds slice
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=1000) == 0
    ck, st = _json(rd / "checkpoint.json"), _json(rd / "status.json")
    assert not ck["kill_checked"] and ck.get("kill_check") is None
    assert st["done"] and not st["lane_done"] and st["lane_fraction"] == pytest.approx(1 / 6)
    assert st["lane_seed_range"] == [0, 6000] and st["seed_range"] == [0, 1000]
    assert _rows(rd)[-1]["lane_done"] is False
    # the full run checks at 3,000 = 50 % of the lane, and fires there
    assert sweep.run(lane_path, smoke=True, base=base) == 3
    ck, st = _json(rd / "checkpoint.json"), _json(rd / "status.json")
    assert ck["kill_check"]["cursor"] == 3000 and ck["kill_check"]["fired"] is True
    assert ck["kill_check"]["at_fraction"] == pytest.approx(0.5)
    assert st["kill_check"] == ck["kill_check"] and st["kill_condition"] == "fired"


def test_the_q5_check_is_recorded_when_it_does_not_fire(tmp_path):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path, kill_condition={"at_fraction": 0.4, "min_seeds_per_s": 1})
    rd = base / load_lane(lane_path).lane_id
    assert sweep.run(lane_path, smoke=True, base=base) == 0
    ck, st = _json(rd / "checkpoint.json"), _json(rd / "status.json")
    check = ck["kill_check"]
    assert check["fired"] is False and check["cursor"] == 3000 and check["backend"] == "cpu"
    assert check["seeds_per_s"] > 1 and "kill_detail" not in ck
    assert st["kill_check"] == check and st["kill_condition"] == "no" and st["lane_done"]


def test_a_max_seeds_at_or_below_the_cursor_is_refused(tmp_path, capsys):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path)
    rd = base / load_lane(lane_path).lane_id
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=3000) == 0
    capsys.readouterr()
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=2000) == 2
    assert "counts from the lane's first seed" in capsys.readouterr().err
    assert _json(rd / "status.json")["cursor"] == 3000
    assert sweep.run(lane_path, smoke=True, base=base, max_seeds=4000) == 0
    assert _json(rd / "status.json")["cursor"] == 4000


# ---------------------------------------------------------------- crash


def test_a_crash_says_so_in_status_json(tmp_path, monkeypatch):
    base = tmp_path / "runs"
    lane_path = _lane(tmp_path)
    rd = base / load_lane(lane_path).lane_id

    def boom(self, cipher, seeds, scorer):
        raise RuntimeError(f"GPU/CPU disagree on seed {seeds[0]} (parity broken)")

    monkeypatch.setattr(sweep._Sweep, "decode", boom)
    with pytest.raises(RuntimeError, match="parity broken"):
        sweep.run(lane_path, smoke=True, base=base)
    st = _json(rd / "status.json")
    assert st["stopped_by"] == "crash" and not st["done"] and not st["lane_done"]
    crash = _rows(rd)[-1]
    assert crash["type"] == "crash" and "seed 0" in crash["error"]
    assert not (rd / "sweep.pid").exists()


# ---------------------------------------------------------------- lane spec, rescoring


@pytest.mark.parametrize(
    ("over", "msg"),
    [
        ({"chunk_size": 0}, "chunk_size"),
        ({"budget": {"max_seeds": 0}}, "budget.max_seeds"),
        ({"kill_condition": {"at_fraction": 1.5}}, "at_fraction"),
        ({"kill_condition": {"at_fraction": 0}}, "at_fraction"),
    ],
)
def test_a_lane_that_cannot_make_progress_or_check_q5_is_refused(tmp_path, over, msg):
    with pytest.raises(ValueError, match=msg):
        load_lane(_lane(tmp_path, **over))


def test_runeforge_score_takes_seeds_past_int64(tmp_path):
    from runeforge.runner import rescore

    lo = 2**63 - 2
    lane = load_lane(_lane(tmp_path, seed_range=[0, 2**64 - 1]))
    out = rescore.score_range(lane, lo, lo + 4, top=4)
    assert sorted(t["seed"] for t in out["top"]) == [lo, lo + 1, lo + 2, lo + 3]
    one = rescore.score_seeds(lane, [lo + 3])[0]
    assert one == pytest.approx(next(t["score"] for t in out["top"] if t["seed"] == lo + 3))


@pytest.mark.parametrize("cmd", ["gate", "control", "null", "sweep"])
def test_a_template_lane_never_writes_evidence(tmp_path, cmd, capsys):
    from runeforge import cli

    tpl = tmp_path / "_template.yaml"
    tpl.write_text(_lane(tmp_path).read_text())
    assert cli.main([cmd, str(tpl)]) == 2
    out = capsys.readouterr()
    assert "template" in out.out + out.err
    assert not (tmp_path / "TOY-INTEGRITY").exists()
