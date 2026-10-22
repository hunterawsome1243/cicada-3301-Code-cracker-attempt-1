#!/usr/bin/env python3
"""Fit the family-wise bar for a scorer/decoder preset at a window length.

    python scripts/calibrate.py --preset lp-ngram3:rigid --L 240 [--draws 1000000]
    python scripts/calibrate.py --preset lp-ngram3-heldout:beam-skip --L 240 --workers 4 \
        --out-dir reports/calib-staging

Writes <out-dir>/<scorer>__<decoder>__L<L>.json, by default
runeforge/scoring/calib/presets/, the directory threshold_for reads (frozen: FROZEN.txt; a
new or refitted calibration there is Hunter's to install, TOOLBOX_REQUESTS.md). The rigid
decoder's null is uniform random strings (runeforge/scoring/calib); a beam decoder's is beam
decodes of uniform ciphers under uniform keys (runeforge/scoring/beam_calib). Re-run whenever
the scorer's training data or a decoder's parameters change; scripts/threshold_for.py refuses
a calibration fitted on a different model.
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

from runeforge.scoring import beam_calib, calib, presets  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preset", required=True, help="<scorer>:<decoder>, e.g. lp-ngram3:rigid")
    ap.add_argument("--L", type=int, required=True, action="append", help="window length(s)")
    ap.add_argument("--draws", type=int, default=1_000_000)
    ap.add_argument("--workers", type=int, default=1, help="processes (beam decoders only)")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=calib.CALIB_DIR,
        help="where to write (default: the calibration directory threshold_for reads)",
    )
    args = ap.parse_args()
    scorer_name, decoder = presets.split_preset(args.preset)
    scorer = presets.get(scorer_name)
    sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for length in args.L:
        t0 = time.time()
        if decoder == "rigid":
            rec = calib.calibrate(scorer, scorer_name, decoder, length, args.draws)
        else:
            rec = beam_calib.calibrate(
                scorer_name, decoder, length, args.draws, workers=args.workers
            )
        rec["git_sha"] = sha
        rec["seconds"] = round(time.time() - t0, 1)
        out = args.out_dir / calib.path_for(args.preset, length).name
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
