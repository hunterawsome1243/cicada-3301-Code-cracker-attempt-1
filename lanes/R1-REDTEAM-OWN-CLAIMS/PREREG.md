# Lane R1-REDTEAM-OWN-CLAIMS — red-team of this project's own claims — PRE-REGISTRATION

_Frozen 2026-10-28, written before any measurement in this lane. No re-derivation, plant, null or
audit of this lane's own has been executed at the time of writing. Committed as
`lane(R1-REDTEAM-OWN-CLAIMS): PREREG frozen` before any check runs; nothing below is edited afterwards
(dated addenda go at the end)._

numbering: "LP2-0-57" · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`
(12,956 runes, LP2 pages 0–55) · category redteam · no lane YAML (this lane searches no key space and
runs no sweep) · repository state audited: git `fbe43e7`

## What was read before this document was written

`CLAUDE.md` (the 20 % red-team budget; "re-derive a headline number with independently written code;
pair each load-bearing sentence with Claim (file:line) → Actual evidence → Overreach → Live lane it
hides → Cheapest settling test"); `SESSION_PROMPT.md` §C1; `.claude/rules/lanes.md`;
`scripts/check_results.py` (red-team verdicts need the claim-audit table, each Claim cell citing
`file:line`); upstream's red-team lane `data/raw/dukotah/liber-primus/analysis/round18/L7-redteam/PREREG.md`
(format); our ledger (`ledger/ledger.jsonl`: one row, `P3-MT19937-PY27-EXACT`, `never-run`); and the
documents whose claims are audited below.

Round split before this lane (rows by category, `ledger/ledger.jsonl` plus the committed instrument
work): instrument ~all, bounded 1 lane pre-registered and not run, red-team 0 %, closeout 0 %. Red-team is
the category furthest below its 20 % share, so it goes next.

Trust anchor, run before writing (last line of each, tree of `193b379`, unchanged in code since):
`pytest -q -m "not slow"` → `1306 passed, 18 deselected in 135.13s (0:02:15)` ·
`runeforge canon --verify` → `pins verified` · `python -m runeforge.oracle --selftest` → `ORACLE SELF-TEST: PASS`

## 0. Aiming Test

- **Q1 What a hit looks like:** a number or sentence this project publishes that an independent
  re-derivation does not reproduce, or a sentence that claims more than its cited evidence shows, and
  that would change what a reader does (run a lane, trust a negative, install a bar). The instrument is
  independently written code (it may load the canon, the gematria table, the built corpora and the
  committed evidence JSONs; it may NOT import `runeforge.scoring`, `runeforge.beam`, `runeforge.runner`,
  `runeforge.gpu` or `scripts/scorer_power.py`) and a sentence-by-sentence audit.
- **Q2 The measured fact that raises the prior:** every headline number of the last three deliverables
  was produced and checked by the same code family that produced it (`reports/scorer_power.md` was
  rendered by `scripts/scorer_power.py`, which imports the scorers it measures; the P3 control ran
  through `runeforge/runner/control.py` with the decoder it tests), and the power table contradicted a
  spec expectation ("Latin power ≈ 0", `docs/liber-primus-solver-spec.md` §3.3) — a surprising result
  from a single code path is the first thing to re-derive (`reports/scorer_power.md` lines 375–382).
- **Q3 Is the space bounded?** Yes: the claim list in §2 is finite (5 re-derivations, 5 documents).
- **Q4 The three conditionals:** this lane checks the instruments and the prose, not a key space; it
  inherits no key-space, decoder or register conditional and adds none.
- **Q5 Kill condition at 10 % of budget:** if the first re-derivation (A1) has not produced its
  independent scorer within 2 agent-hours, the lane stops that sub-attack and records it `not checked`
  rather than widening scope.

## 1. Hypothesis

At least one load-bearing number or sentence in `reports/scorer_power.md`, `reports/beam_decoder.md`,
`lanes/P3-MT19937-PY27-EXACT/PREREG.md`, `README.md` or `PICKUP-HERE.md` (at git `fbe43e7`) is wrong or
overreaches its evidence in a way that changes a decision.

## 2. Sub-attacks, fixed now

| id | target (file:line at `fbe43e7`) | independent re-derivation | reproduced if |
|---|---|---|---|
| A1 | `reports/scorer_power.md`:375, 453, 219, 609 — `lp-ngram3-heldout` at L = 240: power 1.000 on Latin, 1.000 at N = 10^6 / 0.790 at 2^32 on vowel-dropped English, 1.000 on general English and on the held-out solved sections; bar@10^6 −6.1625 and bar@2^32 −5.7788 (line 93) | own order-3 Witten-Bell interpolated model fitted from `data/canon/solved_sections.json` minus A KOAN (1) and THE LOSS OF DIVINITY (the definition in `runeforge/scoring/presets.py` docstrings, not its code); own Gumbel fit (method of moments on block maxima of 1,000) over ≥ 100,000 uniform strings of 240 runes; ≥ 200 plants per register from the built corpora's last 10 % of words (Latin, vowel-dropped English, general English) and from the two held-out sections | the model's per-position log2-probabilities agree with `runeforge` to 1e-5 on 1,000 random windows (a cross-check, run last, by loading the package only then) **and** every power above lies inside the report's Wilson 95 % interval widened by 0.05 on each side **and** both bars within 0.05 |
| A2 | `reports/scorer_power.md`:379, 457 — `kn4-cicada` at L = 240: Latin power 1.000, vowel-dropped power 0.550 at N = 10^6; `docs/kn-scorer-design.md` §2.3 (the KN definition) | own interpolated modified-Kneser-Ney order 4 from the design text (§2.3 discount rule and fallbacks, continuation counts, unseen-history rule) trained on `cicada-english` words [0, ⌊0.9 · 74,803⌋); same bar and plant method as A1 | conditional distributions agree with `presets.get("kn4-cicada").distribution` to 1e-9 on 1,000 histories (seen, unseen, prefix) **and** the two powers inside the widened intervals |
| B1 | `lanes/P3-MT19937-PY27-EXACT/PREREG.md` addendum 2026-10-27 and `control-4c65a7978362.json` — control 20/20 at rank 1, floor −4.3063, recovery ≥ 0.942 | own CPython 2.7 `random29` stream (`random.Random(seed)` words → `genrand_res53` → ×29, written from the C source semantics), own anti-repeat forward model (p_keep 0.19), own beam decoder over (key position, last-2 history) with the skip prior of `reports/beam_decoder.md` §1, scored by the A1 model; ≥ 20 plants at fresh seeds on A KOAN (1) at L = 240, 199 decoys each | ≥ 18/20 identified at rank 1 with recovery ≥ 0.90, and median planted score within 0.15 of the control's −3.8207 (beam widths and tie rules may differ, so scores need not match exactly) |
| B2 | `lanes/P3-MT19937-PY27-EXACT/PREREG.md` §4 — bar −5.7284 at N = 2^32 and −6.0434 at 10^6, expected false positives 0.0101, from the staged record | recompute from `reports/calib-staging/lp-ngram3-heldout__beam-skip__L240.json` `fit` by hand formula; and the claim "the lane's own shuffle replicates average −6.4565, 0.0015 above the fit's −6.455" from `lanes/P3-MT19937-PY27-EXACT/null.json` | all three numbers to 1e-4; the replicate mean and the fit's predicted block-max mean to 1e-3 |
| C | claim audit: `README.md`, `PICKUP-HERE.md`, `reports/beam_decoder.md` §0–§7, `reports/scorer_power.md` §1, §9, `lanes/P3-MT19937-PY27-EXACT/PREREG.md` §0, §8 | one row per load-bearing sentence (a number, a "measured", a coverage or scope statement, a comparison with upstream): Claim (file:line) → Actual evidence → Overreach → Live lane it hides → Cheapest settling test; each overreach finding is judged by three independent refuters and counts only if two or more cannot refute it | — |

Independence rule: re-derivations A1, A2 and B1 are written by agents that are given this table and the
document text, not the implementation; they may read `docs/kn-scorer-design.md`, the report prose and the
docstrings, and may open the implementation only after their own numbers are recorded, for the
cross-checks named above. Each sub-attack records its command and its numbers in
`lanes/R1-REDTEAM-OWN-CLAIMS/out_<id>.json`.

## 3. Decision rule

- `FOUND-ERROR` if any of A1, A2, B1, B2 is not reproduced by its rule in §2 and the difference survives
  three independent refuters (≥ 2 of 3 fail to explain it as an implementation choice the documents
  allow), **or** any claim-audit row is upheld as an overreach that changes a decision (a lane run or not
  run, a negative trusted, a bar installed).
- `NO-ERROR-FOUND` otherwise. Minor wording findings that change no decision are reported in the table
  and fixed in the documents (with a dated note), and do not make the verdict.
- A sub-attack that cannot run is `not checked` and is listed in `not_covered`; it never counts as
  reproduced.
- Every upheld error is fixed in the same session where the fix is in an unfrozen file; a frozen file's
  fix goes to `TOOLBOX_REQUESTS.md`.

## 4. Null, threshold, expected false positives

Not a search lane: no key space, no null of LP2 decodes, no bar on LP2. The "null" of a re-derivation is
its own uniform-string null (A1, A2, B1), reported with n, mean, sd and max.

## 5. Budget

≤ 6 agent-hours of wall clock in one session; CPU only; no GPU.

## 6. Scope, declared now

- not_covered: the GPU kernels (no device; their CPU twins and simulator are already tested in CI);
  the KN scorer at orders 5–8 (A2 checks order 4 only); the beam cells other than
  `lp-ngram3-heldout` / `beam-skip` / anti-repeat at L = 240 (B1); `reports/scorer_power.md` cells other
  than those named in §2; the corpora themselves (their builds are pinned by SHA-256 in
  `scripts/build_corpus.py`); upstream's (Dukotah's, jens-wedin's) numbers, which are quoted, not
  re-derived; any frozen-toolbox code path not named in §2.
- reopens_if: a re-derived number is later shown to have used the implementation it checks; the
  reports are regenerated at a new scorer fingerprint; a claim is added to the audited documents after
  `fbe43e7`.
- external_ids: none (this project's own claims); format follows upstream Round 18 L7.

## Addenda

<!-- Dated, appended after the freeze. Never edit the sections above. -->
