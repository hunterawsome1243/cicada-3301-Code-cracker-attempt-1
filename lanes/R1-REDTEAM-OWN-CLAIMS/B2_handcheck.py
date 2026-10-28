"""R1-REDTEAM-OWN-CLAIMS sub-attack B2: hand-formula recompute of the P3 bar, screening bar,
expected false positives and the null-consistency sentence.

Reads only committed JSON evidence (no runeforge import):
  reports/calib-staging/lp-ngram3-heldout__beam-skip__L240.json  (the staged fit)
  lanes/P3-MT19937-PY27-EXACT/null.json                           (the lane's nulls)
Targets (lanes/P3-MT19937-PY27-EXACT/PREREG.md at fbe43e7): §4 lines 108-119 and the
2026-10-27 addendum lines 200-206.

Gumbel arithmetic written from the standard definitions, not from calib.threshold_for:
  max of n i.i.d. block maxima of block B is Gumbel(mu_b + beta ln(N/B), beta) for N = n B;
  bar(N, alpha) is the (1 - alpha) quantile of that max: mu_N - beta ln(-ln(1 - alpha));
  expected count of single trials above the bar = N P(one trial > bar)
     = exp(-(bar - mu_N)/beta)   (Gumbel tail, exact for the fitted extreme-value model);
  mean of one block maximum = mu_b + gamma beta.

Run from the repo root:  $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/B2_handcheck.py
"""
import json
import math
import os
import sys
import time

T0 = time.time()
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STAGED = os.path.join(ROOT, "reports/calib-staging/lp-ngram3-heldout__beam-skip__L240.json")
NULL = os.path.join(ROOT, "lanes/P3-MT19937-PY27-EXACT/null.json")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out_B2.json")
EULER_GAMMA = 0.5772156649015329
ALPHA = 0.01

fit = json.load(open(STAGED))
null = json.load(open(NULL))
mu_b = fit["fit"]["mu_block"]
beta = fit["fit"]["beta"]
block = fit["fit"]["block"]


def mu_at(n):
    return mu_b + beta * math.log(n / block)


def bar_at(n, alpha=ALPHA):
    return mu_at(n) - beta * math.log(-math.log(1.0 - alpha))


def expected_singles_above(n, bar):
    # N * P(one trial > bar) under the Gumbel model of the max of N
    return math.exp(-(bar - mu_at(n)) / beta)


N_FAM = 2 ** 32
N_CLAIM = 10 ** 6
bar_fam = bar_at(N_FAM)
bar_claim = bar_at(N_CLAIM)
efp = expected_singles_above(N_FAM, bar_fam)
exp_null_max = mu_at(N_FAM) + EULER_GAMMA * beta
survivors_above_claim_bar = N_FAM * expected_singles_above(N_CLAIM, bar_claim) / N_CLAIM
pred_block_max_mean = mu_b + EULER_GAMMA * beta
gumbel_sd = math.pi * beta / math.sqrt(6)
n1 = null["null1_shuffle"]
n2 = null["null2_sha256"]
rep_n = null["trials_per_replicate"]
assert rep_n == block, (rep_n, block)
pred_max_over_reps = mu_at(n1["n"] * rep_n) + EULER_GAMMA * beta

claims = {
    "bar_2^32": {"claimed": -5.7284, "ours": bar_fam},
    "mu_N_2^32": {"claimed": -5.9016, "ours": mu_at(N_FAM)},
    "expected_null_max_2^32": {"claimed": -5.8799, "ours": exp_null_max},
    "claim_bar_10^6": {"claimed": -6.0434, "ours": bar_claim},
    "expected_false_positives": {"claimed": 0.0101, "ours": efp},
    "survivors_above_claim_bar_over_slice": {"claimed": 43, "ours": survivors_above_claim_bar},
    "predicted_block_max_mean": {"claimed": -6.455, "ours": pred_block_max_mean},
    "null1_replicate_mean": {"claimed": -6.4565, "ours": n1["mean"]},
    "null1_minus_predicted": {"claimed": "+0.0015 ('0.0015 above')", "ours": n1["mean"] - pred_block_max_mean},
    "null1_minus_predicted_in_beta": {"claimed": "within 0.04 beta", "ours": abs(n1["mean"] - pred_block_max_mean) / beta},
}
for k, v in claims.items():
    if isinstance(v["claimed"], (int, float)):
        v["delta"] = v["ours"] - v["claimed"]

tol4 = all(abs(claims[k]["delta"]) <= 1e-4 + 5e-5 for k in ("bar_2^32", "claim_bar_10^6", "expected_false_positives"))
tol3 = all(abs(claims[k]["delta"]) <= 1e-3 for k in ("predicted_block_max_mean", "null1_replicate_mean"))

out = {
    "lane": "R1-REDTEAM-OWN-CLAIMS",
    "sub_attack": "B2",
    "numbering": "LP2-0-57",
    "audited_git": "fbe43e7",
    "inputs": {
        "staged_fit": "reports/calib-staging/lp-ngram3-heldout__beam-skip__L240.json",
        "staged_fit_sha256_expected": "46a95f857fbf10ed9bdd164b56f39108cc362970d9b80460f4416e62989162ea",
        "null": "lanes/P3-MT19937-PY27-EXACT/null.json",
        "mu_block": mu_b, "beta": beta, "block": block,
    },
    "claims": claims,
    "extra": {
        "gumbel_sd_of_block_max": gumbel_sd,
        "null1_sd": n1["sd"], "null2_sd": n2["sd"],
        "null2_mean": n2["mean"], "null2_minus_predicted": n2["mean"] - pred_block_max_mean,
        "se_of_null1_mean": n1["sd"] / math.sqrt(n1["n"]),
        "null1_minus_predicted_in_se": (n1["mean"] - pred_block_max_mean) / (n1["sd"] / math.sqrt(n1["n"])),
        "predicted_mean_of_max_over_200x1000": pred_max_over_reps,
        "null1_max": n1["max"], "null2_max": n2["max"],
        "note_expected_fp": "N*P(clear) at the alpha=0.01 Gumbel bar is -ln(0.99)=0.010050 for any fit: the 0.0101 is a property of alpha, not of mu_b/beta",
    },
    "comparison": {
        "rule": "all three numbers (bar 2^32, bar 10^6, expected fp) to 1e-4 (as rounded in the PREREG); the replicate mean and the fit's predicted block-max mean to 1e-3",
        "three_numbers_to_1e-4": tol4,
        "means_to_1e-3": tol3,
        "reproduced": tol4 and tol3,
        "wording": "the PREREG says the replicate mean is '0.0015 above' the prediction; it is 0.0015 BELOW it (-6.4565 < -6.4550), i.e. on the conservative side",
    },
    "command": "V=/tmp/claude-0/-home-user-cicada-3301-Code-cracker-attempt-1/4950dc03-e080-591a-84c1-d8ea81cef212/scratchpad/venv; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/B2_handcheck.py",
    "wall_seconds": None,
}
out["wall_seconds"] = round(time.time() - T0, 3)
json.dump(out, open(OUT, "w"), indent=1)
json.dump(out["claims"], sys.stdout, indent=1)
print()
print(json.dumps(out["comparison"], indent=1))
