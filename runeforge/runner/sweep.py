"""``runeforge sweep <lane.yaml> [--detach]``: the lane runner (CPU backend; GPU in Phase 3).

Refusals -- exit 2, nothing scored, the reasons on stderr. The runner checks them itself,
under an exclusive ``flock`` on ``<runs>/.sweep.lock`` held across its preflight, its PID
write and its first status.json, so two launches can never both pass:

* bars not calibrated, or a family_wise_bar below ``threshold_for`` at the lane's N
  (``LaneSpec.runnable_problems``; smoke skips only that comparison);
* no ledger row, or a latest row whose status is concluded (negative, inconclusive,
  hit-unverified, hit-verified, superseded): concluded ground is not re-run;
* Rule 2 (``control.control_problems``): ``lanes/<id>/control.json`` passed, ran on the lane
  spec as it is now (``lane_pipeline_sha256``), and is the file the ledger row's
  ``control_detail.sha256`` cites -- the ledger string ``positive_control`` alone is not
  evidence;
* thresholds: the ledger row has ``threshold_fixed_in_advance: true`` and its ``threshold``
  equals the lane's ``family_wise_bar`` (|delta| <= 1e-9), the bar crossers are flagged at;
* the fingerprint gate: the newer of ``lanes/<id>/gate.json`` and ``runs/<id>/gate.json`` is
  missing, has ``excluded`` not false or a ``verdict_line`` not starting "GATE PASS", ran
  fewer than ``gate.MIN_KEYS`` (12) keys, or ran on another lane spec
  (``lane_pipeline_sha256``);
* a CLI ``--max-seeds`` above the lane's ``budget.max_seeds``;
* on resume, a checkpoint whose pinned ``claim_bar``, ``family_wise_bar``,
  ``lane_pipeline_sha256`` or ``smoke`` differs from this launch (``--no-resume`` archives it);
* another live sweep under the same runs directory (never two jobs at once);
* ``--smoke`` into the repository's own ``runs/`` unless ``RUNEFORGE_SMOKE_OK=1``. Smoke skips
  the ledger, status, control, threshold and gate checks and the family_wise_bar-vs-
  threshold_for comparison; it exists for test harnesses only, is reachable only as
  ``python -m runeforge.runner.sweep run|launch --smoke`` (never on ``runeforge sweep``), and
  marks everything it writes ``"smoke": true``.

The files (the ops contract overnight.sh and OVERNIGHT_LOOP.md rely on):

* ``runs/<id>/sweep.pid`` -- the bare PID of the runner process, whose cmdline contains
  ``runeforge.runner.sweep`` or ``runeforge sweep``. The runner writes it after its preflight
  passes and removes it on every exit path (never when the file holds another PID). A
  SIGKILLed runner leaves it stale; ``jobs.pid_alive_runeforge`` and overnight.sh's
  ``pid_is_runeforge`` then call it dead (cmdline and ``pid_starttime`` checks).
* ``runs/<id>/status.json`` -- rewritten atomically right after the PID write, after every
  chunk and at least every ``HEARTBEAT_S`` seconds inside one: ``pid``, ``pid_starttime``
  (field 22 of /proc/<pid>/stat), ``updated_epoch``, ``deadline_epoch``, ``done``,
  ``kill_condition`` (no | fired | overridden), ``stopped_by``, ``cursor`` (the resume point:
  the last checkpointed seed), ``scoring_at``, ``smoke``, the bars and progress fields.
* ``runs/<id>/checkpoint.json`` -- ``cursor``, ``seeds_done``, the running top-k, the crosser
  count, the cumulative ``elapsed_s`` over every launch, the pins (``claim_bar``,
  ``family_wise_bar``, ``lane_pipeline_sha256``, ``smoke``) and the Q5 state
  (``kill_condition``, ``kill_detail``, ``q5_overrides``). ``--resume`` is the default: a
  killed run continues from the last completed chunk with no gap and no double count.
* ``runs/<id>/sweep.jsonl`` -- SWEEPROWs, each with ``smoke`` and a ``reproduce`` command. A
  chunk's survivor and crosser rows are buffered and written together with its ``chunk`` row
  immediately before its checkpoint, so a SIGKILL mid-chunk never duplicates them; then
  ``override-q5``, ``done``, ``stopped`` and ``crash`` rows. Survivor and crosser rows
  reproduce with ``runeforge score <lane> <seed>``, chunk rows with
  ``runeforge score <lane> <lo>:<hi>``, the others with the resume command. Survivor and
  crosser rows carry ``stats`` (``runeforge.stats.decode.decode_stats`` of the decoded
  window), chunk rows the stats of the chunk's best decode (``chunk_best_seed``); stats are
  computed for those decodes only, never per trial. ``<lane>`` is repo-relative when the lane
  lies inside the repository (else absolute), so the lines work from a clean checkout.
* ``runs/<id>/crossers/<kid>.pending`` -- written at the crossing (with ``stats`` and the
  same repo-relative ``lane_path``), for HIT_PROTOCOL.md; the sweep never stops for a
  crosser, never re-opens one the crosser steps renamed to ``.noise-crosser`` /
  ``.parity-fail``, and ``--no-resume`` never moves them.
* ``runs/<id>/previous-<stamp>-<pid>/`` -- ``--no-resume`` moves checkpoint.json,
  status.json and sweep.jsonl there.
* ``runs/<id>/killed-history/<stamp>-KILLED-<reason>`` -- overnight.sh's ``KILLED-*`` markers,
  moved there when a relaunch passes its preflight.

Budget: ``deadline_epoch`` = launch + (``wall_clock_hours`` x 3600 - ``elapsed_s`` already
spent): the budget is per lane, not per launch, and a lane with nothing left stops at once
(``stopped_by: deadline``). The seed cap is ``lo + min(--max-seeds, budget.max_seeds)``.

Q5: the kill condition is evaluated once, at ``kill_condition.at_fraction`` of the slice. Once
it fires it is recorded in checkpoint.json, and every later resume writes status.json with
``kill_condition: fired`` and exits 3 without scoring, unless ``--override-q5 "<reason>"``
(appends an ``override-q5`` SWEEPROW and records the reason; status then says
``overridden``).

Exit codes: 0 done · 1 stopped (deadline) · 2 refused · 3 Q5 kill condition · 143 SIGTERM or
SIGINT. ``launch_detached`` returns 0 only once the child has written status.json with its
own PID (or finished cleanly); if the child exits first it returns 2 and prints the tail of
``sweep.log``.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import heapq
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from runeforge import canon
from runeforge.lanes import LaneSpec, load_lane
from runeforge.paths import LEDGER_PATH, REPO_ROOT
from runeforge.runner import control, pipeline
from runeforge.runner.jobs import (  # noqa: F401  (re-exported for crosser and cli)
    RUNS_DIR,
    live_sweeps,
    pid_alive_runeforge,
    pid_starttime,
)
from runeforge.scoring import presets
from runeforge.stats.decode import decode_stats

BATCH = 4096
TOP_K = 20
HEARTBEAT_S = 60  # status.json is rewritten at least this often, even inside a long chunk
LAUNCH_WAIT_S = 30  # launch_detached waits this long for the child's first status.json
LOCK_WAIT_S = 20  # the child waits this long for <runs>/.sweep.lock, then refuses
THRESHOLD_TOL = 1e-9
SMOKE_OK_ENV = "RUNEFORGE_SMOKE_OK"  # test harnesses only: allow --smoke into REPO_ROOT/runs
REPO_RUNS = REPO_ROOT / "runs"
PINNED = ("claim_bar", "family_wise_bar", "lane_pipeline_sha256", "smoke")
# a lane whose latest row says this is concluded ground and is not re-run
CONCLUDED = ("negative", "inconclusive", "hit-unverified", "hit-verified", "superseded")
# a crosser's file: open, or renamed by the crosser steps once adjudicated
CROSSER_SUFFIXES = (".pending", ".noise-crosser", ".parity-fail")


def run_dir(lane: LaneSpec, base: Path | None = None) -> Path:
    return (base or RUNS_DIR) / lane.lane_id


def _atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, default=float) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _refuse(problems: list[str]) -> int:
    print("REFUSED:\n  " + "\n  ".join(problems), file=sys.stderr, flush=True)
    return 2


# ---------------------------------------------------------------- preflight


def smoke_problems(smoke: bool, base: Path | None) -> list[str]:
    """``--smoke`` skips Rules 2 and 3 and the gate; it may never write into the repository's
    runs/."""
    if not smoke or os.environ.get(SMOKE_OK_ENV) == "1":
        return []
    if Path(base or RUNS_DIR).resolve() == REPO_RUNS.resolve():
        return [
            f"--smoke skips the ledger, control, threshold and gate checks and may not write into "
            f"{REPO_RUNS}: point RUNEFORGE_RUNS (or base) at a scratch directory "
            f"({SMOKE_OK_ENV}=1 is for test harnesses only)"
        ]
    return []


def seed_cap_problems(lane: LaneSpec, max_seeds: int | None) -> list[str]:
    if max_seeds is None:
        return []
    out = []
    if max_seeds < 1:
        out.append(f"--max-seeds {max_seeds} must be >= 1")
    cap = lane.budget.max_seeds
    if cap is not None and max_seeds > cap:
        out.append(
            f"--max-seeds {max_seeds} exceeds the lane's budget.max_seeds {cap} (the PREREG "
            "budget; a bigger slice is a new budget, which goes to queue.json)"
        )
    return out


def seed_hi(lane: LaneSpec, max_seeds: int | None) -> int:
    """The exclusive end of this launch's slice: lo + min(--max-seeds, budget.max_seeds)."""
    lo, hi = lane.seed_range
    caps = [c for c in (max_seeds, lane.budget.max_seeds) if c is not None]
    return min(hi, lo + min(caps)) if caps else hi


def threshold_problems(lane: LaneSpec, row) -> list[str]:
    """Rule 3: the bar the sweep flags crossers at is the one the PREREG fixed in advance."""
    out = []
    if not row.threshold_fixed_in_advance:
        out.append(
            "Rule 3: the ledger row's threshold is not fixed in advance "
            "(threshold_fixed_in_advance must be true before the sweep runs)"
        )
    if row.threshold in (None, ""):
        out.append("Rule 3: the ledger row records no threshold")
        return out
    try:
        thr = float(row.threshold)
    except (TypeError, ValueError):
        out.append(f"Rule 3: the ledger row's threshold {row.threshold!r} is not a number")
        return out
    bar = lane.family_wise_bar
    if bar is not None and abs(thr - bar) > THRESHOLD_TOL:
        out.append(
            f"Rule 3: the ledger threshold {thr!r} is not the lane's family_wise_bar {bar!r}; "
            "the sweep flags crossers at the lane's bar, so the two must be the same number"
        )
    return out


def gate_problems(lane: LaneSpec, base: Path | None, lanes_dir: Path | None = None) -> list[str]:
    """The fingerprint gate passed, on >= gate.MIN_KEYS simulated keys, for the lane spec as
    it is now. Reads the newer of lanes/<id>/gate.json (committed) and runs/<id>/gate.json."""
    from runeforge.paths import LANES_DIR
    from runeforge.runner.gate import MIN_KEYS

    found = [
        p
        for p in (
            (lanes_dir or LANES_DIR) / lane.lane_id / "gate.json",
            run_dir(lane, base) / "gate.json",
        )
        if p.is_file()
    ]
    if not found:
        return [
            f"no gate.json for {lane.lane_id} (lanes/<id>/ or runs/<id>/): run `runeforge gate`"
        ]
    path = max(found, key=lambda p: p.stat().st_mtime)
    data = _read_json(path)
    out = []
    line = str(data.get("verdict_line") or "")
    if data.get("excluded") is not False or not line.startswith("GATE PASS"):
        out.append(
            f"{path}: the gate did not pass ({line or 'no verdict_line'}); "
            "an EXCLUDED (gate) lane is not swept"
        )
    n = data.get("n_seeds")
    if not isinstance(n, int):
        rows = data.get("per_seed_rows")
        n = len(rows) if isinstance(rows, list) else 0
    if n < MIN_KEYS:
        out.append(f"{path}: the gate simulated {n} keys, fewer than {MIN_KEYS}")
    if data.get("lane_pipeline_sha256") != control.lane_pipeline_sha256(lane):
        out.append(f"{path}: the lane spec changed since its gate ran; re-run `runeforge gate`")
    return out


def status_problems(row) -> list[str]:
    if row.status in CONCLUDED:
        return [
            f"the lane's latest ledger row is {row.status!r}: concluded ground is not re-run "
            "(a new lane id, or a superseding row, is the way back)"
        ]
    return []


def preflight(
    lane: LaneSpec,
    ledger_path: Path | None,
    smoke: bool,
    base: Path | None,
    lanes_dir: Path | None = None,
    max_seeds: int | None = None,
) -> list[str]:
    """Every reason this lane may not start now (empty = it may). A smoke run (test harness)
    skips only the family_wise_bar-vs-threshold_for comparison, so toy lanes can force
    crossers; every other lane check still applies."""
    problems = list(lane.runnable_problems(check_bar_vs_threshold=not smoke))
    problems += smoke_problems(smoke, base)
    problems += seed_cap_problems(lane, max_seeds)
    if not smoke:
        from runeforge.ledger import Ledger

        try:
            row = (Ledger(ledger_path) if ledger_path else Ledger()).get(lane.lane_id)
        except ValueError as exc:
            row = None
            problems.append(f"the ledger is unreadable: {exc}")
        else:
            if row is None:
                problems.append(f"no ledger row for {lane.lane_id}: pre-register it first")
        if row is not None:
            problems += status_problems(row)
            problems += control.control_problems(lane, row, lanes_dir)
            problems += threshold_problems(lane, row)
        problems += gate_problems(lane, base, lanes_dir)
    alive = live_sweeps(base, exclude_pid=os.getpid())
    if alive:
        problems.append(f"another sweep is alive: {alive} (never two jobs at once)")
    return problems


def pins(lane: LaneSpec, smoke: bool) -> dict:
    """What a checkpoint is only valid for: the bars, the pipeline and smoke-ness."""
    return {
        "claim_bar": lane.claim_bar,
        "family_wise_bar": lane.family_wise_bar,
        "lane_pipeline_sha256": control.lane_pipeline_sha256(lane),
        "smoke": smoke,
    }


def pin_problems(ckpt: dict, lane: LaneSpec, smoke: bool) -> list[str]:
    out = []
    for key, now in pins(lane, smoke).items():
        if key not in ckpt:
            out.append(f"checkpoint.json does not pin {key} (an older runner wrote it)")
        elif key == "smoke" and ckpt[key] != now:
            was, run = ("smoke" if ckpt[key] else "real"), ("smoke" if now else "real")
            out.append(f"checkpoint.json was written by a {was} run; this is a {run} run")
        elif ckpt[key] != now:
            out.append(f"checkpoint.json pins {key} = {ckpt[key]!r}; the lane now gives {now!r}")
    if out:
        out.append(
            "a sweep keeps the bars and pipeline it started with: restore the lane spec, or "
            "start over with --no-resume (archives checkpoint.json, status.json, sweep.jsonl)"
        )
    return out


def keystream_sha256(lane: LaneSpec, seed: int, n: int = 12956) -> str:
    k = pipeline.keys(lane, seed, n)
    return hashlib.sha256(",".join(map(str, k.tolist())).encode()).hexdigest()


def _lane_ref(lane_path: Path) -> str:
    """The lane path as reproduce commands name it: repo-relative when inside the repo."""
    p = Path(lane_path).resolve()
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(p)


@contextlib.contextmanager
def _sweep_lock(base: Path, wait_s: float) -> Iterator[bool]:
    """Exclusive flock on ``<base>/.sweep.lock``; yields False if it was not had in time."""
    base.mkdir(parents=True, exist_ok=True)
    with open(base / ".sweep.lock", "a+b") as fh:
        t_end = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= t_end:
                    yield False
                    return
                time.sleep(0.05)
        try:
            yield True
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _remove_own_pid(path: Path, pid: int) -> None:
    """Remove sweep.pid only while it holds ``pid``: never another process's file."""
    try:
        if int(path.read_text().strip()) == pid:
            path.unlink()
    except (OSError, ValueError):
        pass


# ---------------------------------------------------------------- the runner


class _Sweep:
    def __init__(
        self,
        lane: LaneSpec,
        lane_path: Path,
        base: Path,
        *,
        resume: bool,
        smoke: bool,
        ledger_path: Path | None,
        max_seeds: int | None,
        lanes_dir: Path | None,
        override_q5: str | None,
        stop: dict,
    ):
        self.lane, self.lane_path, self.base = lane, Path(lane_path), base
        self.resume, self.smoke, self.ledger_path = resume, smoke, ledger_path
        self.max_seeds, self.lanes_dir, self.override_q5 = max_seeds, lanes_dir, override_q5
        self.stop = stop
        self.rd = run_dir(lane, base)
        self.pid_path = self.rd / "sweep.pid"
        self.status_path = self.rd / "status.json"
        self.ckpt_path = self.rd / "checkpoint.json"
        self.rows_path = self.rd / "sweep.jsonl"
        self.pid = os.getpid()
        self.starttime = pid_starttime(self.pid)
        self.lo = lane.seed_range[0]
        self.hi = seed_hi(lane, max_seeds)
        self.lane_ref = _lane_ref(lane_path)
        start = lane.resume_cursor if lane.resume_cursor is not None else self.lo
        self.state: dict = {
            "cursor": start,
            "seeds_done": 0,
            "top": [],
            "crossers": 0,
            "kill_checked": False,
            "kill_condition": "no",
            "elapsed_s": 0.0,
        }
        self.top: list[tuple[float, int]] = []
        self.kill = "no"
        self.rate = 0.0
        self.deadline = 0.0
        self.elapsed0 = 0.0
        self.t_start = time.time()
        self.rows = None

    # -- reproduce commands
    def score_cmd(self, what: str) -> str:
        return f"runeforge score {self.lane_ref} {what}"

    @property
    def resume_cmd(self) -> str:
        if self.smoke:
            cmd = f"python -m runeforge.runner.sweep run {self.lane_ref} --smoke"
        else:
            cmd = f"runeforge sweep {self.lane_ref} --resume"
        if self.max_seeds is not None:
            cmd += f" --max-seeds {self.max_seeds}"
        if not self.smoke and self.ledger_path and Path(self.ledger_path) != LEDGER_PATH:
            cmd += f" --ledger {self.ledger_path}"
        return cmd

    # -- outputs
    def halt(self, why: str) -> None:
        if not self.stop["flag"]:
            self.stop["flag"], self.stop["why"] = True, why

    def elapsed(self) -> float:
        return self.elapsed0 + (time.time() - self.t_start)

    def write_status(self, done: bool, scoring_at: int | None = None, rate: float | None = None):
        st = self.state
        best = max(self.top) if self.top else (None, None)
        hours = self.lane.budget.wall_clock_hours
        _atomic_json(
            self.status_path,
            {
                "lane_id": self.lane.lane_id,
                "numbering": canon.LP2_NUMBERING,
                "pid": self.pid,
                "pid_starttime": self.starttime,
                "backend": "cpu",
                "smoke": self.smoke,
                "updated_epoch": int(time.time()),
                "deadline_epoch": int(self.deadline),
                "done": done,
                "kill_condition": self.kill,
                "stopped_by": self.stop["why"] or None,
                "cursor": st["cursor"],  # resume point: the last checkpointed seed
                "scoring_at": st["cursor"] if scoring_at is None else scoring_at,
                "seed_range": [self.lo, self.hi],
                "seeds_done": st["seeds_done"],
                "fraction": (st["cursor"] - self.lo) / max(self.hi - self.lo, 1),
                "seeds_per_s": self.rate if rate is None else rate,
                "best_score": best[0],
                "best_seed": best[1],
                "crossers": st["crossers"],
                "claim_bar": self.lane.claim_bar,
                "family_wise_bar": self.lane.family_wise_bar,
                "lane_pipeline_sha256": st.get("lane_pipeline_sha256"),
                "elapsed_s": self.elapsed(),
                "wall_clock_budget_s": hours * 3600 if hours else None,
                "max_seeds": self.max_seeds,
            },
        )

    def row(self, kind: str, reproduce: str, **data) -> str:
        line = {"type": kind, "lane_id": self.lane.lane_id, "smoke": self.smoke, **data}
        line.update(reproduce=reproduce, t=int(time.time()))
        return json.dumps(line) + "\n"

    def write_rows(self, lines: list[str]) -> None:
        if not lines:
            return
        self.rows.write("".join(lines))
        self.rows.flush()
        os.fsync(self.rows.fileno())

    def checkpoint(self) -> None:
        self.state["elapsed_s"] = self.elapsed()
        _atomic_json(self.ckpt_path, self.state)

    # -- phases
    def start(self) -> int | None:
        """Under the lock: preflight, checkpoint, PID file, first status.json. Returns the
        exit code to stop with, or None to go on to scoring."""
        lane = self.lane
        problems = preflight(
            lane,
            self.ledger_path,
            self.smoke,
            self.base,
            lanes_dir=self.lanes_dir,
            max_seeds=self.max_seeds,
        )
        if problems:
            return _refuse(problems)
        (self.rd / "crossers").mkdir(parents=True, exist_ok=True)
        if self.resume and self.ckpt_path.exists():
            ckpt = _read_json(self.ckpt_path)
            problems = pin_problems(ckpt, lane, self.smoke)
            if problems:
                return _refuse(problems)
            self.state.update(ckpt)
        elif not self.resume:
            _archive_previous(self.rd)
        self.state.update(pins(lane, self.smoke))
        self.state["numbering"] = canon.LP2_NUMBERING
        self.top = [tuple(x) for x in self.state["top"]]
        heapq.heapify(self.top)
        self.pid_path.write_text(f"{self.pid}\n")
        self.rows = open(self.rows_path, "a", encoding="utf-8")  # noqa: SIM115 (closed in run)

        self.elapsed0 = float(self.state.get("elapsed_s") or 0.0)
        self.t_start = time.time()
        hours = lane.budget.wall_clock_hours
        left = None
        if hours:
            left = hours * 3600 - self.elapsed0
            self.deadline = self.t_start + max(left, 0.0)

        kc = self.state.get("kill_condition", "no")
        if kc == "fired" and self.override_q5 is None:
            self.kill = "fired"
            self.halt("q5-kill-condition")
            self.write_status(False)
            print(
                "STOPPED: the lane's Q5 kill condition fired "
                f"({self.state.get('kill_detail')}); resuming needs a human decision: "
                '--override-q5 "<reason>"',
                file=sys.stderr,
                flush=True,
            )
            return 3
        if kc == "fired":
            detail = self.state.get("kill_detail")
            self.write_rows(
                [
                    self.row(
                        "override-q5",
                        self.resume_cmd,
                        reason=self.override_q5,
                        kill_detail=detail,
                        cursor=self.state["cursor"],
                    )
                ]
            )
            self.state.setdefault("q5_overrides", []).append(
                {"reason": self.override_q5, "epoch": int(time.time()), "kill_detail": detail}
            )
            self.state["kill_condition"] = "overridden"
            self.checkpoint()
        elif self.override_q5 is not None:
            print("note: --override-q5 ignored: Q5 has not fired", file=sys.stderr, flush=True)
        if self.state.get("kill_condition") == "overridden":
            self.kill = "overridden"

        if left is not None and left <= 0 and self.state["cursor"] < self.hi:
            self.halt("deadline")  # the lane's wall-clock budget is spent across launches
        else:
            _archive_killed_markers(self.rd)
        self.write_status(False)
        return None

    def loop(self) -> int:
        lane, st, stop = self.lane, self.state, self.stop
        cipher = pipeline.lane_cipher(lane)[: lane.window]
        scorer = presets.get(presets.split_preset(lane.preset)[0])
        top = self.top
        try:
            while st["cursor"] < self.hi and not stop["flag"]:
                c_lo = st["cursor"]
                c_hi = min(c_lo + lane.chunk_size, self.hi)
                t0 = last_beat = time.time()
                b = c_lo
                found: list[str] = []  # survivor/crosser rows: written with the chunk row
                chunk_best: tuple[float, int, np.ndarray] | None = None
                while b < c_hi:
                    if self.deadline and time.time() >= self.deadline:
                        self.halt("deadline")
                    if stop["flag"]:
                        break
                    # Python ints: 64-bit seed spaces reach past int64 (seeds up to 2**64 - 1)
                    seeds = list(range(b, min(b + BATCH, c_hi)))
                    plains = pipeline.decrypt(
                        lane, cipher[None, :], pipeline.keys_batch(lane, seeds, cipher.size)
                    )
                    scores = pipeline.score_batch(scorer, plains)
                    for s, v in zip(seeds, scores.tolist(), strict=True):
                        if len(top) < TOP_K:
                            heapq.heappush(top, (v, s))
                        elif v > top[0][0]:
                            heapq.heapreplace(top, (v, s))
                    i_best = int(np.argmax(scores))
                    if chunk_best is None or scores[i_best] > chunk_best[0]:
                        chunk_best = (
                            float(scores[i_best]),
                            seeds[i_best],
                            plains[i_best].copy(),
                        )
                    for idx in np.flatnonzero(scores > lane.claim_bar):
                        # language-agnostic stats for the decodes worth re-reading, never per trial
                        s, v, stats = seeds[idx], float(scores[idx]), decode_stats(plains[idx])
                        is_crosser = v > lane.family_wise_bar
                        kind = "crosser" if is_crosser else "survivor"
                        found.append(
                            self.row(kind, self.score_cmd(str(s)), seed=s, score=v, stats=stats)
                        )
                        if is_crosser:
                            st["crossers"] += 1
                            _write_pending(
                                lane, self.lane_ref, self.rd, s, v, stats=stats, smoke=self.smoke
                            )
                    b = seeds[-1] + 1
                    if time.time() - last_beat >= HEARTBEAT_S:
                        # overnight.sh kills a live job whose status.json goes stale
                        self.write_status(False, b, (b - c_lo) / max(time.time() - t0, 1e-9))
                        last_beat = time.time()
                if b < c_hi:
                    c_hi = b  # partial chunk: checkpoint exactly what was scored, nothing more
                st["seeds_done"] += c_hi - c_lo
                st["cursor"] = c_hi
                if c_hi > c_lo:
                    self.rate = (c_hi - c_lo) / max(time.time() - t0, 1e-9)
                st["top"] = sorted(top, reverse=True)
                self._check_q5(c_hi)
                best = max(top) if top else (None, None)
                if c_hi > c_lo and chunk_best is not None:
                    found.append(
                        self.row(
                            "chunk",
                            self.score_cmd(f"{c_lo}:{c_hi}"),
                            lo=c_lo,
                            hi=c_hi,
                            seeds_per_s=self.rate,
                            best_score=best[0],  # running best over the whole sweep
                            best_seed=best[1],
                            chunk_best_score=chunk_best[0],
                            chunk_best_seed=chunk_best[1],
                            stats=decode_stats(chunk_best[2]),  # of the chunk's best decode
                            crossers=st["crossers"],
                        )
                    )
                self.write_rows(found)  # immediately before the checkpoint: see the docstring
                self.checkpoint()
                if self.deadline and time.time() >= self.deadline and st["cursor"] < self.hi:
                    self.halt("deadline")
                self.write_status(False)
            done = st["cursor"] >= self.hi
            self.write_status(done)
            self.write_rows(
                [
                    self.row(
                        "done" if done else "stopped",
                        self.resume_cmd,
                        cursor=st["cursor"],
                        why=stop["why"],
                    )
                ]
            )
        except Exception as exc:  # every trial, including crashes, gets a SWEEPROW line
            self.write_rows(
                [self.row("crash", self.resume_cmd, cursor=st["cursor"], error=repr(exc))]
            )
            raise
        if self.kill == "fired":
            return 3
        if done:
            return 0
        return 143 if stop["why"] in ("SIGTERM", "SIGINT") else 1

    def _check_q5(self, cursor: int) -> None:
        st, kc = self.state, self.lane.kill_condition
        frac = (cursor - self.lo) / max(self.hi - self.lo, 1)
        if st.get("kill_checked") or frac < kc.at_fraction:
            return
        st["kill_checked"] = True
        slow = bool(kc.min_seeds_per_s and self.rate < kc.min_seeds_per_s)
        crowded = kc.max_crossers is not None and st["crossers"] > kc.max_crossers
        if slow or crowded:
            self.kill = "fired"
            st["kill_condition"] = "fired"
            st["kill_detail"] = {
                "at_fraction": frac,
                "cursor": cursor,
                "seeds_per_s": self.rate,
                "min_seeds_per_s": kc.min_seeds_per_s,
                "crossers": st["crossers"],
                "max_crossers": kc.max_crossers,
                "epoch": int(time.time()),
            }
            self.halt("q5-kill-condition")

    def close(self) -> None:
        if self.rows is not None:
            self.rows.close()
            self.rows = None


def run(
    lane_path: Path,
    resume: bool = True,
    smoke: bool = False,
    ledger_path: Path | None = None,
    base: Path | None = None,
    max_seeds: int | None = None,
    lanes_dir: Path | None = None,
    override_q5: str | None = None,
) -> int:
    lane = load_lane(lane_path)
    base_dir = Path(base) if base is not None else RUNS_DIR
    early = smoke_problems(smoke, base_dir)  # before anything is created under base_dir
    if override_q5 is not None and not override_q5.strip():
        early.append("--override-q5 needs a reason (it is recorded in sweep.jsonl)")
    if early:
        return _refuse(early)
    stop = {"flag": False, "why": ""}

    def _stop(signum, _frame):
        stop["flag"], stop["why"] = True, signal.Signals(signum).name

    sweep = _Sweep(
        lane,
        Path(lane_path),
        base_dir,
        resume=resume,
        smoke=smoke,
        ledger_path=ledger_path,
        max_seeds=max_seeds,
        lanes_dir=lanes_dir,
        override_q5=override_q5,
        stop=stop,
    )
    previous = {s: signal.signal(s, _stop) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        with _sweep_lock(base_dir, LOCK_WAIT_S) as locked:
            if not locked:
                return _refuse([f"{base_dir / '.sweep.lock'} is held by another launch"])
            code = sweep.start()
        if code is not None:
            return code
        return sweep.loop()
    finally:
        sweep.close()
        _remove_own_pid(sweep.pid_path, sweep.pid)
        for s, handler in previous.items():
            if handler is not None:
                signal.signal(s, handler)


def _archive_previous(rd: Path) -> None:
    """``--no-resume``: move the previous run's state aside, so the new sweep.jsonl is one
    contiguous run. crossers/ stays: a .pending file is a HIT_PROTOCOL.md work item and is
    never moved (the same seed crossing again keeps its existing file)."""
    old = [rd / n for n in ("checkpoint.json", "status.json", "sweep.jsonl")]
    old = [p for p in old if p.exists()]
    if not old:
        return
    dest = rd / f"previous-{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
    dest.mkdir()
    for p in old:
        os.replace(p, dest / p.name)


def _archive_killed_markers(rd: Path) -> None:
    """A relaunch that passed its preflight moves overnight.sh's KILLED-* markers into
    killed-history/ (the kill has been filed; the marker must not describe the new run)."""
    markers = sorted(p for p in rd.glob("KILLED-*") if p.is_file())
    if not markers:
        return
    hist = rd / "killed-history"
    hist.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    for m in markers:
        dest, n = hist / f"{stamp}-{m.name}", 1
        while dest.exists():
            dest, n = hist / f"{stamp}-{n}-{m.name}", n + 1
        os.replace(m, dest)


def _write_pending(
    lane: LaneSpec,
    lane_ref: str,
    rd: Path,
    seed: int,
    score: float,
    stats: dict | None = None,
    smoke: bool = False,
) -> None:
    """``crossers/<kid>.pending``, once: a crosser already open or already adjudicated
    (renamed .noise-crosser / .parity-fail by the crosser steps) is never re-opened.
    ``lane_ref`` is repo-relative when the lane lies inside the repo (crosser.py resolves it
    against REPO_ROOT), so the file works from a clean checkout."""
    kid = f"{lane.lane_id}-{seed}"
    path = rd / "crossers" / f"{kid}.pending"
    if any((rd / "crossers" / f"{kid}{suffix}").exists() for suffix in CROSSER_SUFFIXES):
        return
    from runeforge.ledger import data_sha256, git_sha

    _atomic_json(
        path,
        {
            "kid": kid,
            "status": "FLAGGED-FOR-ORACLE",
            "smoke": smoke,
            "lane_id": lane.lane_id,
            "lane_path": lane_ref,
            "seed": seed,
            "score": score,
            "stats": stats,
            "window": lane.window,
            "claim_bar": lane.claim_bar,
            "family_wise_bar": lane.family_wise_bar,
            "generator": pipeline.generator(lane).spec(),
            "combine": lane.combine,
            "key_offset": lane.key_offset,
            "ciphertext_view": lane.ciphertext_view,
            "preset": lane.preset,
            "pages": lane.pages,
            "keystream_sha256": keystream_sha256(lane, seed),
            "decode_record": crosser_decode_record(lane, seed),
            "git_sha": git_sha(),
            "data_sha256": data_sha256(),
            "numbering": canon.LP2_NUMBERING,
            "found_epoch": int(time.time()),
        },
    )


def record_budget(n: int) -> int:
    """Key symbols a crosser's decode record over ``n`` runes may use: n plus room for the
    anti-repeat skips (under p_keep = 0.19 their net excess over the interrupters is about
    2.8 % of the runes without interrupters, 1.3 % with every plaintext F one; n/8 covers
    either many times over), so a true key's path does not run out (fill) before the last
    page ends."""
    return n + n // 8 + 16


def crosser_decode_record(lane: LaneSpec, seed: int) -> dict | None:
    """A beam decoder's path over the lane's whole pages, for crosser step 6 (re-encipher);
    None under the rigid decoder (nothing to record)."""
    model = pipeline.beam_model(lane)
    if model is None:
        return None
    from runeforge import beam

    stream = pipeline.lane_cipher(lane)
    scorer = presets.get(presets.split_preset(lane.preset)[0])
    k = pipeline.keys(lane, seed, record_budget(stream.size))
    rec = beam.decode_record(stream, k, scorer, model).as_dict()
    rec["key_budget"] = int(k.size)
    rec["pages"] = list(lane.pages)
    return rec


# ---------------------------------------------------------------- detached launch


def _log_tail(path: Path, offset: int, n: int = 20) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-n:])


def launch_detached(
    lane_path: Path,
    resume: bool = True,
    smoke: bool = False,
    ledger_path: Path | None = None,
    base: Path | None = None,
    max_seeds: int | None = None,
    lanes_dir: Path | None = None,
    override_q5: str | None = None,
    wait_s: float = LAUNCH_WAIT_S,
) -> int:
    """setsid + nohup equivalent: the runner survives the shell and Claude's process tree.

    Returns 0 once the child has written status.json carrying its own PID (it passed its
    preflight under the lock) or has already finished cleanly; 2 if this preflight refuses,
    if the child exits first (the tail of sweep.log is printed) or if no status.json shows
    up within ``wait_s`` (the child is then terminated)."""
    lane_path = Path(lane_path).resolve()  # the child runs from the repo root
    ledger_path = Path(ledger_path).resolve() if ledger_path else None
    lanes_dir = Path(lanes_dir).resolve() if lanes_dir else None
    base_dir = Path(base).resolve() if base is not None else RUNS_DIR
    lane = load_lane(lane_path)
    problems = preflight(lane, ledger_path, smoke, base_dir, lanes_dir, max_seeds)
    if override_q5 is not None and not override_q5.strip():
        problems.append("--override-q5 needs a reason (it is recorded in sweep.jsonl)")
    if problems:
        return _refuse(problems)
    rd = run_dir(lane, base_dir)
    rd.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "runeforge.runner.sweep", "run", str(lane_path)]
    if not resume:
        cmd.append("--no-resume")
    if smoke:
        cmd.append("--smoke")
    if ledger_path:
        cmd += ["--ledger", str(ledger_path)]
    if lanes_dir:
        cmd += ["--lanes-dir", str(lanes_dir)]
    if max_seeds is not None:
        cmd += ["--max-seeds", str(max_seeds)]
    if override_q5 is not None:
        cmd += ["--override-q5", override_q5]
    env = dict(os.environ)
    env["RUNEFORGE_RUNS"] = str(base_dir)
    log_path = rd / "sweep.log"
    offset = log_path.stat().st_size if log_path.exists() else 0
    with open(log_path, "ab") as log, open(os.devnull, "rb") as devnull:
        proc = subprocess.Popen(
            cmd,
            stdin=devnull,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=REPO_ROOT,
            env=env,
            close_fds=True,
        )
    status_path = rd / "status.json"
    t_end = time.monotonic() + wait_s
    while True:
        rc = proc.poll()
        st = _read_json(status_path)
        mine = st.get("pid") == proc.pid
        terminal = bool(
            st.get("done") or st.get("stopped_by") or st.get("kill_condition") == "fired"
        )
        if rc is None and mine and not terminal:
            print(f"detached sweep {lane.lane_id}: pid {proc.pid}; status {status_path}")
            return 0
        if rc is not None:
            if rc == 0 and mine:
                print(f"sweep {lane.lane_id} (pid {proc.pid}) already finished; {status_path}")
                return 0
            print(
                f"REFUSED: the sweep child (pid {proc.pid}) exited with {rc} before running; "
                f"tail of {log_path}:\n{_log_tail(log_path, offset)}",
                file=sys.stderr,
            )
            return 2
        if time.monotonic() >= t_end:
            proc.terminate()  # our own child, never a PID read from a file
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            print(
                f"REFUSED: the sweep child (pid {proc.pid}) wrote no status.json within "
                f"{wait_s:g} s and was terminated; tail of {log_path}:\n"
                f"{_log_tail(log_path, offset)}",
                file=sys.stderr,
            )
            return 2
        time.sleep(0.05)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m runeforge.runner.sweep")
    ap.add_argument("mode", choices=("run", "launch"))
    ap.add_argument("lane")
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="test harnesses only: skip the ledger, control, threshold and gate checks; every "
        "output is marked smoke: true; refused into the repository's runs/ unless "
        f"{SMOKE_OK_ENV}=1",
    )
    ap.add_argument("--ledger")
    ap.add_argument("--lanes-dir", help="where lanes/<id>/{control,gate}.json live (lanes/)")
    ap.add_argument("--max-seeds", type=int)
    ap.add_argument(
        "--override-q5",
        metavar="REASON",
        help="resume a lane whose Q5 kill condition fired (a human decision; recorded)",
    )
    a = ap.parse_args(argv)
    kw = {
        "resume": not a.no_resume,
        "smoke": a.smoke,
        "ledger_path": Path(a.ledger) if a.ledger else None,
        "max_seeds": a.max_seeds,
        "lanes_dir": Path(a.lanes_dir) if a.lanes_dir else None,
        "override_q5": a.override_q5,
    }
    if a.mode == "launch":
        return launch_detached(Path(a.lane), **kw)
    return run(Path(a.lane), **kw)


if __name__ == "__main__":
    sys.exit(main())
