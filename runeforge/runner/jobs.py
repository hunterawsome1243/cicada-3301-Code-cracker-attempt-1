"""Detached-job bookkeeping shared by the sweep runner, ``runeforge status`` and overnight.sh.

A job is alive only if its PID exists, its /proc cmdline is a runeforge sweep (it contains
``runeforge.runner.sweep`` or ``runeforge sweep`` -- the bare word "runeforge" is not
enough), and, when the job's status.json records ``pid_starttime`` for that PID, the process
started at that moment (field 22 of /proc/<pid>/stat). A recycled PID is a dead job.
overnight.sh's ``pid_is_runeforge`` applies the same two checks. Never kill by name (no
pkill -f).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from runeforge.paths import REPO_ROOT

RUNS_DIR = Path(os.environ.get("RUNEFORGE_RUNS", REPO_ROOT / "runs"))
SWEEP_CMDLINE_MARKERS = (b"runeforge.runner.sweep", b"runeforge sweep")


def pid_starttime(pid: int) -> int | None:
    """Field 22 of /proc/<pid>/stat (clock ticks after boot), parsed after the last ')' so a
    comm containing spaces or parentheses cannot shift the fields; None if unreadable."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        return int(stat[stat.rindex(")") + 1 :].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def pid_alive_runeforge(pid: int, status: dict | None = None) -> bool:
    """True only if ``pid`` is a live runeforge sweep and, when ``status`` (the job's
    status.json) records ``pid_starttime`` for this PID, it started at that moment."""
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
    except OSError:
        return False
    if not any(m in cmd for m in SWEEP_CMDLINE_MARKERS):
        return False
    if status:
        want = status.get("pid_starttime")
        if want is not None and status.get("pid") in (None, pid):
            try:
                return pid_starttime(pid) == int(want)
            except (TypeError, ValueError):
                return False  # an unreadable start time cannot vouch for the PID
    return True


def read_status(run_dir: Path) -> dict:
    """``run_dir/status.json`` as a dict ({} if missing or unreadable)."""
    try:
        data = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def live_sweeps(base: Path | None = None, exclude_pid: int | None = None) -> list[tuple[str, int]]:
    out = []
    for pidfile in sorted((base or RUNS_DIR).glob("*/sweep.pid")):
        try:
            pid = int(pidfile.read_text().strip())
        except (OSError, ValueError):
            continue
        if pid != exclude_pid and pid_alive_runeforge(pid, read_status(pidfile.parent)):
            out.append((pidfile.parent.name, pid))
    return out
