"""The lane control's verdict arithmetic (runeforge.runner.control): the pass bar cannot be
lowered, a weak control never passes, the ceiling is taken at the lane's own N, and the
control's evidence is bound to the lane spec it ran on."""

from __future__ import annotations

import math

import pytest
import yaml
from pydantic import ValidationError

from runeforge.lanes import load_lane
from runeforge.ledger import Ledger
from runeforge.runner import control
from runeforge.scoring import calib


def _lane(tmp_path, **over):
    bar = calib.threshold_for(30_000, "lp-ngram3-heldout:rigid", 240).bar
    spec = {
        "lane_id": "CTRL-PCG64",
        "hypothesis": "toy control fixture",
        "family": "prng",
        "generator": "numpy-pcg64",
        "seed_range": [0, 30_000],
        "window": 240,
        "pages": [0, 1],
        "preset": "lp-ngram3-heldout:rigid",
        "interrupt_prob": 0.0,
        "claim_bar": bar - 0.3,
        "family_wise_bar": bar,
        "control": {"planted_seed": 3301, "synthetic_page": "solved:a-koan-1", "decoys": 199},
    }
    for k, v in over.items():
        if k == "control":
            spec["control"] = {**spec["control"], **v}
        else:
            spec[k] = v
    path = tmp_path / "lane.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "lowered",
    [{"min_identified": 0.0}, {"min_recovery": 0.5}, {"n_plants": 10}, {"decoys": 20}],
)
def test_the_pass_bar_cannot_be_lowered_in_the_yaml(tmp_path, lowered):
    with pytest.raises(ValidationError, match="never lowered"):
        load_lane(_lane(tmp_path, control=lowered))


def test_a_raised_pass_bar_is_fine(tmp_path):
    lane = load_lane(_lane(tmp_path, control={"min_identified": 1.0, "n_plants": 25}))
    assert lane.control.n_plants == 25


def test_a_lane_the_decoder_cannot_follow_never_passes(tmp_path):
    rep = control.run_control(load_lane(_lane(tmp_path, filter_model="anti-repeat")))
    assert rep.status == "failed" and rep.verdict_if_failed == "INCONCLUSIVE (power)"
    assert rep.identified < rep.n_plants


def test_the_ceiling_is_extrapolated_to_the_lanes_n(tmp_path):
    small = control.run_control(load_lane(_lane(tmp_path)))
    big = control.run_control(load_lane(_lane(tmp_path, seed_range=[0, 2**32])))
    assert small.ceiling_trials == big.ceiling_trials == 20 * 200
    beta = calib.load("lp-ngram3-heldout:rigid", 240)["fit"]["beta"]
    assert big.beta == pytest.approx(beta) and big.beta_source == "calibration"
    want = big.ceiling_observed + beta * math.log(2**32 / big.ceiling_trials)
    assert big.ceiling == pytest.approx(want)
    assert big.ceiling > small.ceiling  # more trials, a higher noise ceiling
    assert big.gap_nats == pytest.approx((big.floor - big.ceiling) * math.log(2))


def test_the_evidence_is_bound_to_the_lane_spec(tmp_path):
    lanes_dir = tmp_path / "lanes"
    lane = load_lane(_lane(tmp_path))
    rep = control.run_control(lane)
    assert rep.status == "passed", rep.reasons
    detail = control.write_report(rep, lane, tmp_path / "runs" / lane.lane_id, lanes_dir)
    led = Ledger(tmp_path / "ledger.jsonl")
    led.new(lane.lane_id, lane.hypothesis, lane.family)
    assert any(
        "does not record a passing" in p
        for p in control.control_problems(lane, led.get(lane.lane_id), lanes_dir)
    )
    row = led.update(lane.lane_id, positive_control="passed", control_detail=detail)
    assert control.control_problems(lane, row, lanes_dir) == []
    edited = lane.model_copy(update={"window": 120})
    assert any("lane spec changed" in p for p in control.control_problems(edited, row, lanes_dir))
    # a re-run control (another report) is not the one the ledger cites
    (lanes_dir / lane.lane_id / "control.json").write_text(
        (lanes_dir / lane.lane_id / "control.json").read_text() + " "
    )
    assert any("does not cite" in p for p in control.control_problems(lane, row, lanes_dir))


def test_a_bare_yaml_off_is_the_filter_model_off(tmp_path):
    """YAML 1.1 reads `filter_model: off` as false; the template documents `off`."""
    text = _lane(tmp_path).read_text() + "filter_model: off\n"
    path = tmp_path / "off.yaml"
    path.write_text(text, encoding="utf-8")
    assert load_lane(path).filter_model == "off"


def test_a_window_longer_than_the_pages_is_not_runnable(tmp_path):
    lane = load_lane(_lane(tmp_path, pages=[49]))  # page 49 holds 66 runes
    assert any("fewer than window 240" in p for p in lane.runnable_problems())
    with pytest.raises(ValueError, match="fewer than window"):
        control.run_control(lane)


def test_a_bar_below_threshold_for_is_not_runnable(tmp_path):
    lane = load_lane(_lane(tmp_path, seed_range=[0, 2**32]))  # bars were set for N = 30,000
    assert any("is below threshold_for" in p for p in lane.runnable_problems())
