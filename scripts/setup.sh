#!/usr/bin/env bash
# One-time setup on a fresh machine (WSL2 Ubuntu or any Linux), idempotent:
#   .venv with runeforge + dev tools, the pinned vendored sources, the corpora,
#   then the trust anchor. Re-run any time; finished steps are skipped.
#
#   bash scripts/setup.sh            # sparse sources (a few hundred MB at most)
#   bash scripts/setup.sh --full     # complete sources incl. page images (~900 MB; Phase 4)
#   RUNEFORGE_GPU=1 bash scripts/setup.sh   # also install the CuPy/Numba extras (Phase 3)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
  || { echo "setup: $PY is older than Python 3.11 (requires-python); set PYTHON=python3.11" >&2; exit 2; }
if [[ -x .venv/bin/python ]]; then
  # a venv from an older or different interpreter is rebuilt, not reused
  want="$("$PY" -c 'import sys; print(sys.version_info[:2])')"
  have="$(.venv/bin/python -c 'import sys; print(sys.version_info[:2])' 2>/dev/null || echo none)"
  if [[ "$have" != "$want" ]]; then
    echo "== .venv is Python $have, $PY is $want: recreating it"
    rm -rf .venv
  fi
fi
if [[ ! -x .venv/bin/python ]]; then
  echo "== creating .venv with $PY"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q --upgrade pip
extras="dev"
[[ "${RUNEFORGE_GPU:-0}" == "1" ]] && extras="dev,gpu"
echo "== installing runeforge[$extras] (+ sympy for the cicada_tools reference)"
python -m pip install -q -e ".[$extras]" sympy

echo "== vendored sources (pinned commits)"
bash scripts/fetch_raw.sh "${1:-}"

echo "== corpora (offline, from the vendored texts)"
python scripts/build_corpus.py

echo "== trust anchor"
python scripts/build_canon.py --check
pytest -q -m "not slow"
runeforge canon --verify
python -m runeforge.oracle --selftest | tail -1
python scripts/validate_ledger.py | tail -1
echo
echo "ready. Activate with: source .venv/bin/activate   (before launching claude)"
