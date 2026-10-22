<!-- Fixture for tests/test_check_results.py and a worked example of .claude/rules/lanes.md.
     Fictional numbers: no lane by this id has run, and nothing here is a ledger row. -->
# Lane B05-PBKDF2-VOCAB — PBKDF2 keystreams from Cicada vocabulary — RESULTS

**Verdict: CANDIDATE — crosser k0001 is FLAGGED-FOR-ORACLE: −5.482 against the bar −5.689 at N = 207,360, z rises at every escalation step, our oracle PASS on LP2 pages 0 and 1; Dukotah's verifier and the re-encipher step are pending. Not a solve.**

numbering: "LP2-0-57" · pre-registered in [`PREREG.md`](PREREG.md) (frozen in 51be0d4) ·
lane spec `lanes/B05-PBKDF2-VOCAB.yaml` · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`

## 0. Headline numbers

| quantity | value |
|---|---|
| trials (true N) | 207,360 keys (2,880 passwords × 9 salts × 4 iteration counts × raw/Atbash) |
| control | recovered 19/20 plants at rank 1 |
| null (shuffle) | n = 200, mean −6.398, sd 0.079, max −6.161 |
| bar | −5.689 (`threshold_for`, fixed in advance) |
| best real | −5.482 (z = +11.59) |
| verdict arithmetic | best real −5.482 vs floor −5.611 vs ceiling −6.170 |
| crossers | 1 (k0001, FLAGGED-FOR-ORACLE) |

## 1. Why this lane

Category bounded (round split before this lane I/B/R/C = 31/36/21/12 %). Q2 fact: the spec's
lane queue names KDF outputs with Cicada-vocabulary passwords and salts 3301, 1033, page numbers
and primes as the third-priority family (`docs/liber-primus-solver-spec.md:228`), and Dukotah's
B-05 was re-run after the payload-byte correction under the English register only. This lane uses
the Cicada-register scorer.

## 2. Instrument audited before the sweep

Trust anchor, run first:

```
pytest -q -m "not slow"                -> 212 passed, 9 deselected in 40.88s
runeforge canon --verify               -> 023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585 OK
python -m runeforge.oracle --selftest  -> selftest PASS (planted key PASS, wrong key FAIL)
```

- Gate (`runeforge gate lanes/B05-PBKDF2-VOCAB.yaml`): GATE PASS — 12/12 keys inside the LP2 band
  under the anti-repeat filter model.
- Control (`runeforge control lanes/B05-PBKDF2-VOCAB.yaml`): recovered 19/20 plants at rank 1 (the
  miss, plant 14, ranked 3rd with recovery 0.871); median rune-index recovery 1.000, minimum
  0.871; planted score median −4.902 vs bar −5.689; wrong key −7.433.

## 3. Result vs null vs bar

- Null 1, size-matched shuffle of the real runes: n = 200, mean −6.398, sd 0.079, max −6.161.
- Null 2, domain-separated SHA-256 stream: n = 200, mean −6.391, sd 0.081, max −6.170.
- Threshold (fixed in advance): `python scripts/threshold_for.py --n 207360 --preset
  cicada-ngram3:rigid --L 120` → bar −5.689; expected false positives over the slice 0.005.
- Best real −5.482, z = +11.59 against null 1.
- Verdict arithmetic: best real −5.482 vs floor −5.611 vs ceiling −6.170: at or above the floor,
  so HIT_PROTOCOL.md ran on k0001 before anything else in the session.
- Q5 kill condition (control replayed through the sweep binary recovers < 18/20 at 10 % of
  budget): checked at 20,736 keys; did not fire (19/20).

## 4. Survivors reported, not dropped

Escalation per HIT_PROTOCOL.md §3, each z against a size-matched null of that length; the key
continues across pages with no re-synchronisation.

| kid | head L=120 | z | 2× | z | page 0 | z | stream | z | outcome |
|---|---|---|---|---|---|---|---|---|---|
| k0001 pbkdf2/w=1187/salt=1033/it=1000/raw | −5.482 | +11.59 | −5.214 | +14.90 | −5.170 | +16.20 | −5.122 | +71.40 | FLAGGED-FOR-ORACLE |
| pbkdf2/w=0266/salt=3301/it=1/atbash | −6.204 | +2.46 | −6.861 | −0.12 | −6.993 | −0.58 | −7.384 | −1.15 | z falls; noise |

- Parity (§2): CPU replay `runeforge crosser replay k0001 --cpu` reproduces the keystream and the
  score (|Δ| = 0); verify-lane reproduced 4/4 numbers.
- Held-out halves (§4): 0.97 and 0.95 under the frozen key; page 1 decoded whole with the same key
  continuation, above the bar on its own.
- Oracle: `python -m runeforge.oracle --key-module runs/B05-PBKDF2-VOCAB/crossers/k0001_key.py
  --pages 2 --n-trials 207360` → PASS (solved-section regression green first; pages 0 and 1
  whole).
- Pending: `data/raw/dukotah/liber-primus/verify_solution.py --key-module …` (§5) and
  `runeforge crosser reencipher k0001` (§6). `PENDING-ADJUDICATION.md` lists the commands; the
  plaintext has not been read. Needs Hunter.

## 5. Coverage — read this, not the verdict

- Measured: 207,360 keys, the full pre-registered slice, screened on the first 120 runes of LP2
  page 0; one crosser escalated to the full 12,956-rune stream.
- not_covered: scrypt and bcrypt; iteration counts other than 1, 1,000, 3,301 and 10,000;
  salts outside the nine listed; passwords outside the 2,880-string list; keys that start after
  page 0.
- Conditionals: key space — 2,880 passwords × 9 salts × 4 iteration counts × 2 views only ·
  decoder — rigid screen at L = 120, beam on the top 1,000 · register — Cicada-register English
  (`cicada-ngram3`).

## 6. What would change this verdict

- reopens_if: `verify_solution.py` FAILs, the re-encipher differs from the canonical runes on any
  rune of pages 0–1, or a second verify-lane run differs on which side of the bar k0001 lands →
  k0001 becomes NOISE-CROSSER or PARITY-FAIL and this lane is re-filed as NULL with k0001 in §4.

## 7. Artifacts and reproduce

- `runs/B05-PBKDF2-VOCAB/sweep.jsonl`, `runs/B05-PBKDF2-VOCAB/control.json`,
  `runs/B05-PBKDF2-VOCAB/crossers/k0001.md`, `runs/B05-PBKDF2-VOCAB/crossers/k0001_key.py`;
  ledger row `B05-PBKDF2-VOCAB` (`hit-unverified`); git 0c9e5f1.

```bash
runeforge control lanes/B05-PBKDF2-VOCAB.yaml
runeforge crosser replay k0001 --cpu
python -m runeforge.oracle --key-module runs/B05-PBKDF2-VOCAB/crossers/k0001_key.py --pages 2 --n-trials 207360
```
