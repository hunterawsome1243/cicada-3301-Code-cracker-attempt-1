# Lane R1-REDTEAM-OWN-CLAIMS — red-team of this project's own claims — RESULTS

**Verdict: FOUND-ERROR — every re-derived instrument number reproduces (A1, B1, B2 within their rules; A2's model to 1.1e-16 and its Latin power), but three load-bearing claims overreached in ways that change what a reader trusts: the P3 lane quoted a vowel-dropped register power of 0.790 that belongs to another decoder and bar (its own is 0.595 [0.526, 0.661]), and PICKUP-HERE and the P3 PREREG called upstream's S2 overlap "0 claim-bar hits" while upstream's own files hold an unresolved above-bar flag (seed 35563892; re-screened here at −6.4894, below both P3 bars). No lane verdict flips; all upheld items are corrected in this session.**

numbering: "LP2-0-57" · pre-registered in [`PREREG.md`](PREREG.md) (frozen in `c757d32`) ·
no lane spec (a red-team lane searches no key space) · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`
· audited state git `fbe43e7` · corrections in `ea91aab`

## 0. Headline numbers

| quantity | value |
|---|---|
| sub-attacks run | 5 of 5 (A1, A2, B1, B2, C); none `not checked` |
| re-derivations reproduced by their PREREG rule | A1 yes (8/8 targets) · A2 not by the orchestrator's first reading, yes by its own rule (distributions 1.1e-16, Latin 1.000; vowel-dropped and the kn4 bars refuted 3/3 as a seed draw outside A2's rule, §3) · B1 yes (7/7) · B2 yes (all to 1e-4; one sign word wrong) |
| claim-audit rows | 91 (C1 34, C2 57): 50 no overreach, 38 minor, 3 decision |
| items sent to refuters (3 each) | 44 (3 A2 non-reproductions, 41 audit rows) → 25 upheld (3 decision, 22 minor), 19 refuted |
| decision-severity findings upheld | 3 (two on the P3 register conditional, one on the upstream overlap) |
| lane verdicts changed | 0 (P3 has not run; its bar −5.7284 is unchanged) |

## 1. Why this lane

Category redteam (round split before this lane I/B/R/C ≈ all instrument / 1 bounded lane pre-registered,
not run / 0 % / 0 %). Q2 fact: every headline number of the last three deliverables was produced and
checked by the code that produced it, and the power table contradicted a spec expectation (Latin power
1.000 where `docs/liber-primus-solver-spec.md` §3.3 expected ≈ 0; `reports/scorer_power.md` lines 375–382).
A surprising result from one code path is the first thing to re-derive, and a wrong conditional is
cheapest to find before a sweep cites it.

## 2. Instrument audited before the sweep

Trust anchor, run first (tree of `193b379`, code unchanged at `fbe43e7`):

```
pytest -q -m "not slow"                -> 1306 passed, 18 deselected in 135.13s (0:02:15)
runeforge canon --verify               -> pins verified
python -m runeforge.oracle --selftest  -> ORACLE SELF-TEST: PASS
```

Independence (PREREG §2): A1, A2 and B1 were written by agents given the PREREG and the documents, not the
implementation; they imported only `runeforge.gematria` / data loaders and opened the package only after
their numbers were on disk, for the cross-checks the PREREG names. A1: own order-3 Witten-Bell; per-position
log2-probabilities agree with `lp-ngram3-heldout` to 9.3e-7 (float32 tables) over 1,000 windows. A2: own
interpolated modified Kneser-Ney order 4 from `docs/kn-scorer-design.md` §2.3; conditional distributions
agree with `kn4-cicada` to 1.1e-16 on 1,000 histories. B1: own CPython 2.7 `random29` (seed 3301 vector
matches the pinned 2.7.3 vector), own anti-repeat forward model (0/20 cipher mismatches against the
package's on the same rng), own beam decoder (same scores as `beam.decode_batch` to 1e-8 on its ciphers).

## 3. Result vs null vs bar

Re-derivations (`lanes/R1-REDTEAM-OWN-CLAIMS/out_<id>.json`):

| target (file:line at `fbe43e7`) | reported | re-derived | rule | outcome |
|---|---|---|---|---|
| `reports/scorer_power.md`:93 lp-ngram3-heldout L240 bar@10^6 / @2^32 | −6.1625 / −5.7788 | −6.1601 / −5.7749 (100,000 draws) | within 0.05 | reproduced; six 100k seeds give sd 0.065 / 0.114, so the rule is tighter than the reduced fit's own seed noise |
| `reports/scorer_power.md`:375 Latin L240 power | 1.000 / 1.000 | 1.000 / 1.000 | widened Wilson | reproduced |
| `reports/scorer_power.md`:453 vowel-dropped L240 power | 1.000 / 0.790 | 1.000 / 0.800 | widened Wilson | reproduced (0.960 at a 10^6-draw bar: the reduced 2^32 bar sets this number) |
| `reports/scorer_power.md`:219, 609 English / held-out sections L240 | 1.000 / 1.000 | 1.000 / 1.000 | widened Wilson | reproduced |
| `reports/scorer_power.md`:379 kn4-cicada Latin L240 | 1.000 | 1.000 (2,000/2,000) | widened Wilson | reproduced |
| `reports/scorer_power.md`:457 kn4-cicada vowel-dropped L240 @10^6 | 0.550 | 0.375 at A2's 10^6-draw bar −6.0017; 0.5545 at the report's bar | widened Wilson | refuted 3/3 as not an error: A2 replays seed 3301 to the record's μ_b, β and bar to 2e-9; the report's bar is a 3rd-percentile draw of its own stated method (200 replicates: mean −6.0145, sd 0.0335); disclosed in the regenerated report's not_covered |
| `reports/scorer_power.md`:97 kn4-cicada bars | −6.0705 / −5.8605 | −6.0017 / −5.7354 (10^6 draws) | (A1's rule; not A2's) | refuted 3/3: outside A2's PREREG rule, and no kn bar is installed or frozen anywhere |
| P3 control (`control-4c65a7978362.json`) | 20/20, median −3.8207, floor −4.3063 | 20/20 (199 decoys), median −3.7535, floor −4.1556; 20/20 at 999 decoys and at widths 4, 16; 200/200 at 200 plants | ≥ 18/20, median within 0.15 | reproduced |
| P3 PREREG §4 bars | −5.7284 / −6.0434 / E[fp] 0.0101 | −5.728379 / −6.043391 / 0.010050 | 1e-4 | reproduced |
| P3 PREREG addendum: shuffle mean vs fit | "−6.4565, 0.0015 above −6.455" | −6.456534 vs −6.455013: 0.0015 **below** | 1e-3 | numbers reproduced, direction word wrong (upheld minor) |

Claim audit — every upheld row (severity **decision** first), and the decision rows' evidence:

| Claim (file:line) | Actual evidence | Overreach | Live lane it hides | Cheapest settling test |
|---|---|---|---|---|
| `lanes/P3-MT19937-PY27-EXACT/PREREG.md:169` "Latin power 1.000 and vowel-dropped 0.790 at the 2^32 bar on rigid-exact plants, `reports/scorer_power.md` §3" | 0.790 = 158/200 at the RIGID 2^32 bar −5.7788. At the lane's bar −5.7284 under beam-skip with anti-repeat plants: 119/200 = **0.595 [0.526, 0.661]**; rigid-exact at −5.7284: 0.670; Latin 200/200 (`C2_register_beam_power.py` → `out_C2.json`) | quotes another decoder's and another bar's power as this lane's conditional | a P3 NULL would over-cover vowel-dropped keys (≈ 40 % uncovered, not 21 %) | done; P3 PREREG addendum 2026-10-28 (2) item 1 (decision, upheld 2/3) |
| `lanes/P3-MT19937-PY27-EXACT/PREREG.md:57-59` Q4 "vowel-dropped English 1.000 at N = 10^6, 0.790 at 2^32" | same as above; at the lane's screening bar −6.0434: 0.995 | presents rigid-bar numbers as the lane's own conditional | same | same (decision, upheld 3/3) |
| `PICKUP-HERE.md:17` "Dukotah R27-S2 scored 44.14 % of the same seeds under a narrower decoder (keyskip1, max_skip 3, L = 120) with 0 claim-bar hits" | upstream `STATUS.json` `n_claim_bar_hits 0`, but the same file's `best_pmax` 7.6707 at seed 35563892 > S2 bar 7.6342 and `run/HIT-CANDIDATE.json` flags it; `handoff/PARKED-SWEEPS.md` §1 calls it unresolved; their beam width is 64 (ours 8), their register a 9-panel max | a clean partial null presented where upstream holds an open flag; "narrower" half true | a CPU-only slice that skipped the 44.14 % band as measured ground | `runeforge score lanes/P3-MT19937-PY27-EXACT.yaml 35563892` → −6.4894, below both bars; disclosed in PICKUP-HERE, P3 PREREG addendum item 2, RESULTS skeleton, lane YAML (decision, upheld 2/3) |
| `lanes/P3-MT19937-PY27-EXACT/PREREG.md:162-166` "the remaining 55.86 % has no scored decode anywhere" | upstream R27-S1 scored all 2^32 seeds (pair relation); R20-SG3, R25, jens-wedin scored slices | false as written; intended scope is "under a single-skip or anti-repeat relation" | — | addendum item 3 |
| `lanes/P3-MT19937-PY27-EXACT/PREREG.md:156-158` "an interrupt-bearing variant of this family is excluded by the gate" | only interrupt_prob 1.0 fails (C1 12/12); 0.1 and 0.44 pass (`reports/beam_decoder.md` §3) | partial-interrupt variants are not excluded, only not covered | partial-interrupter lanes | addendum item 4 |
| `lanes/P3-MT19937-PY27-EXACT/PREREG.md:191-194` "C1 IoC 1.000, C2 doublet rate 0.00664, … on 12/12 keys" | the values are LP2's band targets, not the keys' | wording | — | addendum item 5 |
| `lanes/P3-MT19937-PY27-EXACT/PREREG.md:203-206` "−6.4565 (0.0015 above, within 0.04 β), so the staged fit describes this window's null as measured on the real runes" | −0.0015 (below); a block-max location check on shuffles | sign and scope | — | addendum item 6 |
| `lanes/P3-MT19937-PY27-EXACT/PREREG.md:80` "LP2 pages 0, 1, 2, 3, 4, 5 (1,469 runes)" | 1,470 | off by one, unused downstream | — | addendum item 7 |
| `ledger/ledger.jsonl:1` P3 hypothesis "combined under the \"exact\" key-skip relation" | the lane tests the anti-repeat multi-skip relation; `external_ids` empty | names an upstream relation the lane does not test | ledger queries for "exact" coverage | `runeforge ledger update` row 2026-10-28 |
| `PICKUP-HERE.md:15` "Latin plaintext under the English scorers also has power 1.000 at both bars at every L" | at L = 100 the 2^32 power is 0.55–0.975 for three English scorers | "every L" | — | reworded |
| `PICKUP-HERE.md:15` "at L = 100 every scorer is below 0.35, at L ≥ 500 every English scorer is ≥ 0.93" | matched scorer 1.000; ≥ 0.925 only at 10^6; 0.42–0.64 at 2^32 for KN Cicada at L = 500; wb 0.04 | bar and scorer scope | — | reworded |
| `PICKUP-HERE.md:15` "The beam cells reproduce `reports/beam_decoder.md` (kn4-cicada under beam-skip …)" | `reports/beam_decoder.md` never measured kn4-cicada | attribution | — | reworded |
| `PICKUP-HERE.md:15` "`tests/test_kn.py`, 78 tests green" | 87 (89 collected) | count | — | corrected |
| `PICKUP-HERE.md:19` "No lane has a ledger row yet and `queue.json` is empty" | both hold the P3 entry | stale | — | deleted |
| `PICKUP-HERE.md:23` "the template lane … can be pre-registered" | pre-registered in `fabac07`; power run done | stale next steps | — | rewritten |
| `PICKUP-HERE.md:11` "its PTX compiles for sm_75/86/89" | no committed test or artifact; simulator covers 70 keys × 3 | unchecked claim stated as fact | — | stated as a scratch-environment check |
| `PICKUP-HERE.md:13` "its PTX compiles for sm_75/86/89" | same | same | — | same |
| `PICKUP-HERE.md:7` "found ~60 defects; every upheld one is fixed with a test … smoke-tested … with a stub `claude`" | review commits exist; no findings list or stub script committed | process claims without artifacts | — | stated as uncommitted |
| `README.md:33` "Corpus presets train on the first 90 % of words and plant on the held-out tail." | lane controls cannot plant on the tail until TR-9 | scope | — | reworded |
| `README.md:195` "shuffled surrogates give maxima of 5.5–6.5" | 12 re-run shuffles: 5.09–6.91; nothing committed | range | — | reworded |
| `README.md:197` "the scan's power falls off below about 1,000 aligned runes" | one plant at 1,100 | extrapolation | — | reworded |
| `reports/beam_decoder.md:213-217` "these bars are conservative by at least that much" | only means compared | mean shift carried to the tail | — | scoped to the mean |
| `reports/scorer_power.md:202` "(the 1,533-rune heldout-solved-sections register at L >= 263 …)" | overlap at every L (14 disjoint at L = 100, 6 at 240) | understated | — | harness text fixed; report regenerated |
| `reports/scorer_power.md:971` "1.000 [0.981, 1.000] at the bar@10^6" | 50 disjoint windows of one Caesar text; all-success bound 0.929 | nominal interval without caveat | — | caveat added |

Refuted (19, listed in `out_C1.json` / `out_C2.json` with the votes in the workflow journal) include the
`README.md:3` "GPU-ready" and `README.md:36` "measured power envelope" rows, the P3 PREREG §0 beam-power and
Q2 gate rows, and the `reports/scorer_power.md` §9 single-text and reopens_if rows.

Q5 kill condition (A1 without an independent scorer at 2 agent-hours): checked when A1 returned; did not
fire (A1 finished its re-derivation in 8.2 s of compute).

## 4. Survivors reported, not dropped

Not a search lane: no key space, no survivors, no crossers. The one LP2 decode this lane caused is the
re-screen of upstream's flagged seed 35563892 under the P3 lane: −6.4894 (below −6.0434 and −5.7284;
`runeforge score lanes/P3-MT19937-PY27-EXACT.yaml 35563892`). Oracle: not run (no crosser).

## 5. Coverage — read this, not the verdict

- Measured: the five sub-attacks of PREREG §2 at the stated cells (lp-ngram3-heldout and kn4-cicada at
  L = 240; the P3 control and bars) and 91 sentences of README.md, PICKUP-HERE.md,
  `reports/beam_decoder.md` §0–§7, `reports/scorer_power.md` §1/§9 and the P3 PREREG §0/§8 and addenda.
- not_covered: the GPU kernels (no device); KN orders 5–8; beam cells other than lp-ngram3-heldout /
  beam-skip / anti-repeat at L = 240; every other `reports/scorer_power.md` cell; the corpora themselves;
  upstream numbers (quoted, not re-derived, except the S2 flag, which was read from upstream's files);
  every sentence outside the listed sections; the frozen toolbox code paths.
- Conditionals: key space none (this lane searches none) · decoder none · register none; it audits the
  instruments' stated conditionals and corrected one (P3's register power).

## 6. What would change this verdict

- reopens_if: a re-derivation is shown to have used the implementation it checks; the reports are
  regenerated at a new scorer fingerprint; a new load-bearing sentence is added to the audited documents;
  the `--full` scorer run moves a bar or a power outside the ranges quoted here.

Independent verification (verify-lane subagent, fresh context, own code, no lane imports): the audit row
counts (91; 50 / 38 / 3), the P3 bars (−5.728379, −6.043391, E[fp] 0.010050), the null-consistency sign
(−0.001521, below), the Wilson intervals, the P3 control (20/20, median −3.820666, floor −4.306334) and the
re-score of seed 35563892 (−6.4894315019) all reproduced; nothing changes the verdict. It could not recount
119/200 and 200/200 because `out_C2.json` then held only aggregates: `C2_register_beam_power.py` now also
writes the per-plant scores, ranks and recoveries, and its re-run reproduced every aggregate identically
(recount above −5.7284: 119/200 vowel-dropped, 200/200 Latin, 200/200 held-out sections).

## 7. Artifacts and reproduce

- `lanes/R1-REDTEAM-OWN-CLAIMS/out_{A1,A2,B1,B2,C1,C2}.json` and the scripts beside them; ledger row
  `R1-REDTEAM-OWN-CLAIMS` in `ledger/ledger.jsonl`; corrections in `ea91aab`; git `fbe43e7` audited.

```bash
python lanes/R1-REDTEAM-OWN-CLAIMS/A1_rederive.py --draws 100000 --extra-draws 1000000 --seed 330120261028 --plants 200
python lanes/R1-REDTEAM-OWN-CLAIMS/A2_kn4_independent.py
python lanes/R1-REDTEAM-OWN-CLAIMS/B1_rederive.py --plants 20 --decoys 199 --width 8 --max-skip 6 --p-keep 0.19 --L 240 --seed 330120261028 --workers 4
python lanes/R1-REDTEAM-OWN-CLAIMS/B2_handcheck.py
python lanes/R1-REDTEAM-OWN-CLAIMS/C2_register_beam_power.py
runeforge score lanes/P3-MT19937-PY27-EXACT.yaml 35563892
python scripts/check_results.py lanes/R1-REDTEAM-OWN-CLAIMS/RESULTS.md
```
