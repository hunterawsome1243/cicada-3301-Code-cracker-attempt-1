---
paths:
  - "lanes/**"
---

# Lane files: PREREG.md and RESULTS.md

A lane is `lanes/<id>.yaml` (the machine spec, `runeforge lane lanes/<id>.yaml` validates it) plus
`lanes/<id>/PREREG.md` and `lanes/<id>/RESULTS.md`. Procedure: SESSION_PROMPT.md §C2–§C5.
Style follows Dukotah's round-18 and round-24 lanes (`data/raw/dukotah/liber-primus/analysis/
round18/L7-redteam/`, `round24/C2-skip-by-two/`): numbers in tables, every number next to the
command that regenerates it, scope stated before anyone can misread it.

- **PREREG.md is written and committed (`lane(<id>): PREREG frozen`) before any measurement in the
  lane**, gate included. After that it is never edited; changes are dated addenda at the end, and
  a threshold is never changed after a result has been seen.
- **RESULTS.md is not finished until `python scripts/check_results.py lanes/<id>/RESULTS.md`
  prints PASS** and the verify-lane subagent has re-derived its headline numbers.
- Fill the `<placeholders>`; keep the headings (the checker matches each by its number plus a
  keyword). HTML comments are guidance: the checker ignores them, so nothing inside one counts.
- Vocabulary: the `Verdict:` line starts with `NULL`, `CANDIDATE`, `INCONCLUSIVE (power)`,
  `EXCLUDED (gate)`, or for red-team lanes `FOUND-ERROR` / `NO-ERROR-FOUND`. Never write the
  overclaiming words CLAUDE.md lists (the checker fails the file on them); write coverage,
  not_covered and reopens_if. "solved" is allowed only in "solved page(s)/section(s)".
- Scores: negative, higher = more English. Bars come from `scripts/threshold_for.py` at the lane's
  true N, preset and window, never from Dukotah's −5.5 / −4.6 / −12.06.

## PREREG.md template

<!-- PREREG-TEMPLATE-BEGIN -->
````markdown
# Lane <lane_id> — <family> — PRE-REGISTRATION

_Frozen <date>, written before any measurement in this lane. No decode, plant, null or sweep of
this lane's own has been executed at the time of writing. Committed as
`lane(<lane_id>): PREREG frozen` before the gate runs; nothing below is edited afterwards (dated
addenda go at the end)._

numbering: "LP2-0-57" · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`
(12,956 runes, LP2 pages 0–55) · lane spec `lanes/<lane_id>.yaml` · category <category>

## What was read before this document was written

<file paths: our ledger rows, Dukotah LEDGER.json ids (coverage / not_covered), jens-wedin
BACKLOG.md, murphy research notes, and the code this lane will run>

Trust anchor, run before writing (last line of each):
`pytest -q -m "not slow"` → <pytest_line> · `runeforge canon --verify` → <canon_line> ·
`python -m runeforge.oracle --selftest` → <oracle_line>

## 0. Aiming Test

- **Q1 What a hit looks like, and whether this instrument sees it:** <hit_shape>. The control in
  §3 plants exactly that and must recover it.
- **Q2 The measured fact that raises the prior:** <q2_fact> (`<q2_path>`). <!-- No fact with a file
  path -> label the lane "completeness ritual" and queue it last. -->
- **Q3 Is the space bounded?** <space_size>; <enumerable | samplable, fraction swept | unbounded>.
- **Q4 The three conditionals:** key space <cond_key_space> · decoder <cond_decoder> ·
  register <cond_register>.
- **Q5 Kill condition at 10 % of budget:** <kill_condition>, checked at <kill_check_point>. The
  check and its outcome (fired or did not fire) go into RESULTS.md either way.

## 1. Hypothesis

<one falsifiable sentence: cipher, key model, the pages it applies to>

## 2. Key space, ciphertext view, decoder, register

| item | value |
|---|---|
| key space | <generator / family and parameters>; size <space_size>; this lane sweeps <slice> (<fraction> of it) |
| true N (trials, for the bar) | <n_trials> |
| ciphertext view | <raw / Atbash / chain / first-difference>; LP2 pages <pages> (<n_runes> runes) |
| decoder | rigid screen → beam adjudication; preset `<preset>`; beam width <beam_width>; max_skip <max_skip> |
| scorer register(s) | <register>; calibration `runeforge/scoring/calib/<calib_file>` |
| windows | screen L = <window>; escalation 2× → page → full 12,956-rune stream |
| persisted per decode | IoC·N, min distinct symbols in a 32-rune window, order-2 entropy, zlib ratio, best non-English register |

## 3. Positive control (pre-specified; run by `runeforge control lanes/<lane_id>.yaml`)

- Plant: a key drawn from the searched space in the real shape (<plant_shape>: seed inside the real
  generator, at a random offset) on synthetic Cicada-register English, through the same pipeline,
  decoder preset and window as the sweep. ≥ 20 plants, fresh seeds.
- Pass bar (all of): rune-index recovery ≥ 0.90 on ≥ 90 % of the plants, at rank 1 · planted
  score above the bar <bar> · a deliberately wrong key below the noise ceiling.
- Fail → the lane is `INCONCLUSIVE (power)`. The bar is not lowered and the lane does not search;
  the instrument fix is a new instrument lane.

## 4. Null, threshold, expected false positives

- Null 1: size-matched shuffle of the real runes, n = <null_n> (≥ 200), same decoder, scorer and
  trial count → `null_mean`, `null_sd`, `null_max`.
- Null 2: domain-separated SHA-256 stream (`<null2_source>`, domain `<null2_domain>`), n =
  <null2_n>: a key source outside every family this lane searches.
- Threshold: `python scripts/threshold_for.py --n <n_trials> --preset <preset> --L <window>` →
  <threshold_line>. Small N: `max(floor, null_max + 0.5)`.
- Expected false positives over the slice, N · P(clear) = <expected_fp> (must be < 1).

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

Wall-clock <wall_clock> · decodes <decode_budget> · GPU-hours <gpu_hours> (> 2 needs Hunter's
approval in `queue.json`).

## 8. Scope, declared now

- not_covered: <not_covered, with numbers> <!-- declared before the run so a negative cannot widen
  its own scope -->
- Conditionals: key space <cond_key_space> · decoder <cond_decoder> · register <cond_register>.
- reopens_if: <reopens_if>
- external_ids: <Dukotah / jens-wedin / Leo-Y-Zhang / murphy ids this lane maps to>

## Addenda

<!-- Dated, appended after the freeze. Never edit the sections above. -->
````
<!-- PREREG-TEMPLATE-END -->

## RESULTS.md template

What `check_results.py` enforces, by verdict:

| verdict | must state |
|---|---|
| every verdict | the eight sections; `numbering: "LP2-0-57"`; §5 not_covered + key space, decoder, register conditionals; §6 reopens_if; §7 a `python …` / `runeforge …` command in backticks that regenerates a number (the two gate scripts do not count) |
| `NULL`, `CANDIDATE`, `INCONCLUSIVE (power)` | §2 the gate result (`GATE PASS` / `GATE FAIL`) and "recovered k/n … at rank 1"; §3 every null line with its own n ≥ 20, mean, sd, max values, a z, the bar |
| `NULL`, `CANDIDATE` | the control at its pass bar (≥ 90 % of ≥ 20 plants); the Q5 kill-condition check and whether it fired ("fired" / "did not fire"; "not checked" fails) |
| `NULL` | every "best real X vs floor Y vs ceiling Z" agrees, with X < Y (unless a §4 survivor row says NOISE-CROSSER) and (Y − Z)·ln 2 ≥ 0.25 nats (scores are log2 per rune) |
| `CANDIDATE` | an oracle line with its result: `→ PASS` or `→ FAIL` ("not run" fails) |
| `EXCLUDED (gate)` | a `GATE FAIL` line naming the failed constraints and "k/n keys" (most of ≥ 12); §5 says it excludes the typical key, not the family |
| `FOUND-ERROR`, `NO-ERROR-FOUND` | the claim-audit table, each Claim cell citing `file:line` |

<!-- RESULTS-TEMPLATE-BEGIN -->
````markdown
# Lane <lane_id> — <family> — RESULTS

**Verdict: <verdict> — <verdict_summary>.**

numbering: "LP2-0-57" · pre-registered in [`PREREG.md`](PREREG.md) (frozen in <prereg_commit>) ·
lane spec `lanes/<lane_id>.yaml` · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`

<!-- Verdict vocabulary: NULL | CANDIDATE | INCONCLUSIVE (power) | EXCLUDED (gate) | FOUND-ERROR |
     NO-ERROR-FOUND. The summary carries the key numbers; for NULL it is the verdict arithmetic. -->

## 0. Headline numbers

| quantity | value |
|---|---|
| trials (true N) | <n_trials> |
| control | recovered <k>/<n> plants at rank 1 |
| null (shuffle) | n = <null_n>, mean <null_mean>, sd <null_sd>, max <null_max> |
| bar | <bar> (`threshold_for`, fixed in advance) |
| best real | <best_real> (z = <z>) |
| verdict arithmetic | best real <best_real> vs floor <floor> vs ceiling <ceiling> |
| crossers | <n_crossers> |

## 1. Why this lane

Category <category> (round split before this lane I/B/R/C = <round_split>). Q2 fact: <q2_fact>
(`<q2_path>`). <why_new>

## 2. Instrument audited before the sweep

Trust anchor, run first:

```
pytest -q -m "not slow"                -> <pytest_line>
runeforge canon --verify               -> <canon_line>
python -m runeforge.oracle --selftest  -> <oracle_selftest_line>
```

- Gate (`runeforge gate lanes/<lane_id>.yaml`): <gate_line>
- Control (`runeforge control lanes/<lane_id>.yaml`): recovered <k>/<n> plants at rank 1; median
  rune-index recovery <median_recovery>, minimum <min_recovery>; planted score median
  <planted_score> vs bar <bar>; wrong key <wrong_key_score>.

<!-- EXCLUDED (gate): write the GATE FAIL line here ("GATE FAIL — <constraints> outside the LP2
     band for k/n keys") and say in §3 that control and null were not run. -->

## 3. Result vs null vs bar

- Null 1, size-matched shuffle of the real runes: n = <null_n>, mean <null_mean>, sd <null_sd>,
  max <null_max>.
- Null 2, domain-separated SHA-256 stream: n = <null2_n>, mean <null2_mean>, sd <null2_sd>,
  max <null2_max>.
- Threshold (fixed in advance): `python scripts/threshold_for.py --n <n_trials> --preset <preset>
  --L <window>` → bar <bar>; expected false positives over the slice <expected_fp>.
- Best real <best_real>, z = <z> against null 1.
- Verdict arithmetic: best real <best_real> vs floor <floor> vs ceiling <ceiling>
  (floor − ceiling = <separation>).
- Q5 kill condition (<kill_condition>): checked at <kill_check_point>; <kill_outcome>.

<!-- kill_outcome: "fired" or "did not fire" - both words are what the checker looks for.
     Red-team lanes (FOUND-ERROR / NO-ERROR-FOUND) replace the bullets above with the claim audit,
     one row per load-bearing sentence:
     | Claim (file:line) | Actual evidence | Overreach | Live lane it hides | Cheapest settling test |
     |---|---|---|---|---|
     The Claim cell quotes the audited text verbatim; it is the only place an overclaiming word may
     appear. -->

## 4. Survivors reported, not dropped

Top <top_k> by screen score; escalation per HIT_PROTOCOL.md §3, each z against a size-matched null
of that length.

| kid | head L=<window> | z | 2× | z | page | z | stream | z | outcome |
|---|---|---|---|---|---|---|---|---|---|
| <kid> | <s_head> | <z_head> | <s_2x> | <z_2x> | <s_page> | <z_page> | <s_stream> | <z_stream> | <outcome> |

Crossers above the bar: <n_crossers> (logs in `runs/<lane_id>/crossers/`). Oracle: <oracle_result>.

## 5. Coverage — read this, not the verdict

- Measured: <coverage> (<coverage_fraction> of the stated key space).
- not_covered: <not_covered>.
- Conditionals: key space <cond_key_space> · decoder <cond_decoder> · register <cond_register>.

## 6. What would change this verdict

- reopens_if: <reopens_if>.

## 7. Artifacts and reproduce

- `runs/<lane_id>/sweep.jsonl` (SHA-256 `<sweep_sha256>`), `runs/<lane_id>/control.json`,
  `runs/<lane_id>/null.json`; ledger row `<lane_id>` in `ledger/ledger.jsonl`; git <git_sha>.

```bash
runeforge control lanes/<lane_id>.yaml
runeforge sweep lanes/<lane_id>.yaml --detach
python scripts/check_results.py lanes/<lane_id>/RESULTS.md
```
````
<!-- RESULTS-TEMPLATE-END -->
