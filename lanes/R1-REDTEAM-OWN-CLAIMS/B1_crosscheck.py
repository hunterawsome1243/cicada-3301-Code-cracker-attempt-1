"""R1-REDTEAM-OWN-CLAIMS sub-attack B1: cross-check against the package, run AFTER out_B1.json was written.

Loads B1_rederive's independent pieces and the package's (runeforge.generators.mt19937_py27,
runeforge.scoring.presets lp-ngram3-heldout, runeforge.runner.pipeline.encrypt,
runeforge.beam.decode_batch with presets.beam_model("beam-skip")) and compares them on the exact
plants, ciphers and decoys out_B1.json records. Appends a "crosscheck" block to out_B1.json.

Usage (repo root): python lanes/R1-REDTEAM-OWN-CLAIMS/B1_crosscheck.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import B1_rederive as mine  # noqa: E402
from runeforge.beam import decode_batch  # noqa: E402
from runeforge.generators.mt19937_py27 import MT19937Py27  # noqa: E402
from runeforge.runner import pipeline  # noqa: E402
from runeforge.scoring import presets  # noqa: E402


def main() -> None:
    t0 = time.time()
    outp = HERE / "out_B1.json"
    out = json.loads(outp.read_text())
    P = out["params"]
    L = P["L"]
    plains = mine.solved_plains()
    sc = mine.Scorer([plains[t] for t in P["train_ids"]])
    koan = plains["a-koan-1"]
    ref_sc = presets.get("lp-ngram3-heldout")
    model = presets.beam_model("beam-skip")
    gen = MT19937Py27(mode="random29")
    lane = SimpleNamespace(ciphertext_view="raw", filter_model="anti-repeat", interrupt_prob=0.0,
                           p_keep=P["p_keep"], combine="vigenere")
    # rebuild the decoy lists exactly as B1_rederive did
    rng = np.random.default_rng(P["rng_seed"])
    seen = {3301}
    decoys_of = {}
    for _ in range(P["plants"]):
        while True:
            s = int(rng.integers(0, 2**32))
            if s not in seen:
                break
        seen.add(s)
        rng.integers(0, koan.size - L + 1)
        dec = []
        while len(dec) < P["decoys_per_plant"]:
            d = int(rng.integers(0, 2**32))
            if d not in seen:
                seen.add(d)
                dec.append(d)
        rng.integers(0, 2**63)
        decoys_of[s] = dec

    ks_mismatch = 0
    ks_n = 0
    enc_mismatch = 0
    lp_diff = 0.0
    planted_rows = []
    decoy_score_diff = 0.0
    decoy_plain_mismatch = 0
    rank_ref = []
    for r in out["plants"]:
        seed, off = r["seed"], r["offset"]
        plain = koan[off:off + L]
        seeds = [seed] + decoys_of[seed]
        ref_keys = gen.batch(seeds, L)
        my_keys = np.stack([mine.random29(s, L) for s in seeds])
        ks_mismatch += int((ref_keys != my_keys).any(axis=1).sum())
        ks_n += len(seeds)
        long_key = mine.random29(seed, 4 * L)
        assert (gen.batch([seed], 4 * L)[0] == long_key).all()
        my_c, _, _ = mine.encrypt(plain, long_key, P["p_keep"], np.random.default_rng(r["filter_rng_seed"]))
        ref_c, _ = pipeline.encrypt(lane, plain, long_key, np.random.default_rng(r["filter_rng_seed"]))
        enc_mismatch += int((my_c != ref_c).any())
        res = decode_batch(ref_c, ref_keys, ref_sc, model)
        ref_scores = ref_sc.score_batch(res.plain)
        my_planted, _, _ = mine.beam_decode(my_c, my_keys[0], sc, P["width"], P["max_skip"], P["p_keep"])
        lp_diff = max(lp_diff, float(np.abs(ref_sc.logprobs(my_planted) - sc.positions(my_planted)).max()))
        for t in range(1, len(seeds), 20):  # every 20th decoy decoded by mine as well, plain compared
            md, _, _ = mine.beam_decode(my_c, my_keys[t], sc, P["width"], P["max_skip"], P["p_keep"])
            decoy_plain_mismatch += int((md != res.plain[t]).any())
        my_dec = np.asarray(r["decoy_scores"])
        decoy_score_diff = max(decoy_score_diff, float(np.abs(my_dec - ref_scores[1:]).max()))
        rank = 1 + int((ref_scores[1:] >= ref_scores[0]).sum())
        rec = float((res.plain[0] == plain).mean())
        rank_ref.append(rank)
        planted_rows.append({
            "seed": seed, "mine_score": r["planted_score"], "pkg_score": float(ref_scores[0]),
            "mine_recovery": r["recovery"], "pkg_recovery": rec,
            "same_plaintext": bool((res.plain[0] == my_planted).all()),
            "pkg_rank": rank, "pkg_identified": bool(rank == 1 and rec >= 0.90),
        })
    pk = np.array([p["pkg_score"] for p in planted_rows])
    out["crosscheck"] = {
        "command": "$V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/B1_crosscheck.py",
        "run_after_numbers_written": True,
        "keystream": {"seeds": ks_n, "mismatched_seeds": ks_mismatch,
                      "against": "runeforge.generators.mt19937_py27.MT19937Py27(mode='random29').batch"},
        "forward_model": {"plants": len(planted_rows), "mismatched_ciphers": enc_mismatch,
                          "against": "runeforge.runner.pipeline.encrypt, same rng seed, raw/vigenere/anti-repeat/no interrupters"},
        "scorer": {"max_abs_diff_per_position_log2": lp_diff,
                   "against": "presets.get('lp-ngram3-heldout').logprobs (float32 tables)"},
        "decoder_on_my_ciphers": {
            "against": "runeforge.beam.decode_batch, presets.beam_model('beam-skip')",
            "planted_same_plaintext": sum(p["same_plaintext"] for p in planted_rows),
            "pkg_identified": sum(p["pkg_identified"] for p in planted_rows),
            "pkg_median_planted": float(np.median(pk)), "pkg_floor": float(pk.min()),
            "max_abs_planted_score_diff": float(max(abs(p["mine_score"] - p["pkg_score"]) for p in planted_rows)),
            "max_abs_decoy_score_diff": decoy_score_diff,
            "decoy_plaintexts_compared": sum(len(range(1, P["decoys_per_plant"] + 1, 20)) for _ in planted_rows),
            "decoy_plaintext_mismatches": decoy_plain_mismatch,
            "plants": planted_rows,
        },
        "wall_time_s": round(time.time() - t0, 1),
    }
    outp.write_text(json.dumps(out, indent=1) + "\n")
    c = dict(out["crosscheck"])
    c["decoder_on_my_ciphers"] = {k: v for k, v in c["decoder_on_my_ciphers"].items() if k != "plants"}
    print(json.dumps(c, indent=1))


if __name__ == "__main__":
    main()
