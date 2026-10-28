#!/usr/bin/env bash
# Hunter's one-command setup for a GPU lane, run on the RTX machine (WSL2 Ubuntu), from the repo:
#
#   git fetch origin && git checkout claude/busy-euler-gmxvfy   # or the branch that holds the lane
#   bash scripts/gpu_lane_setup.sh                              # lanes/P3-MT19937-PY27-ANTIREPEAT.yaml
#   bash scripts/gpu_lane_setup.sh lanes/<id>.yaml [--yes] [--no-launch]
#
# It does, in order, and stops at the first failure with the reason:
#   1. .venv with the GPU extra (scripts/setup.sh with RUNEFORGE_GPU=1 when there is no .venv);
#      nvidia-smi lists the GPU; numba sees a CUDA device; no other sweep is alive.
#   2. Trust anchor: pytest -q -m "not slow", runeforge canon --verify, the oracle self-test.
#   3. TOOLBOX_REQUESTS.md TR-1: copies the six staged beam calibrations from reports/calib-staging/
#      into the frozen runeforge/scoring/calib/presets/ unchanged -- this is YOUR approval of TR-1,
#      so it asks first -- then checks the lane's frozen bar against threshold_for (the lane must be
#      runnable) and runs tests/test_calib.py.
#   4. Re-runs the lane's positive control so its ceiling uses the installed calibration's beta (the
#      sweep refuses the older control); the CPU preflight must then be clean.
#   5. The GPU tests (tests/test_gpu_beam.py, tests/test_gpu_mt.py) with their real-device cases, then
#      `python -m runeforge.gpu.parity <lane> --bench 1048576`: the parity record the GPU sweep requires
#      and the throughput number.
#   6. Budget: 2^32 seeds at the measured device rate against the lane's wall clock, GPU-hour cap and
#      Q5 kill rate. Over budget -> it stops; a larger cap is your call in queue.json and a new PREREG
#      addendum, not this script's. Then the GPU sweep's own preflight must be clean, so nothing is
#      approved that the sweep would refuse.
#   7. Commits the evidence (calibrations, control, parity and bench copies under lanes/<id>/, ledger).
#   8. Asks "go", then sets "approved": true for the lane in queue.json (your approval, recorded in a
#      commit), launches `runeforge sweep <lane> --detach --backend gpu` and prints how to watch it.
#      --no-launch stops before this step. --yes answers every question with yes (unattended).
#
# Never run two GPU jobs at once; keep Windows from sleeping while the sweep runs (OVERNIGHT_LOOP.md
# Part 1). Re-running the script is safe: finished steps are detected and skipped.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

LANE="lanes/P3-MT19937-PY27-ANTIREPEAT.yaml"
YES=0
LAUNCH=1
for a in "$@"; do
  case "$a" in
    --yes) YES=1 ;;
    --no-launch) LAUNCH=0 ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    *.yaml) LANE="$a" ;;
    *) echo "unknown argument: $a (see --help)" >&2; exit 2 ;;
  esac
done
[[ -f "$LANE" ]] || { echo "no lane spec $LANE (is this the branch that holds it?)" >&2; exit 2; }

say() { printf '\n== %s\n' "$*"; }
die() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }
ask() {  # ask "<question>" "<word>": returns 0 only if the user types the word (or --yes)
  if [[ "$YES" == "1" ]]; then echo "$1 [--yes]"; return 0; fi
  local reply
  read -r -p "$1 Type '$2' to continue: " reply
  [[ "$reply" == "$2" ]]
}

# ---------------------------------------------------------------- 1. environment
say "1/8 environment"
if [[ ! -x .venv/bin/python ]]; then
  echo "no .venv: running scripts/setup.sh with the GPU extra (vendored sources, corpora, trust anchor)"
  RUNEFORGE_GPU=1 bash scripts/setup.sh
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -c 'import numba' 2>/dev/null || python -m pip install -q -e ".[gpu]"

NVSMI=/usr/lib/wsl/lib/nvidia-smi
[[ -x "$NVSMI" ]] || NVSMI="$(command -v nvidia-smi || true)"
[[ -n "$NVSMI" ]] || die "nvidia-smi not found (WSL: /usr/lib/wsl/lib/nvidia-smi comes with the Windows driver)"
"$NVSMI" -L || die "nvidia-smi does not list a GPU"
if ! python -c 'from numba import cuda; import sys; sys.exit(0 if cuda.is_available() else 1)'; then
  python -c 'from numba import cuda; cuda.detect()' || true
  die "numba sees no CUDA device. Install the CUDA toolkit inside WSL (toolkit only, never a Linux
display driver): https://developer.nvidia.com/cuda-downloads -> Linux / x86_64 / WSL-Ubuntu, package
cuda-toolkit-12-x; then re-run this script"
fi
read -r ID RD < <(python - "$LANE" <<'EOF'
import sys
from runeforge.lanes import load_lane
from runeforge.runner.sweep import run_dir
lane = load_lane(sys.argv[1])
print(lane.lane_id, run_dir(lane))
EOF
)
echo "lane $ID (run directory $RD)"
python - <<'EOF' || die "another sweep is alive (one GPU job at a time): runeforge status --short"
import sys
from runeforge.runner.jobs import live_sweeps
alive = live_sweeps()
print("live sweeps:", alive or "none")
sys.exit(1 if alive else 0)
EOF

# ---------------------------------------------------------------- 2. trust anchor
say "2/8 trust anchor"
out="$(pytest -q -m "not slow" 2>&1)" || { echo "$out" | tail -20; die "the trust anchor is red: repair first (SESSION_PROMPT.md section A)"; }
echo "$out" | tail -1
runeforge canon --verify | tail -1 || die "canon pins do not verify"
python -m runeforge.oracle --selftest | tail -1 || die "oracle self-test failed"

# ---------------------------------------------------------------- 3. TR-1
say "3/8 TR-1: the staged beam calibrations"
STAGED=(reports/calib-staging/*.json)
missing=()
for f in "${STAGED[@]}"; do
  cmp -s "$f" "runeforge/scoring/calib/presets/$(basename "$f")" || missing+=("$f")
done
if (( ${#missing[@]} )); then
  printf '  %s\n' "${missing[@]}"
  echo "These go into runeforge/scoring/calib/presets/ unchanged (TOOLBOX_REQUESTS.md TR-1)."
  ask "Approve TR-1 and install them?" "install" || die "TR-1 not approved; nothing installed"
  for f in "${missing[@]}"; do cp -p "$f" runeforge/scoring/calib/presets/; done
  for f in "${missing[@]}"; do
    cmp "$f" "runeforge/scoring/calib/presets/$(basename "$f")" || die "copy of $f differs"
  done
else
  echo "already installed (byte-identical)"
fi
runeforge lane "$LANE" || die "the lane is not runnable with the installed calibration (see above);
its frozen bar must not sit below threshold_for -- that needs a re-registration, not an edit"
pytest -q tests/test_calib.py | tail -1

# ---------------------------------------------------------------- 4. control with the installed beta
say "4/8 positive control with the installed calibration"
need_control="$(python - "$LANE" <<'EOF'
import json, sys
from pathlib import Path
from runeforge.lanes import load_lane
from runeforge.runner.control import lane_pipeline_sha256
lane = load_lane(sys.argv[1])
p = Path("lanes") / lane.lane_id / "control.json"
try:
    c = json.loads(p.read_text())
except (OSError, ValueError):
    print(1); sys.exit()
ok = (c.get("status") == "passed" and c.get("beta_source") == "calibration"
      and c.get("lane_pipeline_sha256") == lane_pipeline_sha256(lane))
print(0 if ok else 1)
EOF
)"
if [[ "$need_control" == "1" ]]; then
  runeforge control "$LANE" || die "the control did not pass: the lane is INCONCLUSIVE (power); do not lower the bar"
else
  echo "control already passed with the installed calibration"
fi
python - "$LANE" <<'EOF' || die "the CPU preflight still refuses the lane (see above)"
import sys
from runeforge.lanes import load_lane
from runeforge.runner.sweep import RUNS_DIR, preflight
lane = load_lane(sys.argv[1])
problems = preflight(lane, None, False, RUNS_DIR)
for p in problems:
    print("  refused:", p)
sys.exit(1 if problems else 0)
EOF

# ---------------------------------------------------------------- 5. GPU parity and bench
say "5/8 GPU tests, parity record and benchmark"
out="$(pytest -q -rs tests/test_gpu_beam.py tests/test_gpu_mt.py 2>&1)" || { echo "$out" | tail -30; die "GPU tests failed"; }
echo "$out" | tail -1
if grep -q "no CUDA device" <<< "$out"; then
  die "the device tests were skipped ('no CUDA device'): the parity record would not be real"
fi
python -m runeforge.gpu.parity "$LANE" --bench 1048576 || die "GPU parity failed: the kernels do not match the CPU reference on this device; no sweep"

# ---------------------------------------------------------------- 6. budget
say "6/8 budget"
python - "$LANE" <<'EOF' || die "over budget (see above): raise the cap only by your approval in queue.json plus a dated PREREG addendum"
import json, sys
from runeforge.lanes import load_lane
from runeforge.runner.sweep import run_dir
lane = load_lane(sys.argv[1])
rd = run_dir(lane)
par = json.loads((rd / "parity.json").read_text())
b = json.loads((rd / "bench.json").read_text())
assert par["status"] == "passed" and not par["simulated"], "parity record is not a real-device pass"
rate = b.get("gpu_chain_keys_per_s") or b["cpu_keygen_end_to_end_keys_per_s"]
n = lane.seed_range[1] - lane.seed_range[0]
hours = n / rate / 3600
cap = lane.budget.gpu_hours_cap or 0.0
wall = lane.budget.wall_clock_hours or float("inf")
kill = lane.kill_condition.min_seeds_per_s or 0
print(f"device {par.get('device_name')}: {rate:,.0f} seeds/s on the device chain -> "
      f"{n:,} seeds in {hours:.2f} h (cap {cap} GPU-h, wall clock {wall} h, Q5 kill below {kill:,.0f}/s)")
bad = []
if hours * 1.25 > cap:
    bad.append(f"{hours:.2f} h x 1.25 margin exceeds the {cap} GPU-hour cap")
if hours * 1.25 > wall:
    bad.append(f"{hours:.2f} h x 1.25 margin exceeds the {wall} h wall clock")
if rate < 1.2 * kill:
    bad.append(f"the measured rate is within 20 % of the Q5 kill rate {kill:,}/s: the kill would likely fire")
for x in bad:
    print("  over budget:", x)
sys.exit(1 if bad else 0)
EOF
python - "$LANE" <<'EOF' || die "the GPU sweep's own preflight refuses the lane (see above); nothing approved"
import sys
from runeforge.lanes import load_lane
from runeforge.runner.sweep import RUNS_DIR, preflight
lane = load_lane(sys.argv[1])
problems = preflight(lane, None, False, RUNS_DIR, backend="gpu")
for p in problems:
    print("  refused:", p)
print("GPU preflight:", "clean" if not problems else f"{len(problems)} problem(s)")
sys.exit(1 if problems else 0)
EOF

# ---------------------------------------------------------------- 7. commit the evidence
say "7/8 commit the evidence"
cp "$RD/parity.json" "lanes/$ID/parity.json"
cp "$RD/bench.json" "lanes/$ID/bench.json"
git add runeforge/scoring/calib/presets/ "lanes/$ID/" ledger/ledger.jsonl
if git diff --cached --quiet; then
  echo "nothing new to commit"
else
  git commit -q -m "lane($ID): TR-1 installed, control with the installed beta, real-device parity and bench" \
    -m "Run by scripts/gpu_lane_setup.sh on $(hostname) ($("$NVSMI" -L | head -1))."
  git log --oneline -1
fi

# ---------------------------------------------------------------- 8. approve and launch
say "8/8 approve and launch"
if [[ "$LAUNCH" == "0" ]]; then
  echo "--no-launch: stopping here. Everything the sweep checks is in place except your approval."
  exit 0
fi
ask "Approve $ID in queue.json and start the GPU sweep now?" "go" || { echo "not approved; nothing launched"; exit 0; }
python - "$ID" <<'EOF'
import json, sys
from pathlib import Path
p = Path("queue.json")
q = json.loads(p.read_text())
hit = [e for e in q if e["id"] == sys.argv[1]]
if not hit:
    sys.exit(f"{sys.argv[1]} is not in queue.json")
hit[0]["approved"] = True
p.write_text(json.dumps(q, indent=1) + "\n")
EOF
git add queue.json
git commit -q -m "queue: Hunter approves $ID" || true
runeforge sweep "$LANE" --detach --backend gpu
if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  git push -q && echo "pushed" || echo "push failed: run 'git push' yourself so the evidence reaches GitHub"
else
  echo "no upstream branch: run 'git push -u origin HEAD' so the evidence reaches GitHub"
fi
cat <<EOF

The sweep is running detached. Watch it with:
  runeforge status --short
  cat $RD/status.json        # cursor, seeds/s, best score, crossers
A crosser (a seed above the bar) writes $RD/crossers/*.pending: that is HIT_PROTOCOL.md's to
adjudicate, not a result. When status.json says "done": true, open a Claude session and ask it to
write up the lane (RESULTS.md, verify-lane, the ledger row).
EOF
