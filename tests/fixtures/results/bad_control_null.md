<!-- Fixture for tests/test_check_results.py: every section present, but the control and null
     carry no numbers a reader could check. It must FAIL. -->
# Lane BAD-FIELDS — RESULTS

**Verdict: NULL — best real −6.371 vs floor −5.214 vs ceiling −6.198.**

numbering: "LP2-0-57"

## 0. Headline numbers

Best real −6.371.

## 1. Why this lane

Fixture.

## 2. Instrument audited before the sweep

- Gate (`runeforge gate lanes/X.yaml`): GATE PASS — 12/12 keys inside the LP2 band.
- Control: the planted key came out on top.

## 3. Result vs null vs bar

- Null: 5 shuffles, mean −6.412.
- Best real −6.371, comfortably inside the noise.
- Q5 kill condition: checked at 10 % of budget; did not fire.

## 4. Survivors reported, not dropped

None above the bar.

## 5. Coverage — read this, not the verdict

- not_covered: everything outside the slice.
- Conditionals: key space, decoder and register as pre-registered.

## 6. What would change this verdict

- reopens_if: a longer window.

## 7. Artifacts and reproduce

`runeforge sweep lanes/BAD-FIELDS.yaml --detach`
