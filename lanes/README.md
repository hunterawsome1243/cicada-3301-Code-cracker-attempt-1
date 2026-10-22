# Lanes

One YAML file per attack lane, validated by `runeforge.lanes.LaneSpec`
(`runeforge lane lanes/<file>.yaml` prints its runnable problems and exits non-zero while it has
any). Files starting with `_` are templates and never run.

A lane declares, before it runs: the hypothesis, the generator and seed range, chunk size,
ciphertext view (raw / atbash / chain-increment / first-difference), combine, filter model,
scorer preset and window, claim bar, family-wise bar (at least `scripts/threshold_for.py` at the
lane's true N), the planted-seed control and the budget.

`runeforge ledger append --lane lanes/<id>.yaml` writes the pre-registration row from the YAML
(category, N, the bar frozen as the threshold, the control spec). The folder `lanes/<id>/` holds
the committed evidence: `PREREG.md` and `RESULTS.md` (templates in `.claude/rules/lanes.md`), the
control report `control.json` / `control-<sha12>.json` and `gate.json`. `runeforge sweep` refuses
a lane without its ledger row, a passing control and gate on the lane spec as it is now, and the
frozen bar.
