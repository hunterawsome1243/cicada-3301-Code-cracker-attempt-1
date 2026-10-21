"""Append-only ledger and lane specs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from runeforge.canon import read_pins
from runeforge.lanes import load_lane
from runeforge.ledger import Ledger, LedgerRow, to_upstream
from runeforge.paths import LANES_DIR


def test_preregister_then_result(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.preregister("L-1", "toy hypothesis", "prng", params={"seeds": [0, 10]}, claim_bar=-5.5)
    with pytest.raises(ValueError):
        led.preregister("L-1", "again", "prng")  # already running
    led.record_result(
        "L-1",
        "negative",
        control_result="passed",
        n_trials=10,
        best_score=-7.1,
        family_wise_bar=-6.2,
    )
    rows = led.rows()
    assert [r.status for r in rows] == ["running", "negative"]
    assert rows[1].params == {"seeds": [0, 10]} and rows[1].claim_bar == -5.5
    assert rows[1].started == rows[0].started and rows[1].finished
    assert rows[1].data_sha256 == read_pins()["indices:LP2:all"].sha256
    # append-only: the file only ever grows by whole lines
    assert len((tmp_path / "ledger.jsonl").read_text().splitlines()) == 2
    assert led.latest()["L-1"].status == "negative"


def test_result_needs_preregistration(tmp_path):
    with pytest.raises(ValueError):
        Ledger(tmp_path / "l.jsonl").record_result(
            "nope", "negative", control_result="passed", n_trials=1
        )


def test_rule2_no_negative_without_a_passing_control():
    with pytest.raises(ValidationError):
        LedgerRow(lane_id="x", hypothesis="h", family="f", status="negative", n_trials=5)
    row = LedgerRow(
        lane_id="x",
        hypothesis="h",
        family="f",
        status="untested",
        control_result="failed",
        n_trials=5,
    )
    assert to_upstream(row)["status"] == "open"


def test_upstream_mapping_uses_dukotah_field_names():
    row = LedgerRow(
        lane_id="P3-X",
        hypothesis="h",
        family="prng",
        status="negative",
        control_result="passed",
        n_trials=2**32,
        family_wise_bar=-6.1,
        best_score=-6.9,
        started="2026-10-21T00:00:00+00:00",
    )
    up = to_upstream(row)
    assert {
        "id",
        "lane",
        "hypothesis",
        "status",
        "threshold",
        "threshold_fixed_in_advance",
        "positive_control",
        "result",
    } <= set(up)
    assert (
        up["status"] == "negative"
        and up["positive_control"] == "passed"
        and up["threshold"] == -6.1
    )


def test_lane_template_validates_but_is_not_runnable():
    lane = load_lane(LANES_DIR / "_template.yaml")
    assert lane.n_trials == 2**32
    assert lane.runnable_problems()  # bars are not calibrated yet
