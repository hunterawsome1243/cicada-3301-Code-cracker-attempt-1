"""Append-only JSONL ledger of every lane run: a pre-registration row before the run,
a result row after. Rows are never edited or deleted; the latest row per lane wins.

Field names follow the spec; ``to_upstream`` maps a row onto Dukotah/cicada3301
LEDGER.json field names so rows can be submitted there.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from runeforge.paths import LEDGER_PATH, REPO_ROOT

Status = Literal[
    "never-run",
    "running",
    "parked",
    "untested",  # ran, but its control did not pass (Rule 2): NOT a negative
    "negative",
    "hit-unverified",
    "hit-verified",
]
ControlResult = Literal["not-run", "passed", "failed"]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def git_sha(root: Path = REPO_ROOT) -> str | None:
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return r.stdout.strip() or None


def data_sha256() -> str:
    """The pinned hash of the full LP2 index stream (format-independent)."""
    from runeforge.canon import read_pins

    return read_pins()["indices:LP2:all"].sha256


class LedgerRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lane_id: str
    hypothesis: str
    family: str
    params: dict[str, Any] = Field(default_factory=dict)
    control_spec: dict[str, Any] = Field(default_factory=dict)
    control_result: ControlResult = "not-run"
    n_trials: int = 0
    claim_bar: float | None = None
    family_wise_bar: float | None = None
    best_score: float | None = None
    best_candidate_ref: str | None = None
    status: Status
    started: str | None = None
    finished: str | None = None
    host: str = Field(default_factory=platform.node)
    git_sha: str | None = Field(default_factory=git_sha)
    data_sha256: str = Field(default_factory=data_sha256)
    notes: str | None = None
    recorded: str = Field(default_factory=_now)

    @model_validator(mode="after")
    def _rules(self) -> LedgerRow:
        if self.status == "negative" and self.control_result != "passed":
            raise ValueError(
                "Rule 2: a lane without a passing control is 'untested', not 'negative'"
            )
        if self.status == "hit-verified" and self.control_result != "passed":
            raise ValueError("a verified hit needs a passing control")
        if self.status in ("negative", "hit-unverified", "hit-verified") and self.n_trials <= 0:
            raise ValueError("a result row must record its trial count")
        if self.status == "running" and self.started is None:
            raise ValueError("a pre-registration row needs 'started'")
        return self


class Ledger:
    def __init__(self, path: Path | str = LEDGER_PATH):
        self.path = Path(path)

    def append(self, row: LedgerRow) -> LedgerRow:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = row.model_dump_json() + "\n"
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        return row

    def rows(self) -> list[LedgerRow]:
        if not self.path.exists():
            return []
        out = []
        for i, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    out.append(LedgerRow.model_validate_json(line))
                except ValueError as exc:
                    raise ValueError(f"{self.path}:{i}: invalid ledger row: {exc}") from exc
        return out

    def latest(self) -> dict[str, LedgerRow]:
        out: dict[str, LedgerRow] = {}
        for r in self.rows():
            out[r.lane_id] = r
        return out

    def preregister(self, lane_id: str, hypothesis: str, family: str, **kw) -> LedgerRow:
        """Write the pre-registration row (status 'running') before a lane runs."""
        if lane_id in self.latest() and self.latest()[lane_id].status == "running":
            raise ValueError(f"lane {lane_id} is already running (resume it instead)")
        return self.append(
            LedgerRow(
                lane_id=lane_id,
                hypothesis=hypothesis,
                family=family,
                status="running",
                started=_now(),
                **kw,
            )
        )

    def record_result(self, lane_id: str, status: Status, **kw) -> LedgerRow:
        prior = self.latest().get(lane_id)
        if prior is None:
            raise ValueError(f"lane {lane_id} was never pre-registered")
        base = prior.model_dump(
            exclude={"status", "finished", "recorded", "host", "git_sha", "data_sha256"}
        )
        base.update(kw)
        return self.append(LedgerRow(**base, status=status, finished=_now()))


_UPSTREAM_STATUS = {
    "never-run": "never-run",
    "running": "partially-run",
    "parked": "partially-run",
    "untested": "open",
    "negative": "negative",
    "hit-unverified": "open",
    "hit-verified": "open",
}


def to_upstream(row: LedgerRow) -> dict:
    """Map a row onto Dukotah/cicada3301 LEDGER.json entry fields."""
    return {
        "id": row.lane_id,
        "lane": row.family,
        "hypothesis": row.hypothesis,
        "status": _UPSTREAM_STATUS[row.status],
        "date": (row.finished or row.started or row.recorded)[:10],
        "threshold": row.family_wise_bar if row.family_wise_bar is not None else row.claim_bar,
        "threshold_fixed_in_advance": True,
        "positive_control": {"not-run": "none", "passed": "passed", "failed": "failed"}[
            row.control_result
        ],
        "control_detail": row.control_spec or None,
        "result": {
            "status": row.status,
            "n_trials": row.n_trials,
            "best_score": row.best_score,
            "best_candidate_ref": row.best_candidate_ref,
        },
        "coverage": row.params or None,
        "notes": row.notes,
        "reproduce": f"runeforge @ {row.git_sha}" if row.git_sha else None,
        "source_register": "runeforge ledger",
    }


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
