# runeforge

A control-validated, GPU-ready cryptanalysis pipeline for the 56 unsolved pages of
Cicada 3301's *Liber Primus* (LP2 pages 0–55), built so that every result — positive or
negative — is reproducible, pre-registered and publishable.

**Status: Phase 1 (foundation) built; the session toolbox built; the Phase 2 beam
interrupt decoder built; no attack lane has run.**
The canon is rebuilt from raw transcriptions and cross-checked against three other
lineages, all nine solved sections reproduce rune-for-rune, the published statistical
fingerprint is reproduced as tests, and the oracle and ledger work. The toolbox the
session prompts call (`docs/BOOTSTRAP_CHECKLIST.md`) exists: calibrated family-wise bars,
the planted control, murphy's fingerprint gate, a CPU sweep runner with detach, resume and
crosser files, the results checker, the ledger validator, the frozen-file hooks and the
stop gate. The beam decoder (`runeforge/beam.py`, presets `<scorer>:beam`, `:beam-skip`,
`:beam-skip-int`) follows the F-interrupters and the anti-repeat filter's key skips: given
only the key it re-derives the solved sections' interrupt sets, and a lane with LP2's
doublet deficit (anti-repeat filter, which the gate needs) now passes its planted control
where the rigid decoder recovers 0 of 20 (`reports/beam_decoder.md`). Its family-wise bars
are fitted but wait for Hunter to install them (`TOOLBOX_REQUESTS.md`), and on the CPU it
runs at about 10³ keys/s. The Phase 3 kernels (`runeforge/gpu/`, numba.cuda: the beam decoder
and the `mt19937-py27` keystream, which stays on the device for the decoder) are built and
match the numpy references exactly on their CPU twins and the CUDA simulator; they have not yet
run on a real GPU, and `sweep --backend gpu` refuses a lane until
`python -m runeforge.gpu.parity <lane.yaml>` has passed on the device. Not built yet: the Phase 2
Kneser-Ney scorer and kernels for the other generators.

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
bash scripts/setup.sh              # venv, pip install -e '.[dev]', fetch_raw, corpora, trust anchor
```

or by hand:

```bash
pip install -e '.[dev]' sympy      # Python >= 3.11
bash scripts/fetch_raw.sh          # sparse, pinned checkouts of the 5 source repos (~100 MB)
python scripts/build_corpus.py     # scorer/gate corpora from the vendored texts (offline)
python scripts/build_canon.py --check
pytest -q
```

The trust anchor (SESSION_PROMPT.md section A; CI runs the same commands):

```bash
pytest -q -m "not slow"
runeforge canon --verify                 # pins + counts
python -m runeforge.oracle --selftest    # last line: ORACLE SELF-TEST: PASS
runeforge status --short                 # open lanes, jobs, last rows (--round: budget split)
python scripts/validate_ledger.py        # last line: Unsound negatives = 0
```

`scripts/fetch_raw.sh --full` fetches the complete source repos, page images included
(about 900 MB). Phase 4 needs them, and the download needs Hunter's approval (CLAUDE.md).

## Running a lane

Every step writes into the ledger or `runs/<lane_id>/`, and every printed number comes
with the command that regenerates it. The procedure is SESSION_PROMPT.md section C.

```bash
cp lanes/_template.yaml lanes/<id>.yaml                       # then edit
python scripts/threshold_for.py --n <N> --preset lp-ngram3-heldout:beam-skip --L 240  # the bars
runeforge lane lanes/<id>.yaml                                # schema + runnable problems
runeforge ledger append --lane lanes/<id>.yaml   # pre-registration: the bar frozen as threshold
runeforge gate lanes/<id>.yaml        # murphy fingerprint gate, >= 12 keys, majority rule
runeforge null lanes/<id>.yaml        # Null 1 (shuffle) + Null 2 (SHA-256), n >= 200
runeforge control lanes/<id>.yaml     # >= 20 plants; writes lanes/<id>/control*.json and
                                      # records positive_control + its sha256 in the ledger
git add lanes/<id> && git commit      # control, gate and null reports are the evidence
runeforge sweep lanes/<id>.yaml --detach   # refuses without that control and the frozen bar
runeforge status --short              # live jobs with seeds/s, crossers, best score
runeforge score lanes/<id>.yaml <seed>     # re-score any sweep row (its reproduce command)
runeforge crosser list                # FLAGGED-FOR-ORACLE files
runeforge crosser replay <kid>        # HIT_PROTOCOL.md step 2
runeforge crosser escalate <kid>      # step 3
python -m runeforge.oracle --key-module <key.py> --lane lanes/<id>.yaml   # step 5
runeforge crosser reencipher <kid>    # step 6
python scripts/check_results.py lanes/<id>/RESULTS.md   # must print PASS
```

A lane's control is evidence only for the lane spec it ran on: the sweep compares a hash of
the pipeline-defining fields (generator, view, combine, filter, preset, window, pages, bars,
control) with the one in `lanes/<id>/control.json`, and the bar in the YAML with the
threshold the ledger froze. Edit the lane and the control must be re-run.

`sweep --backend gpu` (beam lanes only) generates `mt19937-py27` keystreams on the device
(other generators' on the CPU), scores them with the CUDA beam kernel, and re-generates and
re-decodes every survivor, crosser and chunk best on the CPU reference, stopping if the two
disagree. It is refused unless `runs/<id>/parity.json` (`python -m runeforge.gpu.parity
<lane.yaml>`, ≥ 10⁴ of the lane's own keys: scores, survivors and keystreams) passed on this
device, for this lane spec, `runeforge/beam.py`, the generator and both kernels. `--bench N`
on the same command writes `runs/<id>/bench.json`. The CPU backend is the reference
implementation.

`queue.json` is a top-level JSON array of
`{"id", "category", "approved", "gpu_hours_cap", "prereg_ready", "note"}`; `overnight.sh`
runs only entries Hunter has set `"approved": true` on (`runeforge queue` prints it).

## The toolbox and FROZEN.txt

| file | what |
|---|---|
| `scripts/threshold_for.py` | family-wise bar for N trials from a Gumbel fit to observed block maxima (`runeforge/scoring/calib/presets/*.json`), with a scale check on the fit's own draws; refuses an uncalibrated length |
| `scripts/calibrate.py` | writes those calibration files (10⁶ null strings per preset and length) |
| `scripts/check_results.py` | PASS/FAIL on a lane's RESULTS.md: sections, vocabulary, verdict arithmetic |
| `scripts/validate_ledger.py` | ledger schema, append-only history, and `Unsound negatives = N` |
| `scripts/hooks/deny_frozen.sh` | PreToolUse hook: blocks edits to anything listed in `FROZEN.txt` |
| `scripts/hooks/stop_gate.sh` | Stop hook: no session ends with an unsound ledger or a failing RESULTS.md (changed or unpushed) |
| `scripts/hooks/python_only.sh` | the verify-lane subagent's Bash runs only `python ...` |
| `.claude/settings.json` | registers the two hooks |
| `.claude/rules/*.md`, `.claude/agents/verify-lane.md` | lane, report and GPU conventions; the independent re-derivation subagent |

`FROZEN.txt` lists the files the overnight loop may not edit: the canon, the vendored
sources, the oracle, the controls, the ledger, the stats fingerprint, the Phase 1 tests
and the three scripts above. Changing any of them is Hunter's call.

## What Phase 1 reproduces

| check | value | test |
|---|---|---|
| nine solved sections, from canon runes | exact, all nine | `test_solved_pages.py` |
| our transforms on cicada_tools' ciphertext | exact, all nine | `test_pipeline_matches_cicada_tools_reference` |
| WELCOME / KOAN 2 / AN END interrupters | 11 of 25, 2 of 5, 1 of 5 ciphertext ᚠ | `test_not_every_f_is_an_interrupter` |
| ... and every plaintext F is one | 14 of 14 (11, 2, 1) | `test_every_plaintext_f_in_the_keyed_sections_is_an_interrupter` |
| the same interrupt sets from the key alone (beam) | exact, all three, two non-LP scorers | `test_the_beam_rederives_the_solved_interrupt_sets_from_the_key_alone` |
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
  interrupts.py    F-interrupt rule: rigid, skip_known and beam decoders
  beam.py          beam decoder: F-interrupters + anti-repeat key skips, batched + reference
  stats/           IoC, entropy, chi2, doublets, periodic IoC/kappa scans, shared-key scan
  stats/fingerprint.py  murphy's constraints C1-C6 and the fingerprint gate
  scoring/         baseline rune n-gram scorer (Phase 2 replaces it), named presets,
                   calib/ (family-wise bars from observed maxima), beam_calib.py (beam nulls)
  generators/      keystream generators: sha256-ctr (nulls), mt19937-py27, numpy-pcg64
  corpus.py        rune corpora built by scripts/build_corpus.py
  controls.py      plant-and-recover harness (Rule 2)
  oracle.py        full-page, multi-page, family-wise verification (Rule 3)
  ledger.py        append-only JSONL ledger, Dukotah-compatible export
  lanes.py         lane YAML schema
  queue.py         queue.json (Hunter's approvals)
  runner/          lane runtime: pipeline, control, gate, sweep (detach/resume), crossers
  gpu/             Phase 3: the CUDA beam and mt19937-py27 kernels and their parity/bench command
data/raw/          5 git submodules (read-only): rtkd, scream314, cicada_tools, dukotah, jens-wedin
data/canon/        lp2_runes.json, lp1_runes.json, solved_sections.json, pins, divergences
data/reference/    cicada_tools' own decode of the solved sections
data/corpora/      built by scripts/build_corpus.py (not committed)
lanes/             one YAML per attack lane (_template.yaml = queue item 1)
ledger/            ledger.jsonl (created by the first pre-registration)
runs/              sweep state per lane (not committed)
scripts/           build_canon.py, extract_reference.py, fetch_raw.sh, setup.sh, build_corpus.py,
                   calibrate.py, threshold_for.py, check_results.py, validate_ledger.py, hooks/
tests/             Rules 1-3 and the toolbox
```

## Roadmap

- **Phase 2: rune-native scorer.** Build Gutenberg, Cicada-register and alternate-language
  corpora; a 6–8-gram Kneser-Ney model with a word-boundary symbol, exported as a flat
  `float32` table; null distributions per page length and register; a power table
  (`reports/scorer_power.md`); and the beam interrupt decoder (built:
  `reports/beam_decoder.md`; it recovers a planted DIVINITY key the rigid decoder rejects).
- **Phase 3: CUDA sweep engine.** GPU kernels behind `runeforge sweep --backend gpu`,
  parity-tested against the CPU runner, at ≥ 10⁷ seeds/s, and the Dukotah never-run/parked
  queue. The queue
  starts with the Python 2.7 MT "exact" lane (`lanes/_template.yaml`).
- **Phase 4: open research lanes.** Doublet-site image audit (P-8, which also settles
  DV-01), a keyed-increment chain cipher, a Z340-style transform screener, and OutGuess
  with non-default keys.
