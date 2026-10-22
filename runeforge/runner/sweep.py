"""``runeforge sweep <lane.yaml> [--detach]``: the lane runner (CPU backend; GPU in Phase 3).

The ops contract overnight.sh relies on (OVERNIGHT_LOOP.md, Part 1):

* ``runs/<lane_id>/sweep.pid`` -- the runner's PID; its cmdline contains "runeforge";
* ``runs/<lane_id>/status.json`` -- rewritten atomically after every chunk, and at least
  every ``HEARTBEAT_S`` seconds inside one, with
  ``updated_epoch``, ``deadline_epoch``, ``done``, ``kill_condition`` (no | fired) and the
  resume ``cursor``;
* ``runs/<lane_id>/checkpoint.json`` -- the cursor and the running top-k; ``--resume`` is the
  default, so a killed run continues from the last completed chunk with no gap and no
  double count;
* ``runs/<lane_id>/sweep.jsonl`` -- one SWEEPROW per chunk, survivor, crosser, crash and
  end, each with its reproduce command;
* ``runs/<lane_id>/crossers/<kid>.pending`` -- every score above the family-wise bar, for
  HIT_PROTOCOL.md. The sweep never stops for a crosser.

The runner refuses to start a lane without calibrated bars, without a ledger row whose
positive control passed (Rule 2), or while another sweep is alive.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from runeforge import canon
from runeforge.lanes import LaneSpec, load_lane
from runeforge.paths import REPO_ROOT
from runeforge.runner import pipeline
from runeforge.runner.jobs import RUNS_DIR, live_sweeps, pid_alive_runeforge  # noqa: F401
from runeforge.scoring import presets

BATCH = 4096
TOP_K = 20
HEARTBEAT_S = 60  # status.json is rewritten at least this often, even inside a long chunk


def run_dir(lane: LaneSpec, base: Path | None = None) -> Path:
    return (base or RUNS_DIR) / lane.lane_id


def _atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, default=float) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def preflight(
    lane: LaneSpec, ledger_path: Path | None, smoke: bool, base: Path | None
) -> list[str]:
    problems = list(lane.runnable_problems())
    if not smoke:
        from runeforge.ledger import Ledger

        row = Ledger(ledger_path).get(lane.lane_id) if ledger_path else Ledger().get(lane.lane_id)
        if row is None:
            problems.append(f"no ledger row for {lane.lane_id}: pre-register it first")
        elif row.positive_control != "passed":
            problems.append("Rule 2: the ledger does not record a passing positive control")
    alive = live_sweeps(base, exclude_pid=os.getpid())
    if alive:
        problems.append(f"another sweep is alive: {alive} (never two jobs at once)")
    return problems


def keystream_sha256(lane: LaneSpec, seed: int, n: int = 12956) -> str:
    k = pipeline.keys(lane, seed, n)
    return hashlib.sha256(",".join(map(str, k.tolist())).encode()).hexdigest()


def run(
    lane_path: Path,
    resume: bool = True,
    smoke: bool = False,
    ledger_path: Path | None = None,
    base: Path | None = None,
    max_seeds: int | None = None,
) -> int:
    lane = load_lane(lane_path)
    problems = preflight(lane, ledger_path, smoke, base)
    if problems:
        print("REFUSED:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    rd = run_dir(lane, base)
    (rd / "crossers").mkdir(parents=True, exist_ok=True)
    (rd / "sweep.pid").write_text(f"{os.getpid()}\n")
    status_path, ckpt_path, rows_path = (
        rd / "status.json",
        rd / "checkpoint.json",
        rd / "sweep.jsonl",
    )

    lo, hi = lane.seed_range
    if max_seeds is not None or lane.budget.max_seeds is not None:
        hi = min(hi, lo + (max_seeds or lane.budget.max_seeds))
    state = {"cursor": lane.resume_cursor or lo, "seeds_done": 0, "top": [], "crossers": 0}
    if resume and ckpt_path.exists():
        state.update(json.loads(ckpt_path.read_text(encoding="utf-8")))
    elif not resume:
        _archive_previous(rd)
    started = time.time()
    deadline = started + lane.budget.wall_clock_hours * 3600 if lane.budget.wall_clock_hours else 0
    cipher = pipeline.lane_cipher(lane)[: lane.window]
    scorer = presets.get(presets.split_preset(lane.preset)[0])
    top = [tuple(x) for x in state["top"]]
    heapq.heapify(top)
    stop = {"flag": False, "why": ""}

    def _stop(signum, _frame):
        stop["flag"], stop["why"] = True, signal.Signals(signum).name

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    reproduce = f"runeforge sweep {lane_path} --resume"
    kill_checked = state.get("kill_checked", False)
    kill = "no"

    def write_status(done: bool, rate: float, scoring_at: int | None = None) -> None:
        best = max(top) if top else (None, None)
        _atomic_json(
            status_path,
            {
                "lane_id": lane.lane_id,
                "numbering": canon.LP2_NUMBERING,
                "pid": os.getpid(),
                "backend": "cpu",
                "updated_epoch": int(time.time()),
                "deadline_epoch": int(deadline),
                "done": done,
                "kill_condition": kill,
                "stopped_by": stop["why"] or None,
                "cursor": state["cursor"],  # resume point: the last checkpointed seed
                "scoring_at": state["cursor"] if scoring_at is None else scoring_at,
                "seed_range": [lo, hi],
                "seeds_done": state["seeds_done"],
                "fraction": (state["cursor"] - lo) / (hi - lo),
                "seeds_per_s": rate,
                "best_score": best[0],
                "best_seed": best[1],
                "crossers": state["crossers"],
                "claim_bar": lane.claim_bar,
                "family_wise_bar": lane.family_wise_bar,
            },
        )

    def sweeprow(rows, kind: str, **data) -> None:
        rows.write(
            json.dumps(
                {
                    "type": kind,
                    "lane_id": lane.lane_id,
                    **data,
                    "reproduce": reproduce,
                    "t": int(time.time()),
                }
            )
            + "\n"
        )
        rows.flush()

    rate = 0.0
    with open(rows_path, "a", encoding="utf-8") as rows:
        try:
            write_status(False, rate)
            while state["cursor"] < hi and not stop["flag"]:
                c_lo = state["cursor"]
                c_hi = min(c_lo + lane.chunk_size, hi)
                t0 = last_beat = time.time()
                b = c_lo
                while b < c_hi and not stop["flag"]:
                    seeds = np.arange(b, min(b + BATCH, c_hi), dtype=np.int64)
                    plains = pipeline.decrypt(
                        lane, cipher[None, :], pipeline.keys_batch(lane, seeds, cipher.size)
                    )
                    scores = pipeline.score_batch(scorer, plains)
                    for s, v in zip(seeds.tolist(), scores.tolist(), strict=True):
                        if len(top) < TOP_K:
                            heapq.heappush(top, (v, s))
                        elif v > top[0][0]:
                            heapq.heapreplace(top, (v, s))
                    for idx in np.flatnonzero(scores > lane.claim_bar):
                        s, v = int(seeds[idx]), float(scores[idx])
                        crosser = v > lane.family_wise_bar
                        sweeprow(rows, "crosser" if crosser else "survivor", seed=s, score=v)
                        if crosser:
                            state["crossers"] += 1
                            _write_pending(lane, lane_path, rd, s, v)
                    b = int(seeds[-1]) + 1
                    if time.time() - last_beat >= HEARTBEAT_S:
                        # overnight.sh kills a live job whose status.json goes stale
                        write_status(False, (b - c_lo) / max(time.time() - t0, 1e-9), b)
                        last_beat = time.time()
                if stop["flag"] and b < c_hi:
                    # partial chunk: checkpoint exactly what was scored, nothing more
                    c_hi = b
                state["seeds_done"] += c_hi - c_lo
                state["cursor"] = c_hi
                dt = max(time.time() - t0, 1e-9)
                rate = (c_hi - c_lo) / dt
                state["top"] = sorted(top, reverse=True)
                frac = (state["cursor"] - lo) / (hi - lo)
                if not kill_checked and frac >= lane.kill_condition.at_fraction:
                    kill_checked = True
                    kc = lane.kill_condition
                    if (kc.min_seeds_per_s and rate < kc.min_seeds_per_s) or (
                        kc.max_crossers is not None and state["crossers"] > kc.max_crossers
                    ):
                        kill = "fired"
                        stop["flag"], stop["why"] = True, "q5-kill-condition"
                state["kill_checked"] = kill_checked
                _atomic_json(ckpt_path, state)
                best = max(top) if top else (None, None)
                sweeprow(
                    rows,
                    "chunk",
                    lo=c_lo,
                    hi=c_hi,
                    seeds_per_s=rate,
                    best_score=best[0],
                    best_seed=best[1],
                    crossers=state["crossers"],
                )
                if deadline and time.time() > deadline:
                    stop["flag"], stop["why"] = True, "deadline"
                write_status(False, rate)
            done = state["cursor"] >= hi
            write_status(done, rate)
            sweeprow(rows, "done" if done else "stopped", cursor=state["cursor"], why=stop["why"])
        except Exception as exc:  # every trial, including crashes, gets a SWEEPROW line
            sweeprow(rows, "crash", cursor=state["cursor"], error=repr(exc))
            raise
    if kill == "fired":
        return 3
    return 0 if state["cursor"] >= hi else (143 if stop["why"] in ("SIGTERM", "SIGINT") else 1)


def _archive_previous(rd: Path) -> None:
    """``--no-resume``: move the previous run's state aside, so the new sweep.jsonl is one
    contiguous run and old crossers are never mixed with new ones."""
    old = [rd / n for n in ("checkpoint.json", "status.json", "sweep.jsonl", "crossers")]
    old = [p for p in old if p.exists()]
    if not old:
        return
    dest = rd / f"previous-{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
    dest.mkdir()
    for p in old:
        os.replace(p, dest / p.name)
    (rd / "crossers").mkdir()


def _write_pending(lane: LaneSpec, lane_path: Path, rd: Path, seed: int, score: float) -> None:
    kid = f"{lane.lane_id}-{seed}"
    path = rd / "crossers" / f"{kid}.pending"
    if path.exists():
        return
    from runeforge.ledger import data_sha256, git_sha

    _atomic_json(
        path,
        {
            "kid": kid,
            "status": "FLAGGED-FOR-ORACLE",
            "lane_id": lane.lane_id,
            "lane_path": str(lane_path),
            "seed": seed,
            "score": score,
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
            "git_sha": git_sha(),
            "data_sha256": data_sha256(),
            "numbering": canon.LP2_NUMBERING,
            "found_epoch": int(time.time()),
        },
    )


def launch_detached(
    lane_path: Path,
    resume: bool = True,
    smoke: bool = False,
    ledger_path: Path | None = None,
    base: Path | None = None,
    max_seeds: int | None = None,
) -> int:
    """setsid + nohup equivalent: the runner survives the shell and Claude's process tree."""
    lane_path = Path(lane_path).resolve()  # the child runs from the repo root
    ledger_path = Path(ledger_path).resolve() if ledger_path else None
    lane = load_lane(lane_path)
    problems = preflight(lane, ledger_path, smoke, base)
    if problems:
        print("REFUSED:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    rd = run_dir(lane, base)
    rd.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "runeforge.runner.sweep", "run", str(lane_path)]
    if not resume:
        cmd.append("--no-resume")
    if smoke:
        cmd.append("--smoke")
    if ledger_path:
        cmd += ["--ledger", str(ledger_path)]
    if max_seeds is not None:
        cmd += ["--max-seeds", str(max_seeds)]
    env = dict(os.environ)
    if base:
        env["RUNEFORGE_RUNS"] = str(base)
    with open(rd / "sweep.log", "ab") as log, open(os.devnull, "rb") as devnull:
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
    (rd / "sweep.pid").write_text(f"{proc.pid}\n")
    print(f"detached sweep {lane.lane_id}: pid {proc.pid}; status {rd / 'status.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m runeforge.runner.sweep")
    ap.add_argument("mode", choices=("run", "launch"))
    ap.add_argument("lane")
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="skip the ledger check (tests only)")
    ap.add_argument("--ledger")
    ap.add_argument("--max-seeds", type=int)
    a = ap.parse_args(argv)
    ledger = Path(a.ledger) if a.ledger else None
    if a.mode == "launch":
        return launch_detached(Path(a.lane), not a.no_resume, a.smoke, ledger, None, a.max_seeds)
    return run(Path(a.lane), not a.no_resume, a.smoke, ledger, max_seeds=a.max_seeds)


if __name__ == "__main__":
    sys.exit(main())
