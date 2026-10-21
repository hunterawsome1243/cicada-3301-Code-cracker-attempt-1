# Data

| dir | what | edited by |
|---|---|---|
| `raw/` | five source repos as git submodules, pinned (`scripts/fetch_raw.sh`) | nobody -- read-only |
| `canon/` | canonical runes, solved sections, SHA-256 pins | `scripts/build_canon.py` (only `divergences.json` is curated by hand) |
| `reference/` | cicada_tools' own decode of the solved sections | `scripts/extract_reference.py` |
| `corpora/` | scorer training text (Phase 2, not committed) | `scripts/build_corpus.py` |
