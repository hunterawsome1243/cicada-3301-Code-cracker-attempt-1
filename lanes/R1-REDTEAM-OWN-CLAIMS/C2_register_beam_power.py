"""R1-REDTEAM-OWN-CLAIMS sub-attack C (part 2): settling test for one claim-audit row.

NOT an independent re-derivation. Run only after out_B2.json was written; it loads the package
(runeforge.runner.pipeline, runeforge.scoring.presets) and scripts/scorer_power.py helpers on
purpose, to measure a number that no committed evidence holds:

  lanes/P3-MT19937-PY27-EXACT/PREREG.md (fbe43e7) §0 Q4 (lines 57-59) and §8 (lines 168-170)
  quote "Latin 1.000 at both bars; vowel-dropped English 1.000 at N = 10^6, 0.790 at 2^32" from
  reports/scorer_power.md §3 (lines 375, 453): RIGID-exact plants scored against the RIGID bars
  (-6.1625, -5.7788). The lane runs `lp-ngram3-heldout:beam-skip` with bar -5.7284. This script
  takes the SAME 200 plant windows of each register (scorer_power.plant_windows(reg, 240, 200, 0),
  the power rows' tag), enciphers each under the lane's forward model (anti-repeat, p_keep 0.19,
  no interrupters) with a fresh uniform key, decodes it with the true key under beam-skip, and
  counts plants above the lane's bar. 19 decoys per plant give rank 1.

Run from the repo root:
  $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/C2_register_beam_power.py
"""
import json
import math
import os
import sys
import time

import numpy as np

T0 = time.time()
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import scorer_power as sp  # noqa: E402
from runeforge.runner import pipeline  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out_C2.json")
L = 240
N_PLANTS = 200
DECOYS = 19
BARS = {"lane_bar_2^32_beam-skip_staged": -5.7284, "rigid_bar_2^32": -5.778756354597847,
        "rigid_bar_10^6": -6.162531106082723, "lane_claim_bar_10^6": -6.0434}
SCORER = "lp-ngram3-heldout"


def wilson(k, n, z=1.959964):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [c - h, c + h]


def run(register):
    t0 = time.time()
    lane = sp.toy_lane(L, preset=f"{SCORER}:beam-skip", **sp.MODELS["anti-repeat"])
    scorer = sp.get_scorer(SCORER)
    w = sp.plant_windows(register, L, N_PLANTS, 0)
    rigid = scorer.score_batch(w["plains"])
    rng = np.random.default_rng([3301, 9001, sp.REGISTERS.index(register)])
    planted, rec, rank = [], [], []
    for plain in w["plains"]:
        s_true = pipeline.draw_seeds(rng, 0, 2**32, 1)[0]
        k_true = pipeline.keys(lane, s_true, 3 * L)
        cipher, _ = pipeline.encrypt(lane, plain, k_true, rng)
        decoys = [d for d in pipeline.draw_seeds(rng, 0, 2**32, DECOYS) if d != s_true]
        plains = pipeline.decrypt(lane, cipher[None, :], pipeline.keys_batch(lane, [s_true, *decoys], L))
        sc = scorer.score_batch(plains)
        planted.append(float(sc[0]))
        rec.append(float((plains[0] == plain).mean()))
        rank.append(1 + int((sc[1:] >= sc[0]).sum()))
    planted = np.array(planted)
    out = {
        "register": register, "L": L, "n_plants": int(planted.size), "decoys": DECOYS,
        "n_disjoint": w["n_disjoint"],
        "rigid_exact_mean": float(rigid.mean()), "rigid_exact_sd": float(rigid.std(ddof=1)),
        "beam_skip_mean": float(planted.mean()), "beam_skip_sd": float(planted.std(ddof=1)),
        "beam_skip_min": float(planted.min()),
        "mean_penalty_beam_minus_rigid": float((planted - rigid).mean()),
        "median_recovery": float(np.median(rec)),
        "identified_rank1_rec090": int(sum(r == 1 and x >= 0.9 for r, x in zip(rank, rec))),
        "power": {},
        "rigid_exact_power": {},
    }
    for name, bar in BARS.items():
        k = int((planted > bar).sum())
        out["power"][name] = {"bar": bar, "k": k, "power": k / planted.size, "wilson": wilson(k, planted.size)}
        kr = int((rigid > bar).sum())
        out["rigid_exact_power"][name] = {"bar": bar, "k": kr, "power": kr / rigid.size}
    # per-plant evidence, so a verifier can recount every k above without re-running the beam
    out["per_plant"] = {
        "beam_skip_score": [float(x) for x in planted],
        "rigid_exact_score": [float(x) for x in rigid],
        "recovery": rec,
        "rank": rank,
    }
    out["seconds"] = round(time.time() - t0, 1)
    return out


cells = [run(r) for r in ("vowel-dropped-english", "latin", "heldout-solved-sections")]
res = {
    "lane": "R1-REDTEAM-OWN-CLAIMS", "sub_attack": "C2 (claim audit part 2) settling test",
    "numbering": "LP2-0-57", "audited_git": "fbe43e7",
    "independence": "package-path measurement (loads runeforge.runner.pipeline and scripts/scorer_power.py); run after out_B2.json; not a re-derivation",
    "target": "P3 PREREG §0 Q4 lines 57-59 and §8 lines 168-170: register powers quoted for the lane",
    "cells": cells,
    "command": "V=/tmp/claude-0/-home-user-cicada-3301-Code-cracker-attempt-1/4950dc03-e080-591a-84c1-d8ea81cef212/scratchpad/venv; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/C2_register_beam_power.py",
}
res["wall_seconds"] = round(time.time() - T0, 1)
prev = {}
if os.path.exists(OUT):
    prev = json.load(open(OUT))
prev["settling_register_beam_power"] = res
json.dump(prev, open(OUT, "w"), indent=1)
for c in cells:
    print(c["register"], "rigid", round(c["rigid_exact_mean"], 4), "beam-skip", round(c["beam_skip_mean"], 4),
          "pen", round(c["mean_penalty_beam_minus_rigid"], 4), "id", c["identified_rank1_rec090"],
          {k: round(v["power"], 3) for k, v in c["power"].items()},
          "rigid", {k: round(v["power"], 3) for k, v in c["rigid_exact_power"].items()}, c["seconds"], "s")
print("wall", res["wall_seconds"])
