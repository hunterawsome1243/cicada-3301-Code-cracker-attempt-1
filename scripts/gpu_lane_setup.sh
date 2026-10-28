#!/usr/bin/env bash
# Hunter's one-command setup for a GPU lane, run on the RTX machine (WSL2 Ubuntu) in a terminal:
#
#   git fetch origin && git checkout claude/busy-euler-gmxvfy   # or the branch that holds the lane
#   bash scripts/gpu_lane_setup.sh                              # lanes/P3-MT19937-PY27-ANTIREPEAT.yaml
#   bash scripts/gpu_lane_setup.sh [lanes/<id>.yaml] [--no-launch]
#
# It asks two questions, and only a person at a terminal can answer them (it refuses when stdin is
# not a terminal or when it runs inside a Claude session): typing "install" is your approval of
# TOOLBOX_REQUESTS.md TR-1, typing "go" is your queue approval and the launch. Each answer is printed
# with the time and named in the commit that records it. In order, stopping at the first failure:
#   1. Refuses at once if it will ask a question (a launch, or TR-1 not yet installed) and you are not at
#      a terminal; refuses a launch while the lane spec, its PREREG.md or queue.json has uncommitted
#      changes (commit your own amendment first; the script never commits those files). .venv with the GPU
#      extra (scripts/setup.sh with RUNEFORGE_GPU=1 until setup has completed once); nvidia-smi lists the
#      GPU; numba is not the simulator, sees the device and can compile for it (libNVVM from
#      cuda-toolkit-12-x); no sweep is alive; the lane has a queue.json entry and has never been
#      launched (ledger row never-run, no checkpoint): this script is for a lane's first launch only.
#   2. Trust anchor: pytest -q -m "not slow", runeforge canon --verify, the oracle self-test.
#   3. TR-1: after you type "install", copies the staged beam calibrations from reports/calib-staging/
#      into the frozen runeforge/scoring/calib/presets/ unchanged and marks TR-1 installed in
#      TOOLBOX_REQUESTS.md. Then threshold_for at the lane's N must reproduce the frozen family-wise
#      bar to 1e-6 (0 <= frozen - computed <= 1e-6; the P3 PREREG section 4 condition, otherwise the
#      lane does not run and is re-frozen), recorded in lanes/<id>/threshold_after_TR1.json;
#      `runeforge lane` and tests/test_calib.py must pass.
#   4. Re-runs the lane's positive control unless the sweep's own control checks already pass (the
#      ceiling must use the installed calibration's beta); the CPU preflight must then be clean.
#   5. The GPU tests (tests/test_gpu_beam.py, tests/test_gpu_mt.py); the real-device cases must have
#      run and passed in both files. Then
#      `python -m runeforge.gpu.parity <lane> --bench 1048576`: the parity record the GPU sweep requires
#      and the throughput number.
#   6. Budget: the lane's seeds at the effective rate (the bench's device rate with the sweep's own
#      per-batch host work, timed here, folded in), with a 25 % margin, against the smaller
#      of the lane's and queue.json's GPU-hour cap and the lane's wall clock; the rate must also be at
#      least 1.2 x the PREREG Q5 kill rate. Over the cap or wall clock -> raising it is your edit of
#      budget.gpu_hours_cap / budget.wall_clock_hours in lanes/<id>.yaml and gpu_hours_cap in
#      queue.json, plus a dated PREREG addendum, committed by you (those fields are outside
#      lane_pipeline_sha256, so the control and gate stay valid). Too close to the Q5 rate -> a larger cap
#      does not help. Then the
#      GPU sweep's own preflight must be clean.
#   7. Commits only the evidence paths (calibrations, TOOLBOX_REQUESTS.md, ledger, control, threshold
#      record, parity and bench copies under lanes/<id>/); anything else you changed stays uncommitted
#      and is listed. Every exit from here on pushes the branch.
#   8. After you type "go": launches `runeforge sweep <lane> --detach --backend gpu`, and only once it
#      runs sets "approved": true in queue.json and the ledger row to `running`, commits both and pushes
#      the branch. A refused launch approves nothing. The sweep runs only on a committed lane spec and
#      PREREG. --no-launch stops before this step.
#
# Never run two GPU jobs at once; keep WSL and Windows awake while the sweep runs (OVERNIGHT_LOOP.md
# Part 1). Re-running after a failure is safe: steps 3 and 4 are skipped when already done; the trust
# anchor, GPU tests, parity/bench and budget always re-run, and a re-run commits the refreshed parity
# and bench. After a launch the script refuses the lane; resuming or parking is a session's job.
set -euo pipefail
shopt -s nullglob
SELF="$(readlink -f "${BASH_SOURCE[0]}")"

LANE_ARG=""
LAUNCH=1
for a in "$@"; do
  case "$a" in
    --no-launch) LAUNCH=0 ;;
    -h|--help) awk 'NR > 1 && /^set -euo/ {exit} NR > 1' "$SELF"; exit 0 ;;
    *.yaml) LANE_ARG="$(realpath -m -- "$a")" ;;
    *) echo "unknown argument: $a (see --help)" >&2; exit 2 ;;
  esac
done
cd "$(dirname "$SELF")/.."
git rev-parse --show-toplevel >/dev/null 2>&1 || { echo "$(pwd) is not a git checkout" >&2; exit 2; }
LANE="lanes/P3-MT19937-PY27-ANTIREPEAT.yaml"
if [[ -n "$LANE_ARG" ]]; then LANE="$(realpath --relative-to=. "$LANE_ARG")"; fi
[[ -f "$LANE" ]] || { echo "no lane spec $LANE (is this the branch that holds it?)" >&2; exit 2; }

WHO="$(git config user.name 2>/dev/null || true)"
WHO="${WHO:-$(whoami)}"
say() { printf '\n== %s\n' "$*"; }
die() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }
require_terminal() {
  [[ -t 0 ]] || die "the approvals are Hunter's, typed at a terminal, and stdin is not one; nothing was answered"
  [[ -z "${CLAUDECODE:-}" ]] || die "the approvals are Hunter's: the script is running inside a Claude session; run it in your own terminal"
}
ask() {  # ask "<question>" "<word>": 0 only if a person types the word at a terminal
  require_terminal
  local reply=""
  read -r -p "$1 Type '$2' to continue: " reply || true
  echo "  answer: '$reply' ($(date -Is), $WHO at $(hostname))"
  [[ "$reply" == "$2" ]]
}
pycheck() {  # pycheck "<why it stops>" [args] <<'EOF' ...: the snippet exits 3 to stop, 0 to go on
  local why="$1" rc=0
  shift
  python - "$@" || rc=$?
  case "$rc" in
    0) ;;
    3) die "$why" ;;
    *) die "a check crashed (exit $rc, traceback above) before it could decide; it was checking: $why" ;;
  esac
}
check_no_live_sweep() {
  pycheck "another sweep is alive (one GPU job at a time): runeforge status --short" <<'EOF'
import sys
from runeforge.runner.jobs import live_sweeps
alive = live_sweeps()
print("live sweeps:", alive or "none")
sys.exit(3 if alive else 0)
EOF
}
PUSHED=0
push_branch() {  # once per run; armed as the EXIT trap after the step-7 commit
  (( PUSHED )) && return 0
  PUSHED=1
  if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
    if git push -q; then echo "pushed"; else echo "push failed: run 'git push' yourself so the evidence reaches GitHub"; fi
  else
    echo "no upstream branch: run 'git push -u origin HEAD' so the evidence reaches GitHub"
  fi
}

# ---------------------------------------------------------------- 1. environment
say "1/8 environment"
TR1_PENDING=0
for f in reports/calib-staging/*.json; do
  cmp -s "$f" "runeforge/scoring/calib/presets/$(basename "$f")" || TR1_PENDING=1
done
if [[ "$LAUNCH" == "1" || "$TR1_PENDING" == "1" ]]; then require_terminal; fi
amend_paths=("$LANE" "$(dirname "$LANE")/$(basename "$LANE" .yaml)/PREREG.md" queue.json)
if [[ "$LAUNCH" == "1" ]] && ! git diff --quiet HEAD -- "${amend_paths[@]}"; then
  git --no-pager diff --stat HEAD -- "${amend_paths[@]}"
  die "the lane spec, its PREREG.md or queue.json has uncommitted changes (above). The sweep runs only on
committed files, and the script never commits them for you. If they are your amendment (e.g. a budget raise
with its dated PREREG addendum), commit them yourself:
  git add ${amend_paths[*]} && git commit -m 'lane: amendment (<what and why>)'
and re-run; \"approved\" in queue.json is set by step 8 after you type go, not by hand"
fi
if [[ ! -x .venv/bin/python || ! -f .venv/.runeforge-setup-ok ]]; then
  echo "setup is not recorded as complete on this .venv (no .venv/.runeforge-setup-ok): running scripts/setup.sh"
  echo "with the GPU extra (idempotent: vendored sources, corpora, trust anchor)"
  base=""
  if [[ -x .venv/bin/python ]]; then  # reuse an existing 3.11+ venv's interpreter instead of rebuilding it
    base="$(.venv/bin/python -c 'import sys; print(sys._base_executable) if sys.version_info >= (3, 11) else sys.exit(1)' 2>/dev/null || true)"
  fi
  PYTHON="${PYTHON:-${base:-python3}}" RUNEFORGE_GPU=1 bash scripts/setup.sh || die "scripts/setup.sh failed (see above)"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -c 'import numba' 2>/dev/null || python -m pip install -q -e ".[dev,gpu]" sympy

NVSMI=/usr/lib/wsl/lib/nvidia-smi
[[ -x "$NVSMI" ]] || NVSMI="$(command -v nvidia-smi || true)"
[[ -n "$NVSMI" ]] || die "nvidia-smi not found (WSL: /usr/lib/wsl/lib/nvidia-smi comes with the Windows driver)"
"$NVSMI" -L || die "nvidia-smi does not list a GPU"
rc=0
python - <<'EOF' || rc=$?
import sys
from numba.core import config
if config.ENABLE_CUDASIM:
    sys.exit(4)
from numba import cuda
from numba.cuda.cudadrv import driver, nvvm
from numba.cuda.cudadrv.error import CudaSupportError
try:  # cuda.is_available() is driver AND libNVVM, so test the two halves apart
    drv_ok = driver.driver.is_available
except CudaSupportError:
    drv_ok = False
if not drv_ok:
    print("driver:", driver.driver.initialization_error)
    sys.exit(5)
cuda.detect()
if not nvvm.is_available():
    sys.exit(6)
def probe(a):
    a[0] = 1
try:
    cuda.compile_ptx(probe, "void(int64[:])", cc=(7, 5))
except Exception as exc:  # NvvmSupportError and kin: the compiler, not the device
    print(f"{type(exc).__name__}: {exc}")
    sys.exit(6)
print("numba: CUDA device available, kernels compile")
EOF
case "$rc" in
  0) ;;
  4) die "NUMBA_ENABLE_CUDASIM is set in this shell: unset it and re-run (a lane never runs on numba's simulator)" ;;
  5) die "numba sees no CUDA device (see above): the Windows NVIDIA driver's libcuda (/usr/lib/wsl/lib) is not
usable from WSL. Update the Windows driver; never install a Linux display driver inside WSL" ;;
  6) die "numba cannot compile for the GPU (libNVVM not found, see above): install the CUDA toolkit inside
WSL, toolkit only (never conda, never a Linux display driver): https://developer.nvidia.com/cuda-downloads ->
Linux / x86_64 / WSL-Ubuntu, package cuda-toolkit-12-x; then re-run this script" ;;
  *) die "the CUDA probe crashed (exit $rc, traceback above)" ;;
esac
read -r ID RD < <(python - "$LANE" <<'EOF'
import sys
from runeforge.lanes import load_lane
from runeforge.runner.sweep import run_dir
lane = load_lane(sys.argv[1])
print(lane.lane_id, run_dir(lane))
EOF
) || die "could not load the lane spec $LANE (see the error above)"
echo "lane $ID (run directory $RD)"
check_no_live_sweep
pycheck "this lane is not at its first launch (see above): resuming or parking it is a session's job, not this script's" "$LANE" "$RD" <<'EOF'
import sys
from pathlib import Path
from runeforge.lanes import load_lane
from runeforge.ledger import Ledger
from runeforge.queue import load_queue
lane, rd = load_lane(sys.argv[1]), Path(sys.argv[2])
bad = []
row = Ledger().get(lane.lane_id, strict=False)
if row is None:
    bad.append("no ledger row: pre-register it first (runeforge ledger append --lane <yaml>)")
elif row.status != "never-run":
    bad.append(f"its ledger row is {row.status!r}, not 'never-run'")
if (rd / "checkpoint.json").exists():
    bad.append(f"{rd / 'checkpoint.json'} exists: a sweep of this lane has started before")
if not [e for e in load_queue() if e.id == lane.lane_id]:
    bad.append("queue.json has no entry for it (the approval in step 8 is recorded there)")
for b in bad:
    print("  refused:", b)
sys.exit(3 if bad else 0)
EOF
other="$(git status --porcelain)"
if [[ -n "$other" ]]; then
  echo "note: the working tree has changes; only the evidence paths are committed by this script:"
  sed 's/^/  /' <<< "$other"
fi

# ---------------------------------------------------------------- 2. trust anchor
say "2/8 trust anchor"
out="$(pytest -q -m "not slow" 2>&1)" || { echo "$out" | tail -20; die "the trust anchor is red: repair first (SESSION_PROMPT.md section A)"; }
echo "$out" | tail -1
runeforge canon --verify | tail -1 || die "canon pins do not verify"
python -m runeforge.oracle --selftest | tail -1 || die "oracle self-test failed"

# ---------------------------------------------------------------- 3. TR-1
say "3/8 TR-1: the staged beam calibrations"
STAGED=(reports/calib-staging/*.json)
(( ${#STAGED[@]} )) || die "no staged calibrations in reports/calib-staging/"
missing=()
for f in "${STAGED[@]}"; do
  cmp -s "$f" "runeforge/scoring/calib/presets/$(basename "$f")" || missing+=("$f")
done
TR1_NOTE=""
if (( ${#missing[@]} )); then
  for f in "${missing[@]}"; do
    if [[ -e "runeforge/scoring/calib/presets/$(basename "$f")" ]]; then
      echo "  $f  (REPLACES a different installed file)"
    else
      echo "  $f"
    fi
  done
  sha256sum "${missing[@]}" | sed 's/^/  sha256 /'
  echo "These go into runeforge/scoring/calib/presets/ unchanged (TOOLBOX_REQUESTS.md TR-1)."
  ask "Approve TR-1 and install them?" "install" || die "TR-1 not approved; nothing installed"
  TR1_NOTE="TR-1 approved by $WHO typing 'install' at a terminal on $(hostname), $(date -Is)."
  for f in "${missing[@]}"; do cp -p "$f" runeforge/scoring/calib/presets/; done
  for f in "${missing[@]}"; do
    cmp "$f" "runeforge/scoring/calib/presets/$(basename "$f")" || die "copy of $f differs"
  done
  python - "$TR1_NOTE" <<'EOF'
import sys
from pathlib import Path
p = Path("TOOLBOX_REQUESTS.md")
text = p.read_text(encoding="utf-8")
head = "## TR-1 (2026-10-22): install the beam decoders' calibrations — open"
if head in text:
    new = head.removesuffix("open") + "installed. " + sys.argv[1]
    p.write_text(text.replace(head, new, 1), encoding="utf-8")
    print("TOOLBOX_REQUESTS.md: TR-1 marked installed")
else:
    print("TOOLBOX_REQUESTS.md: no open TR-1 heading; left as it is")
EOF
else
  echo "already installed (byte-identical)"
fi
pycheck "the installed calibration does not reproduce the lane's frozen family-wise bar to 1e-6 (see above): per the PREREG the lane does not run; it is re-frozen first (dated addendum or re-registration)" "$LANE" "lanes/$ID/threshold_after_TR1.json" <<'EOF'
import hashlib, json, sys
from pathlib import Path
from runeforge.lanes import load_lane
from runeforge.scoring import calib, presets
lane = load_lane(sys.argv[1])
scorer, decoder = presets.split_preset(lane.preset)
rec_path = Path("runeforge/scoring/calib/presets") / f"{scorer}__{decoder}__L{lane.window}.json"
t = calib.threshold_for(lane.n_trials, lane.preset, lane.window, **lane.small_n_nulls())
c = calib.threshold_for(10**6, lane.preset, lane.window)
gap = lane.family_wise_bar - t.bar
out = {
    "lane_id": lane.lane_id,
    "numbering": "LP2-0-57",
    "calibration": str(rec_path),
    "calibration_sha256": hashlib.sha256(rec_path.read_bytes()).hexdigest() if rec_path.exists() else None,
    "threshold_for": t.as_dict(),
    "threshold_for_1e6": c.as_dict(),
    "frozen_family_wise_bar": lane.family_wise_bar,
    "frozen_claim_bar": lane.claim_bar,
    "frozen_minus_computed": gap,
    "reproduced_to_1e-6": 0 <= gap <= 1e-6,
}
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
print(f"threshold_for(N={lane.n_trials:,}) = {t.bar!r}; frozen {lane.family_wise_bar}; "
      f"frozen - computed = {gap:.3g} (must be in [0, 1e-6]); at 10^6: {c.bar!r} "
      f"(claim bar {lane.claim_bar}) -> {sys.argv[2]}")
sys.exit(0 if out["reproduced_to_1e-6"] else 3)
EOF
runeforge lane "$LANE" || die "the lane is not runnable with the installed calibration (see above)"
pytest -q tests/test_calib.py | tail -1 || die "tests/test_calib.py failed with the installed calibration"

# ---------------------------------------------------------------- 4. control with the installed beta
say "4/8 positive control with the installed calibration"
rc=0
python - "$LANE" <<'EOF' || rc=$?
import sys
from runeforge.lanes import load_lane
from runeforge.ledger import Ledger
from runeforge.runner import control
from runeforge.runner.sweep import beam_control_problems
lane = load_lane(sys.argv[1])
try:
    row = Ledger().get(lane.lane_id, strict=False)
except ValueError:
    row = None
bad = control.control_problems(lane, row) + beam_control_problems(lane)
for b in bad:
    print("  control needs a re-run:", b)
sys.exit(3 if bad else 0)
EOF
case "$rc" in
  0) echo "the control already passed with the installed calibration (the sweep's own checks)" ;;
  3) runeforge control "$LANE" || die "runeforge control failed or did not pass (see above). A control that
ran and failed makes the lane INCONCLUSIVE (power): do not lower the bar. Any other error is not a verdict"
     python - "$ID" <<'EOF' || die "the control passed, but correcting the ledger note failed (see above)"
import sys
from runeforge.ledger import Ledger
stale = ("The control in this row ran with the per-plant beta (TR-1 not installed); "
         "scripts/gpu_lane_setup.sh re-runs it with the installed beta.")
led = Ledger()
row = led.get(sys.argv[1], strict=False)
if row is not None and row.notes and stale in row.notes:
    fresh = ("The control was re-run with the installed calibration's beta by scripts/gpu_lane_setup.sh "
             f"({(row.control_detail or {}).get('path', 'lanes/<id>/control.json')}).")
    led.update(sys.argv[1], notes=row.notes.replace(stale, fresh))
    print("ledger: note on the control corrected")
EOF
     ;;
  *) die "could not check the control (exit $rc, traceback above)" ;;
esac
pycheck "the CPU preflight refuses the lane (see above)" "$LANE" <<'EOF'
import sys
from runeforge.lanes import load_lane
from runeforge.runner.sweep import RUNS_DIR, preflight
lane = load_lane(sys.argv[1])
problems = preflight(lane, None, False, RUNS_DIR)
for p in problems:
    print("  refused:", p)
print("CPU preflight:", "clean" if not problems else f"{len(problems)} problem(s)")
sys.exit(3 if problems else 0)
EOF

# ---------------------------------------------------------------- 5. GPU parity and bench
say "5/8 GPU tests, parity record and benchmark"
check_no_live_sweep
out="$(PYTEST_ADDOPTS='' pytest -q -rA --color=no tests/test_gpu_beam.py tests/test_gpu_mt.py 2>&1)" || { echo "$out" | tail -30; die "GPU tests failed"; }
echo "$out" | tail -1
if grep -q "no CUDA device" <<< "$out"; then
  die "the device tests were skipped ('no CUDA device'): the parity record would not be real"
fi
for f in tests/test_gpu_beam.py tests/test_gpu_mt.py; do
  grep -q "^PASSED $f::test_the_cuda_kernel_on_the_device" <<< "$out" \
    || die "no real-device test of $f passed (none ran: check PYTEST_ADDOPTS, -m or -k): the parity record would not be backed"
done
T0="$(date +%s)"
if ! python -m runeforge.gpu.parity "$LANE" --bench 1048576; then
  if python - "$RD/parity.json" "$T0" <<'EOF'
import json, os, sys
p = sys.argv[1]
try:
    fresh = os.path.getmtime(p) >= int(sys.argv[2])
    rec = json.load(open(p, encoding="utf-8"))
except (OSError, ValueError):
    sys.exit(1)
sys.exit(0 if fresh and rec.get("status") == "passed" and not rec.get("simulated") else 1)
EOF
  then
    die "parity passed on the device but the benchmark failed (see above); no sweep without a measured rate"
  fi
  die "GPU parity did not pass (see above): the kernels disagree with the CPU reference on this device, or the device could not run them; no sweep"
fi
echo "TR-6: the device tests and parity passed on this GPU. Freezing the kernels is your call: add TR-6's"
echo "      five lines (TOOLBOX_REQUESTS.md) to FROZEN.txt yourself if you want them frozen."

# ---------------------------------------------------------------- 6. budget
say "6/8 budget"
rc=0
python - "$LANE" <<'EOF' || rc=$?
import json, sys
from runeforge.lanes import load_lane
from runeforge.queue import load_queue
from runeforge.runner.sweep import run_dir
lane = load_lane(sys.argv[1])
rd = run_dir(lane)
par = json.loads((rd / "parity.json").read_text())
b = json.loads((rd / "bench.json").read_text())
if par.get("status") != "passed" or par.get("simulated"):
    print("  the parity record is not a real-device pass")
    sys.exit(12)
rate, basis = b.get("gpu_chain_keys_per_s"), "keys generated and scored on the device"
if not rate:
    rate, basis = b.get("cpu_keygen_end_to_end_keys_per_s"), "CPU keys, device scoring"
if not rate:
    print("  bench.json holds no end-to-end rate")
    sys.exit(12)
import heapq, time
import numpy as np
from runeforge.runner.sweep import BATCH, TOP_K
# the sweep's own host work per batch (sweep.py loop: seeds list, tolist, top-K heap, argmax,
# flatnonzero), which the bench's device-chain rate leaves out; the CPU re-decodes of each chunk's
# best and of survivors (a handful per 16.7M-seed chunk) are left out as negligible
scores = np.random.default_rng(0).normal(-6.46, 0.05, BATCH)
top, reps = [], 300
t0 = time.perf_counter()
for r in range(reps):
    seeds = list(range(r * BATCH, (r + 1) * BATCH))
    for s, v in zip(seeds, scores.tolist(), strict=True):
        if len(top) < TOP_K:
            heapq.heappush(top, (v, s))
        elif v > top[0][0]:
            heapq.heapreplace(top, (v, s))
    int(np.argmax(scores))
    np.flatnonzero(scores > lane.claim_bar)
host_s = (time.perf_counter() - t0) / reps
bench_rate = rate
rate = BATCH / (BATCH / bench_rate + host_s)
basis += f"; bench {bench_rate:,.0f}/s with {host_s * 1e3:.2f} ms host work per {BATCH}-seed batch"
n = lane.n_trials
hours = n / rate / 3600
entry = [e for e in load_queue() if e.id == lane.lane_id]
caps = [x for x in (lane.budget.gpu_hours_cap, entry[0].gpu_hours_cap if entry else None) if x]
cap = min(caps) if caps else 0.0
wall = lane.budget.wall_clock_hours or float("inf")
kill = lane.kill_condition.min_seeds_per_s or 0
print(f"device {par.get('device_name')}: effective {rate:,.0f} seeds/s ({basis}) -> {n:,} seeds in "
      f"{hours:.2f} h; cap {cap} GPU-h (lane {lane.budget.gpu_hours_cap}, queue "
      f"{entry[0].gpu_hours_cap if entry else None}), wall clock {wall} h, Q5 kill below {kill:,.0f}/s")
over = []
if hours * 1.25 > cap:
    over.append(f"{hours:.2f} h x 1.25 margin exceeds the {cap} GPU-hour cap")
if hours * 1.25 > wall:
    over.append(f"{hours:.2f} h x 1.25 margin exceeds the {wall} h wall clock")
for x in over:
    print("  over budget:", x)
q5 = bool(kill) and rate < 1.2 * kill
if q5:
    where = "below" if rate < kill else "within 20 % of"
    print(f"  the effective rate is {where} the PREREG Q5 kill rate {kill:,.0f}/s: the kill would "
          + ("fire" if rate < kill else "likely fire"))
sys.exit(11 if q5 else 10 if over else 0)
EOF
case "$rc" in
  0) ;;
  10) die "over budget (see above). Raising it is your edit of budget.gpu_hours_cap and budget.wall_clock_hours
in $LANE and of gpu_hours_cap in queue.json, plus a dated PREREG addendum, committed by you before you re-run
(those fields are outside lane_pipeline_sha256, so the control, gate and parity record stay valid)" ;;
  11) die "the effective rate is too close to the PREREG Q5 kill rate (see above); a larger cap does not help.
A faster device or setting, or a dated PREREG addendum changing the kill condition before any result" ;;
  12) die "the parity/bench record is not usable for the budget (see above)" ;;
  *) die "the budget check crashed (exit $rc, traceback above)" ;;
esac
pycheck "the GPU sweep's own preflight refuses the lane (see above); nothing approved" "$LANE" <<'EOF'
import sys
from runeforge.lanes import load_lane
from runeforge.runner.sweep import RUNS_DIR, preflight
lane = load_lane(sys.argv[1])
problems = preflight(lane, None, False, RUNS_DIR, backend="gpu")
for p in problems:
    print("  refused:", p)
print("GPU preflight:", "clean" if not problems else f"{len(problems)} problem(s)")
sys.exit(3 if problems else 0)
EOF

# ---------------------------------------------------------------- 7. commit the evidence
say "7/8 commit the evidence"
cp "$RD/parity.json" "lanes/$ID/parity.json"
cp "$RD/bench.json" "lanes/$ID/bench.json"
EV=(runeforge/scoring/calib/presets TOOLBOX_REQUESTS.md ledger/ledger.jsonl
    "lanes/$ID/control.json" lanes/"$ID"/control-*.json "lanes/$ID/threshold_after_TR1.json"
    "lanes/$ID/parity.json" "lanes/$ID/bench.json")
git add -- "${EV[@]}"
changed="$(git diff --cached --name-only -- "${EV[@]}")"
if [[ -z "$changed" ]]; then
  echo "nothing new to commit"
else
  what=()
  if grep -q '^runeforge/scoring/calib/presets/' <<< "$changed"; then what+=("TR-1 installed"); fi
  if grep -q "^lanes/$ID/control" <<< "$changed"; then what+=("control with the installed beta"); fi
  if grep -q "^lanes/$ID/threshold_after_TR1.json" <<< "$changed"; then what+=("threshold reproduced"); fi
  if grep -qE "^lanes/$ID/(parity|bench)\.json" <<< "$changed"; then what+=("real-device parity and bench"); fi
  if [[ -z "$TR1_NOTE" ]] && grep -q '^runeforge/scoring/calib/presets/' <<< "$changed"; then
    staged_set=1  # recover the approval only for exactly the staged TR-1 files
    while read -r c; do
      [[ "$c" == runeforge/scoring/calib/presets/* ]] || continue
      cmp -s "$c" "reports/calib-staging/$(basename "$c")" || staged_set=0
    done <<< "$changed"
    if (( staged_set )); then
      TR1_NOTE="$(grep -o "TR-1 approved by .*" TOOLBOX_REQUESTS.md | head -1 || true)"
    else
      TR1_NOTE="calibration files changed that are not the staged TR-1 set: no approval recorded for them"
    fi
  fi
  (( ${#what[@]} )) || what=("setup evidence")
  printf -v summary '%s, ' "${what[@]}"
  msg=(-m "lane($ID): ${summary%, }" -m "Files: $(tr '\n' ' ' <<< "$changed")")
  [[ -z "$TR1_NOTE" ]] || msg+=(-m "$TR1_NOTE")
  gpu="$("$NVSMI" -L 2>/dev/null | sed -n 1p || true)"
  msg+=(-m "Run by scripts/gpu_lane_setup.sh on $(hostname) (${gpu:-GPU unknown}).")
  git commit -q "${msg[@]}" -- "${EV[@]}"
  git --no-pager log --oneline -1
fi
trap push_branch EXIT  # every exit from here on pushes the evidence
rest="$(git status --porcelain)"
if [[ -n "$rest" ]]; then
  echo "left uncommitted (not part of the evidence):"
  sed 's/^/  /' <<< "$rest"
fi

# ---------------------------------------------------------------- 8. approve and launch
say "8/8 approve and launch"
if [[ "$LAUNCH" == "0" ]]; then
  echo "--no-launch: stopping before the launch; the GPU preflight is clean. The sweep runner does not"
  echo "read queue.json itself: the approval is recorded when you launch, by re-running without --no-launch."
  exit 0
fi
git diff --quiet HEAD -- "$LANE" "lanes/$ID/PREREG.md" queue.json \
  || die "the lane spec, its PREREG or queue.json differs from the commit: the sweep runs only on committed files (commit your amendment yourself and re-run)"
ask "Start the GPU sweep of $ID now and record your queue approval?" "go" || { echo "not approved; nothing launched"; exit 0; }
GO_NOTE="Approved by $WHO typing 'go' at a terminal on $(hostname), $(date -Is)."
check_no_live_sweep
runeforge sweep "$LANE" --detach --backend gpu \
  || die "the GPU sweep refused to start (see above): nothing is running, and queue.json and the ledger are unchanged"
python - "$ID" "$RD" "$GO_NOTE" <<'EOF' || die "THE SWEEP IS RUNNING, but recording the launch failed (see above): set \"approved\": true for $ID in queue.json and the ledger row to running yourself, commit both and push"
import json, sys
from pathlib import Path
from runeforge.ledger import Ledger
lane_id, rd, note = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
p = Path("queue.json")
q = json.loads(p.read_text(encoding="utf-8"))
[e for e in q if e["id"] == lane_id][0]["approved"] = True
p.write_text(json.dumps(q, indent=1) + "\n", encoding="utf-8")
st = json.loads((rd / "status.json").read_text(encoding="utf-8"))
led = Ledger()
row = led.get(lane_id, strict=False)
launched = (f"GPU sweep launched (--backend gpu; resume only with --backend gpu), pid {st.get('pid')}, "
            f"cursor {st.get('cursor')}. {note}")
led.update(lane_id, status="running", notes=f"{row.notes} | {launched}" if row.notes else launched)
print("queue.json: approved; ledger: running")
EOF
vout="$(python scripts/validate_ledger.py 2>&1)" || { echo "$vout"; die "THE SWEEP IS RUNNING, but the ledger does not validate (see the errors above): fix the row, commit queue.json and ledger/ledger.jsonl, push"; }
echo "$vout" | tail -1
git add -- queue.json ledger/ledger.jsonl
git commit -q -m "lane($ID): running (GPU sweep launched); queue approval" -m "$GO_NOTE" -- queue.json ledger/ledger.jsonl \
  || die "THE SWEEP IS RUNNING, but the commit failed: commit queue.json and ledger/ledger.jsonl yourself and push"
git --no-pager log --oneline -1
push_branch
cat <<EOF

The sweep is running detached; it does not need this terminal, but WSL and Windows must stay awake
(OVERNIGHT_LOOP.md Part 1). Watch it with:
  runeforge status --short
  cat $RD/status.json     # cursor, seeds/s, best score, crossers, done, stopped_by
A crosser (a seed above the bar) writes $RD/crossers/*.pending: HIT_PROTOCOL.md adjudicates it;
it is not a result. When the sweep's PID is gone, whether status.json says "done": true or
"done": false with a stopped_by (deadline, q5-kill-condition) or with no reason (a crash or a WSL
restart), open a Claude session and ask it to write up or park the lane. Do not relaunch it
yourself: resuming after a Q5 kill needs your --override-q5 decision, and any resume must use
--backend gpu (the CPU default would spend the lane's wall clock at about 1,240 seeds/s).
EOF
