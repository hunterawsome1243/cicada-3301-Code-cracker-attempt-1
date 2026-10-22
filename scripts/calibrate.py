#!/usr/bin/env python3
"""Fit the family-wise bar for a scorer/decoder preset at a window length.

    python scripts/calibrate.py --preset lp-ngram3:rigid --L 240 [--draws 1000000]

Writes runeforge/scoring/calib/presets/<scorer>__<decoder>__L<L>.json (see
runeforge/scoring/calib for the method). Re-run whenever the scorer's training data
changes; scripts/threshold_for.py refuses a calibration fitted on a different model.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runeforge.scoring import calib, presets  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preset", required=True, help="<scorer>:<decoder>, e.g. lp-ngram3:rigid")
    ap.add_argument("--L", type=int, required=True, action="append", help="window length(s)")
    ap.add_argument("--draws", type=int, default=1_000_000)
    args = ap.parse_args()
    scorer_name, decoder = presets.split_preset(args.preset)
    scorer = presets.get(scorer_name)
    sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    calib.CALIB_DIR.mkdir(parents=True, exist_ok=True)
    for length in args.L:
        t0 = time.time()
        rec = calib.calibrate(scorer, scorer_name, decoder, length, args.draws)
        rec["git_sha"] = sha
        rec["seconds"] = round(time.time() - t0, 1)
        out = calib.path_for(args.preset, length)
        out.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
        chk = rec["check"]
        print(
            f"{out.name}: mu_b={rec['fit']['mu_block']:.4f} beta={rec['fit']['beta']:.4f} "
            f"null mean={rec['null']['mean']:.4f} sd={rec['null']['sd']:.4f} "
            f"out-of-sample error={chk['max_error']:.4f} ({rec['seconds']} s)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
