#!/usr/bin/env bash
# PreToolUse hook (OVERNIGHT_LOOP.md Part 1 §6; CLAUDE.md, Frozen toolbox): refuse any Edit, Write,
# MultiEdit, NotebookEdit or Bash call that would write a path listed in FROZEN.txt. Exit 2 blocks
# the call and stderr is shown to Claude as the reason; exit 0 allows it.
#
# The logic is frozen_guard.py, run as `python3 -I` (standard library only, no site packages, no
# subprocesses) because this fires before every tool call. The project root is
# $CLAUDE_PROJECT_DIR, else two levels above this script. No python3 on PATH warns and allows:
# a broken guard must never wedge a session.
here="${BASH_SOURCE[0]%/*}"
[ "$here" = "${BASH_SOURCE[0]}" ] && here="."
if ! command -v python3 >/dev/null 2>&1; then
  echo "deny_frozen: warning: python3 not found; frozen-path check skipped" >&2
  exit 0
fi
exec python3 -I "$here/frozen_guard.py"
