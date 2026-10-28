# Lane P3-MT19937-PY27-EXACT — prng (Python 2.7 MT19937, random29, anti-repeat key skips) — RESULTS

**Verdict: <verdict> — <verdict_summary>.**

<!-- SKELETON, written 2026-10-27 before the sweep has run. Everything in <angle brackets> is
     filled from runs/P3-MT19937-PY27-EXACT/{sweep.jsonl,status.json} and the crosser logs after
     the sweep finishes; everything else below is already measured (PREREG.md addendum of
     2026-10-27) and must not be edited. `python scripts/check_results.py lanes/P3-MT19937-PY27-EXACT/RESULTS.md`
     fails while a placeholder remains, which is the intended state of a lane that has not run.
     Verdict vocabulary: NULL | CANDIDATE | INCONCLUSIVE (power) | EXCLUDED (gate). The gate passed
     and the control passed, so EXCLUDED (gate) and INCONCLUSIVE (power) can only arise from the
     Q5 kill or a re-run that fails; a bar crossing is CANDIDATE only after HIT_PROTOCOL.md. -->

numbering: "LP2-0-57" · pre-registered in [`PREREG.md`](PREREG.md) (frozen in `fabac07`) ·
lane spec `lanes/P3-MT19937-PY27-EXACT.yaml` · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`

## 0. Headline numbers

| quantity | value |
|---|---|
| trials (true N) | 4,294,967,296 (seeds 0 … 2^32 − 1; `<seeds_done>` scored, cursor `<cursor>`) |
| control | recovered 20/20 plants at rank 1 |
| null (shuffle) | n = 200, mean −6.4565, sd 0.0457, max −6.2983 |
| bar | −5.7284 (`threshold_for`, fixed in advance; claim/screening bar −6.0434) |
| best real | <best_real> (z = <z>) |
| verdict arithmetic | best real <best_real> vs floor −4.3063 vs ceiling −5.9806 |
| crossers | <n_crossers> |

## 1. Why this lane

Category bounded (round split before this lane I/B/R/C = 100/0/0/0 %: every row so far is
instrument work; this is the first bounded lane). Q2 fact: LP2 0–55 holds 86 doublets against 447
expected, and only the anti-repeat key-skip forward model reproduces that deficit and passes the
fingerprint gate (`reports/beam_decoder.md` §3; `lanes/P3-MT19937-PY27-EXACT/gate.json`). A Python 2.7
script is the 2012 author's most ordinary tool. Upstream (Dukotah R27-S2) scored 44.14 % of this seed
space under a different decoder (keyskip1, max_skip 3, L = 120, beam width 64, 9-register panel) and
parked with `n_claim_bar_hits 0` but an unresolved above-bar flag at seed 35563892 (re-screened here:
−6.4894, below both of this lane's bars; PREREG addendum 2026-10-28 (2)); the remaining 55.86 % has no
scored decode under a single-skip or anti-repeat relation, and this lane is a second instrument (multi-skip
beam, max_skip 6, our scorer and bar) over the whole space, not a re-run of theirs.

## 2. Instrument audited before the sweep

Trust anchor, run first:

```
pytest -q -m "not slow"                -> 1306 passed, 18 deselected in 135.13s (0:02:15)   (tree of 193b379)
runeforge canon --verify               -> pins verified
python -m runeforge.oracle --selftest  -> ORACLE SELF-TEST: PASS
```

- Gate (`runeforge gate lanes/P3-MT19937-PY27-EXACT.yaml`): GATE PASS — fails per constraint over 12
  keys: none (C1 IoC 1.000, C2 doublet rate 0.00664, C2b 1.026, C2c uniform, C3 15, C6 23 inside the
  LP2 bands on 12/12 keys; C5 soft, reported not deciding, outside its band on 10/12).
- Control (`runeforge control lanes/P3-MT19937-PY27-EXACT.yaml`): recovered 20/20 plants at rank 1; median
  rune-index recovery 0.975, minimum 0.942; planted score median −3.8207 (floor −4.3063) vs bar −5.7284;
  wrong key −6.3381 (the decoys' maximum); ceiling −5.9806 extrapolated to N = 2^32 from the observed
  −6.3762 over 20,000 null keys (β 0.0322 from the per-plant maxima; the calibration was staged, not
  installed, when the control ran); gap 1.160 nats. `control-4c65a7978362.json`.

## 3. Result vs null vs bar

- Null 1, size-matched shuffle of the real runes: n = 200, mean −6.4565, sd 0.0457,
  max −6.2983 (1,000 keys per replicate, `null.json`).
- Null 2, domain-separated SHA-256 stream: n = 200, mean −6.4580, sd 0.0515,
  max −6.2292 (domain `runeforge/null2/P3-MT19937-PY27-EXACT`).
- Threshold (fixed in advance): `python scripts/threshold_for.py --n 4294967296 --preset lp-ngram3-heldout:beam-skip
  --L 240` → bar −5.7284 (Gumbel μ_b −6.4767, β 0.0377, block 1,000, from
  `lp-ngram3-heldout__beam-skip__L240.json`; expected null max −5.8799); expected false positives over the
  slice 0.0101. <threshold_reproduced_after_TR1: the installed record printed −5.7284 / differed by …>
- Best real <best_real> (seed <best_seed>), z = <z> against null 1 (z = (best real − (−6.4565)) / 0.0457
  against the 1,000-key replicate maxima is not the right scale for a 2^32 maximum; the bar is).
- Verdict arithmetic: best real <best_real> vs floor −4.3063 vs ceiling −5.9806
  (floor − ceiling = 1.160 nats).
- Q5 kill condition (at seed 429,496,730: rate < 600,000 seeds/s or > 10 crossers): checked at
  <kill_check_point: status.json kill_checked / epoch>; <kill_outcome: fired / did not fire>; rate at
  the check <seeds_per_s_at_check> seeds/s, crossers at the check <crossers_at_check>.
- Survivors above the screening bar −6.0434: <n_survivors> (≈ 43 expected over the slice under the
  null); each logged with its language-agnostic stats in `runs/P3-MT19937-PY27-EXACT/sweep.jsonl`.
- GPU parity and throughput: `runs/P3-MT19937-PY27-EXACT/parity.json` (<parity_status>, <parity_seeds>
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

Crossers above the bar: <n_crossers> (logs in `runs/P3-MT19937-PY27-EXACT/crossers/`). Oracle:
<oracle_result: not run — no crosser / → PASS / → FAIL per crosser>.

## 5. Coverage — read this, not the verdict

- Measured: <seeds_done> of 4,294,967,296 seeds in [0, 2^32) (<coverage_fraction> of the stated key
  space), each decoded once with `lp-ngram3-heldout:beam-skip` at L = 240 on pages 0–5 and compared with
  the bar −5.7284; of these, 1,895,728,884 (44.14 %) were also scored upstream (R27-S2) under their
  narrower decoder, bar and window, and <new_seeds> had never been scored before.
- not_covered: seeds ≥ 2^32 (the 64-bit two-word `init_by_array` image of string seeds, 2^64 − 2^32
  seeds, 0 swept); the reducers `grb5_mod`, `grb5_rej`, `shuffle29` (3 × 2^32, 0 swept here); key offsets
  ≠ 0; the views atbash, chain-increment, first-difference and the combines variant-beaufort and
  beaufort (0 of 11 other view × combine cells); F-interrupters (excluded by the gate at the every-F
  rule, not searched); skips of more than 6 key symbols at one rune; the pair / skip-by-two relation
  (upstream R27-S1, all 2^32 seeds, NULL under their decoder); non-English plaintext beyond the measured
  power at this lane's decoder and bars (Latin 1.000 at both; vowel-dropped English 0.995 at −6.0434
  and 0.595 [0.526, 0.661] at −5.7284; `lanes/R1-REDTEAM-OWN-CLAIMS/out_C2.json`); <any seeds left unscored if the sweep stopped early, as a count>.
- Conditionals: key space `mt19937-py27` random29, 32-bit int seeds, offset 0, raw view, `c = p + k` ·
  decoder `beam-skip` (width 8, max_skip 6, p_keep 0.19, no interrupters) · register English only
  (`lp-ngram3-heldout`, Cicada spelling). This is an English-register, one-decoder negative if the
  verdict is NULL.

## 6. What would change this verdict

- reopens_if: TR-1 installs a refit whose bar differs from −5.7284 by more than 1e-4 (the slice is
  re-screened against the new bar from the logged survivors, no re-sweep needed while the installed
  bar is above the screening bar −6.0434); a later installed scorer with materially higher power on this
  family's plants at L = 240 (`kn4-cicada:beam-skip`, TR-7; today 50/50 for both); a canonical-rune
  transcription change; evidence that the author's interpreter was not CPython 2.7; a survivor whose
  escalation (§4) improves with the window; a GPU/CPU parity disagreement found later in
  `runs/P3-MT19937-PY27-EXACT/` (every number above is then suspect until re-decoded on the CPU
  reference).

## 7. Artifacts and reproduce

- `runs/P3-MT19937-PY27-EXACT/sweep.jsonl` (SHA-256 `<sweep_sha256>`), `runs/P3-MT19937-PY27-EXACT/status.json`,
  `runs/P3-MT19937-PY27-EXACT/parity.json`, `bench.json`; committed `lanes/P3-MT19937-PY27-EXACT/{gate,control,
  control-4c65a7978362,null}.json`; ledger row `P3-MT19937-PY27-EXACT` in `ledger/ledger.jsonl`; git <git_sha>.

```bash
runeforge gate lanes/P3-MT19937-PY27-EXACT.yaml
runeforge control lanes/P3-MT19937-PY27-EXACT.yaml
runeforge null lanes/P3-MT19937-PY27-EXACT.yaml --n 200
python scripts/threshold_for.py --n 4294967296 --preset lp-ngram3-heldout:beam-skip --L 240
python -m runeforge.gpu.parity lanes/P3-MT19937-PY27-EXACT.yaml --bench 1048576
runeforge sweep lanes/P3-MT19937-PY27-EXACT.yaml --detach --backend gpu
runeforge score lanes/P3-MT19937-PY27-EXACT.yaml <best_seed>
python scripts/check_results.py lanes/P3-MT19937-PY27-EXACT/RESULTS.md
```
