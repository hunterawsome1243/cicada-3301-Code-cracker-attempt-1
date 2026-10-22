#!/usr/bin/env bash
# Stop hook (OVERNIGHT_LOOP.md Part 1 §6): a session may not end while the ledger fails
# scripts/validate_ledger.py, or while a lane write-up it touched fails scripts/check_results.py.
# A write-up counts as touched (lanes/<id>/RESULTS.md, one level) when `git status` lists it as
# modified, added or untracked, or when a commit changed it that is not on the upstream branch yet
# (`git diff @{u}...HEAD`), or, with no upstream, a commit from the last 24 hours. Sessions commit
# before they stop (SESSION_PROMPT.md §C5, OVERNIGHT_LOOP.md), so committing a failing write-up
# does not get it past this gate. Exit 2 sends the failing output back to Claude, which keeps
# working; CLAUDE_CODE_STOP_HOOK_BLOCK_CAP in overnight.sh bounds how often. When
# stop_hook_active is true Claude is already continuing because of this hook, so it exits 0 at
# once instead of looping.
#
# A gate script that does not exist yet, a missing ledger or lanes/ directory, or a tree that is
# not a git work tree is skipped with a note, never failed. Each gate run is capped at 60 s.
# Interpreter: $RUNEFORGE_PYTHON if it resolves, else python3 (both gates are standard library
# only). Register it as "$CLAUDE_PROJECT_DIR"/scripts/hooks/stop_gate.sh (see deny_frozen.sh).
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

checked=$'\n'  # newline-delimited list of write-ups already checked (bash 3 has no assoc arrays)
check_results() {  # check one candidate path once, if it is an existing lanes/<id>/RESULTS.md
  local path="$1"
  [[ $path == lanes/*/RESULTS.md && $path != lanes/*/*/RESULTS.md ]] || return 0
  [ -f "$path" ] || return 0  # deleted
  [[ $checked == *$'\n'"$path"$'\n'* ]] && return 0
  checked+="$path"$'\n'
  run_gate "$py" scripts/check_results.py "$path"
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
  # 1. uncommitted: modified, added, renamed or untracked
  while IFS= read -r -d '' entry; do
    status="${entry:0:2}"
    if [[ $status == R* || $status == C* ]]; then
      IFS= read -r -d '' _ || true  # -z lists a rename's source path as its own entry
    fi
    check_results "${entry:3}"
  done < <(git status --porcelain -z --untracked-files=all -- lanes 2>/dev/null)
  # 2. committed but not pushed; with no upstream, committed in the last 24 hours
  if git rev-parse -q --verify '@{u}' >/dev/null 2>&1; then
    committed=(git diff -z --name-only --relative '@{u}...HEAD' -- lanes)
  else
    committed=(git log -z --since='24 hours ago' --name-only --format= --relative -- lanes)
  fi
  while IFS= read -r -d '' path; do
    path="${path#$'\n'}"  # some git versions start each commit's list with a newline
    [ -n "$path" ] && check_results "$path"
  done < <("${committed[@]}" 2>/dev/null)
fi

if [ "$failed" -ne 0 ]; then
  {
    echo "stop_gate: not done yet. Fix the problems these gates report (a ledger row: append a"
    echo "superseding row; a RESULTS.md: edit the write-up), re-run the gates until they pass"
    echo "(python scripts/validate_ledger.py; python scripts/check_results.py <the RESULTS.md>),"
    echo "then commit the fix. Committing alone does not pass this gate: write-ups in commits not"
    echo "yet pushed (or from the last 24 hours) are checked too."
    printf '%s' "$report"
  } >&2
  exit 2
fi
exit 0
