"""R1-REDTEAM-OWN-CLAIMS A1 cross-check, run only AFTER A1_rederive.py wrote out_A1.json.

Loads runeforge.scoring.presets.get('lp-ngram3-heldout') (the implementation under audit) and
compares its per-position log2-probabilities with the independent WB3 model of A1_rederive.py on
1,000 random 240-rune windows (500 uniform random strings, 125 plaintext windows from each of the
four plant registers). PREREG rule: agreement to 1e-5. Also compares window scores and the full
conditional tables. Appends the result under "crosscheck" in out_A1.json.

Usage (repo root):  python lanes/R1-REDTEAM-OWN-CLAIMS/A1_crosscheck.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import A1_rederive as a1  # noqa: E402

SEED = 3301_2026_1029


def main() -> None:
    t0 = time.time()
    out = json.loads(a1.OUT.read_text(encoding="utf-8"))
    assert "comparison" in out, "run A1_rederive.py first"

    model, _ = a1.build_model()
    from runeforge.scoring import presets  # the implementation under audit, loaded only now

    ref = presets.get("lp-ngram3-heldout")

    rng = np.random.default_rng(SEED)
    wins = [rng.integers(0, a1.A, size=(500, a1.L))]
    plains = a1.solved_plains()
    streams = {n: a1.corpus_tail(n)[0] for n in ("latin", "vowel-dropped-english", "english-general")}
    streams["heldout-solved-sections"] = np.concatenate([plains[k] for k in a1.HELDOUT_IDS])
    for n, s in streams.items():
        w, _ = a1.plant_windows(s, 125, rng)
        wins.append(w)
    W = np.concatenate(wins)
    assert W.shape == (1000, a1.L)

    ours = model.position_logprobs(W)
    theirs = np.stack([ref.logprobs(w) for w in W])
    d = np.abs(ours - theirs)
    s_ours = ours.mean(1)
    s_theirs = ref.score_batch(W)
    ds = np.abs(s_ours - s_theirs)

    # full conditional tables (theirs are float32 log2)
    t = ref.tables
    dt = [float(np.abs(model.l1 - t[0].reshape(-1)).max()),
          float(np.abs(model.l2 - t[1].reshape(a1.A, a1.A)).max()),
          float(np.abs(model.l3.reshape(-1, a1.A) - t[2]).max())]

    cc = {
        "command": "$V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/A1_crosscheck.py",
        "seed": SEED, "windows": "500 uniform + 125 from each of latin, vowel-dropped-english, "
                                 "english-general tails and the held-out sections (L = 240)",
        "n_windows": int(W.shape[0]), "n_positions": int(W.size),
        "max_abs_diff_per_position_log2": float(d.max()),
        "mean_abs_diff_per_position_log2": float(d.mean()),
        "max_abs_diff_window_score": float(ds.max()),
        "max_abs_diff_tables_order1_2_3": dt,
        "reference_fingerprint": ref.fingerprint(),
        "rule": "per-position log2-probabilities agree to 1e-5",
        "pass": bool(d.max() <= 1e-5),
        "note": "the reference stores float32 log2 tables; float32 rounding of values near -5 is ~2e-7",
        "wall_time_s": round(time.time() - t0, 1),
    }
    out["crosscheck"] = cc
    out["comparison"]["crosscheck_pass"] = cc["pass"]
    out["comparison"]["all_pass"] = bool(out["comparison"]["all_pass_excluding_crosscheck"] and cc["pass"])
    a1.OUT.write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps(cc, indent=1))


if __name__ == "__main__":
    main()
