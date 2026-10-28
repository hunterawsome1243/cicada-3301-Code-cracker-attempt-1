"""R1 A2 cross-check, run only AFTER out_A2.json held the independent numbers (A2_kn4_independent.py,
A2_tailcheck.py, A2_seedprobe.py).

PREREG row A2: conditional distributions of the independent KN4 model agree with
runeforge.scoring.presets.get("kn4-cicada").distribution(history) to 1e-9 on 1,000 histories
(seen, unseen, prefix histories of length 0-2). Also (extra, recorded separately): the package's
score_batch on the same 2 x 2,000 plant windows and 20,000 uniform strings vs the independent scores,
and the independent model's vowel-dropped power at alternative bars.

    V=<venv>; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/A2_crosscheck.py
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

OUT = Path(__file__).resolve().parent / "out_A2.json"  # adds key "crosscheck"
SEED = 20261028_6


def main():
    t0 = time.time()
    runes, wid, n_words, _ = a2.load_corpus("cicada-english")
    seq = runes[wid < math.floor(0.9 * n_words)]
    P, info, _, eff, uniq = a2.fit(seq)
    own_score = a2.make_scorer(P)

    from runeforge.scoring import presets  # loaded only now

    pk = presets.get("kn4-cicada")
    rng = np.random.default_rng(SEED)
    B = a2.B
    hist = []
    kinds = []
    # prefix histories: length 0 (1), length 1 (all 29), length 2 (270 random distinct of 841)
    hist.append(()); kinds.append("prefix-0")
    for s in range(B):
        hist.append((s,)); kinds.append("prefix-1")
    for key in rng.choice(B * B, size=270, replace=False):
        hist.append((int(key // B), int(key % B))); kinds.append("prefix-2")
    # full 3-symbol histories: seen at the top level (raw trigram history count > 0) and unseen
    seen_h = np.unique(uniq[4] // B)
    for key in rng.choice(seen_h, size=400, replace=False):
        hist.append((int(key // (B * B)), int(key // B % B), int(key % B))); kinds.append("seen-3")
    unseen_mask = np.ones(B**3, dtype=bool); unseen_mask[seen_h] = False
    unseen_h = np.flatnonzero(unseen_mask)
    for key in rng.choice(unseen_h, size=300, replace=False):
        hist.append((int(key // (B * B)), int(key // B % B), int(key % B))); kinds.append("unseen-3")
    assert len(hist) == 1000

    devs = []
    per_kind = {}
    for h, k in zip(hist, kinds):
        mine = a2.distribution(P, list(h))
        theirs = np.asarray(pk.distribution(np.array(h, dtype=np.int64)), dtype=np.float64)
        d = float(np.abs(mine - theirs).max())
        devs.append(d)
        per_kind[k] = max(per_kind.get(k, 0.0), d)
    devs = np.array(devs)
    dist = dict(n_histories=len(hist), by_kind_count={k: kinds.count(k) for k in sorted(set(kinds))},
                max_abs_diff=float(devs.max()), max_abs_diff_by_kind=per_kind,
                within_1e_9=bool(devs.max() <= 1e-9), n_over_1e_9=int((devs > 1e-9).sum()))

    # extra: window scores (package score_batch vs own float64)
    sc = {}
    prng = np.random.default_rng(a2.SEED_PLANT)
    for name in ("latin", "vowel-dropped-english"):
        r, w, nw, _ = a2.load_corpus(name)
        tail = r[w >= math.floor(0.9 * nw)]
        offs = prng.choice(len(tail) - a2.L + 1, size=a2.N_PLANTS, replace=False)
        X = np.stack([tail[o : o + a2.L] for o in offs])
        mine = own_score(X)
        theirs = pk.score_batch(X.astype(np.int8))
        sc[name] = dict(n=int(len(X)), max_abs_diff=float(np.abs(mine - theirs).max()),
                        own_mean=float(mine.mean()), package_mean=float(theirs.mean()))
        if name == "vowel-dropped-english":
            vd = mine
    U = np.random.default_rng(SEED + 1).integers(0, B, size=(20000, a2.L))
    du = np.abs(own_score(U) - pk.score_batch(U.astype(np.int8)))
    sc["uniform_20000"] = dict(max_abs_diff=float(du.max()))

    # own-model vowel-dropped power at alternative bars (independent numbers, recorded here for the comparison)
    doc = json.loads(OUT.read_text())
    tc = doc["tailcheck"]
    alt = {
        "report_line97_-6.0705": -6.0705,
        "own_primary_1e6_draws_mom": doc["null"]["primary"]["bar_1e6"],
        "own_100k_replicate_mean_mom": doc["seedprobe"]["replicates"]["bar_1e6"]["mean"],
        "own_2e7_all_blocks_mom": tc["fits"]["all_20000_blocks"]["mom"]["bar_1e6"],
    }
    # empirical-anchored: Gumbel MoM on the observed 10^5-block maxima (200) extrapolated x10, and on the 20 10^6-block maxima
    for tag, Nb in (("from_1e5_block_maxima_x10", "100000"), ("from_1e6_block_maxima_direct", "1000000")):
        o = tc["observed_block_maxima"][Nb]
        beta = o["sd"] * math.sqrt(6) / math.pi
        mu = o["mean"] - 0.5772156649015329 * beta
        alt[tag] = mu + beta * math.log(1e6 / int(Nb)) - beta * math.log(-math.log(0.99))
    pw = {k: dict(bar=v, power=float((vd > v).mean())) for k, v in alt.items()}

    out = dict(sub_attack="A2-crosscheck", distribution=dist, scores=sc, vowel_dropped_power_at_alt_bars=pw,
               package_preset_type=type(pk).__name__,
               command="V=/tmp/claude-0/-home-user-cicada-3301-Code-cracker-attempt-1/4950dc03-e080-591a-84c1-d8ea81cef212/"
                       "scratchpad/venv; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/A2_crosscheck.py",
               wall_time_s=round(time.time() - t0, 1))
    doc["crosscheck"] = out
    OUT.write_text(json.dumps(doc, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
