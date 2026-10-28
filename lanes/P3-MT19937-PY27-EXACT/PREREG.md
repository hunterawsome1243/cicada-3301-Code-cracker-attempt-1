# Lane P3-MT19937-PY27-EXACT — prng (Python 2.7 MT19937, random29, anti-repeat key skips) — PRE-REGISTRATION

_Frozen 2026-10-27, written before any measurement in this lane. No decode, plant, null or sweep of
this lane's own has been executed at the time of writing. Committed as
`lane(P3-MT19937-PY27-EXACT): PREREG frozen` before the gate runs; nothing below is edited afterwards (dated
addenda go at the end)._

numbering: "LP2-0-57" · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`
(12,956 runes, LP2 pages 0–55) · lane spec `lanes/P3-MT19937-PY27-EXACT.yaml` · category bounded

## What was read before this document was written

- Our ledger: `ledger/ledger.jsonl` (empty: no lane has a row yet) and `PICKUP-HERE.md`.
- Dukotah `LEDGER.json`, `coverage` / `not_covered` of R19-G3, R20-SG3-PY27-RANDOM29, R21-L3-PY27-REDUCERS,
  R25-COMPUTE-TAIL-CHUNK1, R26-A-GEN-SWEEP-FIRST-FIRE, R27-CPORT-MT32-FULLSWEEP;
  `handoff/PARKED-SWEEPS.md` §1 (R27-S2 parked at 44.14 %); `analysis/round27/PREREG.md` (the S2 relation:
  keyskip1 "exact" = the one-draw rejection loop, decoded with a keyskip1 beam, max_skip 3, at L = 120 under
  their 9-register panel) and `analysis/round27/P0-spec/S2-CONTROL.md` (plant: `encipher_keyskip`, supp 0.83);
  `analysis/round27/S1-CLOSEOUT.md` (S1, the pair / skip-by-two relation: all 2^32 seeds, NULL).
- jens-wedin `REPORT.md` line 468 and `README.md` line 181 (`attack_prng.py`: Mersenne over seeds 0–20k +
  thematic, rigid, judged against a random-text ceiling); `BACKLOG.md` has no MT19937 entry.
- The code this lane runs: `runeforge/generators/mt19937_py27.py` (byte-exact CPython 2.7 seeding, pinned
  vectors), `runeforge/beam.py` (`beam-skip`), `runeforge/scoring/presets.py` (`lp-ngram3-heldout`,
  `DECODER_PARAMS`), `runeforge/runner/{pipeline,control,gate,null,sweep}.py`, `runeforge/gpu/{beam_kernel,
  mt_kernel,parity}.py`; the measured instrument envelopes `reports/beam_decoder.md` and
  `reports/scorer_power.md`; the staged calibration `reports/calib-staging/lp-ngram3-heldout__beam-skip__L240.json`.

Trust anchor, run before writing (last line of each):
`pytest -q -m "not slow"` → `1306 passed, 18 deselected in 135.13s (0:02:15)` (tree of `193b379`) ·
`runeforge canon --verify` → `pins verified` · `python -m runeforge.oracle --selftest` → `ORACLE SELF-TEST: PASS`

## 0. Aiming Test

- **Q1 What a hit looks like, and whether this instrument sees it:** one 32-bit seed `w` whose CPython 2.7
  `random.seed(w)` + `int(random.random()*29)` stream, read under `c = p + k (mod 29)` with the anti-repeat
  key skips (a key symbol that would repeat the previous canonical rune is dropped with probability
  1 − p_keep, p_keep 0.19), deciphers the first 240 runes of LP2 pages 0–5 to Cicada-register English:
  the `beam-skip` decode of that seed scores above −5.7284 under `lp-ngram3-heldout` at L = 240 and
  re-enciphers to the canonical runes rune for rune. The control in §3 plants exactly that and must
  recover it. That this instrument sees such a key is already measured on synthetic plants, not assumed:
  `reports/beam_decoder.md` §5 and `reports/scorer_power.md` §5 (`lp-ngram3-heldout` / `beam-skip` /
  anti-repeat at L = 240: 50/50 plants identified at rank 1 over 99 decoys, planted mean −3.95 against a
  wrong-key null mean −6.87; the rigid decoder identifies 0/50 of the same plants).
- **Q2 The measured fact that raises the prior:** LP2 0–55 holds 86 doublets against 447 expected for
  uniform runes (z ≈ −17), and of the forward models in this repo only the anti-repeat key-skip filter
  reproduces that deficit and passes the fingerprint gate — `GATE PASS` on 12/12 keys at
  `interrupt_prob: 0.0` (`reports/beam_decoder.md` §3; `python scripts/beam_power.py`, section gate;
  `runs/P3-MT19937-PY27-EXACT/gate.json` once this lane's gate runs). A Python 2.7 script is the
  2012 author's most ordinary tool, and upstream found the family runnable but left it 55.86 % unswept
  under a narrower decoder (`data/raw/dukotah/liber-primus/handoff/PARKED-SWEEPS.md` §1). This is a
  bounded, enumerable space with a measured instrument; it is not a completeness ritual.
- **Q3 Is the space bounded?** 2^32 = 4,294,967,296 seeds; enumerable; this lane sweeps all of it
  (fraction 1.0 of the stated space; seeds 0 … 2^32 − 1 in order, resume by cursor).
- **Q4 The three conditionals:** key space `mt19937-py27` mode `random29`, 32-bit int seeds, key offset 0,
  `c = p + k (mod 29)` in the raw view · decoder `beam-skip` (width 8, max_skip 6, p_keep 0.19, no
  interrupters; `presets.DECODER_PARAMS`) · register English only, scorer `lp-ngram3-heldout` (order-3
  Witten-Bell on seven solved sections); Latin and vowel-dropped English are detected only to the
  power `reports/scorer_power.md` §3 measures for that scorer (rigid-exact plants at L = 240: Latin
  1.000 at both bars; vowel-dropped English 1.000 at N = 10^6, 0.790 at 2^32).
- **Q5 Kill condition at 10 % of budget:** at seed 429,496,730 (10 % of the slice) the sweep is killed if
  its rate is below 600,000 seeds/s (2^32 would then not finish inside the 2-hour wall clock) or if more
  than 10 crossers have been flagged (the whole slice expects 0.0101 null crossers; 10 at a tenth of it
  means the bar is wrong, not that there are keys) — `kill_condition` in the lane spec, checked once by
  `runeforge sweep` at `at_fraction: 0.10`. The check and its outcome (fired or did not fire) go into
  RESULTS.md either way.

## 1. Hypothesis

The LP2 pages 0–55 keystream is `random.seed(w)` + `int(random.random()*29)` of CPython 2.7 for one
32-bit integer `w`, read from offset 0 and combined as `c = p + k (mod 29)` under the anti-repeat
key-skip relation (p_keep 0.19), and the first 240 runes of pages 0–5 decode under it to English in the
Cicada register.

## 2. Key space, ciphertext view, decoder, register

| item | value |
|---|---|
| key space | generator `mt19937-py27`, `mode: random29`, `seed_bits: 32`, key offset 0 (`runeforge/generators/mt19937_py27.py`, byte-exact against CPython 2.7.3 / 2.7.18 vectors); size 2^32 = 4,294,967,296; this lane sweeps seeds [0, 2^32) (fraction 1.0 of it) |
| true N (trials, for the bar) | 4,294,967,296 |
| ciphertext view | raw; combine vigenere (`c = p + k`); LP2 pages 0, 1, 2, 3, 4, 5 (1,469 runes), scored window the first 240 |
| decoder | preset `lp-ngram3-heldout:beam-skip`: the beam decoder matching `filter_model: anti-repeat` with `interrupt_prob: 0.0`; beam width 8, max_skip 6, p_keep 0.19 as `presets.DECODER_PARAMS` pins them (`runeforge/beam.py` SHA-256 `4cd3d7ba59e6…`) |
| scorer register(s) | English, Cicada spelling: `lp-ngram3-heldout` (the solved sections minus A KOAN (1) and THE LOSS OF DIVINITY, fingerprint `a144706ac65a…`); calibration `runeforge/scoring/calib/presets/lp-ngram3-heldout__beam-skip__L240.json` once TR-1 installs the staged file `reports/calib-staging/lp-ngram3-heldout__beam-skip__L240.json` (SHA-256 `46a95f857fbf10ed9bdd164b56f39108cc362970d9b80460f4416e62989162ea`) unchanged |
| windows | screen L = 240; escalation 2× (480) → page → full 12,956-rune stream (HIT_PROTOCOL.md §3) |
| persisted per decode | IoC·N, min distinct symbols in a 32-rune window, order-2 entropy, zlib ratio, best non-English register (`runeforge/stats/decode.py`), for every survivor, crosser and chunk best |

## 3. Positive control (pre-specified; run by `runeforge control lanes/P3-MT19937-PY27-EXACT.yaml`)

- Plant: a key drawn from the searched space in the real shape (seed inside the real generator
  `mt19937-py27`/`random29`, the first plant at the pre-named seed 3301 and 19 more at fresh seeds, at a
  random offset of the held-out solved section A KOAN (1), `solved:a-koan-1`, never in the scorer's
  training text) on synthetic Cicada-register English, enciphered through `pipeline.encrypt` with the
  anti-repeat filter (p_keep 0.19, no interrupters), through the same pipeline, decoder preset and window
  as the sweep. 20 plants, 999 decoys each, rng seed 3301 (`control:` in the lane spec).
- Pass bar (all of): rune-index recovery ≥ 0.90 on ≥ 90 % of the plants, at rank 1 · planted score above
  the bar −5.7284 (floor ≥ bar) · a deliberately wrong key below the noise ceiling; floor − ceiling ≥ 0.25
  nats with the ceiling extrapolated to N = 2^32 with the calibration's β (`control._beta`; until TR-1 the
  frozen control uses the per-plant β, which `reports/beam_decoder.md` §5 measured at 1.160 nats of gap
  on the template spec, 1.114 with the staged β).
- Fail → the lane is `INCONCLUSIVE (power)`. The bar is not lowered and the lane does not search;
  the instrument fix is a new instrument lane.

## 4. Null, threshold, expected false positives

- Null 1: size-matched shuffle of the real runes, n = 200 replicates (≥ 200), 1,000 keys per replicate,
  same decoder, scorer and window → `null_mean`, `null_sd`, `null_max` (`runeforge null`).
- Null 2: domain-separated SHA-256 stream (`sha256-ctr`, domain `runeforge/null2/P3-MT19937-PY27-EXACT`
  as `runeforge null` derives it), n = 200 replicates: a key source outside every family this lane searches.
- Threshold: `python scripts/threshold_for.py --n 4294967296 --preset lp-ngram3-heldout:beam-skip --L 240`
  → `threshold_for(N=4,294,967,296, preset=lp-ngram3-heldout:beam-skip, L=240, alpha=0.01) = -5.7284
  [gumbel; expected null max -5.8799; expected false positives 0.0101]`. The command refuses today
  (the calibration is staged, not installed: TR-1); the number is the same Gumbel arithmetic
  (`calib.threshold_for`: μ_N = μ_b + β ln(N/1000) = −6.4767 + 0.037657 × ln(4,294,967.296) = −5.9016;
  bar = μ_N − β ln(−ln 0.99) = −5.7284) applied to the staged record's fit (`mu_block` −6.476749792302121,
  `beta` 0.037657453149229296, block 1,000; 10^6 beam-skip decodes of doublet-free ciphers under uniform
  keys, seed 3301, scale check max error 0.027). The installed record must reproduce this bar to 1e-4 or
  the lane does not run and a dated addendum records the delta. Screening bar `claim_bar` = the same
  arithmetic at N = 10^6: −6.0434 (survivors above it are logged with their stats, ≈ 43 expected over the
  slice; nothing below the family-wise bar is a crosser). Small N does not apply.
- Expected false positives over the slice, N · P(clear) = 0.0101 (must be < 1).

## 5. Hit function and decision rule

A survivor is `FLAGGED-FOR-ORACLE` only if ALL of: it clears the bar at the lane's true N ·
rune-index self-consistency ≥ 0.90 on held-out halves · its z improves when the window doubles
(head → page → full stream) · oracle PASS. Score alone is never a hit; nothing is auto-certified.
Any bar crossing goes to HIT_PROTOCOL.md immediately.
Outcomes: `NULL` · `FLAGGED-FOR-ORACLE` (lane verdict `CANDIDATE`) · `INCONCLUSIVE (power)` ·
`EXCLUDED (gate)` if the fingerprint gate (SESSION_PROMPT.md §C3 step 1, ≥ 12 keys) fails.

## 6. Verdict arithmetic (rendered by `runeforge control`, never by hand)

- Detection floor = the minimum score of the planted hypotheses that self-recover through this
  pipeline.
- Matched ceiling = null 2's max: same length, same number of trials, same scorer.
- `INCONCLUSIVE (power)` if fewer than half of the plants are individually identifiable, or if
  floor − ceiling < 0.25 nats. Best real ≥ floor → crosser protocol. Otherwise `NULL`, written as
  "best real X vs floor Y vs ceiling Z".

## 7. Budget

Wall-clock 2.0 h · decodes 4,294,967,296 beam-skip decodes at L = 240 (one per seed; survivors and
crossers re-decoded on the CPU reference) · GPU-hours ≤ 2.0 (`budget.gpu_hours_cap`; > 2 needs Hunter's
approval in `queue.json`). The sweep runs only as `runeforge sweep … --detach --backend gpu` after
`python -m runeforge.gpu.parity lanes/P3-MT19937-PY27-EXACT.yaml --bench 1048576` has passed on the RTX
(both kernels, ≥ 10^4 seeds, `runs/P3-MT19937-PY27-EXACT/parity.json`): at the spec's 10^7 seeds/s the
slice takes ~7 min, at 10^6 ~72 min. On the CPU reference alone (~1,240 keys/s, `reports/beam_decoder.md`
§6) the slice is ~40 core-days and is not this lane's budget; a CPU-only run would be a dated addendum
naming its slice and fraction before it starts.

## 8. Scope, declared now

- not_covered: seeds ≥ 2^32 (the 64-bit two-word `init_by_array` image of string seeds, `seed_bits: 64`:
  2^64 − 2^32 seeds, 0 swept); the other three 2.7 reducers (`grb5_mod`, `grb5_rej`, `shuffle29`: 3 × 2^32
  seeds, 0 swept here; upstream R21-L3 and R26-A swept prior-dense slices of them, ≤ 0.007 % each); key
  offsets ≠ 0; the ciphertext views atbash, chain-increment and first-difference and the combines
  variant-beaufort and beaufort (0 of 11 other view × combine cells); F-interrupters (`interrupt_prob` 0:
  the every-F rule fails the fingerprint gate on 12/12 keys, `reports/beam_decoder.md` §3, so an
  interrupt-bearing variant of this family is excluded by the gate, not searched); skips of more than 6
  key symbols at one rune (max_skip 6; probability ≈ 1e-11 per rune under a uniform key); the pair /
  skip-by-two relation (upstream R27-S1: all 2^32 seeds, NULL, under their decoder); pages other than
  0–5 as the screen (a true key decodes the whole stream, which the escalation checks); non-English
  plaintext beyond the measured power above. Overlap, declared: 44.14 % of this slice (seeds in six
  upstream worker bands, 1,895,728,884 seeds) was scored by upstream R27-S2 under the keyskip1 beam
  (max_skip 3, L = 120, their 9-register panel-max bar 7.6342) with 0 claim-bar hits; this lane's decoder
  (multi-skip prior, max_skip 6), scorer, window and bar differ, so it is a second instrument over those
  seeds, not a re-run of the same one, and the remaining 55.86 % has no scored decode anywhere.
- Conditionals: key space `mt19937-py27` random29, 32-bit int seeds, offset 0, raw view, `c = p + k` ·
  decoder `beam-skip` (width 8, max_skip 6, p_keep 0.19, no interrupters) · register English only
  (`lp-ngram3-heldout`, Cicada spelling; Latin power 1.000 and vowel-dropped 0.790 at the 2^32 bar on
  rigid-exact plants, `reports/scorer_power.md` §3).
- reopens_if: TR-1 installs a refit whose bar differs from −5.7284 by more than 1e-4 (re-freeze by
  addendum before any run); the GPU parity record fails or is absent (no sweep); the control fails
  (`INCONCLUSIVE (power)`: instrument lane first); a later scorer (`kn4-cicada:beam-skip`, once its
  calibration is installed, TR-7) has materially higher power at L = 240 on this family's plants
  (`reports/scorer_power.md` §5: 50/50 for both today); a canonical-rune transcription change
  (canon SHA-256 moves); evidence that the author's interpreter was not CPython 2.7 (the `random29`
  reducer identity holds for `randrange`, `randint` and `choice` in 2.7 only).
- external_ids: Dukotah R27-CPORT-MT32-FULLSWEEP (S2, `handoff/PARKED-SWEEPS.md` §1; S1 complete),
  R25-COMPUTE-TAIL-CHUNK1, R20-SG3-PY27-RANDOM29, R21-L3-PY27-REDUCERS, R19-G3,
  R26-A-GEN-SWEEP-FIRST-FIRE, upstream tasking ref R27-S2 (`lanes/P3-MT19937-PY27-EXACT.yaml`
  `params.upstream_ledger_ref`); jens-wedin `attack_prng.py` (REPORT.md:468).

## Addenda

<!-- Dated, appended after the freeze. Never edit the sections above. -->

### Addendum 2026-10-27 — what ran after the freeze (C3 steps; nothing above edited)

- Ledger row appended (`runeforge ledger append --lane lanes/P3-MT19937-PY27-EXACT.yaml`): status
  `never-run`, threshold −5.7284 fixed in advance, N = 4,294,967,296, git `fabac07`.
- Gate (`runeforge gate lanes/P3-MT19937-PY27-EXACT.yaml`, 12 keys): **GATE PASS**, fails per
  constraint none; C1 IoC 1.000, C2 doublet rate 0.00664, C2b 1.026, C2c uniform, C3 15, C6 23 all
  inside the LP2 bands on 12/12 keys; C5 (soft, reported not deciding) outside its band on 10/12;
  `lanes/P3-MT19937-PY27-EXACT/gate.json`.
- Control (`runeforge control lanes/P3-MT19937-PY27-EXACT.yaml`, rng seed 3301, 20 plants × 999
  decoys, 30 s): **control PASSED**: recovered 20/20 at rank 1 (recovery 0.942–0.992), floor −4.3063 vs
  ceiling −5.9806 extrapolated to N = 2^32 (observed −6.3762 over 20,000 null keys; gap 1.160 nats);
  wrong-key max −6.3381; bar −5.7284 (floor above the bar by 1.42). β source: per-plant maxima (the
  calibration is staged, not installed); `lanes/P3-MT19937-PY27-EXACT/control-4c65a7978362.json`.
- Nulls (`runeforge null lanes/P3-MT19937-PY27-EXACT.yaml --n 200`, 1,000 keys per replicate, 5 min):
  null 1 (shuffle of the real runes) n = 200, mean −6.4565, sd 0.0457, max −6.2983; null 2 (SHA-256
  stream, domain `runeforge/null2/P3-MT19937-PY27-EXACT`) n = 200, mean −6.4580, sd 0.0515, max −6.2292;
  `lanes/P3-MT19937-PY27-EXACT/null.json`. Consistency with the frozen bar's fit: the staged record
  predicts a mean 1,000-key maximum of μ_b + βγ = −6.4767 + 0.0377 × 0.5772 = −6.455; the lane's own
  shuffle replicates average −6.4565 (0.0015 above, within 0.04 β), so the staged fit describes this
  window's null as measured on the real runes.
- State: `never-run`. The sweep is refused until TR-1 installs the staged calibration unchanged, a
  real-device parity record for both kernels exists, and Hunter approves the lane in `queue.json`
  (entry added with `approved: false`, `gpu_hours_cap: 2.0`).

### Addendum 2026-10-28 — correction to the 2026-10-27 addendum

- The control's rune-index recovery range reads "0.942–0.992"; the maximum in
  `control-4c65a7978362.json` is 0.9875 (0.942–0.988). Transcription slip; no number used by a verdict.

### Addendum 2026-10-28 (2) — corrections from red-team lane R1-REDTEAM-OWN-CLAIMS (nothing above edited; the bar is unchanged)

Source: `lanes/R1-REDTEAM-OWN-CLAIMS/RESULTS.md` (FOUND-ERROR); every item below was upheld by at least
two of three independent refuters.

1. **Register power of THIS lane (supersedes the numbers quoted in §0 Q4 and §8 Conditionals).** §0 and
   §8 quote `reports/scorer_power.md` §3: "vowel-dropped English 1.000 at N = 10^6, 0.790 at 2^32". Those
   are rigid-exact plants against the RIGID bars (−6.1625 / −5.7788), not this lane's decoder and bars.
   Measured at this lane's decoder (`beam-skip`, anti-repeat plants, true key) and bars, 200 held-out
   windows per register, L = 240 (`lanes/R1-REDTEAM-OWN-CLAIMS/C2_register_beam_power.py` →
   `out_C2.json` `settling_register_beam_power`): vowel-dropped English **0.995** at the screening bar
   −6.0434 and **0.595 [0.526, 0.661]** at the decision bar −5.7284 (119/200); Latin **1.000** at both
   (200/200). A NULL from this lane therefore covers vowel-dropped-English keys only to about 0.60, not
   0.79. No run decision changes (the spec target is 0.5).
2. **Upstream overlap (corrects §0 Q2 and §8 "0 claim-bar hits").** Upstream R27-S2's `STATUS.json` reads
   `n_claim_bar_hits 0`, but the same file's `best_pmax` 7.6707 at seed 35563892 is above its S2 bar
   7.6342, and `run/HIT-CANDIDATE.json` flags that seed; upstream marks the contradiction unresolved
   (`handoff/PARKED-SWEEPS.md` §1). Re-screened here under this lane's pipeline on 2026-10-28
   (`runeforge score lanes/P3-MT19937-PY27-EXACT.yaml 35563892`): score **−6.4894**, below the screening
   bar −6.0434 and the decision bar −5.7284 (above claim bar: 0; above family-wise bar: 0). This does not
   resolve upstream's flag under their relation (keyskip1, max_skip 3, L = 120, beam width 64, panel max);
   it says the seed is not a crosser of this lane. Also: "narrower decoder" is half true (max_skip 3 vs 6,
   L 120 vs 240) and half not (their beam width 64 vs our 8; their 9-register panel vs our English).
3. **"no scored decode anywhere" (§8) is false as written.** Upstream R27-S1 scored all 2^32 seeds under the
   pair (skip-by-two) relation; R20-SG3 scored 2,458,000 seeds under keyskip1; R25 scored [3.0 M, 3.5 M) under
   keyskip2; jens-wedin seeds 0–20 k rigid. Intended and correct scope: the remaining 55.86 % has no scored
   decode under a single-skip ("exact") or anti-repeat relation.
4. **Interrupters (§8 not_covered).** Only the every-F variant fails the gate, and only for the typical key;
   partial-interrupt variants (interrupt_prob 0.1, 0.44) pass it (`reports/beam_decoder.md` §3). They are
   not covered by this lane, not excluded by the gate.
5. **Gate numbers (2026-10-27 addendum).** "C1 IoC 1.000, C2 0.00664, C2b 1.026, C3 15, C6 23" are LP2's own
   values (the band targets), not the keys'; every key fell inside each band (pass counts unchanged).
6. **Sign (2026-10-27 addendum).** The shuffle replicates' mean −6.4565 is 0.0015 **below** the staged fit's
   predicted 1,000-key block-max mean −6.455 (the conservative side), not above. It is a location check of a
   1,000-key maximum on shuffled runes (whose doublet rate is about 1/29, against 2 in this 240-rune
   window), not a check of the 2^32 tail.
7. **Page count (§2).** Pages 0–5 hold 1,470 runes (262 + 266 + 201 + 217 + 261 + 263), not 1,469. Unused
   downstream (the scored window is the first 240).
8. **Ledger wording.** The ledger row's hypothesis (from the template) says "the \"exact\" key-skip relation";
   this lane tests the anti-repeat multi-skip relation (§1), not upstream's keyskip1 "exact" relation, and the
   row lacked `external_ids`. Corrected by a ledger update row on 2026-10-28.

### Addendum 2026-10-28 (3) — superseded by `P3-MT19937-PY27-ANTIREPEAT` (nothing above edited)

A rehearsal of the TR-1 install in a disposable clone showed that this lane cannot run once the staged
calibrations are installed. Its frozen bar −5.7284 is 2.07e-5 below `threshold_for` −5.72837932 for the
same N, preset and window, and `runeforge lane` refuses a `family_wise_bar` below `threshold_for` (−1e-6
tolerance). The ledger refuses changing a frozen threshold, and this PREREG is not edited. The lane is
therefore re-registered, not amended, as `P3-MT19937-PY27-ANTIREPEAT`
(`lanes/P3-MT19937-PY27-ANTIREPEAT/PREREG.md`, frozen in `604aebb`). The new lane has the same key space,
decoder, window, control, budget and kill condition, with the bars rounded up: −5.728379 (decision) and
−6.043391 (screen). Ledger: this row is `superseded` with `superseded_by` [ANTIREPEAT]; the new row
carries `supersedes` [EXACT]. This lane's gate, control and null files stay in this folder as history.
The new lane re-ran its own gate, control and nulls and does not cite these. No sweep of this lane ran.
The RESULTS skeleton moved to the new lane. Its power counts are unchanged at the new bars (119/200 and
199/200 vowel-dropped English, per-plant scores in `lanes/R1-REDTEAM-OWN-CLAIMS/out_C2.json`).
