"""Append-only JSONL ledger (``ledger/ledger.jsonl``) of every lane.

Every change to a lane is a NEW row; rows are never edited or deleted, and the latest
row per ``lane_id`` is the lane's current state. Corrections link with ``supersedes`` /
``superseded_by``.

Vocabulary and the rules enforced here follow CLAUDE.md:

* ``status``: never-run · running · parked · inconclusive · negative · hit-unverified ·
  hit-verified · superseded.
* ``negative`` needs ``positive_control: passed``, ``threshold_fixed_in_advance: true``
  and the three ``conditionals`` (key space · decoder · register). A failed control can
  only ever be ``inconclusive``.
* Once a lane has recorded a threshold fixed in advance, later rows may not change it.

Field names follow Dukotah/cicada3301 ``LEDGER.json`` wherever the two overlap
(``positive_control``, ``threshold``, ``threshold_fixed_in_advance``, ``coverage``,
``not_covered``, ``reopens_if``, ``evidence``, ``supersedes``...), so ``to_upstream`` is
mostly a rename of ``lane_id`` to ``id``. ``scripts/validate_ledger.py`` re-checks all of
this with the standard library only.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runeforge.paths import LEDGER_PATH, REPO_ROOT

STATUSES = (
    "never-run",
    "running",
    "parked",
    "inconclusive",
    "negative",
    "hit-unverified",
    "hit-verified",
    "superseded",
)
VERDICTS = (
    "NULL",
    "CANDIDATE",
    "INCONCLUSIVE (power)",
    "EXCLUDED (gate)",
    "FOUND-ERROR",
    "NO-ERROR-FOUND",
)
CATEGORIES = ("instrument", "bounded", "redteam", "closeout")
CONDITIONALS = ("key_space", "decoder", "register")
CONCLUDED = ("negative", "hit-unverified", "hit-verified")  # a result was seen
NUMBERING = "LP2-0-57"

Status = Literal[
    "never-run",
    "running",
    "parked",
    "inconclusive",
    "negative",
    "hit-unverified",
    "hit-verified",
    "superseded",
]
Verdict = Literal[
    "NULL",
    "CANDIDATE",
    "INCONCLUSIVE (power)",
    "EXCLUDED (gate)",
    "FOUND-ERROR",
    "NO-ERROR-FOUND",
]
PositiveControl = Literal["none", "passed", "failed"]
Category = Literal["instrument", "bounded", "redteam", "closeout"]

# Fields a later row inherits from the lane's previous row unless it sets them again.
_VOLATILE = ("recorded", "host", "git_sha", "data_sha256")


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

    # identity
    lane_id: str
    hypothesis: str
    family: str
    category: Category | None = None
    round: str | None = None
    numbering: Literal["LP2-0-57"] = NUMBERING
    # state
    status: Status
    verdict: Verdict | None = None
    # pre-registration
    prereg: str | None = None
    threshold: float | str | None = None
    threshold_fixed_in_advance: bool = False
    claim_bar: float | None = None
    family_wise_bar: float | None = None
    n_trials: int = 0
    params: dict[str, Any] = Field(default_factory=dict)
    # control (Rule 2)
    control_spec: dict[str, Any] = Field(default_factory=dict)
    positive_control: PositiveControl = "none"
    control_detail: dict[str, Any] | str | None = None
    # outcome
    null: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    best_score: float | None = None
    best_candidate_ref: str | None = None
    # bounds, not verdicts
    coverage: str | None = None
    not_covered: str | None = None
    conditionals: dict[str, str] | None = None
    reopens_if: str | None = None
    external_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    reproduce: str | None = None
    # links and job state
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: list[str] = Field(default_factory=list)
    parked_state: dict[str, Any] | str | None = None
    # provenance
    started: str | None = None
    finished: str | None = None
    host: str = Field(default_factory=platform.node)
    git_sha: str | None = Field(default_factory=git_sha)
    data_sha256: str = Field(default_factory=data_sha256)
    notes: str | None = None
    recorded: str = Field(default_factory=_now)

    @field_validator("round", mode="before")
    @classmethod
    def _round_str(cls, v):
        return None if v is None else str(v)

    @model_validator(mode="after")
    def _rules(self) -> LedgerRow:
        if self.status in ("negative", "hit-verified"):
            what = "a negative" if self.status == "negative" else "a verified hit"
            if self.positive_control != "passed":
                raise ValueError(
                    "Rule 2: a lane without a passing control is 'inconclusive', not 'negative'"
                    if self.status == "negative"
                    else "a verified hit needs a passing control"
                )
            if not self.threshold_fixed_in_advance or self.threshold in (None, ""):
                raise ValueError(f"{what} needs a threshold fixed in advance")
            missing = [k for k in CONDITIONALS if not (self.conditionals or {}).get(k)]
            if missing:
                raise ValueError(f"{what} carries its three conditionals; missing {missing}")
        if self.positive_control == "passed":
            d = self.control_detail
            if not isinstance(d, dict) or not d.get("path") or not d.get("sha256"):
                raise ValueError(
                    "positive_control 'passed' must cite its evidence: control_detail "
                    "{path, sha256} as `runeforge control` records it"
                )
        if self.threshold_fixed_in_advance and self.threshold in (None, ""):
            raise ValueError(
                "threshold_fixed_in_advance is true but no threshold is recorded "
                "(a bar filled in later is a post-hoc bar)"
            )
        if self.positive_control == "failed" and self.status in ("negative", "hit-verified"):
            raise ValueError("a failed control can only be 'inconclusive'")
        if self.status == "running" and self.started is None:
            raise ValueError("a running lane needs 'started'")
        if self.status == "superseded" and not self.superseded_by:
            raise ValueError("a superseded row must name its successor in 'superseded_by'")
        if self.verdict == "CANDIDATE" and self.status not in ("hit-unverified", "hit-verified"):
            raise ValueError("a CANDIDATE verdict goes with hit-unverified or hit-verified")
        return self


def repaired_lanes(rows: list[dict]) -> dict[str, str]:
    """Lanes whose latest row is ``superseded`` and whose successor links back with
    ``supersedes``: {lane: successor(s)}. Mirrored in scripts/validate_ledger.py."""
    latest: dict[str, dict] = {}
    links: dict[str, set[str]] = {}
    for row in rows:
        lane = row.get("lane_id")
        if not isinstance(lane, str):
            continue
        latest[lane] = row
        for ref in row.get("supersedes") or []:
            links.setdefault(ref, set()).add(lane)
    out = {}
    for lane, row in latest.items():
        succ = [x for x in row.get("superseded_by") or [] if x in links.get(lane, set())]
        if row.get("status") == "superseded" and succ:
            out[lane] = ", ".join(succ)
    return out


class LedgerUnreadable(ValueError):
    """A row in the file fails ``LedgerRow`` validation (``scripts/validate_ledger.py`` says
    which and why)."""


class Ledger:
    def __init__(self, path: Path | str = LEDGER_PATH):
        self.path = Path(path)

    def append(self, row: LedgerRow) -> LedgerRow:
        row = LedgerRow.model_validate(row.model_dump())  # a model_copy/construct skips the rules
        self._check_threshold_frozen(row)
        self._check_threshold_preceded(row)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = row.model_dump_json() + "\n"
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        return row

    def rows(self, strict: bool = True) -> list[LedgerRow]:
        """Every row, validated. A historical row that fails the model is read leniently only
        when its lane has been repaired (``repaired_lanes``): rows are append-only, so the
        SESSION_PROMPT.md section A step 4 repair can never remove it. ``strict=False`` reads
        every such row leniently; the write path uses it, so the repair rows can be appended
        (each new row is still validated in full)."""
        if not self.path.exists():
            return []
        parsed: list[tuple[int, LedgerRow | dict, Exception | None]] = []
        for i, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                parsed.append((i, LedgerRow.model_validate_json(line), None))
            except ValueError as exc:
                try:
                    data = json.loads(line)
                except ValueError:
                    data = None
                if not isinstance(data, dict) or not isinstance(data.get("lane_id"), str):
                    raise LedgerUnreadable(f"{self.path}:{i}: invalid ledger row: {exc}") from exc
                parsed.append((i, data, exc))
        dicts = [r if isinstance(r, dict) else r.model_dump() for _, r, _ in parsed]
        repaired = repaired_lanes(dicts)
        last = {d["lane_id"]: i for (i, _, _), d in zip(parsed, dicts, strict=True)}
        out = []
        for i, r, exc in parsed:
            if isinstance(r, LedgerRow):
                out.append(r)
                continue
            lane = r["lane_id"]
            if strict and (lane not in repaired or last[lane] == i):
                raise LedgerUnreadable(f"{self.path}:{i}: invalid ledger row: {exc}") from exc
            known = {k: v for k, v in r.items() if k in LedgerRow.model_fields}
            out.append(LedgerRow.model_construct(**known))
        return out

    def latest(self, strict: bool = True) -> dict[str, LedgerRow]:
        out: dict[str, LedgerRow] = {}
        for r in self.rows(strict):
            out[r.lane_id] = r
        return out

    def get(self, lane_id: str, strict: bool = True) -> LedgerRow | None:
        return self.latest(strict).get(lane_id)

    def _check_threshold_frozen(self, row: LedgerRow) -> None:
        frozen = [
            r
            for r in self.rows(strict=False)
            if r.lane_id == row.lane_id and r.threshold_fixed_in_advance
        ]
        if frozen and row.threshold != frozen[0].threshold:
            raise ValueError(
                f"lane {row.lane_id}: threshold was fixed in advance at {frozen[0].threshold!r}; "
                "never edit a threshold after seeing a result -- append a dated addendum instead"
            )

    def _check_threshold_preceded(self, row: LedgerRow) -> None:
        """A concluded row's 'fixed in advance' must be on record before it: an earlier row of
        the lane carries the same threshold with threshold_fixed_in_advance true."""
        if row.status not in CONCLUDED or not row.threshold_fixed_in_advance:
            return
        earlier = [
            r
            for r in self.rows(strict=False)
            if r.lane_id == row.lane_id and r.threshold_fixed_in_advance
        ]
        if not any(r.threshold == row.threshold for r in earlier):
            raise ValueError(
                f"lane {row.lane_id}: a {row.status} row's threshold {row.threshold!r} must be "
                "fixed in advance by an EARLIER row (pre-register it before the run)"
            )

    def new(self, lane_id: str, hypothesis: str, family: str, status: Status = "never-run", **kw):
        """Append the first row of a lane."""
        if self.get(lane_id, strict=False) is not None:
            raise ValueError(f"lane {lane_id} already exists; use update()")
        if status == "running":
            kw.setdefault("started", _now())
        return self.append(
            LedgerRow(lane_id=lane_id, hypothesis=hypothesis, family=family, status=status, **kw)
        )

    def update(self, lane_id: str, **changes) -> LedgerRow:
        """Append a new row for the lane: its latest row with ``changes`` applied."""
        prior = self.get(lane_id, strict=False)
        if prior is None:
            raise ValueError(f"lane {lane_id} has no row yet; use new()")
        base = prior.model_dump(exclude=set(_VOLATILE))
        base.update(changes)
        if base.get("status") == "running" and prior.status != "running":
            # a (re)start: hours are counted per running -> final interval
            base.setdefault("started", None)
            if "started" not in changes:
                base["started"] = _now()
            if "finished" not in changes:
                base["finished"] = None
        if base.get("status") == "running" and not base.get("started"):
            base["started"] = _now()
        final = ("negative", "inconclusive", "hit-verified", "parked")
        if base.get("status") in final and "finished" not in changes:
            base["finished"] = _now()
        return self.append(LedgerRow(**base))

    # Back-compatible helpers used by the Phase 1 tests and the sweep runner.
    def preregister(self, lane_id: str, hypothesis: str, family: str, **kw) -> LedgerRow:
        """Write the row that opens a run (status 'running') before the first trial."""
        prior = self.get(lane_id, strict=False)
        if prior is not None and prior.status == "running":
            raise ValueError(f"lane {lane_id} is already running (resume it instead)")
        if prior is None:
            return self.new(lane_id, hypothesis, family, status="running", **kw)
        return self.update(lane_id, hypothesis=hypothesis, family=family, status="running", **kw)

    def record_result(self, lane_id: str, status: Status, **kw) -> LedgerRow:
        if self.get(lane_id, strict=False) is None:
            raise ValueError(f"lane {lane_id} was never pre-registered")
        return self.update(lane_id, status=status, **kw)


_UPSTREAM_STATUS = {
    "never-run": "never-run",
    "running": "partially-run",
    "parked": "partially-run",
    "inconclusive": "open",
    "negative": "negative",
    "hit-unverified": "open",
    "hit-verified": "open",
    "superseded": "superseded",
}


def to_upstream(row: LedgerRow) -> dict:
    """Map a row onto Dukotah/cicada3301 LEDGER.json entry fields."""
    return {
        "id": row.lane_id,
        "lane": row.family,
        "hypothesis": row.hypothesis,
        "status": _UPSTREAM_STATUS[row.status],
        "round": row.round,
        "date": (row.finished or row.started or row.recorded)[:10],
        "threshold": (
            row.threshold
            if row.threshold is not None
            else (row.family_wise_bar if row.family_wise_bar is not None else row.claim_bar)
        ),
        "threshold_fixed_in_advance": row.threshold_fixed_in_advance,
        "positive_control": row.positive_control,
        "control_detail": row.control_detail or row.control_spec or None,
        "null": row.null,
        "result": row.result
        or {
            "status": row.status,
            "verdict": row.verdict,
            "n_trials": row.n_trials,
            "best_score": row.best_score,
            "best_candidate_ref": row.best_candidate_ref,
        },
        "coverage": row.coverage,
        "not_covered": row.not_covered,
        "conditionals": row.conditionals,
        "evidence": row.evidence,
        "reproduce": row.reproduce or (f"runeforge @ {row.git_sha}" if row.git_sha else None),
        "reopens_if": row.reopens_if,
        "supersedes": row.supersedes,
        "superseded_by": row.superseded_by,
        "external_ids": row.external_ids,
        "numbering": row.numbering,
        "notes": row.notes,
        "source_register": "runeforge ledger",
    }


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
