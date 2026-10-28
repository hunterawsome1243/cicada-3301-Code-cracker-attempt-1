# Lane P3-MT19937-PY27-ANTIREPEAT — prng (Python 2.7 MT19937, random29, anti-repeat key skips) — RESULTS

**Verdict: <verdict> — <verdict_summary>.**

<!-- SKELETON, written 2026-10-27 for P3-MT19937-PY27-EXACT and moved to this lane 2026-10-28 (the
     re-registration that rounds the bars up), before the sweep has run. Everything in <angle brackets> is
     filled from runs/P3-MT19937-PY27-ANTIREPEAT/{sweep.jsonl,status.json}, the post-TR-1 control file and
     the crosser logs after the sweep finishes; everything else below is already measured (PREREG.md and
     this lane's gate.json, control-cb8c97d6285d.json, null.json, threshold_after_TR1.json) and is edited
     only to correct it against its source (corrections of 2026-10-28 from the setup-script review are
     already in). `python scripts/check_results.py` does NOT detect leftover placeholders: it fails the
     skeleton only on <verdict>. Before the write-up counts as finished,
     `grep -nE '<[a-z_]+[:>]' lanes/P3-MT19937-PY27-ANTIREPEAT/RESULTS.md` must print nothing outside
     this comment, and the checker must print PASS.
     Allowed fillings: <kill_outcome> = "fired" | "did not fire"; <oracle_result> = "not run — no
     crosser" | "→ PASS" | "→ FAIL" per crosser.
     Verdict vocabulary: NULL | CANDIDATE | INCONCLUSIVE (power) | EXCLUDED (gate). The gate passed
     and the control passed, so EXCLUDED (gate) and INCONCLUSIVE (power) can only arise from the
     Q5 kill or a re-run that fails; a bar crossing is CANDIDATE only after HIT_PROTOCOL.md. -->

numbering: "LP2-0-57" · pre-registered in [`PREREG.md`](PREREG.md) (frozen in `604aebb`; supersedes `P3-MT19937-PY27-EXACT`) ·
lane spec `lanes/P3-MT19937-PY27-ANTIREPEAT.yaml` · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`

## 0. Headline numbers

| quantity | value |
|---|---|
| trials (true N) | 4,294,967,296 (seeds 0 … 2^32 − 1; `<seeds_done>` scored, cursor `<cursor>`) |
| control | recovered 20/20 plants at rank 1 |
| null (shuffle) | n = 200, mean −6.4565, sd 0.0457, max −6.2983 |
| bar | −5.728379 (`threshold_for` −5.72837932 rounded up, fixed in advance; claim/screening bar −6.043391) |
| best real | <best_real> (z = <z>) |
| verdict arithmetic | best real <best_real> vs floor −4.3063 vs ceiling <ceiling_post_TR1> |
| crossers | <n_crossers> |

## 1. Why this lane

Category bounded (round split before this lane I/B/R/C: instrument work with no ledger rows / no bounded
lane run, `P3-MT19937-PY27-EXACT` pre-registered and superseded unrun / one red-team lane,
`R1-REDTEAM-OWN-CLAIMS` / no closeout; this is the first bounded lane to run). Q2 fact: LP2 0–55 holds 86
doublets against 447 expected, and of the forward models in this repo only the anti-repeat key-skip
filter reproduces that deficit and passes the fingerprint gate (`reports/beam_decoder.md` §3;
`lanes/P3-MT19937-PY27-ANTIREPEAT/gate.json`); whether only this filter passes is not fully measured (no
filter-off gate row is committed; PREREG §0 Q2). A Python 2.7
script is the 2012 author's most ordinary tool. Upstream (Dukotah R27-S2) scored 44.14 % of this seed
space under a different decoder (keyskip1, max_skip 3, L = 120, beam width 64, 9-register panel) and
parked with `n_claim_bar_hits 0` but an unresolved above-bar flag at seed 35563892 (re-screened here:
−6.4894, below both of this lane's bars; `lanes/P3-MT19937-PY27-EXACT/PREREG.md` addendum 2026-10-28 (2)); the remaining 55.86 % has no
scored decode under a single-skip or anti-repeat relation, and this lane is a second instrument (multi-skip
beam, max_skip 6, our scorer and bar) over the whole space, not a re-run of theirs.

## 2. Instrument audited before the sweep

Trust anchor, run first:

```
pytest -q -m "not slow"                -> 1306 passed, 18 deselected in 135.13s (0:02:15)   (tree of 193b379)
runeforge canon --verify               -> pins verified
python -m runeforge.oracle --selftest  -> ORACLE SELF-TEST: PASS
```

- Gate (`runeforge gate lanes/P3-MT19937-PY27-ANTIREPEAT.yaml`): GATE PASS — fails per constraint over 12
  keys: none (C1, C2, C2b, C2c, C3 and C6 inside the LP2 bands on 12/12 keys; the bands are centred on
  LP2's own values C1 IoC 1.000, C2 doublet rate 0.00664, C2b 1.026, C2c uniform, C3 15, C6 23, and each
  key's own values are in `gate.json`; C5 soft, reported not deciding, outside its band on 10/12).
- Control (`runeforge control lanes/P3-MT19937-PY27-ANTIREPEAT.yaml`, the run after TR-1 with the installed
  β, made by `scripts/gpu_lane_setup.sh`): recovered 20/20 plants at rank 1; median rune-index recovery
  0.975, minimum 0.942; planted score median −3.8207 (floor −4.3063) vs bar −5.728379; wrong key −6.3381
  (the decoys' maximum); ceiling <ceiling_post_TR1> extrapolated to N = 2^32 from the observed
  <observed_post_TR1> over 20,000 null keys (β <beta_post_TR1>, source calibration); gap <gap_post_TR1>
  nats. `<control_file_post_TR1>`. (Before TR-1, in this repository: ceiling −5.8347 from −6.3195 with the
  per-plant β, gap 1.059 nats, `control-cb8c97d6285d.json`; superseded by the run above.)

## 3. Result vs null vs bar

- Null 1, size-matched shuffle of the real runes: n = 200, mean −6.4565, sd 0.0457,
  max −6.2983 (1,000 keys per replicate, `null.json`).
- Null 2, domain-separated SHA-256 stream: n = 200, mean −6.4545, sd 0.0508,
  max −6.2495 (domain `runeforge/null2/P3-MT19937-PY27-ANTIREPEAT`).
- Threshold (fixed in advance): `python scripts/threshold_for.py --n 4294967296 --preset lp-ngram3-heldout:beam-skip
  --L 240 --json` → bar −5.72837932, frozen as −5.728379 (Gumbel μ_b −6.4767, β 0.0377, block 1,000, from
  `lp-ngram3-heldout__beam-skip__L240.json`; expected null max −5.8799); expected false positives over the
  slice 0.0101. <threshold_reproduced_after_TR1: the installed record printed bar … (`threshold_after_TR1.json`); frozen − computed = … ∈ [0, 1e-6], PREREG §4>
- Best real <best_real> (seed <best_seed>), z = <z> against null 1 (z = (best real − (−6.4565)) / 0.0457
  against the 1,000-key replicate maxima is not the right scale for a 2^32 maximum; the bar is).
- Verdict arithmetic: best real <best_real> vs floor −4.3063 vs ceiling <ceiling_post_TR1>
  (floor − ceiling = <gap_post_TR1> nats).
- Q5 kill condition (rate < 600,000 seeds/s or > 10 crossers; the sweep checks it once, at the first chunk
  boundary at or past 10 % of the slice: cursor 436,207,616, fraction 0.1015625, with that chunk's own
  rate; source: the `chunk` row with `hi` 436,207,616 in sweep.jsonl, plus `kill_detail` in
  checkpoint.json if it fired; PREREG addendum 2026-10-28): checked at
  <kill_check_point>; <kill_outcome>; rate at the check <seeds_per_s_at_check> seeds/s,
  crossers at the check <crossers_at_check>.
- Survivors above the screening bar −6.043391: <n_survivors> (≈ 43 expected over the slice under the
  null); each logged with its language-agnostic stats in `runs/P3-MT19937-PY27-ANTIREPEAT/sweep.jsonl`.
- GPU parity and throughput: `runs/P3-MT19937-PY27-ANTIREPEAT/parity.json` (<parity_status>, <parity_seeds>
  seeds, device <device_name>, beam.py SHA `4cd3d7ba59e6…`, kernel SHAs <kernel_sha> / <mt_kernel_sha>) and
  `bench.json` (<gpu_chain_keys_per_s> keys/s on the device chain); the sweep's mean rate
  <seeds_per_s> seeds/s over <wall_clock_s> s. Every survivor, crosser and chunk best was re-generated
  and re-decoded on the CPU reference by the sweep (a disagreement over 1e-6 would have stopped it with
  a crash row: <n_crash_rows> crash rows).

## 4. Survivors reported, not dropped

Top 32 by screen score; escalation per HIT_PROTOCOL.md §3, each z against a size-matched null of that
length.

| kid | head L=240 | z | 2× | z | page | z | stream | z | outcome |
|---|---|---|---|---|---|---|---|---|---|
| <kid> | <s_head> | <z_head> | <s_2x> | <z_2x> | <s_page> | <z_page> | <s_stream> | <z_stream> | <outcome> |

Crossers above the bar: <n_crossers> (logs in `runs/P3-MT19937-PY27-ANTIREPEAT/crossers/`). Oracle:
<oracle_result>.

## 5. Coverage — read this, not the verdict

- Measured: <seeds_done> of 4,294,967,296 seeds in [0, 2^32) (<coverage_fraction> of the stated key
  space), each decoded once with `lp-ngram3-heldout:beam-skip` at L = 240 on pages 0–5 and compared with
  the bar −5.728379; of these, <upstream_overlap: 1,895,728,884 (44.14 %) if the whole slice was swept, else
  the overlap actually swept> were also scored upstream (R27-S2) under a different decoder, bar and window
  (keyskip1, max_skip 3, beam width 64, L = 120, 9-register panel), and <new_seeds> had no scored decode
  before under a single-skip or anti-repeat relation (every seed in [0, 2^32) was scored upstream by R27-S1
  under the pair relation; R20-SG3, R25 and jens-wedin scored sub-slices).
- not_covered: seeds ≥ 2^32 (the 64-bit two-word `init_by_array` image of string seeds, 2^64 − 2^32
  seeds, 0 swept); the reducers `grb5_mod`, `grb5_rej`, `shuffle29` (3 × 2^32, 0 swept here); key offsets
  ≠ 0; the views atbash, chain-increment, first-difference and the combines variant-beaufort and
  beaufort (0 of 11 other view × combine cells); F-interrupters (the every-F variant fails the gate on
  12/12 keys for the typical key and the partial-interrupt variants 0.1 and 0.44 pass it; none searched); skips of more than 6 key symbols at one rune; the pair / skip-by-two relation
  (upstream R27-S1, all 2^32 seeds, NULL under their decoder); non-English plaintext beyond the measured
  power at this lane's decoder and bars (Latin 1.000 at both; vowel-dropped English 0.995 at −6.043391
  and 0.595 [0.526, 0.661] at −5.728379, the same 199/200 and 119/200 as at the earlier −6.0434 and
  −5.7284 from the per-plant scores in `lanes/R1-REDTEAM-OWN-CLAIMS/out_C2.json`); <any seeds left
  unscored if the sweep stopped early, as a count>.
- Conditionals: key space `mt19937-py27` random29, 32-bit int seeds, offset 0, raw view, `c = p + k` ·
  decoder `beam-skip` (width 8, max_skip 6, p_keep 0.19, no interrupters) · register English only
  (`lp-ngram3-heldout`, Cicada spelling). This is an English-register, one-decoder negative if the
  verdict is NULL.

## 6. What would change this verdict

- reopens_if: TR-1 installs a record whose bar differs from −5.72837932 by more than 1e-6 (PREREG §8:
  re-freeze before any run; `scripts/gpu_lane_setup.sh` step 3 stops the lane in that case, so a run
  implies the record reproduced the bar; a later re-screen of the logged survivors against another bar
  would itself need a dated PREREG addendum); a later installed scorer with materially higher power on this
  family's plants at L = 240 (`kn4-cicada:beam-skip`, TR-7; today 50/50 for both); a canonical-rune
  transcription change; evidence that the author's interpreter was not CPython 2.7; a survivor whose
  escalation (§4) improves with the window; a GPU/CPU parity disagreement found later in
  `runs/P3-MT19937-PY27-ANTIREPEAT/` (every number above is then suspect until re-decoded on the CPU
  reference).

## 7. Artifacts and reproduce

- `runs/P3-MT19937-PY27-ANTIREPEAT/sweep.jsonl` (SHA-256 `<sweep_sha256>`), `runs/P3-MT19937-PY27-ANTIREPEAT/status.json`,
  `runs/P3-MT19937-PY27-ANTIREPEAT/parity.json`, `bench.json`; committed `lanes/P3-MT19937-PY27-ANTIREPEAT/{gate,control,
  <control_file_post_TR1>, control-cb8c97d6285d, null, threshold_after_TR1, parity, bench}.json`; ledger row `P3-MT19937-PY27-ANTIREPEAT` in `ledger/ledger.jsonl`; git <git_sha>.

```bash
runeforge gate lanes/P3-MT19937-PY27-ANTIREPEAT.yaml
runeforge control lanes/P3-MT19937-PY27-ANTIREPEAT.yaml
runeforge null lanes/P3-MT19937-PY27-ANTIREPEAT.yaml --n 200
python scripts/threshold_for.py --n 4294967296 --preset lp-ngram3-heldout:beam-skip --L 240
bash scripts/gpu_lane_setup.sh lanes/P3-MT19937-PY27-ANTIREPEAT.yaml   # TR-1, control, parity, bench, approval, launch
runeforge score lanes/P3-MT19937-PY27-ANTIREPEAT.yaml <best_seed>
python scripts/check_results.py lanes/P3-MT19937-PY27-ANTIREPEAT/RESULTS.md
```
