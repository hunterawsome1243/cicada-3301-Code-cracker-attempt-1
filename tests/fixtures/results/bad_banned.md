<!-- Fixture for tests/test_check_results.py: complete and numerically sound, but it overclaims.
     Words inside an HTML comment do not count: this lane is closed. It must FAIL. -->
# Lane BAD-WORDS — RESULTS

**Verdict: NULL — best real −6.371 vs floor −5.214 vs ceiling −6.198.**

numbering: "LP2-0-57"

## 0. Headline numbers

The B-04 vocabulary family is now closed and the frontier is complete.

## 1. Why this lane

The nine solved sections re-derive and the solved-page regression is green, but this page is
not solved and no key here is cracked.

## 2. Instrument audited before the sweep

- Gate (`runeforge gate lanes/X.yaml`): GATE PASS — 12/12 keys inside the LP2 band.
- Control: recovered 20/20 plants at rank 1.

## 3. Result vs null vs bar

- Null 1: n = 200, mean −6.412, sd 0.083, max −6.177.
- Threshold −5.702. Best real −6.371, z = +0.49.
- Q5 kill condition: checked at 18,432 keys; did not fire.

## 4. Survivors reported, not dropped

None above the bar; the result is confirmed and the dictionary is exhausted.

## 5. Coverage — read this, not the verdict

- not_covered: offsets ≥ 8. Conditionals: key space 184,320 keys · decoder rigid · register
  Cicada English. LP2 is not unsolvable.

## 6. What would change this verdict

- reopens_if: a longer window.

## 7. Artifacts and reproduce

`runeforge sweep lanes/BAD-WORDS.yaml --detach`
