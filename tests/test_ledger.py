"""Append-only ledger and lane specs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from runeforge.canon import read_pins
from runeforge.lanes import load_lane
from runeforge.ledger import STATUSES, Ledger, LedgerRow, to_upstream
from runeforge.paths import LANES_DIR

CONDITIONALS = {
    "key_space": "seeds 0..2^32, all",
    "decoder": "rigid screen, keyskip1 beam adjudication",
    "register": "cicada-english n-gram",
}


def test_status_vocabulary_matches_claude_md():
    assert STATUSES == (
        "never-run",
        "running",
        "parked",
        "inconclusive",
        "negative",
        "hit-unverified",
        "hit-verified",
        "superseded",
    )


def test_preregister_then_result(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.preregister(
        "L-1",
        "toy hypothesis",
        "prng",
        params={"seeds": [0, 10]},
        threshold=-5.5,
        threshold_fixed_in_advance=True,
    )
    with pytest.raises(ValueError):
        led.preregister("L-1", "again", "prng")  # already running
    led.record_result(
        "L-1",
        "negative",
        positive_control="passed",
        n_trials=10,
        best_score=-7.1,
        conditionals=CONDITIONALS,
    )
    rows = led.rows()
    assert [r.status for r in rows] == ["running", "negative"]
    assert rows[1].params == {"seeds": [0, 10]} and rows[1].threshold == -5.5
    assert rows[1].started == rows[0].started and rows[1].finished
    assert rows[1].data_sha256 == read_pins()["indices:LP2:all"].sha256
    assert rows[1].numbering == "LP2-0-57"
    # append-only: the file only ever grows by whole lines
    assert len((tmp_path / "ledger.jsonl").read_text().splitlines()) == 2
    assert led.latest()["L-1"].status == "negative"


def test_threshold_cannot_change_after_it_was_fixed(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.new("L-2", "h", "prng", threshold=-6.2, threshold_fixed_in_advance=True)
    with pytest.raises(ValueError, match="never edit a threshold"):
        led.update("L-2", threshold=-6.5)
    led.update("L-2", notes="2026-10-22 addendum: bar unchanged")  # other fields are fine


def test_result_needs_preregistration(tmp_path):
    with pytest.raises(ValueError):
        Ledger(tmp_path / "l.jsonl").record_result(
            "nope", "negative", positive_control="passed", n_trials=1
        )


def test_rule2_no_negative_without_a_passing_control():
    base = dict(lane_id="x", hypothesis="h", family="f", n_trials=5)
    good = dict(threshold=-6.0, threshold_fixed_in_advance=True, conditionals=CONDITIONALS)
    with pytest.raises(ValidationError, match="inconclusive"):
        LedgerRow(**base, status="negative", **good)
    with pytest.raises(ValidationError, match="threshold"):
        LedgerRow(**base, status="negative", positive_control="passed", conditionals=CONDITIONALS)
    with pytest.raises(ValidationError, match="conditionals"):
        LedgerRow(
            **base,
            status="negative",
            positive_control="passed",
            threshold=-6.0,
            threshold_fixed_in_advance=True,
        )
    with pytest.raises(ValidationError, match="passing control"):
        LedgerRow(**base, status="hit-verified", positive_control="failed")
    row = LedgerRow(**base, status="inconclusive", positive_control="failed")
    assert to_upstream(row)["status"] == "open"
    ok = LedgerRow(**base, status="negative", positive_control="passed", **good)
    assert ok.status == "negative"


def test_superseded_rows_name_their_successor():
    with pytest.raises(ValidationError):
        LedgerRow(lane_id="a", hypothesis="h", family="f", status="superseded")
    LedgerRow(lane_id="a", hypothesis="h", family="f", status="superseded", superseded_by=["b"])


def test_upstream_mapping_uses_dukotah_field_names():
    row = LedgerRow(
        lane_id="P3-X",
        hypothesis="h",
        family="prng",
        status="negative",
        positive_control="passed",
        n_trials=2**32,
        threshold=-6.1,
        threshold_fixed_in_advance=True,
        conditionals=CONDITIONALS,
        coverage="seeds 0..2^32",
        not_covered="string seeds",
        reopens_if="a decoder that models skip_by_two",
        best_score=-6.9,
        started="2026-10-21T00:00:00+00:00",
    )
    up = to_upstream(row)
    expected = {
        "id",
        "lane",
        "hypothesis",
        "status",
        "threshold",
        "threshold_fixed_in_advance",
        "positive_control",
        "result",
        "coverage",
        "not_covered",
        "reopens_if",
        "evidence",
    }
    assert expected <= set(up)
    assert up["status"] == "negative" and up["positive_control"] == "passed"
    assert up["threshold"] == -6.1 and up["threshold_fixed_in_advance"] is True


def test_lane_template_validates_but_is_not_runnable():
    lane = load_lane(LANES_DIR / "_template.yaml")
    assert lane.n_trials == 2**32
    assert lane.runnable_problems()  # bars are not calibrated yet


def test_a_threshold_fixed_in_advance_must_be_recorded(tmp_path):
    with pytest.raises(ValidationError, match="no threshold is recorded"):
        LedgerRow(
            lane_id="L-1",
            hypothesis="h",
            family="f",
            status="never-run",
            threshold_fixed_in_advance=True,
        )
    led = Ledger(tmp_path / "ledger.jsonl")
    led.new("L-1", "h", "f", threshold=-6.1, threshold_fixed_in_advance=True)
    with pytest.raises(ValueError, match="fixed in advance"):
        led.update("L-1", threshold=-5.0)


def test_a_repaired_lane_keeps_its_bad_row_readable(tmp_path):
    """SESSION_PROMPT.md section A step 4: a hand-written unsound row is repaired by a
    FOUND-ERROR lane and `supersedes` links; the bad row stays (append-only) and stays readable."""
    import json

    from runeforge.ledger import LedgerUnreadable

    path = tmp_path / "ledger.jsonl"
    bad = {"lane_id": "L-1", "hypothesis": "h", "family": "f", "status": "negative"}
    path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    led = Ledger(path)
    with pytest.raises(LedgerUnreadable, match="Rule 2"):
        led.rows()
    led.append(
        LedgerRow(
            lane_id="R-1",
            hypothesis="audit of L-1",
            family="redteam",
            status="inconclusive",
            verdict="FOUND-ERROR",
            supersedes=["L-1"],
        )
    )
    with pytest.raises(LedgerUnreadable):  # not repaired until L-1 itself is superseded
        led.rows()
    led.update("L-1", status="superseded", superseded_by=["R-1"])  # the CLI's path
    assert [r.status for r in led.rows()] == ["negative", "inconclusive", "superseded"]
    assert led.get("L-1").status == "superseded"
