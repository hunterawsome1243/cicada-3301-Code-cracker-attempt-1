# The Phase 2 Kneser-Ney scorer — design record

Status: design fixed 2026-10-27 after a three-design panel (compatibility-first, kernel-first,
power-first) scored by three independent judges; the kernel-first design won 2 of 3 and the
grafts below were taken from the other two. Spec: `docs/liber-primus-solver-spec.md` §3.1–3.3
and §6 (P2). Everything here is an implementation contract; the numbers it produces are in
`reports/scorer_power.md`, never here.

## 0. Decisions the panel left open, settled here (recorded, never tuned after a fit)

| decision | choice | why |
|---|---|---|
| held-out mechanism | the 90/10 **word** split lives in the preset spec (`PRESETS[name]["split"]`); no new corpora | the frozen `tests/test_corpus.py` pins the corpus set (`ALL == sorted(bc.SPECS)`); the frozen `control.plant_source` stays as it is (TR-9 asks for `heldout:<corpus>`) |
| where sparse / wb presets are refused | `presets.split_preset` (KeyError naming the dense presets) **and** `LaneSpec.decoder_problems` | `runeforge control` (cli) skips `runnable_problems`; `beam._tables` must never see a sparse scorer |
| CPU sparse lookup | `np.searchsorted` over sorted packed `uint64` keys | the judges measured hash probing and searchsorted at the same cost in numpy (0.059 vs 0.058 s per 983k queries); the hash exists for the kernel only |
| export | sorted arrays **and** the open-addressing hash layout, both in the `.npz`; the scalar reference probes the **hash** | proves the kernel layout against the arrays score_batch uses |
| dense levels for sparse presets | `D = 4` (2.9 MB float32); the harness measures D = 4 vs 5 throughput | one fewer probe vs 82 MB on the device: measure, do not guess |
| beam-compatible KN order | 4 by default (`kn4-cicada`, `kn4-lp-heldout`); `kn5-cicada` offered for the comparison | 164 MB float64 per beam process at order 5 |
| discounts | modified KN (Chen & Goodman 1998) with the fallback rule in §2.3 | fixed before any fit; `discount_source` recorded per level |
| fingerprint scope | arrays + order + base + dense_levels + discounts only; never the preset name, git SHA or a timestamp | a rename or a commit must not invalidate a staged bar |
| claim bar in the power report | the α = 0.01 Gumbel bar at **N = 10⁶** | a 30-minute CPU screen's trial count; Dukotah's −5.5 is their bar at their lengths and is never pasted |
| family-wise bar in the report | α = 0.01 at **N = 2³²** | the lanes' typical seed space |
| "full page" row | **both** L = 240 (the lane window; installed bars exist) and L = 263 (the median of the 55 non-empty unsolved pages; range 66–277) | the spec asks for a page; 240 gives the installed-vs-refit scale check |
| intervals | 200-resample bootstrap of the block maxima on every bar; Wilson 95 % on every power cell | a point bar at 2³² from 100 block maxima carries ~1 β |
| wb boundary log-probs | **summed** (the word-length signal), divided by L = cipher runes; a `score_boundaries=False` variant is measured once in the report | the authors' word-length distribution is the signal the spec names |
| wrong-key-null check | a reported KS statistic per family, never an assert; the short-key Vigenère family is excluded from the "wrong key = uniform string" claim | a partially matching periodic key leaves structure |
| `--full` harness run (5–20 CPU-hours) | Hunter's call; the reduced-scale report is published first and says so | PREREG-budget rule |
| export artefacts (40–160 MB) | regenerated, gitignored; manifests (JSON) committed under `reports/kn-export/` | "CUDA-loadable table exported" is met by the script + manifest + round-trip test |

## 1. Files

| path | role |
|---|---|
| `runeforge/scoring/kn.py` | `KNScorer`: the model object (order n, base B, dense_levels D, per-level arrays), `score`, `score_batch`, `logprobs`, `distribution(history)`, `fingerprint`, `tables` (dense presets only), `export(path)`, `load_export(path)`, `reference_logprobs(...)` (scalar, probes the exported hash), `boundary_extend`. No fitting code. |
| `runeforge/scoring/kn_fit.py` | pure functions: `collect_counts`, `continuation_counts`, `discounts`, `estimate` → the per-level arrays; `build_hash` (open addressing, deterministic). |
| `runeforge/scoring/boundaries.py` | word-start masks: `window_starts(pages, window, offset=0)` from `canon.Page.words()`, `corpus_starts(word_ids)`, `sample_starts(rng, L, lengths)` from LP2's word-length histogram, `lp2_word_lengths()`. |
| `runeforge/scoring/presets.py` | edit: `model` key (`ngram` default, unchanged entries and fingerprints; `kn`), `split`, `dense_levels`, `boundary`; `get()` dispatch; `split_preset` refusals; `beam_compatible(name)`; `heldout_stream(corpus_name)`; `training_slice(corpus_name)`; `check_held_out` + derived-corpus rule. |
| `runeforge/scoring/__init__.py` | export `KNScorer`. |
| `runeforge/lanes.py` | `decoder_problems`: a sparse or wb preset with a `:beam*` decoder is a problem (belt and braces with `split_preset`). |
| `scripts/export_kn.py` | `--preset NAME --out DIR`: writes the export, reloads it, asserts bit-for-bit parity (1,000 random windows, 100 held-out windows, the all-F window, the longest-probe keys), prints sizes and the manifest. |
| `scripts/scorer_power.py` | the power harness (§6); writes `reports/scorer_power.json` and renders `reports/scorer_power.md`. |
| `tests/test_kn.py`, `tests/test_scorer_power.py` | new test files (`tests/*` existing files are frozen). |
| `runeforge/gpu/kernels/README.md` | the `knx-1` export layout and the lookup algorithm a future `score_ngram.cu` implements. |
| `TOOLBOX_REQUESTS.md` | TR-7 install the staged KN calibrations (only after 10⁶-draw fits); TR-8 `runeforge/stats/decode.NON_ENGLISH_PRESETS` → KN register presets; TR-9 `heldout:<corpus>` plant source in `control.plant_source`; TR-10 freeze kn.py, kn_fit.py, boundaries.py, test_kn.py when green. |

## 2. Model

### 2.1 Alphabet and keys
Symbols 0..28 are runes; in a wb model symbol 29 is the word boundary; base B = 29 (nb) or
30 (wb). A k-gram (x_{i-k+1} … x_i) packs as `key = Σ_j x_{i-k+1+j} · B**(k-1-j)`: **oldest
most significant, newest least significant**. Hence the (k−1)-history of a position is
`H mod B**(k-1)` where H is the rolling (n−1)-history `H ← (H·B + x) mod B**(n-1)` (the beam's
`(h*N + x) % hist_mod`); the gram key of (history, x) is `hist·B + x`; the lower history drops
the oldest symbol: `h' = h mod B**(k-2)`; a gram's history is `key // B`; its suffix is
`key mod B**(k-1)`. Max key 30**8 < 2**40: uint64 (and int64) hold every key. All key
arithmetic in explicit `np.uint64` / `np.int64`; never mix the two (numpy promotes to float64).

### 2.2 Fields
`order n (1..8)`, `base B`, `boundary (None | 29)`, `dense_levels D (1..min(n, 5))`,
`discounts float64[n, 3]`, `discount_source: list[str]`, `version "knx-1"`.
- `dense_lp[k-1] = float32[B**k]`, k = 1..D: the **complete** interpolated log2 P_k(x | k−1
  history) at every packed k-gram key (unseen grams and histories resolved).
- `dense_bow = float32[B**D]` (iff D < n): log2 γ_{D+1}(h) by packed D-gram key, 0.0 for
  histories unseen at level D+1.
- sparse levels k = D+1..n: `keys uint64[M_k]` ascending, `lp float32[M_k]`, `bow float32[M_k]`
  (bow of this k-gram as a history of level k+1; all 0.0 at k = n).
- `tables` (property, dense presets only: D == n and B == 29): the **same list object** every
  call (`beam._tables` caches by list identity), `[dense_lp[i].reshape(B**i, B)]`; a sparse or
  wb model raises `AttributeError("… pairs with the rigid decoder only …")`.

### 2.3 Fit (`kn_fit.estimate`)
Sequences: nb — the corpus runes with `word_ids < train_words` (one contiguous prefix);
lp-solved presets — one sequence per solved section minus `exclude`; wb — per sequence,
`concat over words ([29] + runes(word)) + [29]` (a boundary before every word and one trailing).
N-grams never cross a sequence join; no start symbol.

1. Raw counts per level k = 1..n: `np.unique(packed k-grams, return_counts=True)`.
2. Continuation counts for k < n: from the next level's distinct keys `U_{k+1}`, suffix
   `U_{k+1} mod B**k` → `np.unique(..., return_counts=True)` = N1+(· g). The level-k key set is
   `U_k` (raw count > 0); a gram seen only at a sequence start has continuation count 0 and is
   stored with P_k = γ_k(h)·P_{k−1} (h seen) or P_{k−1} (h unseen). Effective count at k < n is
   the continuation count; at k = n the raw count.
3. Discounts per level from that level's effective counts-of-counts n1..n4:
   `Y = n1/(n1+2n2)`, `D1 = 1 − 2Y n2/n1`, `D2 = 2 − 3Y n3/n2`, `D3+ = 3 − 4Y n4/n3`.
   **Fallback rule (fixed):** D1 is undefined when n1 == 0 or n2 == 0 → D1 = 0.5; D2 is
   undefined when n2 == 0 or n3 == 0 → D2 = D1; D3+ is undefined when n3 == 0 or n4 == 0 →
   D3+ = D2; then clip D_r to [0.05, r]. `discount_source[k]` ∈ {`modified-kn`, `partial:D2<-D1`,
   `partial:D3<-D2`, `partial:D2<-D1,D3<-D2`, `fallback-0.5`}. A preset may pin `discounts`
   explicitly (tests).
4. Probabilities, lowest level first. Level 1: C = Σ cc_1, N_j = symbols in class j;
   `P_1(w) = max(cc_1(w) − D(cc_1(w)), 0)/C + γ_1/V`, `γ_1 = (D1 N_1 + D2 N_2 + D3+ N_3+)/C`, V = B
   (uniform floor: every symbol > 0). Level k ≥ 2, seen history h: `P_k(w|h) = max(cc − D(cc), 0)/cc(h)
   + γ_k(h) · P_{k−1}(w|h')`, `γ_k(h) = (D1 N_1(h·) + D2 N_2(h·) + D3+ N_3+(h·))/cc(h)`; unseen
   history: `P_k = P_{k−1}(w|h')` exactly (γ = 1, bow = 0, nothing stored). `P_{k−1}` is obtained by
   the model's own lookup on the finished lower levels (dense gather or sorted search) in float64.
   Dense level k ≤ D: materialise `lower = P_{k−1}[(h mod B**(k-2))·B + w]` broadcast over all
   histories, scale seen histories by γ_k(h), overwrite seen grams; one float32 cast at the end.
   Store `lp = log2 P` (float32); `bow` on the **lower** level's entry for every seen history.
5. Sanity (raise, never clamp): every dense row sums to 1 within 1e-9 before the cast (sample
   2,000 histories per level); no NaN/inf; lp ≤ 0; bow ≤ 0.
6. `distribution(history) → float64[B]` on the fitted float64 values (for the sum-to-1 test);
   the float32 tables are checked at 1e-5.

### 2.4 Scoring (the kernel's inner loop; scalar reference and numpy agree bit-for-bit)
Per position i with symbol x, m = min(i, n−1) history symbols available:
```
acc = 0.0 (float64)
for k = m+1 down to D+1:                 # sparse levels
    hk = H mod B**(k-1)
    if k-1 > D: (hit_h, bow) = lookup(level k-1, hk); if not hit_h: continue
    else:       bow = dense_bow[hk]
    (hit_g, lp) = lookup(level k, hk*B + x)
    if hit_g: return acc + float64(lp)
    acc += float64(bow)
kd = min(m+1, D)
return acc + float64(dense_lp[kd-1][(H mod B**(kd-1))*B + x])
```
then `H ← (H·B + x) mod B**(n−1)`. Window score = Σ positions / L, L = cipher runes (wb: boundary
symbols scored, not counted in L). `score_batch(plains (B_rows, L), starts=None, end_boundary=False)
→ float64[B_rows]` is the chain vectorised over all positions with compaction (searchsorted per
level on the live subset); `logprobs` returns the per-position vector; `score(plain)` =
`logprobs(plain).sum()/L` with the same `np.sum(dtype=float64)` call as the batch (|Δ| ≤ 1e-9
in the test). A wb model without `starts` raises ValueError. Scores of uniform noise under a
trained model are expected around −7…−8 at order 8 (units unchanged: mean log2-prob per rune).

### 2.5 Boundaries
Decodes arrive as pure (B, L) rune arrays; the cipher's word starts are window data
(`canon.Page.words()`, 2,928 LP2 words, mean 4.42, max 14) and never inferred from a decode.
`boundary_extend(x, starts, end_boundary)` inserts 29 before every True position (and at the
end when `end_boundary`). All rows of a batch share one mask. A window that cuts into a word has
`starts[0] = False`. wb is adjudication/report-only this phase: its null depends on the mask
(the harness measures masks drawn from the LP2 word-length histogram vs the 54 page-start
windows' own masks at L = 240 and reports the dependence); `split_preset` refuses every wb
preset with any decoder, so no lane can name one until a window-conditioning rule is staged.

## 3. Presets (`presets.PRESETS`; `model: "ngram"` entries byte-identical to today)

| preset | order | B | D | train | held out (plants) | beam |
|---|---|---|---|---|---|---|
| kn4-lp-heldout | 4 | 29 | 4 | lp-solved minus a-koan-1, the-loss-of-divinity | the two sections | yes |
| kn4-cicada | 4 | 29 | 4 | cicada-english words [0, ⌊0.9·n_words⌋) | its tail; lp-solved for lane controls | yes |
| kn5-cicada | 5 | 29 | 5 | same | same | yes (82 MB) |
| kn6-cicada | 6 | 29 | 4 | same | same | no |
| kn8-cicada | 8 | 29 | 4 | same | same | no |
| kn8-general | 8 | 29 | 4 | english-general 90 % words | tail | no |
| kn8-latin | 8 | 29 | 4 | latin 90 % | tail | no |
| kn8-old-english | 8 | 29 | 4 | old-english 90 % | tail | no |
| kn8-vowel-dropped | 8 | 29 | 4 | vowel-dropped-english 90 % | tail | no |
| kn8-cicada-wb | 8 | 30 | 4 | cicada-english 90 %, boundary-extended | tail | no |

`split = {"rule": "words [0, floor(0.9*n_words)) train", "train_words": int, "n_words": int,
"indices_sha256": corpus pin}` — the ints are filled from the built corpus and checked against
it at `get()` (a rebuilt corpus that moved the split is refused, not silently refit).
`heldout_stream(corpus)` returns the tail (runes, word_ids rebased). `check_held_out` keeps
refusing `corpus:<name>` for any name in `train`, follows `derived_from` (vowel-dropped-english
vs english-general share word ids and text), and keeps the `exclude` rule for `solved:<id>`.
`presets.get` stays `lru_cache`d; a fit takes 1–5 s.

## 4. Export (`knx-1`)
One uncompressed `.npz` + a JSON manifest (also stored inside the npz as `manifest`). Arrays,
all 1-D contiguous little-endian: `dense_lp float32[Σ_{k≤D} B**k]` (level k at `dense_off[k-1]`),
`dense_bow float32[B**D]` (iff D < n), `hash_keys uint64[Σ S_k]`, `hash_lp float32`, `hash_bow
float32` (sparse levels concatenated; `S_k` = next power of two ≥ 2·M_k; EMPTY =
0xFFFFFFFFFFFFFFFF; slot0 = `(key · 0x9E3779B97F4A7C15 mod 2**64) >> (64 − bits)`, linear
probing, insertion in ascending key order, `max_probe` recorded), `sorted_keys uint64[Σ M_k]`,
`sorted_lp`, `sorted_bow`, `discounts float64[n, 3]`. Manifest: version, order, base,
boundary_symbol, dense_levels, key_packing, per-level {kind, n_entries, offset, slots, bits,
mult, shift, max_probe, empty_key, discounts, counts_of_counts, count_type, discount_source},
score_rule, the lookup algorithm text, training {corpora, split, n_runes, indices_sha256s},
fingerprint, numbering "LP2-0-57". `load_export` rebuilds a scorer from the file (no refit)
whose fingerprint equals the manifest's; `reference_logprobs` is the scalar recursion over the
exported arrays, probing the hash, bit-for-bit equal per position to `logprobs`.

## 5. Beam compatibility
A KN scorer is beam-compatible iff B == 29 and D == n (order ≤ 5). Its `tables[i][h, x]` is
the same float32 entry `score_batch` gathers at position i (level min(i+1, n), prefix history
for i < kmax), so the beam's scorer-only sum equals `score_batch(plain)·L` to float64 summation
order (the 1e-9 replay-parity test; the GPU twin's 1e-6). `beam_kernel.prepare` is unchanged.
`split_preset("kn8-cicada:beam")` and every `<wb>:<decoder>` raise KeyError naming the dense
presets; `LaneSpec` refuses the same in `decoder_problems`.

## 6. Power harness (`scripts/scorer_power.py`)
`--quick` (default) | `--full`; `--workers 4`; `--section`; `--smoke` (tests); writes
`reports/scorer_power.json` and renders `reports/scorer_power.md` (line 1 "not a solve";
numbering, canon SHA-256, git SHA, scale and N in every caption; negatives first; the banned
word list of `scripts/check_results.py` run over the rendered text before it is written).
Read-only with respect to lanes and the ledger; reduced-scale fits go to
`reports/scorer_power/fits/` (marked `scale: reduced`, never installable); only `--full`
writes 10⁶-draw records to `reports/calib-staging/`.

Registers: english-general, cicada-english, latin, vowel-dropped-english, old-english (held-out
tails), plus the two held-out solved sections (true Cicada spelling, 1,533 runes, L ≤ 500,
labelled separately). Lengths: 100, 240, 250, 263, 500, 1000. Scorers: lp-ngram3-heldout,
cicada-ngram3, general-ngram3, kn4-lp-heldout, kn4-cicada, kn5-cicada, kn6-cicada, kn8-cicada,
kn8-general, kn8-latin, kn8-old-english, kn8-vowel-dropped, kn8-cicada-wb (boundary column).
Families on the real code paths (`pipeline.encrypt/decrypt` on a toy LaneSpec; `transforms`):
short-key Vigenère (period 8–13), atbash+shift, totient stream, sha256-ctr and numpy-pcg64
streams × combines {vigenere, beaufort} × views {raw, atbash, first-difference, chain-increment}.
Beam cells: {lp-ngram3-heldout, kn4-lp-heldout, kn4-cicada} × {beam, beam-skip, beam-skip-int}
at L ∈ {120, 240} under the forward models interrupters (1.0) / anti-repeat (0.19) / both,
plus the rigid decoder under the same forward models (the rigid collapse is a result).

Nulls per (scorer, L): (a) uniform strings via `calib.measure`; (b) wrong-key decodes per family
with a KS statistic against (a); (c) beam nulls via `beam_calib` at the fit's canonical-F count;
(d) wb nulls under sampled masks and the 54 page-start masks. Fits with `calib._gumbel_fit` on
block maxima (block 1,000) + 200-resample bootstrap; bars at N = 10⁶ (claim) and 2³²
(family-wise), α = 0.01; the installed lp-ngram3-heldout / cicada-ngram3 records at L 120/240
compared with the reduced refit as the scale check. Plants per (register, L, scorer): random
held-out windows, random key, encrypt, decode with the true key, assert decode == plaintext for
the rigid additive families, score under **every** scorer (one decode, many scorers → the
register confusion matrix = the adjudicator-register conditional measured); one power row per
(register, L, scorer) with the family list attached; power with Wilson intervals at the point
bar and both bootstrap bars; planted mean/sd/min; rank-1 over decoys for a subset. Reduced
scale: 100,000 null draws per (scorer, L), 200 plants per cell, beam cells 50 plants × 99
decoys, beam nulls 25,000, 2,000 wb masks; expected 30–60 min on 4 cores; a kill condition at
10 % of the budget (the smoke cell > 12 min aborts with the reason); per-section timings
printed next to the command. `--full`: 10⁶ draws, 1,000 plants, 200-plant beam cells.
Report sections: 0 reusable parts; 1 not covered (first); 2 nulls and bars; 3 power table;
4 confusion matrix; 5 beam cells; 6 boundaries (gain, mask dependence); 7 order and discounts;
8 throughput (D = 4 vs 5; L 240 and 1000; with the command); 9 the three conditionals and
reopens_if; 10 reproduce. The spec's target line ("power ≥ 0.9 English and ≥ 0.5 Latin /
vowel-dropped at the claim bar: met / not met per cell") is printed per cell, never as a verdict
word; a Latin power near 0 is published as the standing conditional (SESSION_PROMPT.md §B).

## 7. Tests (`tests/test_kn.py`)
sum-to-1 (1e-12 on `distribution`, 1e-5 on float32 tables; dense, sparse and wb; seen, once-seen,
unseen-at-top, never-seen and prefix histories) · the hand-computed order-2 example on
[0,1,0,1,2] under the §2.3 rule (expected values as `fractions.Fraction`) · order 1 = the
discounted unigram with D from counts-of-counts · continuation counts by brute force on a tiny
sequence · discount fallbacks and clamps, `discount_source` recorded · score_batch == per-row
score ≤ 1e-9 (L 1, 3, 7, 50, 240, 1000; dense, sparse, wb) · a row scores the same alone and in
a batch of 4096 · short positions use the lower-order distribution · an unseen history backs
off with weight one; a seen history with an unseen symbol uses the stored bow · export
round-trip: `reference_logprobs` bit-for-bit (500 random, 100 held-out, all-F, max-key and
longest-probe windows), layout invariants (slots, no duplicate keys, every key found within
max_probe), reloaded fingerprint equals · fingerprint: same data twice equal, one rune changed
differs, order/base differ, Phase 1 fingerprints pinned to the shipped calibration records ·
dense `tables` identity-stable, shapes, equal to `log2(distribution)`; sparse/wb `tables`
raises; `split_preset` and `LaneSpec` refusals · beam replay parity for kn4-lp-heldout and
kn4-cicada (numpy beam vs score_batch ≤ 1e-9; `decode_reference` path for path; GPU twin
skipped without numba) · WELCOME's 11-of-25 interrupters re-derived under kn4-lp-heldout ·
held-out refusals and `heldout_stream` word alignment; a 12-gram only in the tail is unseen ·
boundary extension and the L divisor · `calib.calibrate` on a KN preset (25,000 draws) and
`calib.load` of a staged record via a monkeypatched `CALIB_DIR` · determinism across two
subprocesses · throughput smoke (slow, prints keys/s). Corpus-dependent cases are marked
`raw` and skip without `data/corpora`.
