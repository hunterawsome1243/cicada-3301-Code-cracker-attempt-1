"""R1-REDTEAM-OWN-CLAIMS sub-attack C (part 2): arithmetic behind the claim-audit rows of
reports/beam_decoder.md §0-§7, reports/scorer_power.md §1/§9 and the P3 PREREG §0/§8/addenda
(all at fbe43e7). Reads committed JSON evidence and the canon (runeforge.canon, a data loader);
imports no scorer, decoder or runner. Appends a "handchecks" block to out_C2.json.

Run from the repo root:  $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/C2_handchecks.py
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
from runeforge import canon  # noqa: E402  (data loader only)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out_C2.json")
LN2 = math.log(2)
bd = json.load(open(os.path.join(ROOT, "reports/beam_decoder.json")))
sp = json.load(open(os.path.join(ROOT, "reports/scorer_power.json")))
ctl = json.load(open(os.path.join(ROOT, "lanes/P3-MT19937-PY27-EXACT/control-4c65a7978362.json")))
h = {}

# beam_decoder §1 parameters
h["max_skip_tail_(0.81/29)^7"] = (0.81 / 29) ** 7
h["p_keep_86/447"] = 86 / 447
h["interrupt_prior_rule_of_succession_15/16"] = (14 + 1) / (14 + 2)

# canon: F and doublets, solved-section plaintext F's, page-start windows
lp = canon.load_lp2()
pages = [p for p in lp.pages if p.page <= 55]
st = np.concatenate([np.asarray(p.runes) for p in pages])
h["lp2_runes"] = int(st.size)
h["lp2_F"] = int((st == 0).sum())
h["lp2_doublets"] = int((st[1:] == st[:-1]).sum())
h["uniform_F"] = st.size / 29
starts, pos = [], 0
for p in pages:
    if p.n_runes:
        starts.append((p.page, pos))
    pos += p.n_runes
for L in (240, 120):
    win = [(int((st[s:s + L] == 0).sum()), pg) for pg, s in starts if s + L <= st.size]
    h[f"page_start_windows_L{L}"] = {"n": len(win), "max_F_window": max(win)}
h["P3_pages_0_5_runes"] = int(sum(p.n_runes for p in pages if p.page <= 5))
h["P3_window_F_doublets"] = [int((st[:240] == 0).sum()), int((st[:240][1:] == st[:240][:-1]).sum())]
pf, tot, ints = 0, 0, {}
for s in canon.load_solved_sections():
    pl = np.asarray(s.plain)
    pf += int((pl == 0).sum())
    tot += pl.size
    if s.interrupts:
        ints[s.id] = [len(s.interrupts), int((pl == 0).sum())]
    if s.id == "a-koan-1":
        k1 = pl[:515]
        h["a_koan_1_first515_plain_F"] = [int((k1 == 0).sum()), int(np.flatnonzero(k1 == 0)[0])]
    h.setdefault("heldout_section_lengths", {})
    if s.id in ("a-koan-1", "the-loss-of-divinity"):
        h["heldout_section_lengths"][s.id] = int(pl.size)
h["solved_plain_F"] = [pf, tot, pf / tot]
h["keyed_interrupters_vs_plain_F"] = ints
a, b = h["heldout_section_lengths"]["a-koan-1"], h["heldout_section_lengths"]["the-loss-of-divinity"]
h["heldout_disjoint_windows"] = {L: a // L + b // L for L in (100, 240, 250, 263, 500, 1000)}
h["heldout_offsets"] = {L: max(a - L + 1, 0) + max(b - L + 1, 0) for L in (100, 240, 250, 263, 500)}
for f, n in ((0.016123614376889486, "solved_sections"), (8268 / 306683, "cicada_english")):
    h[f"expected_F_every_plaintext_F_{n}"] = f * st.size + (1 - f) * st.size / 29

# beam_decoder §4 arithmetic
fits = {(c["decoder"], c["L"]): c for c in bd["staged_calibrations"]}
h["fit_checks"] = {
    f"{d}@{L}": {
        "25k_minus_pred": c["check"]["mean_max_25000"] - c["check"]["predicted_mean_max_25000"],
        "1e6max_minus_pred": c["check"]["max_1000000"] - c["check"]["predicted_mean_max_1000000"],
        "in_gumbel_sd": (c["check"]["max_1000000"] - c["check"]["predicted_mean_max_1000000"]) / (math.pi / math.sqrt(6) * c["beta"]),
        "in_beta": (c["check"]["max_1000000"] - c["check"]["predicted_mean_max_1000000"]) / c["beta"],
    }
    for (d, L), c in fits.items()
}
h["windows_expected_above_z2_of_54"] = 54 * 0.5 * math.erfc(2 / math.sqrt(2))
r_fit = math.sqrt((1 / 20000) / (1 / 2000 + 1 / 20000))
r_win = math.sqrt((1 / 2000) / (1 / 2000 + 1 / 20000)) / math.sqrt(54)
h["mean_z_uncertainty"] = {"from_fit_mean": r_fit, "from_windows": r_win, "total": math.hypot(r_fit, r_win)}
sd_bs240 = fits[("beam-skip", 240)]["null_sd"]
se = sd_bs240 * math.sqrt(1 / 2000 + 1 / 20000)
h["mean_z_uncertainty"]["in_score"] = math.hypot(r_fit, r_win) * se
h["mean_z_uncertainty"]["in_beta"] = h["mean_z_uncertainty"]["in_score"] / fits[("beam-skip", 240)]["beta"]
for d, z in (("beam", -9.511122214771795), ("beam-skip-int", -8.56676899886805)):
    c = fits[(d, 120)]
    s = abs(z) * c["null_sd"] * math.sqrt(1 / 2000 + 1 / 20000)
    h[f"L120_{d}_page43_shift"] = {"score": s, "beta": s / c["beta"]}

# beam_decoder §5 gaps
tc = bd["template_control"]
h["template_gap_staged_beta"] = (tc["floor"] - tc["ceiling_observed"] - 0.037657453149229296 * math.log(2**32 / 20000)) * LN2
h["template_gap_plant_beta"] = (tc["floor"] - tc["ceiling_observed"] - tc["beta"] * math.log(2**32 / 20000)) * LN2
h["P3_control"] = {
    "ceiling_2^32": ctl["ceiling_observed"] + ctl["beta"] * math.log(2**32 / ctl["ceiling_trials"]),
    "gap_nats": (ctl["floor"] - (ctl["ceiling_observed"] + ctl["beta"] * math.log(2**32 / ctl["ceiling_trials"]))) * LN2,
    "floor_minus_bar": ctl["floor"] + 5.7284,
    "recovery_min_max": [min(p["recovery"] for p in ctl["plants"]), max(p["recovery"] for p in ctl["plants"])],
    "median_planted": float(np.median([p["planted_score"] for p in ctl["plants"]])),
    "wrong_key_max_field": ctl["wrong_key_max"],
    "max_best_decoy": max(p["best_decoy"] for p in ctl["plants"]),
    "max_wrong_key_score": max(p["wrong_key_score"] for p in ctl["plants"]),
    "distinct_offsets": len({p["offset"] for p in ctl["plants"]}),
    "identical_to_beam_decoder_template_control": ctl["floor"] == tc["floor"] and ctl["ceiling_observed"] == tc["ceiling_observed"],
}
h["cpu_days_2^32_at_1240"] = 2**32 / 1240 / 86400
h["kill_rate_2^32_in_2h"] = 2**32 / 7200
h["upstream_S2_fraction"] = 1895728884 / 2**32

# scorer_power power rows quoted by the P3 PREREG
rows = {(r["register"], r["L"], r["scorer"]): r for r in sp["sections"]["power"]["rows"]}
for reg in ("latin", "vowel-dropped-english"):
    r = rows[(reg, 240, "lp-ngram3-heldout")]
    h[f"scorer_power_{reg}_240_lp3"] = {
        "claim": r["claim"]["power"], "family": r["family"]["power"], "family_bar": r["family"]["bar"],
        "family_ci_high_bar": r["family_ci_high_bar"]["power"], "n_disjoint": r["n_disjoint"],
        "normal_approx_at_lane_bar": 0.5 * math.erfc((-5.7284 - r["planted_mean"]) / r["planted_sd"] / math.sqrt(2)),
    }
h["wilson_all_success_n50"] = 50 / (50 + 1.959964**2)

res = json.load(open(OUT)) if os.path.exists(OUT) else {}
res["handchecks"] = h
res["handchecks_command"] = "V=/tmp/claude-0/-home-user-cicada-3301-Code-cracker-attempt-1/4950dc03-e080-591a-84c1-d8ea81cef212/scratchpad/venv; $V/bin/python lanes/R1-REDTEAM-OWN-CLAIMS/C2_handchecks.py"
res["handchecks_wall_seconds"] = round(time.time() - T0, 2)
json.dump(res, open(OUT, "w"), indent=1, default=str)
print(json.dumps(h, indent=1, default=str))
