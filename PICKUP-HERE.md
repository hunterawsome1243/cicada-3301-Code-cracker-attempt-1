# PICKUP-HERE

## Status

Phase 1 (spec §7 Sessions 1 and 2) is built: the canon (LP2 13,136 runes; pages 0–55 = 12,956 runes, SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`, equal to Dukotah `PROBLEM.json`), the nine solved sections reproduced rune-for-rune, the stats fingerprint as tests, the oracle with a self-test, the ledger and the lane schema.

The docs/BOOTSTRAP_CHECKLIST.md toolbox is built: FROZEN.txt, the deny-frozen and stop-gate hooks in `.claude/settings.json`, `scripts/{threshold_for,calibrate,check_results,validate_ledger}.py`, the CLI verbs the prompts call (`canon --verify`, `status --short/--round/--grep`, `ledger append/update/show`, `queue`, `gate`, `control`, `sweep --detach`, `crosser list/replay/escalate/reencipher`, `python -m runeforge.oracle --selftest/--key-module`), the verify-lane subagent and `.claude/rules/`. The sweep runs on the CPU reference backend.

Not built: the Phase 2 Kneser-Ney scorer and the beam interrupt decoder (spec §7 Session 3), and the Phase 3 CUDA kernels. Consequence: a lane with `filter_model: anti-repeat` (queue item 1, `lanes/_template.yaml`) fails its control as `INCONCLUSIVE (power)` under the rigid decoder, and `sweep --backend gpu` is refused. No lane has a ledger row yet and `queue.json` is empty (`[]`).

Next: spec §7 Session 3 (corpora are in `data/corpora/`, built offline from the vendored texts; the KN model and the beam decoder), then a first instrument lane whose control passes.

## Rejections

(none yet — every rejected lane, hypothesis or decode goes here with one line of why)

## Lessons

(none yet)
