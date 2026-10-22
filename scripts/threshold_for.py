#!/usr/bin/env python3
"""The pre-registered bar for a lane: trial-count-corrected, per preset and window length.

    python scripts/threshold_for.py --n 4294967296 --preset lp-ngram3:rigid --L 240
    python scripts/threshold_for.py --n 300 --preset lp-ngram3:rigid --L 240 --null-max -6.9

Prints the bar, the expected null maximum and the expected number of false positives over
the slice (N * P(clear), which must be < 1 before a run; CLAUDE.md, Doctrine). Paste the
printed line into PREREG.md; never edit a threshold after seeing a result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runeforge.scoring.calib import threshold_for  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=float, required=True, help="the lane's TRUE number of trials")
    ap.add_argument("--preset", required=True, help="<scorer>:<decoder>, e.g. lp-ngram3:rigid")
    ap.add_argument("--L", type=int, required=True, help="scored window length (runes)")
    ap.add_argument("--alpha", type=float, default=0.01, help="family-wise error rate")
    ap.add_argument("--floor", type=float, help="optional absolute floor for the bar")
    ap.add_argument("--null-max", type=float, help="small-N rule: shuffle-null max (n >= 200)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        t = threshold_for(int(args.n), args.preset, args.L, args.alpha, args.floor, args.null_max)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(t.as_dict(), indent=1))
        return 0
    print(
        f"threshold_for(N={t.n_trials:,}, preset={t.preset}, L={t.length}, alpha={t.alpha}) "
        f"= {t.bar:.4f}  [{t.regime}; expected null max {t.expected_null_max:.4f}; "
        f"expected false positives {t.expected_false_positives:.4f}]"
    )
    print(f"  {t.note}")
    if t.expected_false_positives >= 1:
        print("  REFUSE: expected false positives >= 1; raise the bar or shrink the slice")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
