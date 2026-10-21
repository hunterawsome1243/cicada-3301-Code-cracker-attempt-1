# runeforge

A control-validated, GPU-ready cryptanalysis pipeline for the 56 unsolved pages of
Cicada 3301's *Liber Primus* (LP2 pages 0–55), built so that every result — positive or
negative — is reproducible, pre-registered and publishable.

**Status: Phase 1 (foundation) complete.** The canon is rebuilt from raw transcriptions
and cross-checked against three other lineages, all nine solved sections reproduce
rune-for-rune, the published statistical fingerprint is reproduced as tests, and the
oracle and ledger work. No attack lane has run yet.

## The canon

| | |
|---|---|
| Source | `rtkd/iddqd` master transcription @ `f2267b0` |
| Cross-checked against | `yo-yo-yo-jbo/cicada_tools` @ `717625c` (LP2 page-for-page: identical) · `Dukotah/cicada3301` @ `f08b20b` (PROBLEM.json identity + 57 segments: identical) · `scream314/cicada3301` @ `10733fe` (2 documented substitutions on LP2) |
| LP2 runes | **13,136** on 58 pages (page 50 carries no runes) |
| Unsolved runes | **12,956** (pages 0–55) |
| `sha256` of unsolved indices | `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585` (= Dukotah PROBLEM.json) |
| `sha256` of all LP2 indices | `74cebdb074898f4c2742733a421e6d1717068a4f4cf2802d2b50923285aad329` |

Hashes are over the comma-joined decimal rune indices, so they don't depend on the JSON
formatting. Every pin is in `data/canon/lp2_runes.sha256` and is checked on every load.

### Page numbering

All outputs use **LP2 numbering, pages 0–57** (`numbering: "LP2-0-57"`), i.e. the image
files `0.jpg`–`57.jpg`. The "complete set" (book) numbering runs 0–74, and
**book page = LP2 page + 17**: LP2 page 56 (AN END) is book page 73 and LP2 page 57
(PARABLE) is book page 74. LP1 is book pages 0–16 (`"LP1-0-16"`); its pages 0 and 2 are
cleartext title pages with no runes. Dukotah's "pages 0–54" count *segments*, not pages:
they skip the runeless page 50.

### Transcription divergences

`scripts/build_canon.py` fails on any disagreement between the sources unless it is
recorded edit-for-edit in `data/canon/divergences.json`. Seven edits are recorded:

| id | where | canon vs other | status |
|---|---|---|---|
| DV-01 | LP2 p24 rune 172 (unsolved) | ᚫ AE vs scream314 ᚪ A | **open**: three lineages read AE; needs the image (lane P-8) |
| DV-02 | LP2 p57 (PARABLE) | DIUINITY vs scream314 DIUINITE | decided for canon |
| DV-03 | LP1 p6–7 (A KOAN) | ᛠ ×2 vs scream314 ᚹᛋ | decided for canon ("NOT WHO YOU ARE") |
| DV-04 | LP1 p10 | FOLLOWNG vs scream314 FLLOWNG | decided for canon |
| DV-05 | LP1 p10 | BELEIUE vs cicada_tools BELIEUE | majority (rtkd, scream314, rtkd translation) |

The project brief describes the three lineages as identical over all 13,136 runes. For
rtkd, cicada_tools and Dukotah that holds. scream314 differs at two LP2 positions, and
one of them (DV-01) is on an unsolved page.

## Quick start

```bash
git clone <this repo> && cd <this repo>
pip install -e '.[dev]'            # Python >= 3.11
bash scripts/fetch_raw.sh          # sparse, pinned checkouts of the 5 source repos (~MB)
python scripts/build_canon.py --check
pytest -q
runeforge canon --verify           # pins + counts
runeforge solved                   # the nine solved sections (Rule 1)
runeforge stats                    # the LP2 fingerprint
runeforge oracle --selftest        # the oracle accepts a planted key and rejects a wrong one
runeforge status                   # the ledger
```

`scripts/fetch_raw.sh --full` fetches the complete source repos, page images included
(about 900 MB). Phase 4 needs them.

## What Phase 1 reproduces

| check | value | test |
|---|---|---|
| nine solved sections, from canon runes | exact, all nine | `test_solved_pages.py` |
| our transforms on cicada_tools' ciphertext | exact, all nine | `test_pipeline_matches_cicada_tools_reference` |
| WELCOME / KOAN 2 / AN END interrupters | 11 of 25, 2 of 5, 1 of 5 ᚠ | `test_not_every_f_is_an_interrupter` |
| A WARNING sentence GP-sums | 757 1009 691 353 769 911 1051 859 677, all prime | `test_a_warning_sentences_have_prime_gp_sums` |
| KNOW THIS squares | magic, 1033 and 3301 (rows, columns, diagonals) | `test_know_this_squares_are_magic` |
| English → runes spelling rules | exact on 5 of 7 translation blocks; the other 2 differ by 3 explained edits | `test_english_spelling_reproduces_the_solved_pages` |
| IoC·29, entropy | 1.000, 4.857 bits | `test_global_fingerprint` |
| doublets | 86 (0.66 %), expected 447, z = −17.4 | `test_global_fingerprint` |
| periodic IoC / kappa | no family-wise peak, periods 1–400 per section, 1–600 corpus-wide; max κ 0.0398 | `test_no_periodicity_*` (+ planted period-13 control) |
| shared keystream across sections | none: family-wise p = 0.44 over 82,084 shifts | `test_no_shared_keystream` (+ planted shared-key control) |

**A correction to the brief.** The brief asks for "cross-section shared-keystream scan
max z < 3.5", which is Leo-Y-Zhang's published max z of 3.3. That number does not
reproduce with the exact null SD, √56/(n−1), which Leo's own repository now uses. The raw
maximum is z = 6.0. That is what about 80,000 null shifts produce, given the statistic's
χ² tail: shuffled surrogates give maxima of 5.5–6.5. Read family-wise, the conclusion is
the same: no shared keystream (p = 0.44). The test asserts the family-wise criterion. A
planted shared key with 1,100 aligned runes is found at p ≈ 10⁻³, so the scan's power
falls off below about 1,000 aligned runes.

## Layout

```
runeforge/
  gematria.py      29-rune alphabet, primes, data-driven English->rune spelling rules
  canon.py         pinned canon loader (asserts SHA-256s), solved sections, rendering
  sources.py       parsers for the vendored transcriptions
  transforms/      invertible primitives: atbash, shift, vigenere, beaufort,
                   stream_subtract, totient_prime_stream, running_key, chain, compose
  interrupts.py    F-interrupt rule: rigid and skip_known decoders (beam: Phase 2)
  stats/           IoC, entropy, chi2, doublets, periodic IoC/kappa scans, shared-key scan
  scoring/         baseline rune n-gram scorer (Phase 2 replaces it); family-wise bars
  controls.py      plant-and-recover harness (Rule 2)
  oracle.py        full-page, multi-page, family-wise verification (Rule 3)
  ledger.py        append-only JSONL ledger, Dukotah-compatible export
  lanes.py         lane YAML schema
  gpu/             Phase 3 (CUDA kernels)
data/raw/          5 git submodules (read-only)
data/canon/        lp2_runes.json, lp1_runes.json, solved_sections.json, pins, divergences
data/reference/    cicada_tools' own decode of the solved sections
lanes/             one YAML per attack lane (_template.yaml = queue item 1)
ledger/            ledger.jsonl (created by the first pre-registration)
scripts/           build_canon.py, extract_reference.py, fetch_raw.sh
tests/             Rules 1-3
```

## Roadmap

- **Phase 2: rune-native scorer.** Build Gutenberg, Cicada-register and alternate-language
  corpora; a 6–8-gram Kneser-Ney model with a word-boundary symbol, exported as a flat
  `float32` table; null distributions per page length and register; a power table
  (`reports/scorer_power.md`); and the beam interrupt decoder. That decoder must recover
  a planted DIVINITY key that the rigid decoder rejects.
- **Phase 3: CUDA sweep engine.** `runeforge sweep lanes/<lane>.yaml` with
  checkpoint/resume, ≥ 10⁷ seeds/s, and the Dukotah never-run/parked queue. The queue
  starts with the Python 2.7 MT "exact" lane (`lanes/_template.yaml`).
- **Phase 4: open research lanes.** Doublet-site image audit (P-8, which also settles
  DV-01), a keyed-increment chain cipher, a Z340-style transform screener, and OutGuess
  with non-default keys.
