# Ledger

`ledger.jsonl` is the append-only record of every lane run (`runeforge.ledger`): a
pre-registration row before the run, a result row after. Never edit or delete a row.
`runeforge status` prints the latest row per lane; `runeforge.ledger.to_upstream` maps a
row onto Dukotah/cicada3301 `LEDGER.json` fields for submission.
