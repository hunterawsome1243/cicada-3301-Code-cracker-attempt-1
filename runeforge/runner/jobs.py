"""Detached-job bookkeeping shared by the sweep runner, ``runeforge status`` and overnight.sh.

A job is alive only if its PID exists AND its /proc cmdline names runeforge -- a recycled
PID belonging to something else is a dead job. Never kill by name (no pkill -f).
"""

from __future__ import annotations

import os
from pathlib import Path

from runeforge.paths import REPO_ROOT

RUNS_DIR = Path(os.environ.get("RUNEFORGE_RUNS", REPO_ROOT / "runs"))


def pid_alive_runeforge(pid: int) -> bool:
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
    except OSError:
        return False
    return b"runeforge" in cmd


def live_sweeps(base: Path | None = None, exclude_pid: int | None = None) -> list[tuple[str, int]]:
    out = []
    for pidfile in sorted((base or RUNS_DIR).glob("*/sweep.pid")):
        try:
            pid = int(pidfile.read_text().strip())
        except (OSError, ValueError):
            continue
        if pid != exclude_pid and pid_alive_runeforge(pid):
            out.append((pidfile.parent.name, pid))
    return out
