# Liber Primus Solver — Project Spec for Claude Code

**Project name:** `runeforge` (working title — rename freely)
**Owner:** Hunter
**Target machine:** Windows 11 + WSL2 (Ubuntu), NVIDIA RTX GPU, Python 3.11+, CUDA 12.x
**Goal:** A control-validated, GPU-accelerated cryptanalysis pipeline for the 56 unsolved pages of Cicada 3301's Liber Primus (LP2), built to the standard the CicadaSolvers community actually uses, so that every result — positive or negative — is reproducible, pre-registered, and publishable.

---

## 0. Read this first (for Claude Code)

This is not a "cipher cracker" toy. The unsolved pages have survived ~10¹⁰ decode attempts by three independent 2026 projects (Dukotah/cicada3301, Leo-Y-Zhang/LiberPrimusAnalysis, jens-wedin/liber-primus). Every classical family is **closed**. The ciphertext is flat at every statistical order (IoC 1.000, entropy 4.857/4.858 bits) except one anomaly: adjacent identical runes occur at 0.66% instead of the expected 3.45% (z ≈ −17).

The project's value comes from three things the existing tools lack:

1. A **rune-native language-model scorer** (none exists; current scorers have 0.00 power on non-English plaintext).
2. A **CUDA sweep engine** fast enough to finish the seeded-PRNG and derived-key lanes that Dukotah's ledger marks `never-run` or `parked` (most generators are only ~3% enumerated).
3. **Rigor as a first-class feature**: planted-key controls, calibrated null distributions, family-wise significance bars that rise with trial count, and a ledger that records every negative.

**Three non-negotiable rules** (enforce them in CI):

- **Rule 1 — Reproduce before you attack.** No attack runs until the pipeline re-derives all nine solved LP sections byte-for-byte from the raw rune transcription.
- **Rule 2 — Plant before you claim.** Every attack lane must recover a synthetic planted key on a synthetic page before its null result on real pages counts. An attack with no passing control is "untested," not "negative."
- **Rule 3 — Hits must survive the oracle.** A candidate decode is a "hit" only if it (a) beats the family-wise threshold for that lane's trial count, (b) decodes the *entire* page, not a fragment, and (c) passes `verify_solution.py`. "Looks like English for 20 runes" is the archetypal false positive.

### What NOT to build

- Do not build another Caesar / Atbash / Vigenère / totient brute-forcer as a *product*. Boxentriq, idkfa-web, cicada_tools and LiberPrayground already do this and the families are closed. We implement these only as **regression tests** (Phase 1) and as **primitives** the sweep engine composes.
- Do not use LLMs (including Claude) to read the rune images. GPT-4-class vision scored 0.145 alignment on re-transcription. LLMs here write code and review literature; they do not read pages.
- Do not chase "art-inspired" orderings (Möbius strips, spirals, rail-fences on illustrated pages) — Pitchfork-and-Torch already ran them, all null.

---

## 1. Architecture

```
runeforge/
├── CLAUDE.md                  # the rules above + conventions, for Claude Code
├── pyproject.toml
├── data/
│   ├── raw/                   # git-submodules or vendored copies (see §2.1)
│   ├── canon/
│   │   ├── lp2_runes.json     # canonical ciphertext, indices 0–28, with page/line/word structure
│   │   ├── lp2_runes.sha256   # pinned hash — every run asserts this
│   │   └── solved_sections.json  # the 9 solved sections: runes, method, key, interrupts, plaintext
│   └── corpora/               # transliterated training text for the scorer (Phase 2)
├── runeforge/
│   ├── gematria.py            # the 29-rune alphabet, prime values, transliteration rules
│   ├── transforms/            # composable cipher primitives (Atbash, shift, Vigenère, stream-subtract, chain)
│   ├── interrupts.py          # F-interrupt handling: rigid, skip, and beam-search decoders
│   ├── scoring/               # n-gram scorer, calibration, null distributions, register packs
│   ├── stats/                 # IoC, entropy, doublet rate, kappa, chi-square, autocorrelation
│   ├── controls.py            # plant-and-recover harness
│   ├── oracle.py              # verify_solution: full-page re-decode + solved-page regression
│   ├── ledger.py              # append-only JSONL ledger of every lane run (pre-registration + result)
│   └── gpu/                   # CUDA kernels (CuPy RawKernel / Numba) — Phase 3
│       ├── kernels/
│       │   ├── decrypt_mod29.cu
│       │   ├── score_ngram.cu
│       │   └── prng_*.cu      # one per generator family
│       └── sweep.py           # lane runner: chunking, checkpoint/resume, threshold logic
├── lanes/                     # one YAML per attack lane: hypothesis, params, control spec, threshold
├── tests/                     # pytest; Rule 1 and Rule 2 live here
├── notebooks/                 # exploratory only, never load-bearing
└── reports/                   # auto-generated lane reports (markdown) for publishing
```

**Tech stack:** Python 3.11, NumPy, CuPy (CUDA), Numba (`@cuda.jit` for simpler kernels), pytest, Pydantic for lane/ledger schemas, `rich` for CLI output, KenLM or a hand-rolled Kneser-Ney for the n-gram model, PyTorch only if the char-Transformer scorer (Phase 2b) is pursued.

**Conventions:**
- All cipher arithmetic is on rune index 0–28, **mod 29**. Prime values (2…109) are used only for "GP-sums," never for shift arithmetic.
- Page numbering: **LP2 scheme, 0.jpg–57.jpg**. Every output states `numbering: "LP2-0-57"`. (The "complete set" scheme runs 0–74; LP2 page 56 = book page 73. Never mix them silently.)
- Every lane is a YAML file in `lanes/` and gets a ledger row *before* it runs (pre-registration) and after (result). No ad-hoc runs.

---

## 2. Phase 1 — Foundation (target: 1–2 weeks)

**Deliverable:** `pytest` passes with all nine solved sections reproduced from raw runes, the oracle works, and the stats module reproduces the published numbers.

### 2.1 Data ingestion

Vendor these repos under `data/raw/` (read-only; never edit):
- `rtkd/iddqd` — master transcription with delimiters `-` word, `.` clause, `&` paragraph, `/` line, `%` page; plus index, keys, translations.
- `scream314/cicada3301` — Unicode-rune per-page transcription with solved keys (`liber_primus.md`), full image set.
- `yo-yo-yo-jbo/cicada_tools` — reference transformer pipeline with exact interrupt indices (`section.json` per page).
- `Dukotah/cicada3301` — `liber-primus/PROBLEM.json` (SHA-256-pinned ciphertext), `verify_solution.py`, `LEDGER.json`, `ELIMINATION-LEDGER.md`, `handoff/PARKED.md`, `handoff/PARKED-SWEEPS.md`.
- `jens-wedin/liber-primus` — `validate_solved.py` and controls.

Write `scripts/build_canon.py` that:
1. Parses rtkd's master transcription into `lp2_runes.json` with structure `{page: [{line: [{word: [idx, …]}]}]}`.
2. Cross-checks rune-for-rune against scream314's Unicode transcription and Dukotah's `PROBLEM.json`. **Any disagreement is a hard error** — all three lineages are documented as identical over 13,136 runes; if ours differs, our parser is wrong.
3. Pins the SHA-256 and writes it to `lp2_runes.sha256`.

### 2.2 `gematria.py`

The 29-rune table (index → rune → Latin → prime):

| idx | rune | Latin | prime | | idx | rune | Latin | prime |
|---|---|---|---|---|---|---|---|---|
| 0 | ᚠ | F | 2 | | 15 | ᛋ | S | 53 |
| 1 | ᚢ | U | 3 | | 16 | ᛏ | T | 59 |
| 2 | ᚦ | TH | 5 | | 17 | ᛒ | B | 61 |
| 3 | ᚩ | O | 7 | | 18 | ᛖ | E | 67 |
| 4 | ᚱ | R | 11 | | 19 | ᛗ | M | 71 |
| 5 | ᚳ | C/K | 13 | | 20 | ᛚ | L | 73 |
| 6 | ᚷ | G | 17 | | 21 | ᛝ | NG/ING | 79 |
| 7 | ᚹ | W | 19 | | 22 | ᛟ | OE | 83 |
| 8 | ᚻ | H | 23 | | 23 | ᛞ | D | 89 |
| 9 | ᚾ | N | 29 | | 24 | ᚪ | A | 97 |
| 10 | ᛁ | I | 31 | | 25 | ᚫ | AE | 101 |
| 11 | ᛄ | J | 37 | | 26 | ᛡ | Y | 103 |
| 12 | ᛇ | EO | 41 | | 27 | ᛠ | IA/IO | 107 |
| 13 | ᛈ | P | 43 | | 28 | ᛠ | EA | 109 |
| 14 | ᛉ | X | 47 | | | | | |

> Verify this table against `cicada_tools` and `scream314` on ingest — cite the source in a test. (Indices 27/28 and the exact glyphs for IA/IO vs EA differ between fonts; the *index order* is what matters.)

Functions needed:
- `rune_to_idx`, `idx_to_rune`, `idx_to_latin`, `idx_to_prime`
- `transliterate_english(text) -> list[int]` implementing the authors' spelling rules: digraphs TH / NG / OE / EO / AE / EA / IA matched **per word, greedy, never across word boundaries**; K→C (idx 5), Q→CW, V→U, Z→S as the solved pages do (BOOC, CNOW, YOV, CWESTIAN). Make the rule set data-driven so Phase 2 can test variants.
- `gp_sum(indices) -> int` and `is_prime` — needed to reproduce the "every sentence of A Warning is prime" and the two magic squares (sums 1033 and 3301).

### 2.3 `transforms/` — composable primitives

Each transform is a pure function `(cipher_idx: ndarray, key_state) -> plain_idx` with an inverse, so the same code encrypts synthetic pages for controls. Minimum set:
- `atbash` (p = 28 − c)
- `shift(n)`
- `vigenere(key_indices)` and `beaufort`
- `stream_subtract(stream)` — generic "subtract keystream mod 29," used for totient, PRNG, running-key
- `totient_prime_stream` — φ(pₙ) = pₙ − 1 for n-th prime, the page-56 method
- `chain(increment_stream)` — cᵢ = cᵢ₋₁ + pᵢ + kᵢ (and inverse), the only published mechanism matching the doublet deficit
- `running_key(text_indices, offset, direction)`

### 2.4 `interrupts.py` — the F rule

Authors' house rule: a plaintext **F is written as an unencrypted ᚠ and does not advance the key**. But not every ciphertext ᚠ is an interrupt (Welcome: 11 of 25 ᚠ; Koan 2: 2 of 5; An End: 1 of 5). Implement three decoders:
1. `rigid` — no interrupts (baseline; known to reject correct keys).
2. `skip_known(indices)` — use a given interrupt set (for reproducing solved pages).
3. `beam(scorer, width)` — treat each ᚠ as a binary choice, beam-search with the Phase 2 scorer. Dukotah showed a planted key scores −6.835 rigid vs −4.170 beam; this is the difference between finding and missing a key.

### 2.5 Regression suite (Rule 1) — `tests/test_solved_pages.py`

Must reproduce, from `lp2_runes.json` + the earlier LP1 sections:

| Section | Method | Key / stream | Interrupts |
|---|---|---|---|
| A Warning | Atbash | — | — |
| Welcome | Vigenère | DIVINITY = idx [23,10,1,10,9,10,16,26] | rune idx 48,74,84,132,159,160,250,421,443,465,514 |
| A Koan (1) | Atbash → +3 | — | — |
| A Koan (2) | Vigenère | FIRFUMFERENFE = [0,10,4,0,1,19,0,18,4,18,9,0,18] (key runs across the page boundary) | 49, 58 |
| An End (LP2 p.56) | subtract φ(p) = p−1 mod 29 over primes 2,3,5,… | — | 56 |
| Some Wisdom, Divinity, Instruction, Parable, Loss of Divinity (LP2 p.57) | plaintext | — | — |

Plus: both "KNOW THIS" squares are magic under GP-sums (1033 and 3301); all nine sentences of A Warning have prime GP-sums (757, 1009, 691, 353, 769, 911, 1051, 859, 677). Assert the exact plaintexts from `cicada_tools`.

### 2.6 `stats/` and `oracle.py`

Reproduce the published fingerprint of LP2 pages 0–55 (12,956 runes) as tests, within tolerance:
- IoC (normalized) = 1.000; entropy = 4.857 bits; unigram χ² ≈ df per section
- doublet count = 86 (0.66%), expected 447 — this exact number is a test
- no kappa/periodic-IoC peak for periods 1–400 per section, 1–600 corpus-wide
- cross-section shared-keystream scan max z < 3.5

`oracle.py` wraps Dukotah's `verify_solution.py` semantics: given a claimed method + key, re-decode the full page, re-decode all solved pages under the same code path, and emit pass/fail. Every "hit" from Phase 3 is piped here automatically.

### 2.7 `ledger.py`

Append-only JSONL. Schema (Pydantic):
```
lane_id, hypothesis, family, params, control_spec, control_result,
n_trials, claim_bar, family_wise_bar, best_score, best_candidate_ref,
status: never-run | running | parked | negative | hit-unverified | hit-verified,
started, finished, host, git_sha, data_sha256
```
Match Dukotah's field names where they overlap so our rows can be submitted upstream.

---

## 3. Phase 2 — Rune-native scorer (target: 1–2 weeks)

**Deliverable:** `scoring.score(plain_idx) -> float` with calibrated null distributions per page length and per register, and a documented **power curve** (probability of detecting a planted key at a given score bar) for English, Latin, vowel-dropped English, and Cicada-register text.

### 3.1 Corpus (`data/corpora/`)

Build `scripts/build_corpus.py`:
- **English general:** Project Gutenberg subset (~50 MB), transliterated with `gematria.transliterate_english`.
- **Cicada register:** the solved LP plaintext, all PGP-signed Cicada messages, Crowley's *Liber AL*, Emerson's *Self-Reliance*, Blake, the Mabinogion, *Gödel, Escher, Bach* excerpts if licensable — the texts Cicada verifiably used.
- **Alternates (for power testing, not necessarily for scoring):** Latin (Vulgate), Welsh, vowel-dropped English, Old English (the Rune Poem).

Store each as rune-index arrays + metadata; everything is regenerated from scripts, never hand-edited.

### 3.2 Model

- **2a (required):** 6–8-gram Kneser-Ney over the 29-symbol alphabet, with word-boundary tokens as a 30th symbol (LP2 preserves word spacing, and the authors' word-length distribution is a signal: mean 4.47 vs 4.03 solved). Export as a flat log-prob table (`float32[29^k]`, backoff weights) that the CUDA kernel can load as a texture/constant buffer.
- **2b (optional):** small char-Transformer (≤10M params) for re-ranking beam-search survivors on CPU/GPU in PyTorch. Not used in the inner sweep loop.

### 3.3 Calibration and power (this is the part nobody has done)

- For each page length L ∈ {100, 250, 500, 1000, full-page} and each register, draw 10⁴ random rune strings → null distribution of score; store mean/sd.
- For each register, plant 1,000 synthetic keys under each transform family, decode, score → **power at the claim bar** (Dukotah's −5.5) and at the family-wise bar.
- Report the table. Target: power ≥ 0.9 on English *and* ≥ 0.5 on Latin / vowel-dropped at the claim bar. If Latin power is still ~0, that's a published finding too.
- Family-wise bar: `bar(N) = μ_null − sd_null · sqrt(2 ln N)`; for N = 2³² Dukotah's was −12.06. Compute ours, don't copy theirs.

---

## 4. Phase 3 — CUDA sweep engine (target: 3–5 weeks)

**Deliverable:** `runeforge sweep lanes/<lane>.yaml` runs a lane end-to-end on the GPU with checkpoint/resume, writes the ledger, and auto-pipes any above-bar candidate to the oracle.

### 4.1 Inner loop (per candidate key/seed)

```
1. generate keystream k[0..N) from (family, seed/params)
2. apply anti-repeat filter model (optional, per lane): if decrypt would produce c[i]==c[i-1], keep with p_keep≈0.18 else rewrite — implement as the *inverse* on decode
3. p[i] = (c[i] − k[j]) mod 29, with interrupt handling (rigid in the sweep; beam only on survivors)
4. score = Σ log-prob n-gram(p)   (table in constant/texture memory)
5. if score > lane.claim_bar: write (seed, score, page) to survivors buffer
```

Implement 1–4 as a single CuPy `RawKernel` per family (one thread = one seed, pages looped inside, early-exit when partial score falls below a running threshold). Target ≥ 10⁷ seeds/s on an RTX 40-series for 32-bit seed families; Dukotah's CPU rate was 7.7×10⁴/s on six cores, and they estimate 10³–10⁵× is what unlocks the >32-bit spaces.

### 4.2 Lane queue (from Dukotah `handoff/PARKED-SWEEPS.md` and `LEDGER.json status=never-run`)

Priority order:
1. **Python 2.7 Mersenne Twister, "exact" lane** — parked at 44.14% on 2026-09-15; resume and finish.
2. **Unswept 32-bit generators:** PHP `mt_rand`, .NET `System.Random`, ISAAC, Blum-Blum-Shub (small moduli), 32-bit LFSRs, xorshift32/64*, RC4 keystream (short keys from Cicada vocabulary), Marsaglia KISS. Each is its own `prng_<name>.cu`; validate each against the reference implementation in `tests/test_prng.py`.
3. **Derived-key lanes B-04 / B-05:** KDF outputs (SHA-256/512, PBKDF2, scrypt with Cicada-vocabulary passwords × salts such as 3301, 1033, page numbers, prime values) used as keystream or as seed.
4. **Each of the above × {raw, Atbash, chain-increment, first-difference} ciphertext views × {filter on, filter off}.**

Every lane YAML declares: hypothesis, generator, seed range, chunk size, ciphertext view, filter model, scorer register, claim bar, family-wise bar, control spec (planted seed + synthetic page), and the resume cursor.

### 4.3 Hit handling

Survivors (score above claim bar) → CPU beam decoder with interrupts → full-page score → family-wise bar check → `oracle.verify` → ledger `hit-unverified` or `hit-verified`. Generate a `reports/<lane>.md` with the top-20 survivors, their scores vs the null, and the control recovery result, regardless of outcome.

### 4.4 Ops

- Checkpoint every chunk (seed cursor + survivors) to disk; `--resume` is the default.
- `runeforge status` prints the ledger as a table.
- Long runs: `nohup` inside WSL2 or a systemd user unit; Windows power settings must not sleep the GPU.

---

## 5. Phase 4 — Open research lanes (pick after Phase 3 is stable)

- **4a. Doublet-site audit (lane P-8).** OpenCV template-matching re-read of the 86 doublet sites plus the ~41 unadjudicated oversized/mid-size marks; output a per-site table with crops. If ≥20 sites show the canonical count is off by one, the anti-repeat model is overturned — the single highest-leverage small project.
- **4b. Keyed-increment chain cipher.** cᵢ = cᵢ₋₁ + pᵢ + kᵢ with kᵢ from the Phase 3 generator families (sequence-keyed variants already failed; stream-keyed is open). Reuse the sweep engine with the `chain` view.
- **4c. Transform screener (Z340 method).** Enumerate page-order permutations, red/black rune separation, and grid read-outs; filter with substitution-invariant stats (repeating-bigram count, doublet rate, periodic IoC) against 10⁴ random-permutation nulls; run the scorer only on survivors.
- **4d. OutGuess with non-default keys** (control G-02 "not yet done") — Cicada-vocabulary key list × all 75 images.

---

## 6. Definition of done (per phase)

- **P1:** `pytest` green; `runeforge canon --verify` matches the pinned SHA-256; `runeforge stats` reproduces the published fingerprint; README documents numbering scheme.
- **P2:** power table published in `reports/scorer_power.md`; CUDA-loadable table exported; beam decoder recovers the planted DIVINITY key on a synthetic Welcome page from a rigid score of ≈ −6.8.
- **P3:** at least one `never-run` lane finished with a passing control and a ledger row; throughput ≥ 10⁷ seeds/s measured and logged; resume works across a forced kill.
- **Publishing:** open a PR or issue on Dukotah/cicada3301 (or the cicada-solvers org) with the ledger rows and the lane report; post the summary in the CicadaSolvers Discord's relevant channel. Negative results count.

---

## 7. Kickoff prompts for Claude Code

**Session 1 (Phase 1 scaffolding):**
> Read this spec and `CLAUDE.md`. Create the repo layout in §1 with pyproject, pre-commit (ruff, black), and pytest. Vendor the five data repos from §2.1 as git submodules under `data/raw/`. Implement `gematria.py` exactly per §2.2 with the table verified against `cicada_tools`, then `scripts/build_canon.py` per §2.1 with the three-way cross-check as a hard error. Stop and show me the canon SHA-256 and rune count before going further.

**Session 2 (Phase 1 regression):**
> Implement `transforms/`, `interrupts.py` (rigid + skip_known), and `tests/test_solved_pages.py` per §2.3–2.5. All nine solved sections must reproduce exactly, including the magic squares and prime sentence sums. Then implement `stats/` and make the §2.6 fingerprint numbers tests. Don't implement any attack yet.

**Session 3 (Phase 2):**
> Build the corpora per §3.1, the 8-gram KN scorer per §3.2a with CUDA-ready export, and the calibration + power harness per §3.3. Deliver `reports/scorer_power.md`. Then implement the beam interrupt decoder and show it recovering a planted DIVINITY key that the rigid decoder rejects.

**Session 4 (Phase 3):**
> Implement `gpu/sweep.py` and the first kernel: Python 2.7 MT seed sweep with the anti-repeat filter model, per §4.1. Validate the kernel against the CPU reference on 10⁴ seeds, benchmark seeds/s, and resume the parked "exact" lane from the §4.2 cursor with a passing planted-seed control. Write the ledger row before the run starts.

---

## 8. Reading list to attach as context in Claude Code

- cicadasolvers.com Quick Start (the "already tried" primer)
- Boxentriq Liber Primus guide + Totient Cipher page
- Connor Tumbleson's seven-part series (connortumbleson.com) + repo `iBotPeaches/cicada_3301`
- `Dukotah/cicada3301` README, `ELIMINATION-LEDGER.md`, `SOLVERS-DOSSIER.md`, `handoff/PARKED.md`, `handoff/PARKED-SWEEPS.md`
- `Leo-Y-Zhang/LiberPrimusAnalysis/docs/FINDINGS.md` (the doublet fingerprint simulations)
- Oranchak / Blake / Van Eycke, Z340 solve (2020) — the transform-screener method
- Aldarrab & May 2020 (arXiv 2012.15229); Kambhatla et al. 2018 (ACL D18-1102) — neural decipherment baselines
