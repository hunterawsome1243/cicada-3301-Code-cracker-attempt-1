<!-- Fixture for tests/test_check_results.py: a NULL with control, null and bar, but no verdict
     arithmetic (floor / ceiling). It must FAIL. -->
# Lane BAD-FLOOR — RESULTS

**Verdict: NULL — best real −6.371 against a null max of −6.177; 0 above the bar.**

numbering: "LP2-0-57"

## 0. Headline numbers

Best real −6.371.

## 1. Why this lane

Fixture.

## 2. Instrument audited before the sweep

- Gate (`runeforge gate lanes/X.yaml`): GATE PASS — 12/12 keys inside the LP2 band.
- Control: recovered 20/20 plants at rank 1.

## 3. Result vs null vs bar

- Null 1: n = 200, mean −6.412, sd 0.083, max −6.177.
- Threshold −5.702. Best real −6.371, z = +0.49.
- Q5 kill condition: checked at 18,432 keys; did not fire.

## 4. Survivors reported, not dropped

None above the bar.

## 5. Coverage — read this, not the verdict

- not_covered: offsets ≥ 8. Conditionals: key space 184,320 keys · decoder rigid · register
  Cicada English.

## 6. What would change this verdict

- reopens_if: a longer window.

## 7. Artifacts and reproduce

`runeforge sweep lanes/BAD-FLOOR.yaml --detach`
