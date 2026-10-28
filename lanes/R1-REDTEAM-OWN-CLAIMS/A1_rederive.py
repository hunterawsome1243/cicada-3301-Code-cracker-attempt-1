"""R1-REDTEAM-OWN-CLAIMS sub-attack A1: independent re-derivation of lp-ngram3-heldout at L = 240.

Written from the PREREG section 2 row A1 and the presets.py / ngram.py docstrings only. It does
NOT import runeforge.scoring, runeforge.beam, runeforge.runner, runeforge.gpu, runeforge.generators
or scripts/scorer_power.py. Data loaders only: runeforge.gematria.runes_to_indices for the
solved sections' plaintext; corpora are read with np.load and data/corpora/index.json.

Model: order-3 interpolated Witten-Bell over 29 rune indices,
  P_k(x|h) = lam(h) ML_k(x|h) + (1 - lam(h)) P_{k-1}(x|h'),  lam(h) = c(h) / (c(h) + N1+(h.)),
  lam = 0 when c(h) = 0, P_0 = 1/29, c(h) = number of (h, next) events in training, counts collected
  per training sequence (no n-gram crosses a sequence). Training: plaintext of every solved section
  except a-koan-1 and the-loss-of-divinity. Score = mean log2 P per rune over the window; position 0
  is scored by P_1, position 1 by P_2 with a one-rune history, the rest by P_3.

Usage (repo root):  python lanes/R1-REDTEAM-OWN-CLAIMS/A1_rederive.py [--draws 100000] [--seed S]
Writes lanes/R1-REDTEAM-OWN-CLAIMS/out_A1.json.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from runeforge.gematria import runes_to_indices  # noqa: E402  (data loader only)

A = 29
HELDOUT_IDS = ("a-koan-1", "the-loss-of-divinity")
L = 240
EULER = 0.5772156649
ALPHA = 0.01
OUT = REPO / "lanes" / "R1-REDTEAM-OWN-CLAIMS" / "out_A1.json"


# ---------------------------------------------------------------- data
def solved_plains() -> dict[str, np.ndarray]:
    d = json.loads((REPO / "data/canon/solved_sections.json").read_text(encoding="utf-8"))
    out = {}
    for s in d["sections"]:
        idx = runes_to_indices(s["plain"])
        assert idx.size == s["n_runes"], (s["id"], idx.size, s["n_runes"])
        out[s["id"]] = idx.astype(np.int64)
    return out


def corpus_tail(name: str) -> tuple[np.ndarray, dict]:
    index = json.loads((REPO / "data/corpora/index.json").read_text(encoding="utf-8"))
    n_words = int(index["corpora"][name]["n_words"])
    z = np.load(REPO / "data/corpora" / f"{name}.npz", allow_pickle=False)
    runes = z["runes"].astype(np.int64)
    wid = z["word_ids"].astype(np.int64)
    cut = (9 * n_words) // 10  # floor(0.9 * n_words), integer-exact
    tail = runes[wid >= cut]
    return tail, {"n_words": n_words, "cut_word": cut, "n_runes": int(runes.size),
                  "tail_runes": int(tail.size)}


# ---------------------------------------------------------------- model
class WB3:
    def __init__(self, seqs: list[np.ndarray]):
        c1 = np.zeros(A, np.float64)
        c2 = np.zeros((A, A), np.float64)
        c3 = np.zeros((A, A, A), np.float64)
        for s in seqs:
            np.add.at(c1, s, 1)
            if s.size >= 2:
                np.add.at(c2, (s[:-1], s[1:]), 1)
            if s.size >= 3:
                np.add.at(c3, (s[:-2], s[1:-1], s[2:]), 1)
        self.c1, self.c2, self.c3 = c1, c2, c3
        # order 1 (empty history)
        n = c1.sum()
        t = (c1 > 0).sum()
        lam = n / (n + t)
        p1 = lam * c1 / n + (1 - lam) / A
        # order 2
        n2 = c2.sum(axis=1, keepdims=True)
        t2 = (c2 > 0).sum(axis=1, keepdims=True)
        with np.errstate(invalid="ignore", divide="ignore"):
            lam2 = np.where(n2 > 0, n2 / (n2 + t2), 0.0)
            ml2 = np.where(n2 > 0, c2 / np.where(n2 > 0, n2, 1), 0.0)
        p2 = lam2 * ml2 + (1 - lam2) * p1[None, :]
        # order 3
        n3 = c3.sum(axis=2, keepdims=True)
        t3 = (c3 > 0).sum(axis=2, keepdims=True)
        with np.errstate(invalid="ignore", divide="ignore"):
            lam3 = np.where(n3 > 0, n3 / (n3 + t3), 0.0)
            ml3 = np.where(n3 > 0, c3 / np.where(n3 > 0, n3, 1), 0.0)
        p3 = lam3 * ml3 + (1 - lam3) * p2[None, :, :]
        assert np.allclose(p1.sum(), 1) and np.allclose(p2.sum(-1), 1) and np.allclose(p3.sum(-1), 1)
        self.p1, self.p2, self.p3 = p1, p2, p3
        self.l1, self.l2, self.l3 = np.log2(p1), np.log2(p2), np.log2(p3)
        self.n_train = int(n)

    def position_logprobs(self, w: np.ndarray) -> np.ndarray:
        """w: (M, L) int array -> (M, L) log2 P per position."""
        w = np.asarray(w, np.int64)
        if w.ndim == 1:
            w = w[None, :]
        out = np.empty(w.shape, np.float64)
        out[:, 0] = self.l1[w[:, 0]]
        if w.shape[1] > 1:
            out[:, 1] = self.l2[w[:, 0], w[:, 1]]
        if w.shape[1] > 2:
            out[:, 2:] = self.l3[w[:, :-2], w[:, 1:-1], w[:, 2:]]
        return out

    def scores(self, w: np.ndarray) -> np.ndarray:
        return self.position_logprobs(w).mean(axis=1)


def build_model() -> tuple[WB3, dict]:
    plains = solved_plains()
    train_ids = [k for k in plains if k not in HELDOUT_IDS]
    model = WB3([plains[k] for k in train_ids])
    return model, {"train_ids": train_ids, "n_train_runes": model.n_train,
                   "heldout_ids": list(HELDOUT_IDS),
                   "heldout_runes": int(sum(plains[k].size for k in HELDOUT_IDS))}


# ---------------------------------------------------------------- null + bar
def null_scores(model: WB3, draws: int, seed: int, chunk: int = 20000) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.empty(draws, np.float64)
    for i in range(0, draws, chunk):
        m = min(chunk, draws - i)
        out[i:i + m] = model.scores(rng.integers(0, A, size=(m, L)))
    return out


def gumbel_fit(scores: np.ndarray, block: int = 1000) -> dict:
    k = scores.size // block
    mx = scores[: k * block].reshape(k, block).max(axis=1)
    sd = mx.std(ddof=1)
    beta = sd * math.sqrt(6) / math.pi
    mu = mx.mean() - EULER * beta
    def bar(N):
        return mu + beta * math.log(N / block) - beta * math.log(-math.log(1 - ALPHA))
    return {"blocks": int(k), "block": block, "mu_b": mu, "beta": beta,
            "blockmax_mean": float(mx.mean()), "blockmax_sd": float(sd),
            "bar_1e6": bar(1e6), "bar_2p32": bar(2.0 ** 32),
            "null_mean": float(scores.mean()), "null_sd": float(scores.std(ddof=1)),
            "null_max": float(scores.max()), "draws": int(scores.size),
            # out-of-sample check: the M-draw maximum vs the fit's predicted mode/mean of max(M)
            "pred_mean_max_of_all": mu + beta * math.log(scores.size / block) + EULER * beta}


# ---------------------------------------------------------------- plants
def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def plant_windows(stream: np.ndarray, n: int, rng: np.random.Generator,
                  segments: list[tuple[int, int]] | None = None) -> np.ndarray:
    """n windows of L runes at distinct random start offsets. segments (start, stop) restricts
    windows to lie inside one segment (None = the whole stream)."""
    if segments is None:
        segments = [(0, stream.size)]
    starts = np.concatenate([np.arange(a, b - L + 1) for a, b in segments])
    pick = rng.choice(starts, size=n, replace=False)
    return np.stack([stream[s:s + L] for s in pick]), pick


REPORT = {  # reports/scorer_power.md at fbe43e7, lp-ngram3-heldout, L = 240
    "bar_1e6": -6.1625, "bar_2p32": -5.7788, "null_mean": -7.1687, "null_sd": 0.1506,
    "mu_b": -6.6905, "beta": 0.0459,
    "registers": {
        "latin": {"line": 375, "power_1e6": 1.000, "power_2p32": 1.000, "mean": -4.8332, "sd": 0.142, "min": -5.2940},
        "vowel-dropped-english": {"line": 453, "power_1e6": 1.000, "power_2p32": 0.790, "mean": -5.6522, "sd": 0.160, "min": -6.0281},
        "english-general": {"line": 219, "power_1e6": 1.000, "power_2p32": 1.000, "mean": -4.3200, "sd": 0.177, "min": -4.7470},
        "heldout-solved-sections": {"line": 609, "power_1e6": 1.000, "power_2p32": 1.000, "mean": -3.8723, "sd": 0.272, "min": -4.2799},
    },
    "n_plants": 200,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=100_000)
    ap.add_argument("--extra-draws", type=int, default=1_000_000,
                    help="a second, larger null to measure the bar's own sampling noise")
    ap.add_argument("--seed", type=int, default=3301_2026_1028)
    ap.add_argument("--plants", type=int, default=200)
    args = ap.parse_args()
    t0 = time.time()

    model, minfo = build_model()

    # null + bars: the PREREG fit (100,000 draws) at our seed, plus 5 more seeds at the same scale
    # (spread of a 100-block fit) and one 10^6-draw fit
    nulls = {}
    fit_main = gumbel_fit(null_scores(model, args.draws, args.seed))
    nulls["main"] = fit_main
    rep_fits = []
    for j in range(1, 6):
        rep_fits.append(gumbel_fit(null_scores(model, args.draws, args.seed + j)))
    nulls["replicate_seeds_100k"] = [{k: f[k] for k in ("bar_1e6", "bar_2p32", "mu_b", "beta", "null_mean", "null_sd", "null_max")} for f in rep_fits]
    b6 = np.array([fit_main["bar_1e6"]] + [f["bar_1e6"] for f in rep_fits])
    b32 = np.array([fit_main["bar_2p32"]] + [f["bar_2p32"] for f in rep_fits])
    nulls["spread_6x100k"] = {"bar_1e6_mean": float(b6.mean()), "bar_1e6_sd": float(b6.std(ddof=1)),
                              "bar_2p32_mean": float(b32.mean()), "bar_2p32_sd": float(b32.std(ddof=1))}
    if args.extra_draws:
        big = gumbel_fit(null_scores(model, args.extra_draws, args.seed + 100))
        nulls["big"] = big

    # plants
    rng = np.random.default_rng(args.seed + 7)
    plains = solved_plains()
    regs = {}
    tail_info = {}
    for name in ("latin", "vowel-dropped-english", "english-general"):
        tail, info = corpus_tail(name)
        tail_info[name] = info
        regs[name] = (tail, None)
    ho = np.concatenate([plains[k] for k in HELDOUT_IDS])
    regs["heldout-solved-sections"] = (ho, None)
    tail_info["heldout-solved-sections"] = {"tail_runes": int(ho.size), "rule": "concatenation a-koan-1 + the-loss-of-divinity"}

    bars = {"ours_main": (fit_main["bar_1e6"], fit_main["bar_2p32"]),
            "report": (REPORT["bar_1e6"], REPORT["bar_2p32"])}
    if "big" in nulls:
        bars["ours_1e6draws"] = (nulls["big"]["bar_1e6"], nulls["big"]["bar_2p32"])

    def cell(scores):
        res = {"n": int(scores.size), "mean": float(scores.mean()), "sd": float(scores.std(ddof=1)),
               "min": float(scores.min()), "max": float(scores.max())}
        for bn, (b6_, b32_) in bars.items():
            k6 = int((scores > b6_).sum()); k32 = int((scores > b32_).sum())
            res[f"power_1e6@{bn}"] = k6 / scores.size
            res[f"power_2p32@{bn}"] = k32 / scores.size
            res[f"wilson_1e6@{bn}"] = wilson(k6, scores.size)
            res[f"wilson_2p32@{bn}"] = wilson(k32, scores.size)
        return res

    plants = {}
    for name, (stream, segs) in regs.items():
        w, _ = plant_windows(stream, args.plants, rng, segs)
        plants[name] = cell(model.scores(w))
    # variant: held-out sections with windows confined to one section (no window across the join)
    a, b = plains[HELDOUT_IDS[0]].size, ho.size
    w, _ = plant_windows(ho, args.plants, rng, [(0, a), (a, b)])
    plants["heldout-solved-sections (within-section windows, variant)"] = cell(model.scores(w))

    # comparison against the PREREG rule
    comp = {"targets": []}
    def widened(p, n=200):
        lo, hi = wilson(round(p * n), n)
        return max(0.0, lo - 0.05), min(1.0, hi + 0.05)
    for bn, ours in (("bar@10^6", fit_main["bar_1e6"]), ("bar@2^32", fit_main["bar_2p32"])):
        rep = REPORT["bar_1e6"] if bn == "bar@10^6" else REPORT["bar_2p32"]
        comp["targets"].append({"target": f"lp-ngram3-heldout L240 {bn}", "reported": rep, "ours": ours,
                                "delta": ours - rep, "rule": "|delta| <= 0.05", "pass": bool(abs(ours - rep) <= 0.05)})
    for name, r in REPORT["registers"].items():
        for key, rk in (("power_1e6@ours_main", "power_1e6"), ("power_2p32@ours_main", "power_2p32")):
            lo, hi = widened(r[rk])
            ours = plants[name][key]
            comp["targets"].append({"target": f"{name} L240 {rk} (scorer_power.md:{r['line']})",
                                    "reported": r[rk], "ours": ours, "delta": ours - r[rk],
                                    "rule": f"inside Wilson95(reported, n=200) widened by 0.05 = [{lo:.3f}, {hi:.3f}]",
                                    "pass": bool(lo <= ours <= hi)})
    comp["all_pass_excluding_crosscheck"] = all(t["pass"] for t in comp["targets"])

    out = {
        "lane": "R1-REDTEAM-OWN-CLAIMS", "sub_attack": "A1", "numbering": "LP2-0-57",
        "canon_sha256": "023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585",
        "audited_git": "fbe43e7",
        "command": "$V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/A1_rederive.py "
                   f"--draws {args.draws} --extra-draws {args.extra_draws} --seed {args.seed} --plants {args.plants}",
        "independence": "no import of runeforge.scoring/beam/runner/gpu/generators or scripts/scorer_power.py; "
                        "implementation source not read before these numbers were written",
        "model": {"type": "order-3 interpolated Witten-Bell, P_0 = 1/29, c(h) = sum_x c(h x)", **minfo,
                  "N1plus_unigram": int((model.c1 > 0).sum()),
                  "seen_bigram_histories": int((model.c2.sum(1) > 0).sum()),
                  "seen_trigram_histories": int((model.c3.sum(2) > 0).sum())},
        "L": L, "alpha": ALPHA, "seed": args.seed,
        "null": nulls, "plant_registers": tail_info, "plants": plants,
        "report_values": REPORT, "comparison": comp,
        "wall_time_s": None,
    }
    out["wall_time_s"] = round(time.time() - t0, 1)
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps({"bars": bars, "plants": {k: {kk: v[kk] for kk in ("mean", "sd", "min", "power_1e6@ours_main", "power_2p32@ours_main")} for k, v in plants.items()},
                      "comparison": comp, "wall_time_s": out["wall_time_s"]}, indent=1, default=float))


if __name__ == "__main__":
    main()
