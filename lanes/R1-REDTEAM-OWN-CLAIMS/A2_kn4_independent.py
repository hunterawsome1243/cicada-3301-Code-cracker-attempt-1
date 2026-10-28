"""R1-REDTEAM-OWN-CLAIMS sub-attack A2: independent interpolated modified Kneser-Ney order 4.

Written from docs/kn-scorer-design.md section 2 only (2.1 keys, 2.3 fit, 2.4 scoring positions);
it does not import runeforge.scoring / beam / runner / gpu / generators or scripts/scorer_power.py,
and their implementation source was not read before these numbers were recorded. It reads the
built corpora with numpy (data/corpora/*.npz) and checks their pins against data/corpora/index.json.

Targets (reports/scorer_power.md at fbe43e7): line 97 (kn4-cicada L = 240 bar row), line 379
(latin, L = 240, kn4-cicada: power 1.000 [0.981, 1.000]), line 457 (vowel-dropped-english,
L = 240, kn4-cicada: power 0.550 [0.481, 0.617]).

Method fixed before running (PREREG section 2, rows A1/A2):
- train: cicada-english runes with word_ids < floor(0.9 * 74,803) = 67,322, one sequence;
- null: uniform strings of 240 runes; Gumbel by the method of moments on block maxima of 1,000
  consecutive draws; bar(N) = mu_b + beta * ln(N / 1000) - beta * ln(-ln(1 - 0.01)).
  Primary: 1,000,000 draws (1,000 blocks). The first 100,000 draws (100 blocks, the report's
  scale) are reported as well.
- plants: random distinct offsets in the held-out tail (words >= floor(0.9 * n_words)) of latin
  and vowel-dropped-english, windows of 240 runes at any rune offset; the decode of a rigid
  additive family with its true key is the plaintext, so a plant's score is the window's score.
  Primary: 2,000 plants per register; the first 200 are reported as well.
- power = share of plants strictly above the bar@10^6; Wilson 95 %.

    V=<venv>; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/A2_kn4_independent.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out_A2.json"
B = 29
N_ORDER = 4
L = 240
BLOCK = 1000
ALPHA = 0.01
SEED_NULL = 20261028_2
SEED_PLANT = 20261028_3
N_NULL = 1_000_000
N_NULL_REPORT_SCALE = 100_000
N_PLANTS = 2000
N_PLANTS_MIN = 200


# ---------------------------------------------------------------- data
def load_corpus(name: str):
    z = np.load(ROOT / "data" / "corpora" / f"{name}.npz")
    runes = z["runes"].astype(np.int64)
    wid = z["word_ids"].astype(np.int64)
    idx = json.loads((ROOT / "data" / "corpora" / "index.json").read_text())["corpora"][name]
    sha = hashlib.sha256(",".join(str(int(v)) for v in runes).encode()).hexdigest()
    assert sha == idx["indices_sha256"], (name, sha)
    n_words = int(wid.max()) + 1
    assert n_words == idx["n_words"], (name, n_words)
    return runes, wid, n_words, sha


# ---------------------------------------------------------------- fit (design 2.3)
def grams(seq: np.ndarray, k: int) -> np.ndarray:
    """packed k-gram keys, oldest symbol most significant (design 2.1)."""
    n = len(seq) - k + 1
    key = np.zeros(n, dtype=np.int64)
    for j in range(k):
        key = key * B + seq[j : j + n]
    return key


def discounts(eff_values: np.ndarray):
    pos = eff_values[eff_values > 0]
    n1, n2, n3, n4 = (int((pos == r).sum()) for r in (1, 2, 3, 4))
    if n1 == 0 or n2 == 0:
        return [0.5, 0.5, 0.5], "fallback-0.5", (n1, n2, n3, n4)
    Y = n1 / (n1 + 2 * n2)
    D1 = 1 - 2 * Y * n2 / n1
    src = []
    if n3 == 0:
        D2 = D1
        src.append("D2<-D1")
    else:
        D2 = 2 - 3 * Y * n3 / n2
    if n3 == 0 or n4 == 0:
        D3 = D2
        src.append("D3<-D2")
    else:
        D3 = 3 - 4 * Y * n4 / n3
    D = [min(max(D1, 0.05), 1.0), min(max(D2, 0.05), 2.0), min(max(D3, 0.05), 3.0)]
    source = "modified-kn" if not src else "partial:" + ",".join(src)
    return D, source, (n1, n2, n3, n4)


def disc_of(c: np.ndarray, D) -> np.ndarray:
    d = np.zeros(c.shape, dtype=np.float64)
    d[c == 1] = D[0]
    d[c == 2] = D[1]
    d[c >= 3] = D[2]
    return d


def fit(seq: np.ndarray, order: int = N_ORDER):
    raw = {}
    uniq = {}
    for k in range(1, order + 1):
        u, c = np.unique(grams(seq, k), return_counts=True)
        uniq[k] = u
        raw[k] = c.astype(np.int64)
    eff = {}
    for k in range(1, order + 1):
        full = np.zeros(B**k, dtype=np.int64)
        if k == order:
            full[uniq[k]] = raw[k]
        else:
            suf, cc = np.unique(uniq[k + 1] % (B**k), return_counts=True)
            full[suf] = cc
        eff[k] = full
    P = {}
    info = {}
    # level 1
    D, src, coc = discounts(eff[1][uniq[1]])
    c1 = eff[1].astype(np.float64)
    C = c1.sum()
    N1 = int((eff[1] == 1).sum()); N2 = int((eff[1] == 2).sum()); N3 = int((eff[1] >= 3).sum())
    gamma1 = (D[0] * N1 + D[1] * N2 + D[2] * N3) / C
    P[1] = np.maximum(c1 - disc_of(eff[1], D), 0.0) / C + gamma1 / B
    info[1] = dict(discounts=D, source=src, counts_of_counts=coc, n_keys=int(len(uniq[1])))
    edge = {}
    for k in range(2, order + 1):
        D, src, coc = discounts(eff[k][uniq[k]])
        e = eff[k].reshape(B ** (k - 1), B)
        ef = e.astype(np.float64)
        cch = ef.sum(axis=1)
        N1 = (e == 1).sum(axis=1); N2 = (e == 2).sum(axis=1); N3 = (e >= 3).sum(axis=1)
        lower_h = np.arange(B ** (k - 1)) % (B ** (k - 2))
        lower = P[k - 1].reshape(B ** (k - 2), B)[lower_h]  # (B^(k-1), B)
        seen = cch > 0
        Pk = lower.copy()
        g = (D[0] * N1[seen] + D[1] * N2[seen] + D[2] * N3[seen]) / cch[seen]
        Pk[seen] = np.maximum(ef[seen] - disc_of(e[seen], D), 0.0) / cch[seen, None] + g[:, None] * lower[seen]
        # edge case audit: histories present as a gram's history in U_k but with cc(h) == 0
        hist_in_U = np.zeros(B ** (k - 1), dtype=bool)
        hist_in_U[uniq[k] // B] = True
        edge[k] = int((hist_in_U & ~seen).sum())
        P[k] = Pk.reshape(-1)
        info[k] = dict(discounts=D, source=src, counts_of_counts=coc, n_keys=int(len(uniq[k])),
                       seen_histories=int(seen.sum()), histories_in_U_with_zero_eff=edge[k])
    # sanity: every row sums to 1
    maxdev = {}
    for k in range(1, order + 1):
        rows = P[k].reshape(-1, B)
        dev = float(np.abs(rows.sum(axis=1) - 1).max())
        assert dev < 1e-9, (k, dev)
        assert (rows > 0).all()
        maxdev[k] = dev
    return P, info, maxdev, eff, uniq


def distribution(P, history) -> np.ndarray:
    """P(. | history) using the last min(len, n-1) symbols (prefix positions use lower levels)."""
    h = list(history)[-(N_ORDER - 1):] if len(history) else []
    k = len(h) + 1
    key = 0
    for s in h:
        key = key * B + int(s)
    return P[k].reshape(-1, B)[key].copy()


# ---------------------------------------------------------------- scoring (design 2.4)
def make_scorer(P):
    LP = {k: np.log2(P[k]) for k in P}

    def score_rows(x: np.ndarray) -> np.ndarray:
        x = x.astype(np.int64)
        R, n = x.shape
        tot = np.zeros(R, dtype=np.float64)
        for i in range(n):
            m = min(i, N_ORDER - 1)
            key = np.zeros(R, dtype=np.int64)
            for j in range(i - m, i + 1):
                key = key * B + x[:, j]
            tot += LP[m + 1][key]
        return tot / n

    return score_rows


def gumbel_mom(blockmax: np.ndarray):
    s = float(blockmax.std(ddof=1))
    beta = s * math.sqrt(6) / math.pi
    mu = float(blockmax.mean()) - 0.5772156649015329 * beta
    return mu, beta


def bar(mu, beta, N):
    return mu + beta * math.log(N / BLOCK) - beta * math.log(-math.log(1 - ALPHA))


def wilson(k, n, z=1.959963984540054):
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [max(0.0, c - h), min(1.0, c + h)]


def main():
    t0 = time.time()
    runes, wid, n_words, sha_c = load_corpus("cicada-english")
    train_words = math.floor(0.9 * n_words)
    seq = runes[wid < train_words]
    P, info, maxdev, eff, uniq = fit(seq)
    t_fit = time.time() - t0
    score_rows = make_scorer(P)

    # null
    rng = np.random.default_rng(SEED_NULL)
    null = np.empty(N_NULL)
    CH = 20000
    for s in range(0, N_NULL, CH):
        null[s : s + CH] = score_rows(rng.integers(0, B, size=(CH, L)))
    t_null = time.time() - t0 - t_fit

    def fit_bars(v):
        bm = v.reshape(-1, BLOCK).max(axis=1)
        mu, beta = gumbel_mom(bm)
        return dict(n=int(len(v)), mean=float(v.mean()), sd=float(v.std(ddof=1)), max=float(v.max()),
                    blocks=int(len(bm)), mu_b=mu, beta=beta,
                    bar_1e6=bar(mu, beta, 1e6), bar_2p32=bar(mu, beta, 2.0**32))

    null_primary = fit_bars(null)
    null_report_scale = fit_bars(null[:N_NULL_REPORT_SCALE])

    # plants
    prng = np.random.default_rng(SEED_PLANT)
    plants = {}
    for name in ("latin", "vowel-dropped-english"):
        r, w, nw, sha = load_corpus(name)
        tail = r[w >= math.floor(0.9 * nw)]
        n_off = len(tail) - L + 1
        offs = prng.choice(n_off, size=N_PLANTS, replace=False)
        X = np.stack([tail[o : o + L] for o in offs])
        sc = score_rows(X)
        plants[name] = dict(tail_runes=int(len(tail)), offsets_available=int(n_off), indices_sha256=sha,
                            scores=sc, offsets=offs)
    t_plant = time.time() - t0 - t_fit - t_null

    def power_block(sc, bars):
        out = {}
        for tag, b in bars.items():
            k = int((sc > b).sum())
            out[tag] = dict(bar=b, above=k, n=int(len(sc)), power=k / len(sc), wilson95=wilson(k, len(sc)))
        return out

    reported = {
        "latin": dict(line=379, power=1.000, wilson=[0.981, 1.000], planted_mean=-4.3551, planted_sd=0.163,
                      planted_min=-4.7632, power_2p32=1.000),
        "vowel-dropped-english": dict(line=457, power=0.550, wilson=[0.481, 0.617], planted_mean=-6.0336,
                                      planted_sd=0.184, planted_min=-6.4721, power_2p32=0.170),
    }
    rep_bar = dict(line=97, null_mean=-6.6765, null_sd=0.0937, mu_b=-6.3592, beta=0.0251,
                   bar_1e6=-6.0705, bar_1e6_ci=[-6.1210, -6.0138], bar_2p32=-5.8605,
                   bar_2p32_ci=[-5.9471, -5.7625])

    results = {}
    for name, d in plants.items():
        sc = d["scores"]
        rp = reported[name]
        res = dict(
            tail_runes=d["tail_runes"], offsets_available=d["offsets_available"], indices_sha256=d["indices_sha256"],
            planted_mean=float(sc.mean()), planted_sd=float(sc.std(ddof=1)), planted_min=float(sc.min()),
            planted_mean_first200=float(sc[:N_PLANTS_MIN].mean()),
            primary_2000_plants_primary_bar=power_block(sc, {"bar_1e6": null_primary["bar_1e6"],
                                                            "bar_2p32": null_primary["bar_2p32"]}),
            first200_plants_primary_bar=power_block(sc[:N_PLANTS_MIN], {"bar_1e6": null_primary["bar_1e6"]}),
            primary_2000_plants_report_scale_bar=power_block(sc, {"bar_1e6": null_report_scale["bar_1e6"]}),
            primary_2000_plants_reported_bar=power_block(sc, {"bar_1e6": rep_bar["bar_1e6"],
                                                             "bar_1e6_ci_low": rep_bar["bar_1e6_ci"][0],
                                                             "bar_1e6_ci_high": rep_bar["bar_1e6_ci"][1]}),
            reported=rp,
        )
        lo, hi = rp["wilson"][0] - 0.05, rp["wilson"][1] + 0.05
        p = res["primary_2000_plants_primary_bar"]["bar_1e6"]["power"]
        p200 = res["first200_plants_primary_bar"]["bar_1e6"]["power"]
        res["rule"] = dict(widened_interval=[lo, hi], primary_power=p, primary_inside=bool(lo <= p <= hi),
                           first200_power=p200, first200_inside=bool(lo <= p200 <= hi),
                           delta_primary=p - rp["power"])
        results[name] = res

    bars_cmp = dict(
        reported=rep_bar,
        primary=dict(delta_bar_1e6=null_primary["bar_1e6"] - rep_bar["bar_1e6"],
                     delta_bar_2p32=null_primary["bar_2p32"] - rep_bar["bar_2p32"],
                     delta_null_mean=null_primary["mean"] - rep_bar["null_mean"],
                     within_0_05=bool(abs(null_primary["bar_1e6"] - rep_bar["bar_1e6"]) <= 0.05
                                      and abs(null_primary["bar_2p32"] - rep_bar["bar_2p32"]) <= 0.05)),
        report_scale=dict(delta_bar_1e6=null_report_scale["bar_1e6"] - rep_bar["bar_1e6"],
                          delta_bar_2p32=null_report_scale["bar_2p32"] - rep_bar["bar_2p32"],
                          within_0_05=bool(abs(null_report_scale["bar_1e6"] - rep_bar["bar_1e6"]) <= 0.05
                                           and abs(null_report_scale["bar_2p32"] - rep_bar["bar_2p32"]) <= 0.05)),
    )

    # sample probabilities for the cross-check record (fixed histories)
    out = dict(
        sub_attack="A2",
        lane="R1-REDTEAM-OWN-CLAIMS",
        numbering="LP2-0-57",
        canon_sha256="023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585",
        audited_git="fbe43e7",
        command="V=/tmp/claude-0/-home-user-cicada-3301-Code-cracker-attempt-1/4950dc03-e080-591a-84c1-d8ea81cef212/"
                "scratchpad/venv; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/A2_kn4_independent.py",
        independence=("imports numpy, json, hashlib, math only; reads data/corpora/*.npz and index.json; "
                      "no runeforge import; implementation source of runeforge.scoring not read"),
        training=dict(corpus="cicada-english", indices_sha256=sha_c, n_words=n_words, train_words=train_words,
                      train_runes=int(len(seq)), rule="word_ids < floor(0.9*n_words), one sequence"),
        model=dict(order=N_ORDER, base=B, levels={str(k): v for k, v in info.items()},
                   row_sum_max_dev={str(k): v for k, v in maxdev.items()},
                   arithmetic="float64 throughout (the package stores float32 log2 tables; |diff| ~1e-7 per position)"),
        null=dict(L=L, seed=SEED_NULL, primary=null_primary, report_scale_first_100000=null_report_scale,
                  fit="Gumbel method of moments on block maxima of 1,000; bar = mu_b + beta ln(N/1000) - beta ln(-ln 0.99)"),
        bars_vs_line97=bars_cmp,
        plants=dict(L=L, seed=SEED_PLANT, n=N_PLANTS, method="distinct random rune offsets in the held-out tail",
                    results=results),
        wall_time_s=dict(fit=round(t_fit, 2), null=round(t_null, 2), plants=round(t_plant, 2),
                         total=round(time.time() - t0, 2)),
        python=sys.version.split()[0], numpy=np.__version__,
    )
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(dict(bars=bars_cmp, null=null_primary, null100k=null_report_scale,
                          rules={k: v["rule"] for k, v in results.items()},
                          planted={k: (v["planted_mean"], v["planted_sd"], v["planted_min"]) for k, v in results.items()},
                          levels=info, wall=out["wall_time_s"]), indent=1))


if __name__ == "__main__":
    main()
