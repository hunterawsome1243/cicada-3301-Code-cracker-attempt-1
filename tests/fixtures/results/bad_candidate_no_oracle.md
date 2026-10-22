<!-- Fixture for tests/test_check_results.py: a CANDIDATE whose only oracle PASS is the trust
     anchor's self-test. It must FAIL. -->
# Lane BAD-CANDIDATE — RESULTS

**Verdict: CANDIDATE — crosser k0001 is FLAGGED-FOR-ORACLE at −5.482 against the bar −5.689.**

numbering: "LP2-0-57"

## 0. Headline numbers

One crosser above the bar.

## 1. Why this lane

Fixture.

## 2. Instrument audited before the sweep

- Gate (`runeforge gate lanes/X.yaml`): GATE PASS — 12/12 keys inside the LP2 band.
```
python -m runeforge.oracle --selftest  -> selftest PASS (planted key PASS, wrong key FAIL)
```

- Control: recovered 19/20 plants at rank 1.

## 3. Result vs null vs bar

- Null 1: n = 200, mean −6.398, sd 0.079, max −6.161.
- Threshold −5.689. Best real −5.482, z = +11.59.
- Q5 kill condition: checked at 20,736 keys; did not fire.

## 4. Survivors reported, not dropped

k0001 rises at every escalation step. Next: the oracle.

## 5. Coverage — read this, not the verdict

- not_covered: scrypt. Conditionals: key space 207,360 keys · decoder rigid · register Cicada
  English.

## 6. What would change this verdict

- reopens_if: the community verifier FAILs.

## 7. Artifacts and reproduce

`runeforge crosser replay k0001 --cpu`
