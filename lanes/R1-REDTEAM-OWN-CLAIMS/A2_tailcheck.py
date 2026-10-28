"""R1 A2 supplement: which Gumbel fit of the 1,000-block maxima extrapolates correctly to large N?

Independent code (imports only the A2 script's own model, numpy and the corpora). The A2 primary run
found the scorer and the plants reproduce (null mean, planted means, power 0.5545 at the report's own
bar) but the bar does not: method-of-moments on the block maxima gives beta 0.0318 where the report
has 0.0251. This script (a) fits a Gumbel by maximum likelihood (own Newton iteration) as well as by
moments on the same 1,000-block maxima, and (b) draws 2 x 10^7 uniform strings of 240 runes so the
maxima of 10^5-blocks (200 of them) and 10^6-blocks (20) can be compared with each fit's prediction.

    V=<venv>; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/A2_tailcheck.py
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

OUT = Path(__file__).resolve().parent / "out_A2.json"  # adds key "tailcheck"
SEED = 20261028_4
N_TOTAL = 20_000_000
EULER = 0.5772156649015329


def gumbel_mle(x: np.ndarray):
    x = np.asarray(x, dtype=np.float64)
    beta = x.std(ddof=1) * math.sqrt(6) / math.pi
    for _ in range(200):
        z = np.exp(-(x - x.max()) / beta)
        w = (x * z).sum() / z.sum()
        f = beta - (x.mean() - w)
        # derivative of w wrt beta: Var_z(x)/beta^2
        var = ((x - w) ** 2 * z).sum() / z.sum()
        fp = 1 + var / beta**2
        nb = beta - f / fp
        if abs(nb - beta) < 1e-15:
            beta = nb
            break
        beta = nb
    z = np.exp(-(x - x.max()) / beta)
    mu = x.max() - beta * math.log(z.mean())
    return float(mu), float(beta)


def main():
    t0 = time.time()
    runes, wid, n_words, _ = a2.load_corpus("cicada-english")
    seq = runes[wid < math.floor(0.9 * n_words)]
    P, *_ = a2.fit(seq)
    score_rows = a2.make_scorer(P)
    rng = np.random.default_rng(SEED)
    CH = 20000
    v = np.empty(N_TOTAL)
    for s in range(0, N_TOTAL, CH):
        v[s : s + CH] = score_rows(rng.integers(0, a2.B, size=(CH, a2.L)))
    t_draw = time.time() - t0

    bm1k = v.reshape(-1, 1000).max(axis=1)
    fits = {}
    for tag, sub in (("first_100_blocks", bm1k[:100]), ("first_1000_blocks", bm1k[:1000]), ("all_20000_blocks", bm1k)):
        mom = a2.gumbel_mom(sub)
        mle = gumbel_mle(sub)
        fits[tag] = {"mom": dict(mu_b=mom[0], beta=mom[1], bar_1e6=a2.bar(*mom, 1e6), bar_2p32=a2.bar(*mom, 2.0**32)),
                     "mle": dict(mu_b=mle[0], beta=mle[1], bar_1e6=a2.bar(*mle, 1e6), bar_2p32=a2.bar(*mle, 2.0**32)),
                     "block_max_mean": float(sub.mean()), "block_max_sd": float(sub.std(ddof=1)),
                     "block_max_skew": float(((sub - sub.mean()) ** 3).mean() / sub.std() ** 3)}
    # Gumbel skewness is 1.1395; a lighter right tail shows as smaller skew
    obs = {}
    for N in (10_000, 100_000, 1_000_000):
        m = v.reshape(-1, N).max(axis=1)
        obs[str(N)] = dict(n_blocks=int(len(m)), mean=float(m.mean()), sd=float(m.std(ddof=1)) if len(m) > 1 else None,
                           max=float(m.max()), q50=float(np.median(m)))
    pred = {}
    for tag in fits:
        for meth in ("mom", "mle"):
            mu, beta = fits[tag][meth]["mu_b"], fits[tag][meth]["beta"]
            pred[f"{tag}/{meth}"] = {
                str(N): dict(mean=mu + beta * math.log(N / 1000) + EULER * beta, sd=beta * math.pi / math.sqrt(6),
                             q99=a2.bar(mu, beta, N),
                             observed_share_above_q99=float((v.reshape(-1, N).max(axis=1) > a2.bar(mu, beta, N)).mean()))
                for N in (10_000, 100_000, 1_000_000)
            }
    # empirical per-draw exceedance of the candidate bars at N = 10^6 (the bar means P = 0.01 / 10^6 per draw)
    exceed = {k: int((v > val).sum()) for k, val in
              {"report_bar_1e6_-6.0705": -6.0705, "mom_1000blocks_bar_1e6": fits["first_1000_blocks"]["mom"]["bar_1e6"],
               "mle_1000blocks_bar_1e6": fits["first_1000_blocks"]["mle"]["bar_1e6"]}.items()}
    out = dict(sub_attack="A2-supplement", n_draws=N_TOTAL, L=a2.L, seed=SEED,
               command="V=/tmp/claude-0/-home-user-cicada-3301-Code-cracker-attempt-1/4950dc03-e080-591a-84c1-d8ea81cef212/"
                       "scratchpad/venv; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/A2_tailcheck.py",
               overall=dict(mean=float(v.mean()), sd=float(v.std(ddof=1)), max=float(v.max())),
               fits=fits, observed_block_maxima=obs, predicted=pred, draws_above_bar_in_2e7=exceed,
               expected_draws_above_a_true_1e6_bar_in_2e7=0.01 / 1e6 * N_TOTAL,
               wall_time_s=dict(draws=round(t_draw, 1), total=round(time.time() - t0, 1)))
    doc = json.loads(OUT.read_text())
    doc["tailcheck"] = out
    OUT.write_text(json.dumps(doc, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
