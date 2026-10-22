#!/usr/bin/env python3
"""Regenerate the numbers of reports/beam_decoder.md (the beam decoder's power envelope).

    python scripts/beam_power.py [--out reports/beam_decoder.json] [--quick]

Read-only with respect to lane evidence and the ledger: controls and gates run in memory on
toy lane specs (lane id BEAM-POWER) and nothing is written but ``--out``. Sections:

1. solved sections: given only the key, does the beam re-derive the published interrupt set?
2. a planted DIVINITY key on a synthetic Welcome page: rigid vs beam (spec P2)
3. the fingerprint gate of the template lane's family at several interrupt rates
4. the frozen control (``runeforge.runner.control.run_control``) per forward model x decoder
5. noise: mean score of wrong-key decodes per decoder, and CPU throughput
6. the staged beam calibrations (``reports/calib-staging``) and the control ceilings they imply
7. fill: the share of a planted key's window lost to the key budget, per forward model
8. width: control recovery and wrong-key noise at beam widths 4, 8 and 16
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runeforge import beam, canon, interrupts  # noqa: E402
from runeforge.lanes import LaneSpec, load_lane  # noqa: E402
from runeforge.runner import control, gate  # noqa: E402
from runeforge.scoring import presets  # noqa: E402
from runeforge.sources import raw_available  # noqa: E402
from runeforge.transforms import Vigenere, from_method  # noqa: E402

DIVINITY = [23, 10, 1, 10, 9, 10, 16, 26]
SCORER = "lp-ngram3-heldout"
STAGING = ROOT / "reports" / "calib-staging"


def solved_sections() -> list[dict]:
    names = ["lp-ngram3-heldout"] + (["general-ngram3", "cicada-ngram3"] if raw_available() else [])
    rows = []
    for name in names:
        scorer = presets.get(name)
        for s in canon.load_solved_sections():
            t = from_method(s.method)
            try:
                plain, chosen = interrupts.decode_beam(s.cipher, t, scorer)
            except TypeError:
                continue
            rows.append(
                {
                    "scorer": name,
                    "section": s.id,
                    "cipher_F": int((s.cipher == 0).sum()),
                    "published_interrupts": len(s.interrupts),
                    "beam_interrupts": len(chosen),
                    "same_set": chosen == sorted(s.interrupts),
                    "plaintext_exact": bool(np.array_equal(plain, s.plain)),
                    "rigid_score": float(scorer.score(interrupts.decode_rigid(s.cipher, t))),
                    "beam_score": float(scorer.score(plain)),
                    "trained_on_lp": presets.PRESETS[name]["train"] == ["lp-solved"],
                }
            )
    return rows


def planted_divinity() -> dict:
    scorer = presets.get(SCORER)
    text = canon.solved_section("a-koan-1").plain[:515]  # held out of lp-ngram3-heldout
    chosen = np.flatnonzero(text == interrupts.F).tolist()  # the rule: every plaintext F
    t = Vigenere(DIVINITY)
    cipher = interrupts.encrypt_with_interrupts(text, t, chosen)
    rigid = interrupts.decode_rigid(cipher, t)
    plain, got = interrupts.decode_beam(cipher, t, scorer)
    return {
        "text": "a-koan-1 plaintext, first 515 runes (WELCOME's length), held out of the scorer",
        "interrupters": len(chosen),
        "first_interrupter": chosen[0],
        "rigid_score": float(scorer.score(rigid)),
        "rigid_recovery": float((rigid == text).mean()),
        "beam_score": float(scorer.score(plain)),
        "beam_recovery": float((plain == text).mean()),
        "beam_interrupts_exact": got == chosen,
    }


def gate_rates(rates) -> list[dict]:
    lane = load_lane(ROOT / "lanes" / "_template.yaml")
    out = []
    for q in rates:
        res = gate.run_gate(lane.model_copy(update={"interrupt_prob": q}), seeds=12)
        out.append(
            {"interrupt_prob": q, "verdict": res.verdict_line, "fails": res.fails_per_constraint}
        )
    return out


def _lane(**over) -> LaneSpec:
    spec = {
        "lane_id": "BEAM-POWER",
        "hypothesis": "power envelope (scripts/beam_power.py)",
        "family": "prng",
        "generator": "numpy-pcg64",
        "seed_range": [0, 2**32],
        "window": 240,
        "pages": [0, 1, 2, 3, 4, 5],
        "preset": f"{SCORER}:rigid",
        "control": {"planted_seed": 3301, "synthetic_page": "solved:a-koan-1", "decoys": 199},
    }
    spec.update(over)
    return LaneSpec(**spec)


MODELS = {
    "interrupts": {"filter_model": "off", "interrupt_prob": 1.0},
    "anti-repeat": {"filter_model": "anti-repeat", "interrupt_prob": 0.0},
    "anti-repeat + interrupts": {"filter_model": "anti-repeat", "interrupt_prob": 1.0},
}


def controls(windows, staged: dict) -> list[dict]:
    rows = []
    for name, model in MODELS.items():
        for length in windows:
            for dec in presets.DECODERS:
                lane = _lane(window=length, preset=f"{SCORER}:{dec}", **model)
                t0 = time.time()
                rep = control.run_control(lane)
                row = {
                    "forward_model": name,
                    "L": length,
                    "decoder": dec,
                    "status": rep.status,
                    "identified": rep.identified,
                    "n_plants": rep.n_plants,
                    "median_recovery": float(np.median([p.recovery for p in rep.plants])),
                    "floor": rep.floor,
                    "ceiling_observed": rep.ceiling_observed,
                    "ceiling_trials": rep.ceiling_trials,
                    "ceiling_at_2^32": rep.ceiling,
                    "beta": rep.beta,
                    "beta_source": rep.beta_source,
                    "gap_nats": rep.gap_nats,
                    "seconds": round(time.time() - t0, 1),
                }
                cal = staged.get((dec, length))
                if cal is not None:  # the ceiling the installed calibration would give
                    b = cal["fit"]["beta"]
                    c = rep.ceiling_observed + b * math.log(2**32 / rep.ceiling_trials)
                    row["staged_beta"] = b
                    row["ceiling_at_2^32_staged"] = c
                    row["gap_nats_staged"] = (
                        None if rep.floor is None else (rep.floor - c) * math.log(2)
                    )
                row["runnable_pairing"] = not lane.decoder_problems()
                rows.append(row)
                print(
                    f"  control {name:26s} L={length:3d} {dec:13s} {rep.status:6s} "
                    f"{rep.identified:2d}/{rep.n_plants} gap {rep.gap_nats}",
                    flush=True,
                )
    return rows


def noise(length: int, n: int) -> list[dict]:
    scorer = presets.get(SCORER)
    rng = np.random.default_rng(3301)
    cipher = rng.integers(0, 29, (n, length))
    keys = rng.integers(0, 29, (n, length))
    rows = []
    for dec in presets.DECODERS:
        model = presets.beam_model(dec)
        t0 = time.time()
        plain = (cipher - keys) % 29 if model is None else beam.decode(cipher, keys, scorer, model)
        dt = time.time() - t0
        s = scorer.score_batch(plain)
        rows.append(
            {
                "decoder": dec,
                "L": length,
                "n": n,
                "mean": float(s.mean()),
                "sd": float(s.std()),
                "max": float(s.max()),
                "keys_per_s": n / dt if dt > 0 else None,
            }
        )
    return rows


def fill_fraction(length: int = 240, plants: int = 200) -> list[dict]:
    """Share of a planted window decoded as fill (key budget used up: the skips' net excess
    over the interrupters), under each skip model's own decoder, on held-out Cicada-register
    text through pipeline.encrypt."""
    from runeforge.runner import pipeline

    scorer = presets.get(SCORER)
    src = canon.solved_section("a-koan-1").plain
    out = []
    for name, model in MODELS.items():
        if model["filter_model"] != "anti-repeat":
            continue
        dec = "beam-skip-int" if model["interrupt_prob"] else "beam-skip"
        lane = _lane(window=length, preset=f"{SCORER}:{dec}", **model)
        rng = np.random.default_rng(3301)
        fills, recov = [], []
        for _ in range(plants):
            off = int(rng.integers(0, src.size - length))
            plain = src[off : off + length]
            k = rng.integers(0, 29, 3 * length)
            mc, _ = pipeline.encrypt(lane, plain, k, rng)
            rec = beam.decode_record(mc, k[:length], scorer, pipeline.beam_model(lane))
            fills.append(len(rec.fill) / length)
            recov.append(float((np.asarray(rec.plain) == plain).mean()))
        out.append(
            {
                "forward_model": name,
                "decoder": dec,
                "L": length,
                "plants": plants,
                "mean_fill_fraction": float(np.mean(fills)),
                "mean_recovery": float(np.mean(recov)),
            }
        )
    return out


def widths(widths_=(4, 8, 16), n: int = 2000) -> list[dict]:
    """Control recovery (anti-repeat lane, beam-skip) and wrong-key noise at other widths: the
    width is pinned at 8, so this is the evidence that the choice is not tuned."""
    out = []
    saved = dict(presets.DECODER_PARAMS["beam-skip"])
    scorer = presets.get(SCORER)
    rng = np.random.default_rng(3301)
    cipher, keys = rng.integers(0, 29, (n, 240)), rng.integers(0, 29, (n, 240))
    try:
        for w in widths_:
            presets.DECODER_PARAMS["beam-skip"] = {**saved, "width": w}
            rep = control.run_control(_lane(preset=f"{SCORER}:beam-skip", **MODELS["anti-repeat"]))
            noise_mean = float(
                scorer.score_batch(
                    beam.decode(cipher, keys, scorer, presets.beam_model("beam-skip"))
                ).mean()
            )
            out.append(
                {
                    "width": w,
                    "identified": rep.identified,
                    "n_plants": rep.n_plants,
                    "median_recovery": float(np.median([p.recovery for p in rep.plants])),
                    "floor": rep.floor,
                    "ceiling_observed": rep.ceiling_observed,
                    "noise_mean": noise_mean,
                }
            )
    finally:
        presets.DECODER_PARAMS["beam-skip"] = saved
    return out


def staged_calibrations() -> dict:
    out = {}
    for p in sorted(STAGING.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        out[(rec["decoder"], rec["L"])] = rec
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "beam_decoder.json")
    ap.add_argument("--quick", action="store_true", help="L = 240 only, smaller noise sample")
    a = ap.parse_args()
    windows = [240] if a.quick else [240, 120]
    staged = staged_calibrations()
    t0 = time.time()
    print("1. solved sections", flush=True)
    data = {"numbering": canon.LP2_NUMBERING, "scorer": SCORER}
    data["solved_sections"] = solved_sections()
    print("2. planted DIVINITY", flush=True)
    data["planted_divinity"] = planted_divinity()
    print("3. gate", flush=True)
    data["gate_template_family"] = gate_rates([0.0, 0.1, 0.44, 1.0])
    print("4. controls", flush=True)
    data["controls"] = controls(windows, staged)
    print("5. noise", flush=True)
    data["noise"] = noise(240, 2000 if a.quick else 10_000)
    print("7. fill", flush=True)
    data["fill"] = fill_fraction(plants=50 if a.quick else 200)
    print("8. width", flush=True)
    data["width"] = widths()
    data["staged_calibrations"] = [
        {
            "decoder": d,
            "L": length,
            "mu_block": rec["fit"]["mu_block"],
            "beta": rec["fit"]["beta"],
            "null_mean": rec["null"]["mean"],
            "null_sd": rec["null"]["sd"],
            "check_max_error": rec["check"]["max_error"],
            "check": rec["check"],
        }
        for (d, length), rec in sorted(staged.items())
    ]
    lp2 = canon.load_lp2().stream(canon.UNSOLVED_LP2_PAGES)
    data["lp2_F"] = {"runes": int(lp2.size), "F": int((lp2 == 0).sum()), "uniform": lp2.size / 29}
    data["seconds"] = round(time.time() - t0, 1)
    a.out.write_text(json.dumps(data, indent=1, default=float) + "\n", encoding="utf-8")
    print(f"wrote {a.out} ({data['seconds']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
