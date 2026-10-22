#!/usr/bin/env bash
# overnight.sh — unattended runeforge iterations on the local WSL2 + RTX box.
#
# Launch:   tmux new -d -s loop "$HOME/runeforge/overnight.sh"
# Watch:    tmux attach -t loop        (Ctrl-b d to detach)
# Stop:     touch runs/overnight/STOP  (exits after the current iteration; GPU jobs keep running)
#
# Each iteration starts a FRESH `claude -p` session (clean context; CLAUDE.md + the ledger carry
# the state) with the prompt cut from OVERNIGHT_LOOP.md between the PROMPT-BEGIN/PROMPT-END markers.
# GPU jobs are never children of Claude: `runeforge sweep --detach` starts them with setsid nohup and
# tracks them with runs/<id>/sweep.pid + status.json. This script watches those files and kills only
# by a PID it has verified (a runeforge sweep cmdline, and the start time status.json recorded for it,
# so a recycled PID is never signalled). It never uses pkill -f.
set -uo pipefail

# ---------------------------------------------------------------- settings (override via env)
REPO="${REPO:-$HOME/runeforge}"
VENV="${VENV:-$REPO/.venv}"
MODEL="${MODEL:-sonnet}"                 # routine iterations; use opus/fable interactively for planning
MAX_TURNS="${MAX_TURNS:-60}"             # per iteration; the prompt tells Claude to plan inside it
ITER_BUDGET_USD="${ITER_BUDGET_USD:-6}"  # client-side estimate; a relative meter under a subscription
NIGHT_BUDGET_USD="${NIGHT_BUDGET_USD:-60}"
MAX_ITER="${MAX_ITER:-40}"
STOP_AT="${STOP_AT:-07:00}"              # local wall-clock hard stop
ITER_TIMEOUT_MIN="${ITER_TIMEOUT_MIN:-90}"   # SIGINT ends the turn cleanly; then SIGKILL after 2 min
SLEEP_BETWEEN="${SLEEP_BETWEEN:-120}"    # seconds between iterations (lets checkpoints land)
FAIL_LIMIT="${FAIL_LIMIT:-3}"            # consecutive non-zero exits / error_max_turns
STALL_LIMIT="${STALL_LIMIT:-3}"          # consecutive iterations with no commit and no ledger change
STALE_MIN="${STALE_MIN:-30}"             # status.json older than this while the PID is alive -> kill
MIN_DISK_GB="${MIN_DISK_GB:-20}"
NVSMI="${NVSMI:-/usr/lib/wsl/lib/nvidia-smi}"

# ---------------------------------------------------------------- environment for claude -p
export CLAUDE_CODE_RETRY_WATCHDOG=1                 # wait out 429/529 and 5-hour usage windows
export CLAUDE_CODE_RETRY_WATCHDOG_MAX_USAGE_LIMIT_WAIT_MS=$((6*3600*1000))  # a weekly limit ends the run
export CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=3            # a broken Stop gate cannot loop forever
export CLAUDE_CODE_TOOL_MEMORY_LIMIT=8G             # one runaway script cannot take the box
export CLAUDE_CODE_DISABLE_CRON=1                   # no /loop timers inside unattended sessions
unset ANTHROPIC_API_KEY                             # subscription login, never API billing, never --bare

cd "$REPO" || { echo "no repo at $REPO"; exit 2; }
# shellcheck disable=SC1091
set +u; source "$VENV/bin/activate" || { echo "no venv at $VENV"; exit 2; }; set -u
mkdir -p runs/overnight
DAY="$(date +%F)"
LOG="runs/overnight/$DAY.log"
COSTS="runs/overnight/$DAY.costs"
touch "$COSTS"
log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }
beat() { date +%s > runs/overnight/heartbeat; }

# ---------------------------------------------------------------- the iteration prompt
PROMPT="$(awk '/<!-- PROMPT-BEGIN -->/{f=1;next} /<!-- PROMPT-END -->/{f=0} f' OVERNIGHT_LOOP.md)"
[ -n "$PROMPT" ] || { log "PROMPT markers not found in OVERNIGHT_LOOP.md"; exit 2; }

# ---------------------------------------------------------------- helpers
stop_at_epoch() {
  local t; t="$(date -d "today $STOP_AT" +%s)"
  [ "$t" -le "$(date +%s)" ] && t="$(date -d "tomorrow $STOP_AT" +%s)"
  echo "$t"
}
STOP_EPOCH="$(stop_at_epoch)"

pid_is_runeforge() {            # $1 = pid, $2 = status.json (optional). True only if the PID is alive, its
  # cmdline is a runeforge sweep (not merely "runeforge"), and -- when status.json records pid_starttime
  # for this PID -- field 22 of /proc/<pid>/stat matches it: a recycled PID is not our job.
  # Same checks as runeforge/runner/jobs.py pid_alive_runeforge.
  local pid="$1" st="${2:-}" cmd spid want have
  { [ -n "$pid" ] && [ -r "/proc/$pid/cmdline" ]; } || return 1
  cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)" || return 1
  grep -Eq 'runeforge(\.runner\.sweep| sweep)' <<< "$cmd" || return 1
  { [ -n "$st" ] && [ -f "$st" ]; } || return 0
  spid="$(jq -r '.pid // empty' "$st" 2>/dev/null || true)"
  [ -z "$spid" ] || [ "$spid" = "$pid" ] || return 0   # status.json of another launch: nothing to compare
  want="$(jq -r '.pid_starttime // empty' "$st" 2>/dev/null || true)"
  [ -n "$want" ] || return 0
  have="$(sed -E 's/^.*\) //' "/proc/$pid/stat" 2>/dev/null | awk '{print $20}')"
  [ "$have" = "$want" ]
}

kill_job() {                    # $1 = run dir, $2 = reason
  local dir="$1" reason="$2" st="$1/status.json" pid
  pid="$(cat "$dir/sweep.pid" 2>/dev/null || true)"
  if pid_is_runeforge "$pid" "$st"; then
    log "KILL $dir pid=$pid reason=$reason"
    kill -TERM "$pid" 2>/dev/null
    for _ in $(seq 1 60); do pid_is_runeforge "$pid" "$st" || break; sleep 1; done
    pid_is_runeforge "$pid" "$st" && kill -KILL "$pid" 2>/dev/null
  fi
  echo "$(date '+%F %T') $reason" >> "$dir/KILLED-$reason"
}

watch_jobs() {                  # kill conditions; everything else is left for the next iteration to file
  local dir pid st now upd dl kc
  now="$(date +%s)"
  for pidfile in runs/*/sweep.pid; do
    [ -e "$pidfile" ] || continue
    dir="$(dirname "$pidfile")"; st="$dir/status.json"
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    pid_is_runeforge "$pid" "$st" || continue     # dead or recycled PIDs are filed by Claude, not killed by us
    [ -f "$st" ] || { log "WARN $dir alive without status.json"; continue; }
    [ "$(jq -r '.done // false' "$st" 2>/dev/null)" = "true" ] && continue   # finished; it is exiting
    upd="$(jq -r '.updated_epoch // 0' "$st")"; dl="$(jq -r '.deadline_epoch // 0' "$st")"
    kc="$(jq -r '.kill_condition // "no"' "$st")"
    if [ $((now - upd)) -gt $((STALE_MIN*60)) ]; then kill_job "$dir" "stale-status"
    elif [ "$dl" -gt 0 ] && [ "$now" -gt "$dl" ]; then kill_job "$dir" "deadline"
    elif [ "$kc" = "fired" ]; then kill_job "$dir" "q5-kill-condition"
    fi
  done
}

gpu_ok() { "$NVSMI" -L >/dev/null 2>&1; }
disk_gb() { df --output=avail -BG . | tail -1 | tr -dc '0-9'; }
night_cost() { awk '{s+=$1} END{printf "%.2f", s+0}' "$COSTS"; }
over_budget() { awk -v c="$(night_cost)" -v b="$NIGHT_BUDGET_USD" 'BEGIN{exit !(c>=b)}'; }
state_sig() { printf '%s %s' "$(git rev-parse HEAD 2>/dev/null)" "$(sha256sum ledger/ledger.jsonl 2>/dev/null | cut -c1-16)"; }
anchor() { pytest -q -m "not slow" >"runs/overnight/anchor.out" 2>&1 && python scripts/validate_ledger.py >>"runs/overnight/anchor.out" 2>&1; }

hard_stop_reason() {
  [ -e runs/overnight/STOP ] && { echo "STOP file"; return; }
  [ -e LEAD.md ] && { echo "LEAD.md exists — a human must adjudicate"; return; }
  [ -e PENDING-ADJUDICATION.md ] && { echo "PENDING-ADJUDICATION.md exists"; return; }
  [ -e runs/overnight/ANCHOR-RED ] && { echo "trust anchor red (see runs/overnight/ANCHOR-RED)"; return; }
  { [ "$(git log -1 --format=%H -- TOOLBOX_REQUESTS.md 2>/dev/null)" != "$TOOLBOX_SHA" ] || [ -n "$(git status --porcelain TOOLBOX_REQUESTS.md)" ]; } && { echo "TOOLBOX_REQUESTS.md changed — a human must decide"; return; }
  [ "$(date +%s)" -ge "$STOP_EPOCH" ] && { echo "STOP_AT $STOP_AT reached"; return; }
  over_budget && { echo "night budget $NIGHT_BUDGET_USD reached (est. $(night_cost))"; return; }
  [ "$(disk_gb)" -lt "$MIN_DISK_GB" ] && { echo "disk below ${MIN_DISK_GB}G"; return; }
  gpu_ok || { echo "nvidia-smi cannot see the GPU"; return; }
  [ "$(jq '[.[] | select(.approved==true)] | length' queue.json 2>/dev/null || echo 0)" -gt 0 ] || { echo "queue.json has nothing approved"; return; }
  echo ""
}

# ---------------------------------------------------------------- preflight
log "=== overnight loop start: model=$MODEL max_turns=$MAX_TURNS iter_budget=$ITER_BUDGET_USD night_budget=$NIGHT_BUDGET_USD stop_at=$STOP_AT ==="
command -v claude >/dev/null || { log "claude not on PATH"; exit 2; }
command -v jq >/dev/null || { log "jq missing (sudo apt install jq)"; exit 2; }
gpu_ok || { log "GPU not visible via $NVSMI"; exit 2; }
[ -z "$(git status --porcelain)" ] || { log "working tree dirty; finish or stash the last session first"; exit 2; }
if ! anchor; then log "trust anchor or ledger validator red at preflight; see runs/overnight/anchor.out"; exit 2; fi
rm -f runs/overnight/STOP
TOOLBOX_SHA="$(git log -1 --format=%H -- TOOLBOX_REQUESTS.md 2>/dev/null)"
beat

# ---------------------------------------------------------------- the loop
fails=0; stalls=0; iter=0
while [ "$iter" -lt "$MAX_ITER" ]; do
  iter=$((iter+1)); beat; watch_jobs
  reason="$(hard_stop_reason)"
  if [ -n "$reason" ]; then log "HARD STOP: $reason"; break; fi

  before="$(state_sig)"
  out="runs/overnight/iter-$DAY-$(printf '%02d' "$iter").json"
  log "--- iteration $iter (night est. \$$(night_cost)) ---"

  timeout -s INT -k 120 "${ITER_TIMEOUT_MIN}m" \
    claude -p "$PROMPT" \
      --model "$MODEL" \
      --permission-mode auto --permission-prompts none \
      --max-turns "$MAX_TURNS" --max-budget-usd "$ITER_BUDGET_USD" \
      --output-format json \
      > "$out" 2>"${out%.json}.err" &
  cpid=$!
  while kill -0 "$cpid" 2>/dev/null; do sleep 60; beat; watch_jobs; done
  wait "$cpid"; rc=$?

  subtype="$(jq -r '.subtype // "unknown"' "$out" 2>/dev/null || echo parse-error)"
  cost="$(jq -r '.total_cost_usd // 0' "$out" 2>/dev/null || echo 0)"
  sid="$(jq -r '.session_id // "?"' "$out" 2>/dev/null || echo '?')"
  result="$(jq -r '.result // ""' "$out" 2>/dev/null || true)"
  echo "$cost" >> "$COSTS"
  log "iteration $iter rc=$rc subtype=$subtype cost=$cost session=$sid"
  printf '%s\n' "$result" | grep -E '^(lane|verdict|needs Hunter|next lane|LOOP):' | while read -r l; do log "  $l"; done

  if [ "$rc" -ne 0 ] || [ "$subtype" != "success" ]; then
    fails=$((fails+1)); log "non-success ($fails/$FAIL_LIMIT)"
    [ "$fails" -ge "$FAIL_LIMIT" ] && { log "HARD STOP: $FAIL_LIMIT consecutive failures"; break; }
  else
    fails=0
  fi

  loopline="$(printf '%s\n' "$result" | grep -E '^LOOP: STOP' | tail -1 || true)"
  if [ -n "$loopline" ]; then log "HARD STOP: Claude said '$loopline'"; break; fi

  if [ "$(state_sig)" = "$before" ]; then
    stalls=$((stalls+1)); log "no commit and no ledger change ($stalls/$STALL_LIMIT)"
    [ "$stalls" -ge "$STALL_LIMIT" ] && { log "HARD STOP: $STALL_LIMIT iterations produced no row — progress mirage guard"; break; }
  else
    stalls=0
  fi

  [ -n "$(git status --porcelain)" ] && log "WARN tree left dirty by iteration $iter; next boot will see it"
  if ! anchor; then
    log "trust anchor red after iteration $iter; giving the next iteration one chance to repair"
    if [ -e runs/overnight/anchor.red ]; then log "HARD STOP: anchor red twice in a row"; break; fi
    touch runs/overnight/anchor.red
  else
    rm -f runs/overnight/anchor.red
  fi
  sleep "$SLEEP_BETWEEN"
done

beat
log "=== overnight loop end: iterations=$iter night est. \$$(night_cost); jobs alive: $(for p in runs/*/sweep.pid; do [ -e "$p" ] && pid_is_runeforge "$(cat "$p")" "$(dirname "$p")/status.json" && basename "$(dirname "$p")"; done | tr '\n' ' ') ==="
exit 0
