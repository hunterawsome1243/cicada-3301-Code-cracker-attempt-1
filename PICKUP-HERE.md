# PICKUP-HERE

## Status

Phase 1 (spec §7 Sessions 1 and 2) is built: the canon (LP2 13,136 runes; pages 0–55 = 12,956 runes, SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`, equal to Dukotah `PROBLEM.json`), the nine solved sections reproduced rune-for-rune, the stats fingerprint as tests, the oracle with a self-test, the ledger and the lane schema.

The docs/BOOTSTRAP_CHECKLIST.md toolbox is built and frozen (FROZEN.txt, hooks registered in `.claude/settings.json`): `scripts/{threshold_for,calibrate,check_results,validate_ledger}.py`; the CLI verbs the prompts call (`canon --verify`, `status`, `ledger append [--lane]/update/show`, `queue`, `gate`, `control [--out]`, `null`, `sweep --detach`, `score`, `crosser list/replay/escalate/reencipher`, `python -m runeforge.oracle --selftest/--key-module --lane`); the verify-lane subagent (python-only Bash via a hook); `.claude/rules/`. The sweep runs on the CPU reference backend. An adversarial review (per component, then five integration dimensions with a skeptic per dimension) found ~60 defects; every confirmed one is fixed with a test (1,039+ tests, CI green on 3.11 and 3.12). `overnight.sh` was smoke-tested end to end with a stub `claude` (preflight, iteration, PID-verified kill of a detached sweep, stall guard, `LOOP: STOP`).

Not built: the Phase 2 Kneser-Ney scorer and the beam interrupt decoder (spec §7 Session 3), and the Phase 3 CUDA kernels (`sweep --backend gpu` is refused). No lane has a ledger row yet and `queue.json` is empty (`[]`).

Next: spec §7 Session 3, the beam decoder first (see Lessons: until it exists no lane can pass both the gate and its control). Corpora are built offline from the vendored texts (`scripts/build_corpus.py`); `latin` and `old-english` already back the per-decode non-English register stat.

## Rejections

(none yet — every rejected lane, hypothesis or decode goes here with one line of why)

## Lessons

- 2026-10-22, instrument: under the rigid decoder no lane can pass both the fingerprint gate and its planted control. LP2's doublet deficit (86 vs 447 expected) is reproduced only with the anti-repeat filter (`runeforge gate lanes/_template.yaml`: GATE PASS, marginal C3 C6); without it the doublet rate is ~5x LP2's and the gate excludes the family. But the rigid decoder cannot follow the filter's key skips, so the control of every filtered lane is `INCONCLUSIVE (power)` (`runeforge control lanes/_template.yaml`: recovered 0/20). Every lane today therefore ends `EXCLUDED (gate)` or `INCONCLUSIVE (power)`; the Phase 2 beam decoder is the critical path, not more sweeping.
- 2026-10-22, instrument: the oracle cannot tell a one-time pad from a key (k = c - p maps any page to English and passes, `tests/test_oracle_cli.py`). A key's provenance -- generator, seed, and the bar at the lane's true N -- is what HIT_PROTOCOL.md steps 4-5 check; `--key-module` must be the generator's own keystream (`--lane` decodes it the lane's way).
- 2026-10-22, calibration: the Gumbel extrapolation from block maxima errs conservative -- the single max of 10^6 null draws fell below the predicted mean max in all 8 fits (`runeforge/scoring/calib/presets/*.json`, `check`), so bars at 2^32 are slightly high (fewer false positives, slightly less power).
