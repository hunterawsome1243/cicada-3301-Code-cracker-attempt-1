<!-- Fixture for tests/test_check_results.py and a worked example of .claude/rules/lanes.md.
     Fictional numbers: no lane by this id has run, and nothing here is a ledger row. -->
# Lane B04-CICADA-REGISTER — SHA-256/512 keystreams from Cicada vocabulary — RESULTS

**Verdict: NULL — best real −6.371 vs floor −5.214 vs ceiling −6.198 over 184,320 keys; 0 above the bar −5.702.**

numbering: "LP2-0-57" · pre-registered in [`PREREG.md`](PREREG.md) (frozen in 3f1c2a9) ·
lane spec `lanes/B04-CICADA-REGISTER.yaml` · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`

## 0. Headline numbers

| quantity | value |
|---|---|
| trials (true N) | 184,320 keys (2,880 strings × SHA-256/512 × counter/chain × raw/Atbash × offsets 0–7) |
| control | recovered 20/20 plants at rank 1 |
| null (shuffle) | n = 200, mean −6.412, sd 0.083, max −6.177 |
| bar | −5.702 (`threshold_for`, fixed in advance) |
| best real | −6.371 (z = +0.49) |
| verdict arithmetic | best real −6.371 vs floor −5.214 vs ceiling −6.198 |
| crossers | 0 |

## 1. Why this lane

Category bounded (round split before this lane I/B/R/C = 34/31/22/13 %, B furthest below its
40 % share). Q2 fact: every upstream B-04 negative is an English-quadgram negative, and the L7
red-team measured that scorer's power on other registers at 0.00–0.58
(`data/raw/dukotah/liber-primus/analysis/round18/L7-redteam/RESULTS.md`, §A.1). This lane re-runs
the B-04 dictionary family under the Cicada-register scorer (`cicada-ngram3`) with the
anti-repeat filter model; the dictionary, hashes and views are B-04's, the register is new.

## 2. Instrument audited before the sweep

Trust anchor, run first:

```
pytest -q -m "not slow"                -> 212 passed, 9 deselected in 41.07s
runeforge canon --verify               -> 023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585 OK
python -m runeforge.oracle --selftest  -> selftest PASS (planted key PASS, wrong key FAIL)
```

- Gate (`runeforge gate lanes/B04-CICADA-REGISTER.yaml`): GATE PASS — 12/12 keys inside the LP2
  band (IoC, doublet rate, lag-5, cross-word doublets, mod-5) under the anti-repeat filter model.
- Control (`runeforge control lanes/B04-CICADA-REGISTER.yaml`): recovered 20/20 plants at rank 1
  (key strings drawn from the list, random offset, synthetic Cicada-register English, same rigid
  screen at L = 120 and beam adjudication of the top 1,000); median rune-index recovery 1.000,
  minimum 0.958; planted score median −4.830 vs bar −5.702; wrong key −7.460.

## 3. Result vs null vs bar

- Null 1, size-matched shuffle of the real runes: n = 200, mean −6.412, sd 0.083, max −6.177.
- Null 2, domain-separated SHA-256 stream: n = 200, mean −6.405, sd 0.080, max −6.198.
- Threshold (fixed in advance): `python scripts/threshold_for.py --n 184320 --preset
  cicada-ngram3:rigid --L 120` → bar −5.702; expected false positives over the slice 0.004.
- Best real −6.371, z = +0.49 against null 1 (below null 1's max −6.177).
- Verdict arithmetic: best real −6.371 vs floor −5.214 vs ceiling −6.198
  (floor − ceiling = 1.016).
- Q5 kill condition (control replayed through the sweep binary recovers < 18/20 at 10 % of
  budget): checked at 18,432 keys; did not fire (20/20).

## 4. Survivors reported, not dropped

Top 3 by screen score; escalation per HIT_PROTOCOL.md §3, each z against a size-matched null of
that length.

| kid | head L=120 | z | 2× | z | page 0 | z | stream | z | outcome |
|---|---|---|---|---|---|---|---|---|---|
| sha512-ctr/w=0412/atbash/+3 | −6.371 | +0.49 | −6.902 | −0.21 | −6.987 | −0.44 | −7.381 | −1.07 | z falls; noise |
| sha256-chain/w=1907/raw/+0 | −6.388 | +0.29 | −6.951 | −0.48 | −7.104 | −1.02 | −7.392 | −1.31 | z falls; noise |
| sha256-ctr/w=0031/raw/+6 | −6.395 | +0.20 | −6.874 | −0.06 | −7.043 | −0.71 | −7.377 | −0.96 | z falls; noise |

Crossers above the bar: 0 (`runs/B04-CICADA-REGISTER/crossers/` is empty). Oracle: not run (no
crosser).

## 5. Coverage — read this, not the verdict

- Measured: 184,320 keys, the full pre-registered slice (2,880 strings × 64 configurations),
  screened on the first 120 runes of LP2 page 0 and escalated on page 0 (262 runes) and the full
  12,956-rune stream.
- not_covered: PBKDF2/scrypt stretching (B-05's axis); salts; offsets ≥ 8; strings outside the
  2,880-string list; keys that start after page 0 (the screen window is page 0's head); the
  filter-off view.
- Conditionals: key space — the 2,880-string list × 64 configurations only · decoder — rigid
  screen at L = 120, beam on the top 1,000 only; a key the screen ranks below 1,000 is never
  adjudicated (the control placed 20/20 plants inside the top 1,000) · register — Cicada-register
  English (`cicada-ngram3`); Latin and vowel-dropped English have no measured power for this
  scorer, so this is an English-register negative for them.

## 6. What would change this verdict

- reopens_if: a vocabulary string with documented Cicada provenance that is not in the list; a
  key that starts after page 0; `reports/scorer_power.md` measuring Cicada-register power < 0.90
  at L = 120; any re-run with a beam screen instead of the rigid screen.

## 7. Artifacts and reproduce

- `runs/B04-CICADA-REGISTER/sweep.jsonl` (SHA-256 `9c41e0d27b5a`…), `runs/B04-CICADA-REGISTER/control.json`,
  `runs/B04-CICADA-REGISTER/null.json`; ledger row `B04-CICADA-REGISTER` in `ledger/ledger.jsonl`;
  git 7d02e4b.

```bash
runeforge control lanes/B04-CICADA-REGISTER.yaml
runeforge sweep lanes/B04-CICADA-REGISTER.yaml --detach
python scripts/check_results.py lanes/B04-CICADA-REGISTER/RESULTS.md
```
