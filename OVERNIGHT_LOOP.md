# OVERNIGHT_LOOP.md — unattended runeforge iterations on the local WSL2 + RTX machine

<!-- Two parts. Part 1 is for Hunter (how to launch, keep the box awake, what stops the loop, what
     kills a job). Part 2, between the PROMPT-BEGIN / PROMPT-END markers, is the iteration prompt that
     overnight.sh pipes into a fresh `claude -p` session each iteration. Keep the markers. -->

## Part 1 — operator notes (Hunter)

### Why it runs here and not in the cloud
Cloud scheduled tasks (Routines) run on Anthropic infrastructure from a fresh clone with no access to
local files or hardware, so they can never touch the RTX GPU. Desktop scheduled tasks and `/loop` need
the Desktop app open or an open session. The dependable primitive for GPU sweeps is a plain shell loop
in a tmux session inside WSL2 that starts a **fresh** `claude -p` session per iteration (clean context;
CLAUDE.md + the ledger carry the state), with the GPU job itself **detached** from Claude
(`setsid nohup`, PID file, `status.json`), because `-p` runs end their background commands at exit and
SIGTERM kills a Bash tool's whole process tree.

### One-time setup
1. `%USERPROFILE%\.wslconfig` (Windows side; then `wsl --shutdown` once to apply):
   ```
   [wsl2]
   vmIdleTimeout=-1
   memory=<about half your RAM, e.g. 32GB>
   processors=<physical cores you can spare>
   ```
2. `/etc/wsl.conf` (inside Ubuntu): `[boot]` `systemd=true` — optional, but it lets you run the loop as
   a user service later. tmux is enough to start with.
3. Windows must never sleep while a sweep runs (WSL hangs after sleep are a known, unfixed bug class):
   PowerShell as admin: `powercfg -change -standby-timeout-ac 0` and `powercfg -change -hibernate-timeout-ac 0`.
   Verify during a run with `powercfg /requests`. If you use the Claude Desktop app, its
   "Keep computer awake" toggle does the same job.
4. Never install a Linux NVIDIA driver inside WSL; only the Windows driver plus `cuda-toolkit-12-x`.
   `/usr/lib/wsl/lib/nvidia-smi` must list the GPU before you start.
5. Authentication: the loop uses your subscription login. Do **not** export `ANTHROPIC_API_KEY` in the
   loop shell (it would bill the API instead) and do **not** use `--bare` (it drops CLAUDE.md, hooks,
   skills and auto memory, and needs an API key). The retry watchdog makes a `-p` run wait out a 5-hour
   usage window instead of dying; a weekly limit that is days away ends the run (bounded by
   `CLAUDE_CODE_RETRY_WATCHDOG_MAX_USAGE_LIMIT_WAIT_MS`).
6. Enforcement hooks in `.claude/settings.json` (advisory text in CLAUDE.md is not enough; hooks are
   deterministic and fire in every permission mode, including unattended ones):
   ```json
   {
     "hooks": {
       "SessionStart": [{"hooks": [{"type": "command",
         "command": "echo \"export PATH=$CLAUDE_PROJECT_DIR/.venv/bin:$PATH\" >> \"$CLAUDE_ENV_FILE\""}]}],
       "PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
         "hooks": [{"type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/hooks/deny_frozen.sh"}]}],
       "Stop": [{"hooks": [{"type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/hooks/stop_gate.sh", "timeout": 120}]}]
     }
   }
   ```
   (`$CLAUDE_PROJECT_DIR`, not a relative path: the Bash tool's working directory moves, and a hook
   that cannot start fails open.) `scripts/hooks/deny_frozen.sh` reads the tool input JSON from stdin, extracts `tool_input.file_path`
   (or, for Bash, scans `tool_input.command` for every path listed in `FROZEN.txt` next to `sed -i`,
   `>`, `>>`, `mv`, `cp`, `rm`, `git checkout --`, `git restore`, `chmod`, `tee`), and exits 2 with the
   reason "frozen: write it to TOOLBOX_REQUESTS.md" when a frozen path would be written. Exit 0 otherwise.
   `scripts/hooks/stop_gate.sh` exits 0 immediately when `stop_hook_active` is true; otherwise it runs
   `python scripts/validate_ledger.py` and `python scripts/check_results.py` on every `lanes/*/RESULTS.md`
   that `git status --porcelain` shows as modified or that an unpushed commit (no upstream: a commit of
   the last 24 hours) changed -- committing a failing write-up does not pass the gate -- and exits 2
   with the failure text if any fails.
   `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=3` in `overnight.sh` keeps a broken gate from looping.

### Before bed (the human part of the budget split)
- Approve the night's lanes in `queue.json`: each entry needs `id`, `category` (instrument | bounded |
  redteam | closeout), `approved: true`, `gpu_hours_cap`, and `prereg_ready: true|false`. The loop never
  invents a lane, never runs an unapproved one, and never starts a lane that would need a
  `TOOLBOX_REQUESTS.md` entry. Keep the mix near 30/40/20/10 over a week, not per night.
- Make sure the tree is clean, `pytest -q -m "not slow"` is green, and no `LEAD.md` or
  `PENDING-ADJUDICATION.md` exists.
- Launch: `tmux new -d -s loop "$HOME/runeforge/overnight.sh"` (or set it as a Windows Task Scheduler
  "At log on" action: `wsl -d Ubuntu -- tmux new -d -s loop /home/<you>/runeforge/overnight.sh`).
  Watch with `tmux attach -t loop`; detach with `Ctrl-b d`.
- Stop gracefully: `touch runs/overnight/STOP` (the loop exits after the current iteration; running GPU
  jobs keep going on their own and get written up by the next session).

### Hard stop conditions (the loop exits; nothing is lost because every job checkpoints)
`STOP` file · `LEAD.md` or `PENDING-ADJUDICATION.md` exists (a human must look) · `TOOLBOX_REQUESTS.md`
changed (a human must decide) · trust anchor red at preflight, or red twice in a row · ledger validator
fails · `STOP_AT` clock reached · night budget reached (a client-side estimate under a subscription,
used as a relative meter) · `FAIL_LIMIT` consecutive non-zero exits or `error_max_turns` ·
`STALL_LIMIT` consecutive iterations with no new commit and no ledger change (the "progress mirage"
guard: an iteration that produces no row produced nothing) · free disk below `MIN_DISK_GB` ·
`nvidia-smi` cannot see the GPU · `queue.json` has nothing approved left.

### Kill conditions (a GPU job is killed, by PID only, and parked with its checkpoint cursor)
- `status.json` not updated for `STALE_MIN` minutes while the PID is alive (hung kernel, D3D12 stall).
- `status.json.deadline_epoch` passed (the PREREG wall-clock budget; the runner writes it at launch).
- The job's PREREG Q5 kill condition fired (`status.json.kill_condition == "fired"`); the runner stops
  itself, the next iteration records it as `parked` with cause, never as `negative`.
The script verifies `/proc/<pid>/cmdline` contains `runeforge` before sending SIGTERM, then SIGKILL after
60 s. It never uses `pkill -f`. Each kill leaves `runs/<id>/KILLED-<reason>` so the next iteration files it.

### Morning check (five minutes)
`tail -n 40 runs/overnight/$(date +%F).log` · `cat runs/overnight/heartbeat` (if it is hours old the VM
was suspended, not Claude) · `runeforge status --short` · `git log --oneline -10` · read every
CHECKPOINT block in `runs/overnight/iter-*.json` (`jq -r .result`) · then start an interactive session
with SESSION_PROMPT.md, whose boot step reads the `Rejections` first.

### Alternative for a supervised evening
`claude -p "/goal lanes/<id>/RESULTS.md exists, scripts/check_results.py prints PASS on it, the ledger
row for <id> validates, and the work is committed; or stop after 40 turns" --permission-mode auto
--permission-prompts none --output-format stream-json --verbose` — a fresh evaluator model judges
completion after each turn, with an explicit turn cap in the condition. Use this for one lane you want to
watch, not for the night.

## Part 2 — the iteration prompt (piped by overnight.sh; fresh session each time)

<!-- PROMPT-BEGIN -->
You are one unattended iteration of the runeforge overnight loop. Nobody is watching and nobody can
approve anything; anything that would need approval is denied and must not be retried. Your limit is
this session's `--max-turns`; plan to finish inside it and leave the tree clean. Do one unit of work,
end with the CHECKPOINT block from SESSION_PROMPT.md §C5, then one final line:
`LOOP: CONTINUE` or `LOOP: STOP <reason>`. Never write "hit", "solved" or "lead" anywhere except
inside HIT_PROTOCOL.md's own log files.

Order of work (take the first branch that applies, then stop):

0. Read `runs/overnight/REJECTIONS.md` and the `Rejections` section of `PICKUP-HERE.md` first. A rejected
   verify, a failed control or a NOISE-CROSSER from a previous iteration is the first thing you must know.
1. Boot exactly as SESSION_PROMPT.md §A (git state, trust anchor, `runeforge status --short`,
   `validate_ledger.py`). Trust anchor red: if the failing code is outside `FROZEN.txt`, make one repair
   commit and re-run; if it is still red, or the failure is in a frozen file, write
   `runs/overnight/ANCHOR-RED` with the output and end with `LOOP: STOP anchor red`.
2. Jobs. For every `runs/*/sweep.pid`: alive (`/proc/<pid>/cmdline` contains `runeforge`)? `status.json`
   fresh? A `KILLED-*` marker or a dead PID with a `running` row → set the row to `parked` with
   `parked_state` = the checkpoint cursor and the reason, commit, continue to the next branch.
   A finished job (`status.json.done == true`) → this iteration's unit of work is the write-up:
   SESSION_PROMPT.md §C4 (RESULTS.md, `check_results.py` PASS, verify-lane subagent) and §C5 (ledger row,
   PICKUP-HERE.md, commit). If verify-lane reports a `differs` that changes the verdict, write it to
   `runs/overnight/REJECTIONS.md` and leave the row `inconclusive`; the next iteration starts from it.
3. Crossers. Any `runs/*/crossers/*.pending` → run HIT_PROTOCOL.md steps 1–8 within this session's turn
   budget, without stopping the sweep and without announcing anything. Outcomes: NOISE-CROSSER or
   PARITY-FAIL → log it in `runs/<id>/crossers/`, append the row note, `LOOP: CONTINUE`;
   steps unfinished at the turn budget → write `PENDING-ADJUDICATION.md` (what was done, what remains,
   the exact commands), `LOOP: STOP pending adjudication`; all eight steps passed → write `LEAD.md` per
   HIT_PROTOCOL.md §5, set the row `hit-verified`, commit, `LOOP: STOP LEAD`.
4. Next lane. Take the first entry in `queue.json` with `approved: true` whose ledger status is
   `never-run` or `parked`, whose `gpu_hours_cap` ≤ 2 unless Hunter wrote a larger cap on that entry,
   and whose Q2 fact you can cite with a file path. Do SESSION_PROMPT.md §C2 (PREREG frozen and
   committed before any measurement; thresholds from `scripts/threshold_for.py`; expected false positives
   < 1), then §C3 steps 1–2 (gate, control). `EXCLUDED (gate)` or `INCONCLUSIVE (power)` → RESULTS.md,
   row, commit, `LOOP: CONTINUE`. Control passed → launch the sweep detached
   (`runeforge sweep lanes/<id>.yaml --detach`), confirm `sweep.pid` and `status.json` exist, set the row
   to `running` with the resume cursor, commit, `LOOP: CONTINUE`. Do not wait for the sweep.
   If a GPU job is already alive, do not launch another; take a CPU-only lane (red-team or closeout)
   from the queue instead, or `LOOP: CONTINUE` with nothing started.
5. Queue empty. Pick the cheapest closeout item (a finished run with no RESULTS.md, a row without
   `reopens_if`, a headline number nobody has re-derived) and do it as a closeout or red-team lane.
   Nothing left → `LOOP: STOP queue empty`.

Rules that override everything above: no lane without a frozen PREREG; no `negative` without a passed
control; no threshold edited after a result; no new sweep while a GPU job is alive; no edits to frozen
paths (write `TOOLBOX_REQUESTS.md` and `LOOP: STOP toolbox request`); no network fetches beyond the
vendored repos; no posting anywhere; never kill a process except by a PID you verified; never read a
decode and decide it is English. Read logs with `tail -n 20` or `grep`; never cat a sweep log.
<!-- PROMPT-END -->
