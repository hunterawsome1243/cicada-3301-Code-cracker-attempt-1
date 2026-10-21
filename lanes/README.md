# Lanes

One YAML file per attack lane, validated by `runeforge.lanes.LaneSpec`
(`runeforge lane lanes/<file>.yaml`). Files starting with `_` are templates and never run.

A lane declares, before it runs: the hypothesis, the generator and seed range, chunk size,
ciphertext view (raw / atbash / chain-increment / first-difference), filter model, scorer
register, claim bar, family-wise bar, the planted-seed control, and the resume cursor.
The Phase 3 runner writes the pre-registration ledger row from this file and refuses to
start while the bars are uncalibrated or the control is not required to recover.
