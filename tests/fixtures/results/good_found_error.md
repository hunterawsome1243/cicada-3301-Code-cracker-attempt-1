<!-- Fixture for tests/test_check_results.py and a worked example of .claude/rules/lanes.md.
     Fictional numbers: no lane by this id has run, and nothing here is a ledger row. It audits
     the fictional lane in good_null.md as if that file were lanes/B04-CICADA-REGISTER/RESULTS.md. -->
# Lane R-B04-AUDIT — red-team of B04-CICADA-REGISTER's headline claims — RESULTS

**Verdict: FOUND-ERROR — 2 of 3 audited claims overreach (coverage overstated by 1.4 %; the ledger row drops its register conditional). The B04-CICADA-REGISTER verdict does not flip.**

numbering: "LP2-0-57" · pre-registered in [`PREREG.md`](PREREG.md) (frozen in e19a6b3) ·
canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`

## 0. Headline numbers

| quantity | value |
|---|---|
| load-bearing sentences in the audited RESULTS.md and ledger row | 11 |
| audited here | 3 |
| overreach found | 2 (coverage −2,624 keys = −1.4 %; register conditional missing) |
| numbers re-derived with independent code | 5 of 5 within 0.002 |
| verdicts that change | 0 |

## 1. Why this lane

Category red-team (round split before this lane I/B/R/C = 33/41/14/12 %, R furthest below its
20 % share). B04-CICADA-REGISTER is this project's first negative on a derived-key family, and
nobody has re-derived its headline numbers with code that does not import the lane.

## 2. Instrument audited before the sweep

Trust anchor, run first:

```
pytest -q -m "not slow"                -> 212 passed, 9 deselected in 41.12s
runeforge canon --verify               -> 023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585 OK
python -m runeforge.oracle --selftest  -> selftest PASS (planted key PASS, wrong key FAIL)
```

- Instrument: `lanes/R-B04-AUDIT/rederive.py`, written for this lane; standard library and numpy
  only, reads `runs/B04-CICADA-REGISTER/` and `data/canon/`, imports nothing from the lane's code.
- Its own check: on a 1,000-row synthetic sweep log with 7 planted duplicate strings it counts 7
  duplicates and reproduces the log's null statistics exactly.

## 3. Result vs null vs bar

One row per audited sentence. The Claim cell quotes the audited text verbatim.

| Claim (file:line) | Actual evidence | Overreach | Live lane it hides | Cheapest settling test |
|---|---|---|---|---|
| `lanes/B04-CICADA-REGISTER/RESULTS.md:14` "184,320 keys (2,880 strings × …)" | `sweep.jsonl` holds 184,320 rows, but 41 strings repeat after case-folding: 2,839 distinct strings × 64 = 181,696 distinct keys | coverage overstated by 2,624 keys (1.4 %) | none: duplicates add no coverage | dedupe the list and restate coverage in a superseding row (1 min CPU) |
| `ledger/ledger.jsonl:14` "status negative; B-04 vocabulary family closed under the Cicada register" | the row's `conditionals` omit the register limit RESULTS.md §5 states: `cicada-ngram3` has no measured Latin or vowel-dropped power | an English-register negative recorded without its register conditional | Latin and vowel-dropped re-score of the stored top 1,000 | re-score `runs/B04-CICADA-REGISTER/top1000.jsonl` under both registers (≈ 3 min CPU); superseding row with the conditional |
| `lanes/B04-CICADA-REGISTER/RESULTS.md:16` "n = 200, mean −6.412, sd 0.083, max −6.177" | independent re-derivation from `null.json`: mean −6.414, sd 0.082, max −6.177 | none (differences ≤ 0.002) | none | none needed |

## 4. Survivors reported, not dropped

This lane searches nothing, so there is nothing to escalate. Both findings are filed as rows that
supersede the originals (`R-B04-AUDIT-1` coverage restated to 181,696 keys; `R-B04-AUDIT-2`
register conditional added); neither changes the B04-CICADA-REGISTER verdict.

## 5. Coverage — read this, not the verdict

- Measured: 3 of the 11 load-bearing sentences (the headline coverage, the ledger row's scope,
  the null statistics), each re-derived from the run's own artifacts.
- not_covered: the other 8 sentences, including the control numbers (20 plants) and the
  escalation table; the sweep itself was not re-run.
- Conditionals: key space — the audit reads the existing 184,320-row log, no new keys ·
  decoder — B04's rigid screen and beam, not re-run · register — the Latin and vowel-dropped
  re-score is the settling test, not run here.

## 6. What would change this verdict

- reopens_if: the register re-score of the top 1,000 finds a decode above that register's own
  bar (B04-CICADA-REGISTER then reopens), or an audit of the remaining 8 sentences finds a
  difference that moves a number across a bar.

## 7. Artifacts and reproduce

- `lanes/R-B04-AUDIT/rederive.py`, `runs/R-B04-AUDIT/rederive.json`; superseding rows
  `R-B04-AUDIT-1`, `R-B04-AUDIT-2` in `ledger/ledger.jsonl`; git 6af2d91.

```bash
python lanes/R-B04-AUDIT/rederive.py --runs runs/B04-CICADA-REGISTER --out runs/R-B04-AUDIT/rederive.json
python scripts/validate_ledger.py
```
