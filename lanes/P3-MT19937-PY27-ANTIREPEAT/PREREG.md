# Lane P3-MT19937-PY27-ANTIREPEAT — prng (Python 2.7 MT19937, random29, anti-repeat key skips) — PRE-REGISTRATION

_Frozen 2026-10-28, before this lane's gate, control, null or sweep runs in the repository, and before
any LP2 decode of this lane. Committed as `lane(P3-MT19937-PY27-ANTIREPEAT): PREREG frozen`; nothing below is edited afterwards
(dated addenda go at the end)._

**Supersedes `P3-MT19937-PY27-EXACT`** (pre-registered 2026-10-27 in `fabac07`, never run). Identical
hypothesis, key space, decoder, scorer, window, control, budget and kill condition; two changes only:
(1) the bars are the same staged fit's values rounded UP (family-wise −5.728379 for −5.72837932, claim
−6.043391 for −6.04339142) instead of −5.7284 / −6.0434: P3's −5.7284 sits 2.07e-5 BELOW
`threshold_for`, which `LaneSpec.runnable_problems` refuses (tolerance 1e-6), and the ledger refuses to
change a frozen threshold, so the lane could never run once TR-1 installs its calibration; the new bar is
2e-5 more conservative and leaves the expected false positives at 0.0101 (0.0100503, below the exact
bar's 0.0100503 in the seventh digit); (2) every correction red-team
lane `R1-REDTEAM-OWN-CLAIMS` upheld against P3's plan is built in (register power at this lane's own
decoder and bar, the upstream flag, scope wording). The lane id drops "EXACT", which named upstream's
keyskip1 relation this lane does not test.

**Disclosure.** Before this freeze, a rehearsal in a disposable clone (outside the repository, with the
six staged calibrations installed there) ran this spec's gate (GATE PASS 12/12) and control (20/20 at
rank 1, gap 1.075 nats with the calibration's β) and the sweep preflight (no refusal on the CPU backend;
on the GPU backend only "no CUDA device"), to check that the setup is runnable. Those numbers are of the
same instrument P3 already measured (`lanes/P3-MT19937-PY27-EXACT/`); none of them chose anything below
(the bars follow the frozen rule "threshold_for at N = 2^32 and 10^6, α = 0.01", rounded toward the
conservative side). No LP2 decode of this lane has run, apart from P3's one-seed re-screen of upstream's
flagged seed 35563892 (−6.4894, below both bars; P3 addendum 2026-10-28 (2)).

numbering: "LP2-0-57" · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`
(12,956 runes, LP2 pages 0–55) · lane spec `lanes/P3-MT19937-PY27-ANTIREPEAT.yaml` · category bounded

## What was read before this document was written

- Our ledger: `ledger/ledger.jsonl` (rows of `P3-MT19937-PY27-EXACT`, never-run, and `R1-REDTEAM-OWN-CLAIMS`,
  FOUND-ERROR), `PICKUP-HERE.md`, `lanes/P3-MT19937-PY27-EXACT/PREREG.md` with its addenda, and
  `lanes/R1-REDTEAM-OWN-CLAIMS/RESULTS.md`.
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

Trust anchor, run before writing (last line of each; code unchanged since except the harness's text):
`pytest -q -m "not slow"` → `1306 passed, 18 deselected in 135.13s (0:02:15)` (tree of `193b379`) ·
`runeforge canon --verify` → `pins verified` · `python -m runeforge.oracle --selftest` → `ORACLE SELF-TEST: PASS`

## 0. Aiming Test

- **Q1 What a hit looks like, and whether this instrument sees it:** one 32-bit seed `w` whose CPython 2.7
  `random.seed(w)` + `int(random.random()*29)` stream, read under `c = p + k (mod 29)` with the anti-repeat
  key skips (a key symbol that would repeat the previous canonical rune is dropped with probability
  1 − p_keep, p_keep 0.19), deciphers the first 240 runes of LP2 pages 0–5 to Cicada-register English:
  the `beam-skip` decode of that seed scores above −5.728379 under `lp-ngram3-heldout` at L = 240 and
  re-enciphers to the canonical runes rune for rune. The control in §3 plants exactly that and must
  recover it. That this instrument sees such a key is already measured on synthetic plants, not assumed:
  `reports/beam_decoder.md` §5 and `reports/scorer_power.md` §5 (`lp-ngram3-heldout` / `beam-skip` /
  anti-repeat at L = 240: 50/50 plants identified at rank 1 over 99 decoys, planted mean −3.95 against a
  wrong-key null mean −6.87; the rigid decoder identifies 0/50 of the same plants).
- **Q2 The measured fact that raises the prior:** LP2 0–55 holds 86 doublets against 447 expected for
  uniform runes (z ≈ −17), and of the forward models in this repo only the anti-repeat key-skip filter
  reproduces that deficit and passes the fingerprint gate — `GATE PASS` on 12/12 keys at
  `interrupt_prob: 0.0` (`reports/beam_decoder.md` §3; `python scripts/beam_power.py`, section gate;
  `lanes/P3-MT19937-PY27-ANTIREPEAT/gate.json` once this lane's gate runs). Whether only this filter passes is not fully
  measured (no filter-off gate row is committed; with the filter off ≈ 447 doublets are expected). A
  Python 2.7 script is the 2012 author's most ordinary tool, and upstream scored 44.14 % of this space
  under a different decoder (keyskip1, max_skip 3, L = 120, beam width 64, a 9-register panel) and parked
  with an unresolved above-bar flag (`data/raw/dukotah/liber-primus/handoff/PARKED-SWEEPS.md` §1); the
  remaining 55.86 % has no scored decode under a single-skip or anti-repeat relation. This is a bounded,
  enumerable space with a measured instrument; it is not a completeness ritual.
- **Q3 Is the space bounded?** 2^32 = 4,294,967,296 seeds; enumerable; this lane sweeps all of it
  (fraction 1.0 of the stated space; seeds 0 … 2^32 − 1 in order, resume by cursor).
- **Q4 The three conditionals:** key space `mt19937-py27` mode `random29`, 32-bit int seeds, key offset 0,
  `c = p + k (mod 29)` in the raw view · decoder `beam-skip` (width 8, max_skip 6, p_keep 0.19, no
  interrupters; `presets.DECODER_PARAMS`) · register English only, scorer `lp-ngram3-heldout` (order-3
  Witten-Bell on seven solved sections); Latin and vowel-dropped English are detected only to the
  power measured at THIS lane's decoder and bars (anti-repeat plants decoded with `beam-skip` and the true
  key, 200 held-out windows per register, L = 240; `lanes/R1-REDTEAM-OWN-CLAIMS/C2_register_beam_power.py`
  → `out_C2.json`): Latin 1.000 at both bars (200/200); vowel-dropped English 0.995 at the screening bar
  and **0.595 [0.526, 0.661]** at the decision bar (119/200; the Latin plants come from one text, Caesar,
  with 50 disjoint windows, so its interval is nominal).
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
| ciphertext view | raw; combine vigenere (`c = p + k`); LP2 pages 0, 1, 2, 3, 4, 5 (1,470 runes), scored window the first 240 |
| decoder | preset `lp-ngram3-heldout:beam-skip`: the beam decoder matching `filter_model: anti-repeat` with `interrupt_prob: 0.0`; beam width 8, max_skip 6, p_keep 0.19 as `presets.DECODER_PARAMS` pins them (`runeforge/beam.py` SHA-256 `4cd3d7ba59e6…`) |
| scorer register(s) | English, Cicada spelling: `lp-ngram3-heldout` (the solved sections minus A KOAN (1) and THE LOSS OF DIVINITY, fingerprint `a144706ac65a…`); calibration `runeforge/scoring/calib/presets/lp-ngram3-heldout__beam-skip__L240.json` once TR-1 installs the staged file `reports/calib-staging/lp-ngram3-heldout__beam-skip__L240.json` (SHA-256 `46a95f857fbf10ed9bdd164b56f39108cc362970d9b80460f4416e62989162ea`) unchanged |
| windows | screen L = 240; escalation 2× (480) → page → full 12,956-rune stream (HIT_PROTOCOL.md §3) |
| persisted per decode | IoC·N, min distinct symbols in a 32-rune window, order-2 entropy, zlib ratio, best non-English register (`runeforge/stats/decode.py`), for every survivor, crosser and chunk best |

## 3. Positive control (pre-specified; run by `runeforge control lanes/P3-MT19937-PY27-ANTIREPEAT.yaml`)

- Plant: a key drawn from the searched space in the real shape (seed inside the real generator
  `mt19937-py27`/`random29`, the first plant at the pre-named seed 3301 and 19 more at fresh seeds, at a
  random offset of the held-out solved section A KOAN (1), `solved:a-koan-1`, never in the scorer's
  training text) on synthetic Cicada-register English, enciphered through `pipeline.encrypt` with the
  anti-repeat filter (p_keep 0.19, no interrupters), through the same pipeline, decoder preset and window
  as the sweep. 20 plants, 999 decoys each, rng seed 3301 (`control:` in the lane spec).
- Pass bar (all of): rune-index recovery ≥ 0.90 on ≥ 90 % of the plants, at rank 1 · planted score above
  the bar −5.728379 (floor ≥ bar) · a deliberately wrong key below the noise ceiling; floor − ceiling ≥ 0.25
  nats with the ceiling extrapolated to N = 2^32 with the calibration's β (`control._beta`). The control
  that counts for the sweep is the one run after TR-1, with the installed β (the sweep checks it:
  `beam_control_problems`); a control run before TR-1 uses the per-plant β and is recorded but superseded.
- Fail → the lane is `INCONCLUSIVE (power)`. The bar is not lowered and the lane does not search;
  the instrument fix is a new instrument lane.

## 4. Null, threshold, expected false positives

- Null 1: size-matched shuffle of the real runes, n = 200 replicates (≥ 200), 1,000 keys per replicate,
  same decoder, scorer and window → `null_mean`, `null_sd`, `null_max` (`runeforge null`).
- Null 2: domain-separated SHA-256 stream (`sha256-ctr`, domain `runeforge/null2/P3-MT19937-PY27-ANTIREPEAT`
  as `runeforge null` derives it), n = 200 replicates: a key source outside every family this lane searches.
- Threshold: `python scripts/threshold_for.py --n 4294967296 --preset lp-ngram3-heldout:beam-skip --L 240`
  `--json` → `"bar": -5.72837931982132` (printed as −5.7284; expected null max −5.8799). The command
  refuses in the repository until TR-1 installs the staged record; in the rehearsal clone it printed exactly
  this. Arithmetic: μ_N = μ_b + β ln(N/1000) = −6.476749792 + 0.037657453 × ln(4,294,967.296) = −5.901609;
  bar = μ_N − β ln(−ln 0.99) = −5.728379 (staged record `mu_block` −6.476749792302121, `beta`
  0.037657453149229296, block 1,000; 10^6 beam-skip decodes of doublet-free ciphers under uniform keys,
  seed 3301, scale check max error 0.027). **Frozen family-wise bar −5.728379** (the value rounded up, so it
  is never below `threshold_for`). The installed record must reproduce −5.72837932 to 1e-6 or the lane
  does not run and a dated addendum records the delta. Screening bar `claim_bar` = the same arithmetic at
  N = 10^6: −6.04339142, frozen as **−6.043391** (survivors above it are logged with their stats, ≈ 43
  expected over the slice; nothing below the family-wise bar is a crosser). Small N does not apply.
- Expected false positives over the slice, N · P(clear) at the frozen bar: 0.0101 (0.01005030, α at the
  frozen bar 0.0099999; must be < 1).

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
`python -m runeforge.gpu.parity lanes/P3-MT19937-PY27-ANTIREPEAT.yaml --bench 1048576` has passed on the RTX
(both kernels, ≥ 10^4 seeds, `runs/P3-MT19937-PY27-ANTIREPEAT/parity.json`; `scripts/gpu_lane_setup.sh` runs every step): at the spec's 10^7 seeds/s the
slice takes ~7 min, at 10^6 ~72 min. On the CPU reference alone (~1,240 keys/s, `reports/beam_decoder.md`
§6) the slice is ~40 core-days and is not this lane's budget; a CPU-only run would be a dated addendum
naming its slice and fraction before it starts.

## 8. Scope, declared now

- not_covered: seeds ≥ 2^32 (the 64-bit two-word `init_by_array` image of string seeds, `seed_bits: 64`:
  2^64 − 2^32 seeds, 0 swept); the other three 2.7 reducers (`grb5_mod`, `grb5_rej`, `shuffle29`: 3 × 2^32
  seeds, 0 swept here; upstream R21-L3 and R26-A swept prior-dense slices of them, ≤ 0.007 % each); key
  offsets ≠ 0; the ciphertext views atbash, chain-increment and first-difference and the combines
  variant-beaufort and beaufort (0 of 11 other view × combine cells); F-interrupters (`interrupt_prob` 0:
  the every-F variant fails the fingerprint gate on 12/12 keys for the typical key, and partial-interrupt
  variants (0.1, 0.44) pass it, `reports/beam_decoder.md` §3; none of them is searched here); skips of more than 6
  key symbols at one rune (max_skip 6; probability ≈ 1e-11 per rune under a uniform key); the pair /
  skip-by-two relation (upstream R27-S1: all 2^32 seeds, NULL, under their decoder); pages other than
  0–5 as the screen (a true key decodes the whole stream, which the escalation checks); non-English
  plaintext beyond the measured power above (vowel-dropped English: about 40 % of such keys would be
  missed at the decision bar). Overlap, declared: 44.14 % of this slice (seeds in six upstream worker bands,
  1,895,728,884 seeds) was scored by upstream R27-S2 under the keyskip1 beam (max_skip 3, L = 120, beam width
  64, their 9-register panel-max bar 7.6342); their `STATUS.json` reads `n_claim_bar_hits 0` but holds an
  above-bar `best_pmax` 7.6707 at seed 35563892, flagged in `run/HIT-CANDIDATE.json` and unresolved upstream
  (that seed scores −6.4894 under this lane's pipeline, below both bars). This lane's decoder, scorer, window
  and bar differ, so it is a second instrument over those seeds, not a re-run, and it does not skip them.
  Other upstream scoring of this seed space: R27-S1 all 2^32 seeds under the pair relation (NULL), R20-SG3
  2,458,000 seeds under keyskip1, R25 [3.0 M, 3.5 M) under keyskip2, jens-wedin seeds 0–20 k rigid; the
  remaining 55.86 % has no scored decode under a single-skip or anti-repeat relation.
- Conditionals: key space `mt19937-py27` random29, 32-bit int seeds, offset 0, raw view, `c = p + k` ·
  decoder `beam-skip` (width 8, max_skip 6, p_keep 0.19, no interrupters) · register English only
  (`lp-ngram3-heldout`, Cicada spelling; at this lane's decoder and decision bar: Latin 1.000,
  vowel-dropped English 0.595 [0.526, 0.661]; `lanes/R1-REDTEAM-OWN-CLAIMS/out_C2.json`).
- reopens_if: TR-1 installs a record whose bar differs from −5.72837932 by more than 1e-6 (re-freeze
  before any run); the GPU parity record fails or is absent (no sweep); the control fails
  (`INCONCLUSIVE (power)`: instrument lane first); a later scorer (`kn4-cicada:beam-skip`, once its
  calibration is installed, TR-7) has materially higher power at L = 240 on this family's plants
  (`reports/scorer_power.md` §5: 50/50 for both today); a canonical-rune transcription change
  (canon SHA-256 moves); evidence that the author's interpreter was not CPython 2.7 (the `random29`
  reducer identity holds for `randrange`, `randint` and `choice` in 2.7 only).
- external_ids: Dukotah R27-CPORT-MT32-FULLSWEEP (S2, `handoff/PARKED-SWEEPS.md` §1; S1 complete),
  R25-COMPUTE-TAIL-CHUNK1, R20-SG3-PY27-RANDOM29, R21-L3-PY27-REDUCERS, R19-G3,
  R26-A-GEN-SWEEP-FIRST-FIRE, upstream tasking ref R27-S2 (`lanes/P3-MT19937-PY27-ANTIREPEAT.yaml`
  `params.upstream_ledger_ref`); jens-wedin `attack_prng.py` (REPORT.md:468). Supersedes our
  `P3-MT19937-PY27-EXACT`.

## Addenda

<!-- Dated, appended after the freeze. Never edit the sections above. -->

### Addendum 2026-10-28 — corrections from the setup-script review (nothing above edited; no bar or condition changed)

1. **Q5 check point (§0 Q5).** The sweep evaluates `kill_condition` once, at the first chunk boundary at
   or past `at_fraction` (`runeforge/runner/sweep.py` `_check_q5`, called after each chunk). With
   `chunk_size` 16,777,216 that is cursor 436,207,616 (fraction 0.1015625), not seed 429,496,730. The
   rate it compares is that chunk's own rate, not a cumulative one. The condition is unchanged
   (600,000 seeds/s, 10 crossers). RESULTS.md cites the `chunk` row with `hi` 436,207,616 in sweep.jsonl,
   and `kill_detail` in checkpoint.json if the kill fired.
2. **Expected false positives (header and §4).** At the frozen bar −5.728379, N · P(clear) = 0.01005025
   (α 0.00999992). At the exact bar −5.72837932 it is −ln 0.99 = 0.01005034. The 0.01005030 written
   above is `threshold_for`'s float print, which is the same for both bars, so the header's seventh-digit
   comparison compares two equal prints. 0.0101, α 0.0099999 and "< 1" stand.
3. **The §4 run condition is enforced.** The condition is that the installed record reproduces −5.72837932
   to 1e-6. `runeforge lane` alone refuses only a frozen bar below `threshold_for`. Since 2026-10-28,
   `scripts/gpu_lane_setup.sh` step 3 also writes `lanes/P3-MT19937-PY27-ANTIREPEAT/threshold_after_TR1.json`
   and stops the lane unless 0 ≤ frozen − computed ≤ 1e-6. This was rehearsed in a disposable clone with
   a re-staged fit (μ_b −6.49): bar −5.74163, gap 0.0133, stopped.
4. **Lane spec wording.** At the freeze, the lane spec's `hypothesis` field carried the template's "exact"
   key-skip wording. It was replaced by §1's text on 2026-10-28, with a ledger update row carrying the same
   note. The field is not in `lane_pipeline_sha256`, so the gate and control bindings are unchanged
   (pipeline SHA-256 `c296c437df68…` before and after).
