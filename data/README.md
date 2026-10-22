# Data

| dir | what | edited by |
|---|---|---|
| `raw/` | five source repos as git submodules, pinned: `rtkd`, `scream314`, `cicada_tools`, `dukotah`, `jens-wedin` (`scripts/fetch_raw.sh`) | nobody -- read-only |
| `canon/` | canonical runes, solved sections, SHA-256 pins | `scripts/build_canon.py` (only `divergences.json` is curated by hand) |
| `reference/` | cicada_tools' own decode of the solved sections | `scripts/extract_reference.py` |
| `corpora/` | scorer and gate training text, built offline from the vendored texts (not committed) | `scripts/build_corpus.py` |
