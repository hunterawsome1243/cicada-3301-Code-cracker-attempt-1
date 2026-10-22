#!/usr/bin/env bash
# Stop hook (OVERNIGHT_LOOP.md Part 1 §6): a session may not end while the ledger fails
# scripts/validate_ledger.py, or while a lane write-up it touched (any lanes/*/RESULTS.md that
# `git status` shows as modified, added or untracked) fails scripts/check_results.py. Exit 2 sends
# the failing output back to Claude, which keeps working; CLAUDE_CODE_STOP_HOOK_BLOCK_CAP in
# overnight.sh bounds how often. When stop_hook_active is true Claude is already continuing
# because of this hook, so it exits 0 at once instead of looping.
#
# A gate script that does not exist yet, a missing ledger or lanes/ directory, or a tree that is
# not a git work tree is skipped with a note, never failed. Interpreter: $RUNEFORGE_PYTHON if it
# resolves, else python3 (both gate scripts are standard library only).
set -u

payload=""
[ -t 0 ] || payload="$(cat)"
if [[ $payload =~ \"stop_hook_active\"[[:space:]]*:[[:space:]]*true ]]; then
  exit 0
fi

root="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$root" ]; then
  here="${BASH_SOURCE[0]%/*}"
  [ "$here" = "${BASH_SOURCE[0]}" ] && here="."
  root="$(cd "$here/../.." && pwd)"
fi
cd "$root" 2>/dev/null || { echo "stop_gate: cannot cd to '$root'; gate skipped" >&2; exit 0; }

py="${RUNEFORGE_PYTHON:-}"
if [ -z "$py" ] || ! command -v "$py" >/dev/null 2>&1; then
  py="python3"
fi
if ! command -v "$py" >/dev/null 2>&1; then
  echo "stop_gate: no python3 on PATH; gate skipped" >&2
  exit 0
fi
limit=()
command -v timeout >/dev/null 2>&1 && limit=(timeout 60)

failed=0
report=""
run_gate() {  # run one gate command; collect its output if it fails
  local out rc
  out="$(${limit[@]+"${limit[@]}"} "$@" 2>&1)"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    failed=1
    [ "$rc" -eq 124 ] && out+=$'\n'"(timed out after 60 s)"
    report+="--- ${*:2} (exit $rc)"$'\n'"$(printf '%s\n' "$out" | head -n 60)"$'\n'
  fi
}

if [ -f scripts/validate_ledger.py ]; then
  run_gate "$py" scripts/validate_ledger.py
else
  echo "stop_gate: scripts/validate_ledger.py not found; ledger check skipped" >&2
fi

if [ ! -f scripts/check_results.py ]; then
  echo "stop_gate: scripts/check_results.py not found; RESULTS.md check skipped" >&2
elif ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "stop_gate: not a git work tree; RESULTS.md check skipped" >&2
elif [ -d lanes ]; then
  while IFS= read -r -d '' entry; do
    status="${entry:0:2}"
    path="${entry:3}"
    if [[ $status == R* || $status == C* ]]; then
      IFS= read -r -d '' _ || true  # -z lists a rename's source path as its own entry
    fi
    [[ $path == lanes/*/RESULTS.md && $path != lanes/*/*/RESULTS.md ]] || continue
    [ -f "$path" ] || continue  # deleted
    run_gate "$py" scripts/check_results.py "$path"
  done < <(git status --porcelain -z --untracked-files=all -- lanes 2>/dev/null)
fi

if [ "$failed" -ne 0 ]; then
  {
    echo "stop_gate: not done yet. Fix what these gates report (a new superseding ledger row, or"
    echo "the RESULTS.md), re-run them, commit, then stop."
    printf '%s' "$report"
  } >&2
  exit 2
fi
exit 0
