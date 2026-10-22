<!-- Fixture for tests/test_check_results.py and a worked example of .claude/rules/lanes.md.
     Fictional numbers: no lane by this id has run, and nothing here is a ledger row. -->
# Lane RUNKEY-LP1-RIGID — running key from the LP1 plaintext, rigid — RESULTS

Verdict: EXCLUDED (gate) — the doublet rate of 12/12 simulated keys sits far above LP2's 0.66 %; control, null and sweep were not run.

numbering: "LP2-0-57" (the key text is LP1, numbering "LP1-0-16") · pre-registered in
[`PREREG.md`](PREREG.md) (frozen in c40b7e2) · lane spec `lanes/RUNKEY-LP1-RIGID.yaml`

## 0. Headline numbers

| quantity | value |
|---|---|
| keys simulated by the gate | 12 (random LP1 offsets) on 12,956 runes of synthetic Cicada-register English |
| gate | GATE FAIL on doublet rate and cross-word doublets for 12/12 keys |
| simulated doublet rate | 2.94–3.87 % (LP2: 86 doublets, 0.66 %) |
| control / null / sweep | not run |

## 1. Why this lane

Category bounded (round split before this lane I/B/R/C = 32/35/20/13 %). Q2 fact: the solved-page
keys came from Cicada's own vocabulary (`CLAUDE.md:33`), which makes Cicada's own LP1 plaintext
the most natural running key. A rigid running key is cheap to test with the fingerprint gate
before any control or sweep is spent on it.

## 2. Instrument audited before the sweep

Trust anchor, run first:

```
pytest -q -m "not slow"                -> 212 passed, 9 deselected in 40.95s
runeforge canon --verify               -> 023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585 OK
python -m runeforge.oracle --selftest  -> selftest PASS (planted key PASS, wrong key FAIL)
```

- Gate (`runeforge gate lanes/RUNKEY-LP1-RIGID.yaml`): GATE FAIL — doublet rate and cross-word
  doublets outside the LP2 band for 12/12 keys; IoC, lag-5 and mod-5 inside the band.

| statistic | LP2 | simulated, min–max over 12 keys | keys outside the band |
|---|---|---|---|
| IoC | 1.000 | 1.004–1.031 | 0/12 |
| doublet rate | 0.66 % | 2.94–3.87 % | 12/12 |
| cross-word doublets | inside band | 11–14 × LP2's count | 12/12 |
| lag-5 / mod-5 | inside band | inside band | 0/12 |

## 3. Result vs null vs bar

Not run: the gate stops the lane before control and null (SESSION_PROMPT.md §C3 step 1). There is
no real-page score, no bar crossing and no z.

## 4. Survivors reported, not dropped

No sweep, so no survivors.

## 5. Coverage — read this, not the verdict

- Measured: 12 random LP1 offsets enciphered rigidly over synthetic Cicada-register English. The
  gate excludes the typical key of this construction, not the family.
- not_covered: a running key followed by an output anti-repeat filter (the doublet deficit would
  then come from the filter, not the key; that is a different lane); key texts other than LP1;
  Atbash or reversed LP1; Beaufort sign.
- Conditionals: key space — 12 sampled offsets, nothing enumerated · decoder — none; the gate
  simulates encipherment only · register — synthetic Cicada-register English plaintext; a
  plaintext with a different doublet structure is not simulated.

## 6. What would change this verdict

- reopens_if: the P-8 doublet-site audit finds ≥ 20 miscounted doublet sites (LP2's deficit
  would shrink), or a construction is proposed that feeds the running-key output through the
  anti-repeat filter.

## 7. Artifacts and reproduce

- `runs/RUNKEY-LP1-RIGID/gate.json`; ledger row `RUNKEY-LP1-RIGID`; git 2b9d4f7.

```bash
runeforge gate lanes/RUNKEY-LP1-RIGID.yaml
python scripts/check_results.py lanes/RUNKEY-LP1-RIGID/RESULTS.md
```
