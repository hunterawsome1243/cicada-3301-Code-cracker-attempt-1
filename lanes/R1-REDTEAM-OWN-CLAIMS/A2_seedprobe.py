"""R1 A2 supplement 2: is the report's kn4-cicada L=240 beta (0.02509, MoM on 100 block maxima, seed
3301, per the committed record reports/scorer_power/fits/kn4-cicada__rigid__L240.json) a sampling draw?

Independent code (the A2 script's own model). (a) Tries to regenerate the record's 100,000 null draws
with np.random.default_rng(3301) under two simple draw layouts and compares the null mean/sd with the
record's (-6.676455961955175, 0.09373836281765496). (b) The sampling distribution of the
100-block MoM beta and of the bars it implies, over 200 independent 100,000-draw replicates.

    V=<venv>; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/A2_seedprobe.py
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import A2_kn4_independent as a2  # noqa: E402

OUT = Path(__file__).resolve().parent / "out_A2.json"  # adds key "seedprobe"
REC = dict(mean=-6.676455961955175, sd=0.09373836281765496, mu_b=-6.359236906270471, beta=0.02509461142847051,
           bar_1e6=-6.070450514342512, bar_2p32=-5.860529090396022)
N_REP = 200
SEED = 20261028_5


def fitstats(v):
    bm = v.reshape(-1, 1000).max(axis=1)
    mu, beta = a2.gumbel_mom(bm)
    return dict(mean=float(v.mean()), sd=float(v.std(ddof=1)), mu_b=mu, beta=beta,
                bar_1e6=a2.bar(mu, beta, 1e6), bar_2p32=a2.bar(mu, beta, 2.0**32))


def main():
    t0 = time.time()
    runes, wid, n_words, _ = a2.load_corpus("cicada-english")
    P, *_ = a2.fit(runes[wid < math.floor(0.9 * n_words)])
    score = a2.make_scorer(P)
    layouts = {}
    rng = np.random.default_rng(3301)
    layouts["one_call_(100000,240)"] = fitstats(score(rng.integers(0, a2.B, size=(100000, a2.L))))
    rng = np.random.default_rng(3301)
    v = np.concatenate([score(rng.integers(0, a2.B, size=(10000, a2.L))) for _ in range(10)])
    layouts["ten_calls_(10000,240)"] = fitstats(v)
    for k, d in layouts.items():
        d["delta_mean_vs_record"] = d["mean"] - REC["mean"]
        d["matches_record_1e-6"] = bool(abs(d["mean"] - REC["mean"]) < 1e-6 and abs(d["sd"] - REC["sd"]) < 1e-6)

    rng = np.random.default_rng(SEED)
    reps = []
    for _ in range(N_REP):
        v = np.concatenate([score(rng.integers(0, a2.B, size=(20000, a2.L))) for _ in range(5)])
        reps.append(fitstats(v))
    betas = np.array([r["beta"] for r in reps])
    b6 = np.array([r["bar_1e6"] for r in reps])
    b32 = np.array([r["bar_2p32"] for r in reps])
    summ = dict(
        n_replicates=N_REP, draws_each=100000, seed=SEED,
        beta=dict(mean=float(betas.mean()), sd=float(betas.std(ddof=1)), min=float(betas.min()),
                  q025=float(np.quantile(betas, 0.025)), share_le_record=float((betas <= REC["beta"]).mean())),
        bar_1e6=dict(mean=float(b6.mean()), sd=float(b6.std(ddof=1)), min=float(b6.min()),
                     q025=float(np.quantile(b6, 0.025)), share_le_record=float((b6 <= REC["bar_1e6"]).mean())),
        bar_2p32=dict(mean=float(b32.mean()), sd=float(b32.std(ddof=1)), min=float(b32.min()),
                      q025=float(np.quantile(b32, 0.025)), share_le_record=float((b32 <= REC["bar_2p32"]).mean())),
    )
    out = dict(sub_attack="A2-supplement-2", record=REC, seed3301_layouts=layouts, replicates=summ,
               command="V=/tmp/claude-0/-home-user-cicada-3301-Code-cracker-attempt-1/4950dc03-e080-591a-84c1-d8ea81cef212/"
                       "scratchpad/venv; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/A2_seedprobe.py",
               wall_time_s=round(time.time() - t0, 1))
    doc = json.loads(OUT.read_text())
    doc["seedprobe"] = out
    OUT.write_text(json.dumps(doc, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
