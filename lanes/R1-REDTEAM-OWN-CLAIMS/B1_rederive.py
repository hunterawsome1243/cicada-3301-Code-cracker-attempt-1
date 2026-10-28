"""R1-REDTEAM-OWN-CLAIMS sub-attack B1: independent re-derivation of the P3 lane's positive control.

Written from the PREREG section 2 row B1, the P3 PREREG text, reports/beam_decoder.md prose and the
module docstrings only. It does NOT import runeforge.scoring, runeforge.beam, runeforge.runner,
runeforge.gpu, runeforge.generators or scripts/scorer_power.py. Data loader only:
runeforge.gematria.runes_to_indices for the solved sections' plaintext.

Pieces, each written here:
* keystream: CPython 2.7 random.seed(int) + int(random()*29). CPython 3's
  random.Random(seed).getrandbits(32*m) gives the same genrand_int32 words for int seeds (least
  significant word first); genrand_res53 = ((a >> 5) * 67108864 + (b >> 6)) / 2**53 on consecutive
  words a, b; symbol = int(u * 29). Checked against the CPython 2.7.3 vector for seed 3301.
* forward model: raw view, c = (p + k) mod 29, one key symbol per enciphered rune; when c_i equals
  c_{i-1} (i > 0) the filter redraws the next key symbol with probability 1 - p_keep (0.19), and
  repeats until the rune differs or the keep fires. No F-interrupters.
* scorer: order-3 interpolated Witten-Bell over 29 runes, P_0 = 1/29, counts per section (no n-gram
  crosses a section), trained on every solved section except a-koan-1 and the-loss-of-divinity.
  Score = mean log2 P per rune; position 0 by P_1, position 1 by P_2, the rest by P_3.
* decoder: beam over states (key position j, last two plaintext runes), Viterbi merge of equal
  states, width W. At rune i from key position j, s = 0..max_skip key symbols are dropped (s > 0
  only for i > 0) and k[j+s] enciphers: x = c_i - k[j+s]. A drop is legal only if the dropped
  symbol re-enciphers x to the previous canonical rune: (x + k[j+t]) mod 29 == c_{i-1} for every
  t < s. Prior: s * log2(1 - p_keep), plus log2(p_keep) when c_i == c_{i-1} (a kept repeat).
  Objective = prior + scorer log2 P. Key budget K = window length; positions beyond it wrap
  (k[j mod K]), as reports/beam_decoder.md section 1 describes. Ties: first-inserted wins.
* plants: fresh seeds uniform in [0, 2**32) (3301 excluded), random 240-rune window of the
  a-koan-1 plaintext, decoys uniform in [0, 2**32); identified = rank 1 among 1 + decoys and
  rune-index recovery >= 0.90.

Usage (repo root):
  python lanes/R1-REDTEAM-OWN-CLAIMS/B1_rederive.py [--plants 20] [--decoys 199] [--width 8]
Writes lanes/R1-REDTEAM-OWN-CLAIMS/out_B1.json (or --out).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from runeforge.gematria import runes_to_indices  # noqa: E402  (data loader only)

M = 29
HELDOUT_IDS = ("a-koan-1", "the-loss-of-divinity")
VECTOR_3301 = [6, 6, 13, 12, 13, 17, 25, 23, 11, 17, 21, 15, 14, 25, 4, 19]


# ----------------------------------------------------------------------------- keystream
def random29(seed: int, n: int) -> np.ndarray:
    words = random.Random(seed).getrandbits(64 * n)
    w = np.frombuffer(words.to_bytes(8 * n, "little"), dtype="<u4").astype(np.uint64)
    a = w[0::2] >> np.uint64(5)
    b = w[1::2] >> np.uint64(6)
    u = (a.astype(np.float64) * 67108864.0 + b.astype(np.float64)) / 9007199254740992.0
    return (u * 29).astype(np.int64)


# ----------------------------------------------------------------------------- scorer
def solved_plains() -> dict[str, np.ndarray]:
    d = json.loads((REPO / "data/canon/solved_sections.json").read_text(encoding="utf-8"))
    out = {}
    for s in d["sections"]:
        idx = np.asarray(runes_to_indices(s["plain"]), dtype=np.int64)
        assert idx.size == int(s["n_runes"]), s["id"]
        out[s["id"]] = idx
    return out


def build_wb3(seqs):
    c1 = np.zeros(M)
    c2 = np.zeros((M, M))
    c3 = np.zeros((M, M, M))
    for q in seqs:
        for i, x in enumerate(q):
            c1[x] += 1
            if i >= 1:
                c2[q[i - 1], x] += 1
            if i >= 2:
                c3[q[i - 2], q[i - 1], x] += 1

    def interp(counts, lower):
        tot = counts.sum(axis=-1, keepdims=True)
        n1 = (counts > 0).sum(axis=-1, keepdims=True)
        denom = tot + n1
        with np.errstate(invalid="ignore", divide="ignore"):
            p = np.where(tot > 0, (counts + n1 * lower) / np.where(denom > 0, denom, 1), lower)
        return p

    p0 = np.full(M, 1.0 / M)
    p1 = interp(c1, p0)
    p2 = interp(c2, p1[None, :])
    p3 = interp(c3, p2[None, :, :])
    for p, ax in ((p1, -1), (p2, -1), (p3, -1)):
        assert np.allclose(p.sum(axis=ax), 1.0)
    return np.log2(p1), np.log2(p2), np.log2(p3)


class Scorer:
    def __init__(self, seqs):
        self.l1, self.l2, self.l3 = build_wb3(seqs)
        # python-list views for the scalar beam
        self.L1 = self.l1.tolist()
        self.L2 = self.l2.tolist()
        self.L3 = self.l3.tolist()

    def positions(self, w) -> np.ndarray:
        w = np.asarray(w, dtype=np.int64)
        out = np.empty(w.size)
        out[0] = self.l1[w[0]]
        if w.size > 1:
            out[1] = self.l2[w[0], w[1]]
        if w.size > 2:
            out[2:] = self.l3[w[:-2], w[1:-1], w[2:]]
        return out

    def score(self, w) -> float:
        return float(self.positions(w).mean())


# ----------------------------------------------------------------------------- forward model
def encrypt(plain, key, p_keep, rng):
    """c = p + k mod 29 with the anti-repeat redraw; returns cipher, key symbols used, drops."""
    c = np.empty(len(plain), dtype=np.int64)
    j = 0
    drops = 0
    for i, x in enumerate(plain):
        ci = (x + key[j]) % M
        j += 1
        if i > 0:
            while ci == c[i - 1] and rng.random() >= p_keep:
                ci = (x + key[j]) % M
                j += 1
                drops += 1
        c[i] = ci
    return c, j, drops


# ----------------------------------------------------------------------------- beam decoder
def beam_decode(cipher, key, sc: Scorer, width=8, max_skip=6, p_keep=0.19):
    K = len(key)
    k = [int(v) for v in key]
    cl = [int(v) for v in cipher]
    lskip = math.log2(1.0 - p_keep)
    lkeep = math.log2(p_keep)
    L1, L2, L3 = sc.L1, sc.L2, sc.L3
    # state: (j, a, b) with a, b the last two plaintext runes (-1 = none)
    beam = [(0.0, 0, -1, -1)]  # (obj, j, a, b)
    back = []  # per step: list of (prev_index, x) aligned with beam order
    for i, ci in enumerate(cl):
        cand = {}
        order = []
        cprev = cl[i - 1] if i > 0 else -1
        rep = i > 0 and ci == cprev
        base_prior = lkeep if rep else 0.0
        for bi, (obj, j, a, b) in enumerate(beam):
            kj = k[j % K]
            smax = max_skip if i > 0 else 0
            for s in range(0, smax + 1):
                if s >= 2 and k[(j + s - 1) % K] != kj:
                    break  # s drops need s equal key symbols; no larger s is legal either
                x = (ci - k[(j + s) % K]) % M
                if s >= 1 and (x + kj) % M != cprev:
                    continue
                if i == 0:
                    lp = L1[x]
                elif i == 1:
                    lp = L2[b][x]
                else:
                    lp = L3[a][b][x]
                o = obj + lp + base_prior + s * lskip
                key_ = (j + s + 1, b, x)
                cur = cand.get(key_)
                if cur is None:
                    cand[key_] = [o, bi, x]
                    order.append(key_)
                elif o > cur[0]:
                    cand[key_] = [o, bi, x]
        # best `width` by objective; ties by insertion order (stable sort)
        ranked = sorted(order, key=lambda kk: -cand[kk][0])[:width]
        back.append([(cand[kk][1], cand[kk][2]) for kk in ranked])
        beam = [(cand[kk][0], kk[0], kk[1], kk[2]) for kk in ranked]
    # best final path (index 0 after the sort)
    best = 0
    out = [0] * len(cl)
    for i in range(len(cl) - 1, -1, -1):
        pi, x = back[i][best]
        out[i] = x
        best = pi
    return np.asarray(out, dtype=np.int64), beam[0][0], beam[0][1]


# ----------------------------------------------------------------------------- one plant
_G = {}


def _init(train_ids, koan, L, width, max_skip, p_keep):
    plains = solved_plains()
    _G["sc"] = Scorer([plains[t] for t in train_ids])
    _G.update(koan=np.asarray(koan, dtype=np.int64), L=L, width=width, max_skip=max_skip, p_keep=p_keep)


def run_plant(job):
    seed, offset, decoys, filt_seed = job
    sc, koan, L = _G["sc"], _G["koan"], _G["L"]
    W, S, pk = _G["width"], _G["max_skip"], _G["p_keep"]
    plain = koan[offset:offset + L]
    rng = np.random.default_rng(filt_seed)
    key_long = random29(seed, 4 * L)
    cipher, used, drops = encrypt(plain, key_long, pk, rng)
    t0 = time.time()
    dec, obj, jend = beam_decode(cipher, key_long[:L], sc, W, S, pk)
    rec = float((dec == plain).mean())
    planted = sc.score(dec)
    dscores = []
    for d in decoys:
        dd, _, _ = beam_decode(cipher, random29(int(d), L), sc, W, S, pk)
        dscores.append(sc.score(dd))
    dscores = np.asarray(dscores)
    rank = 1 + int((dscores >= planted).sum())
    return {
        "seed": int(seed), "offset": int(offset), "filter_rng_seed": int(filt_seed),
        "key_symbols_used_by_encryption": int(used), "drops": int(drops),
        "cipher_doublets": int((cipher[1:] == cipher[:-1]).sum()),
        "rank": rank, "recovery": rec, "planted_score": planted,
        "true_plaintext_score": sc.score(plain),
        "best_decoy": float(dscores.max()), "decoy_mean": float(dscores.mean()),
        "identified": bool(rank == 1 and rec >= 0.90),
        "beam_key_position_end": int(jend), "seconds": time.time() - t0,
        "decoy_scores": [round(float(v), 6) for v in dscores],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plants", type=int, default=20)
    ap.add_argument("--decoys", type=int, default=199)
    ap.add_argument("--width", type=int, default=8)
    ap.add_argument("--max-skip", type=int, default=6)
    ap.add_argument("--p-keep", type=float, default=0.19)
    ap.add_argument("--L", type=int, default=240)
    ap.add_argument("--seed", type=int, default=330120261028)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(REPO / "lanes/R1-REDTEAM-OWN-CLAIMS/out_B1.json"))
    args = ap.parse_args()
    t_start = time.time()

    # (a) keystream vector check
    v = random29(3301, 16).tolist()
    assert v == VECTOR_3301, v

    plains = solved_plains()
    train_ids = [k for k in plains if k not in HELDOUT_IDS]
    koan = plains["a-koan-1"]
    rng = np.random.default_rng(args.seed)
    jobs = []
    seen = {3301}
    for _ in range(args.plants):
        while True:
            s = int(rng.integers(0, 2**32))
            if s not in seen:
                break
        seen.add(s)
        off = int(rng.integers(0, koan.size - args.L + 1))
        dec = []
        while len(dec) < args.decoys:
            d = int(rng.integers(0, 2**32))
            if d not in seen:
                seen.add(d)
                dec.append(d)
        jobs.append((s, off, dec, int(rng.integers(0, 2**63))))

    with Pool(args.workers, initializer=_init,
              initargs=(train_ids, koan.tolist(), args.L, args.width, args.max_skip, args.p_keep)) as pool:
        res = pool.map(run_plant, jobs)

    planted = np.array([r["planted_score"] for r in res])
    recs = np.array([r["recovery"] for r in res])
    ident = sum(r["identified"] for r in res)
    rank1 = sum(r["rank"] == 1 for r in res)
    all_decoys = np.concatenate([r["decoy_scores"] for r in res])
    ctrl = json.loads((REPO / "lanes/P3-MT19937-PY27-EXACT/control-4c65a7978362.json").read_text())
    c_pl = np.array([p["planted_score"] for p in ctrl["plants"]])
    c_rec = np.array([p["recovery"] for p in ctrl["plants"]])
    med = float(np.median(planted))
    c_med = float(np.median(c_pl))
    summary = {
        "identified": int(ident), "rank1": int(rank1), "n_plants": len(res),
        "floor": float(planted.min()), "median_planted": med, "mean_planted": float(planted.mean()),
        "max_planted": float(planted.max()),
        "recovery_min": float(recs.min()), "recovery_median": float(np.median(recs)),
        "recovery_max": float(recs.max()),
        "decoy_null": {"n": int(all_decoys.size), "mean": float(all_decoys.mean()),
                       "sd": float(all_decoys.std(ddof=1)), "max": float(all_decoys.max())},
        "true_plaintext_score_median": float(np.median([r["true_plaintext_score"] for r in res])),
    }
    reported = {
        "file": "lanes/P3-MT19937-PY27-EXACT/control-4c65a7978362.json",
        "identified": ctrl["identified"], "n_plants": ctrl["n_plants"], "floor": ctrl["floor"],
        "median_planted": c_med, "recovery_min": float(c_rec.min()),
        "recovery_median": float(np.median(c_rec)), "recovery_max": float(c_rec.max()),
        "decoys_per_plant": 999, "wrong_key_max": ctrl["wrong_key_max"],
    }
    rule_ok = ident >= 18 and abs(med - c_med) <= 0.15
    out = {
        "lane": "R1-REDTEAM-OWN-CLAIMS", "sub_attack": "B1", "numbering": "LP2-0-57",
        "canon_sha256": "023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585",
        "audited_git": "fbe43e7",
        "command": "$V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/B1_rederive.py "
                   f"--plants {args.plants} --decoys {args.decoys} --width {args.width} "
                   f"--max-skip {args.max_skip} --p-keep {args.p_keep} --L {args.L} --seed {args.seed} "
                   f"--workers {args.workers}",
        "independence": "no import of runeforge.scoring/beam/runner/gpu/generators or "
                        "scripts/scorer_power.py; their implementation source not read before these "
                        "numbers were written (docstrings and report prose only)",
        "keystream_check": {"seed": 3301, "first16": v, "expected": VECTOR_3301, "pass": v == VECTOR_3301},
        "params": {"L": args.L, "width": args.width, "max_skip": args.max_skip, "p_keep": args.p_keep,
                   "decoys_per_plant": args.decoys, "plants": args.plants, "rng_seed": args.seed,
                   "key_budget": args.L, "wrap": "k[j mod K]",
                   "ties": "first-inserted candidate wins (stable sort by objective)",
                   "scorer": "order-3 interpolated Witten-Bell, P_0 = 1/29, per-section counts",
                   "train_ids": train_ids, "plaintext": "a-koan-1 (778 runes), window offset uniform"},
        "summary": summary,
        "reported": reported,
        "comparison": {
            "rule": ">= 18/20 identified at rank 1 with recovery >= 0.90, and median planted score "
                    "within 0.15 of the control's -3.8207",
            "identified": f"{ident}/{len(res)}", "median_delta": med - c_med,
            "floor_delta": float(planted.min()) - ctrl["floor"],
            "reproduced": bool(rule_ok),
        },
        "plants": res,
        "wall_time_s": round(time.time() - t_start, 1),
    }
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("summary", "reported", "comparison", "wall_time_s")}, indent=1))


if __name__ == "__main__":
    main()
