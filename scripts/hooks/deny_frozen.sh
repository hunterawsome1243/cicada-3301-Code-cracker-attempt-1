#!/usr/bin/env bash
# PreToolUse hook (OVERNIGHT_LOOP.md Part 1 §6; CLAUDE.md, Frozen toolbox): refuse any Edit, Write,
# MultiEdit, NotebookEdit or Bash call that would write a path listed in FROZEN.txt. Exit 2 blocks
# the call and stderr is shown to Claude as the reason; exit 0 allows it.
#
# Register it in .claude/settings.json by absolute path, through the project-dir variable:
#   "PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash", "hooks": [{"type":
#     "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/hooks/deny_frozen.sh"}]}]
# A relative command ("scripts/hooks/deny_frozen.sh") resolves against the session's current
# directory, which follows the Bash tool's `cd`; after a `cd runs` it no longer exists. A hook
# that cannot start exits 127, which Claude Code treats as a non-blocking error: the freeze then
# fails open until the session's directory is the project root again.
#
# The logic is frozen_guard.py, run as `python3 -I` (standard library only, no site packages, no
# subprocesses) because this fires before every tool call. The project root is
# $CLAUDE_PROJECT_DIR, else two levels above this script. No python3 on PATH warns and allows:
# a broken guard must never wedge a session. A FROZEN.txt that exists but cannot be decoded is
# the exception: write-capable calls are blocked until it is UTF-8 again.
here="${BASH_SOURCE[0]%/*}"
[ "$here" = "${BASH_SOURCE[0]}" ] && here="."
if ! command -v python3 >/dev/null 2>&1; then
  echo "deny_frozen: warning: python3 not found; frozen-path check skipped" >&2
  exit 0
fi
exec python3 -I "$here/frozen_guard.py"
