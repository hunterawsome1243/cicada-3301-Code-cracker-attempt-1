<!-- Fixture for tests/test_check_results.py and a worked example of .claude/rules/lanes.md.
     Fictional numbers: no lane by this id has run, and nothing here is a ledger row. -->
# Lane CHAIN-PY27MT-L120 — keyed-increment chain, Python 2.7 MT keystream — RESULTS

**Verdict: INCONCLUSIVE (power) — control recovered 9/20 plants; floor −5.871 vs ceiling −6.020 (separation 0.149 < 0.25). The sweep was not run.**

numbering: "LP2-0-57" · pre-registered in [`PREREG.md`](PREREG.md) (frozen in a77d310) ·
lane spec `lanes/CHAIN-PY27MT-L120.yaml` · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`

## 0. Headline numbers

| quantity | value |
|---|---|
| trials (true N, had the sweep run) | 4,294,967,296 seeds |
| control | recovered 9/20 plants at rank 1 |
| null (shuffle) | n = 200, mean −6.233, sd 0.091, max −5.998 |
| bar | −5.412 (`threshold_for`, fixed in advance) |
| planted median | −6.050 (z = +2.01) |
| verdict arithmetic | floor −5.871 vs ceiling −6.020 (separation 0.149) |
| seeds screened | 0 |

## 1. Why this lane

Category bounded (round split before this lane I/B/R/C = 30/33/24/13 %). Q2 fact: the
keyed-increment chain cᵢ = cᵢ₋₁ + pᵢ + kᵢ (mod 29) failed only with sequence keys; stream keys
are open (`docs/liber-primus-solver-spec.md:248`). Python 2.7 MT is the generator family the
upstream seed prior was built for.

## 2. Instrument audited before the sweep

Trust anchor, run first:

```
pytest -q -m "not slow"                -> 212 passed, 9 deselected in 41.30s
runeforge canon --verify               -> 023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585 OK
python -m runeforge.oracle --selftest  -> selftest PASS (planted key PASS, wrong key FAIL)
```

- Gate (`runeforge gate lanes/CHAIN-PY27MT-L120.yaml`): GATE PASS — 11/12 keys inside the LP2 band
  on the chain view.
- Control (`runeforge control lanes/CHAIN-PY27MT-L120.yaml`): recovered 9/20 plants at rank 1;
  median rune-index recovery 0.412, minimum 0.031; planted score median −6.050 vs bar −5.412;
  wrong key −7.452. The pre-registered pass bar (≥ 90 % of ≥ 20 plants) is not met.

## 3. Result vs null vs bar

- Null 1, size-matched shuffle of the real runes: n = 200, mean −6.233, sd 0.091, max −5.998.
- Null 2, domain-separated SHA-256 stream: n = 200, mean −6.241, sd 0.088, max −6.020.
- Threshold (fixed in advance): `python scripts/threshold_for.py --n 4294967296 --preset
  cicada-ngram3:rigid --L 120` → bar −5.412.
- Planted median −6.050, z = +2.01 against null 1: the planted key sits inside the noise, 0.64
  below the bar.
- Verdict arithmetic: floor −5.871 (the worst of the 9 self-recovering plants) vs ceiling
  −6.020; floor − ceiling = 0.149 < 0.25, and fewer than half of the plants are identifiable.
  Either condition alone makes the lane INCONCLUSIVE (power).
- Q5 kill condition: not reached; no sweep was launched.

## 4. Survivors reported, not dropped

No sweep was run, so there are no survivors. The 11 plants that failed are listed with their
ranks and recoveries in `runs/CHAIN-PY27MT-L120/control.json`; 8 of the 11 lose sync at the
first F-interrupt inside the 120-rune window.

## 5. Coverage — read this, not the verdict

- Measured: the instrument's power for this hypothesis class at L = 120 (20 plants), not the key
  space: 0 of 2^32 seeds screened.
- not_covered: the entire 2^32 seed space; windows longer than 120 runes; the beam decoder on the
  chain view; chain variants with a non-zero initial c₋₁.
- Conditionals: key space — none swept · decoder — rigid screen only; the chain view propagates
  every interrupt error forward, which is the measured failure · register — Cicada-register
  English (`cicada-ngram3`).

## 6. What would change this verdict

- reopens_if: an instrument lane measures chain-view recovery ≥ 0.90 on ≥ 90 % of plants (a
  longer window, L = 480 is next, or the beam decoder on the chain view); this lane then re-runs
  from a new PREREG with a bar computed for that preset.

## 7. Artifacts and reproduce

- `runs/CHAIN-PY27MT-L120/control.json`, `runs/CHAIN-PY27MT-L120/null.json`; ledger row
  `CHAIN-PY27MT-L120` (`inconclusive`); git 5e8a1c0.

```bash
runeforge control lanes/CHAIN-PY27MT-L120.yaml
python scripts/check_results.py lanes/CHAIN-PY27MT-L120/RESULTS.md
```
