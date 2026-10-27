# TOOLBOX_REQUESTS

Claude writes requests here when a frozen tool (see FROZEN.txt) needs changing. Hunter approves or rejects; nothing in FROZEN.txt changes without an entry here.

## TR-1 (2026-10-22): install the beam decoders' calibrations — open

**Frozen path:** `runeforge/scoring/calib/presets/` (`runeforge/scoring/calib/*`).

**Why.** `threshold_for` reads bars only from that directory, and the beam decoders need their
own: a beam picks the best interrupt/skip path through a wrong key, so its noise scores sit above
the uniform strings the rigid calibrations were fitted on (see `runeforge/scoring/beam_calib.py`).
Until these files are installed, no `:beam*` lane has a bar (`runeforge lane` lists "no bar for
this lane's N"), the sweep refuses it, and `runeforge control` extrapolates its ceiling with a
beta from the per-plant maxima instead of the calibration (`control._beta`).

**What.** Copy the fitted files from `reports/calib-staging/` into
`runeforge/scoring/calib/presets/` unchanged, or refit them yourself:

```bash
for d in beam-skip beam-skip-int beam; do
  python scripts/calibrate.py --preset lp-ngram3-heldout:$d --L 240 --L 120 --workers 4
done   # writes straight into runeforge/scoring/calib/presets/
```

Each file records the scorer fingerprint `calib.load` checks, plus what `calib.load` does not
check (TR-5): `decoder_params` (pinned per decoder name in `presets.DECODER_PARAMS`), the
SHA-256 of `runeforge/beam.py` it was fitted with, and, for the interrupt decoders,
`canonical_F`. An interrupt decoder's wrong-key null rises with the window's canonical F count
(review, 2026-10-22), so `beam` and `beam-skip-int` are fitted at the most F's of any LP2
page-start window (L = 120: 10; L = 240: 14). Every compared window sits at or below its fit
(the 54 page-start windows per L; 2,563 of 2,875 L = 240 windows in review round 3); where the
F's fall matters as well as how many, so the 312 four-page L = 240 and 160 of 214 L = 120
windows not compared are a stated gap (`reports/beam_decoder.md` §7), not covered by proof; `beam-skip` ignores F's. All six are fitted on doublet-free ciphers (LP2 has
86 doublets in 12,956 runes; at a doublet a skip offers the beam no new choice, so fewer
doublets mean a higher null), and a path that uses up its key wraps round it, so no window's
own runes reach a wrong-key decode. All 54 page-start windows at L = 120 and 240 sit at or below
their fits for every decoder within sampling error (`scripts/beam_power.py`, windows); review
round 3 found the same for 2,563 of the 2,875 distinct L = 240 lane windows (the 312 four-page
ones were not compared), and the one 15-F window is refused. `LaneSpec.runnable_problems`
refuses a lane whose window holds more F's than its calibration, or whose calibration no
longer matches the decoder. Fit numbers and scale checks (on the fit's own draws; bars good to
about 1.5 beta): `reports/beam_decoder.md` §4. After installing, re-run any `:beam*` control so its ceiling
uses the calibrated beta. Any later edit of `runeforge/beam.py` or `DECODER_PARAMS` needs a
refit (the lane check says so).

## TR-2 (2026-10-22): freeze the beam decoder with its tests — open

Spec §6: the files of a phase are frozen in the commit that turns that phase's tests green. The
beam decoder is the part of Phase 2 that is built (the Kneser-Ney scorer is not). Proposed lines
for FROZEN.txt:

```
runeforge/beam.py
runeforge/scoring/beam_calib.py
tests/test_beam.py
```

`runeforge/scoring/presets.py` stays unfrozen (the Kneser-Ney presets go there), so the decoder
parameters are pinned by `test_the_decoder_parameters_are_pinned_to_their_names` instead.

## TR-3 (2026-10-22): the oracle cannot verify a beam decode — open

**Frozen path:** `runeforge/oracle.py`.

A crosser found under a `:beam*` preset reaches HIT_PROTOCOL step 5 with a decode record (the
sweep writes `decode_record`: plain, interrupts, skips) that the oracle has no way to take:

1. `--key-module`/`--lane` builds a `Claim` with no interrupts, and `Claim` has no skips at all,
   so `decode_claim` and `reencipher_matches` replay a rigid decode of the generator's keystream:
   a true beam-skip key fails criterion (d) and every page bar.
2. The per-page bars are fitted on uniform strings (`page_bar`); a beam decode chose its
   interrupt/skip path, so its bar must come from the beam's null (`beam_calib.measure` at the
   page's length), or the oracle overstates every beam decode's significance.

Proposed: a `--decode-record <json>` option (the crosser file's `decode_record`) that sets the
claim's interrupts and skips; `reencipher_matches` replaying skips the way
`runeforge/runner/crosser.py` `reencipher_forward` + `record_violations` do; and per-page bars
from `beam_calib.measure` when the claim names a beam decoder. Until then a beam crosser stops at
step 5 (a crosser is Hunter's anyway).

## TR-4 (2026-10-22): the 11-of-25 interrupt figure read as a per-F probability — open

**Frozen paths:** `runeforge/controls.py` (docstring of `synthetic_page`), `tests/test_controls.py`
(`interrupt_prob=11 / 25`), and CLAUDE.md's "Non-derivable facts" (not frozen by the hook, but
marked "do not alter").

"Welcome 11/25, Koan 2 2/5, An End 1/5" counts **ciphertext** ᚠ's that are interrupters. In
the keyed solved sections **every plaintext F** is an interrupter: 14 of 14 (WELCOME 11/11,
A KOAN 2 2/2, AN END 1/1; `canon.load_solved_sections()`). `runeforge/lanes.py` took 11/25 as
P(a plaintext F is interrupted) and defaulted `interrupt_prob` to 0.44; that is corrected to 1.0
(not frozen). The frozen `synthetic_page` docstring says "(the solved pages use 11/25, 2/5,
1/5)" next to its `interrupt_prob` parameter and its test plants at 11/25: the same misreading.
Proposed wording for both docstrings and CLAUDE.md: "not every ciphertext ᚠ is an interrupt
(Welcome 11/25, Koan 2 2/5, An End 1/5), but every plaintext F is (14/14)".

The same CLAUDE.md bullet (and spec §2.4 item 3) quotes Dukotah's "a planted key scores −6.835
rigid vs −4.170 beam" under the F-interrupt rule. Dukotah measured that pair under the
anti-repeat filter with a skip-aware beam (`data/raw/dukotah/PAPER.md` §3, 98.9 % rune
accuracy), not with interrupters. Our interrupter-only analogue is in
`reports/beam_decoder.md` §2 (rigid −6.644 vs beam −3.506 on a synthetic Welcome page).
Proposed: move the pair to the anti-repeat sentence, or say which mechanism it measures. The consequence for
LP2 is measured in `reports/beam_decoder.md` §3: under the every-F rule the template lane fails
the fingerprint gate on C1 (LP2 0–55 holds 458 ᚠ against 447 uniform).

## TR-5 (2026-10-22): bind beam calibrations to their decoder in `calib.load` — open

**Frozen path:** `runeforge/scoring/calib/__init__.py`.

`calib.load` checks only the scorer fingerprint. A beam calibration is valid only for the
decoder parameters, the `runeforge/beam.py` and (interrupt decoders) the canonical F count it
was fitted with. The unfrozen `beam_calib.calibration_problems` checks all three, from
`LaneSpec.runnable_problems` (the sweep preflight and `runeforge lane`), but two callers
reach `calib.load` without it: `scripts/threshold_for.py` (prints a bar for any window) and the
frozen control's `_beta` (the ceiling's extrapolation slope). Proposed: `calib.load` refuses a
record whose `decoder_params` differ from `presets.DECODER_PARAMS` or whose `beam_sha256`
differs from `runeforge/beam.py`, as it refuses a changed scorer; `threshold_for` takes an
optional window and refuses one with more canonical F's than `canonical_F`.

## TR-6 (2026-10-22): freeze the GPU beam kernel once it passes on the device — open

Spec §6 freezes a phase's files in the commit that turns its tests green. The kernel's tests are
green on its CPU twin and numba's simulator, but its device tests
(`test_the_cuda_kernel_on_the_device`) skip here, because this container has no GPU. After
`pytest -q tests/test_gpu_beam.py` and `python -m runeforge.gpu.parity lanes/_template.yaml`
pass on the RTX, the proposed lines for FROZEN.txt are:

```
runeforge/gpu/beam_kernel.py
runeforge/gpu/mt_kernel.py
runeforge/gpu/parity.py
tests/test_gpu_beam.py
tests/test_gpu_mt.py
```

Until then a later edit of a kernel only invalidates its parity records: `sweep --backend gpu`
compares the record's `kernel_sha256` and `mt_kernel_sha256` with the files. It does not touch
any lane evidence.

## TR-7 (2026-10-27): install the Kneser-Ney calibrations, only after 10^6-draw fits — open

**Frozen path:** `runeforge/scoring/calib/presets/` (`runeforge/scoring/calib/*`).

**Why.** The Phase 2 Kneser-Ney presets (`runeforge/scoring/presets.py`: `kn4-lp-heldout`,
`kn4-cicada`, `kn5-cicada`, `kn6-cicada`, `kn8-cicada`, `kn8-general`, `kn8-latin`,
`kn8-old-english`, `kn8-vowel-dropped`, `kn8-cicada-wb`; `docs/kn-scorer-design.md`) have no
record under the frozen calibration directory, so `threshold_for` has no bar for them,
`runeforge lane` lists "no bar for this lane's N" and the sweep refuses every `kn*` lane. The
reduced-scale fits the power harness writes to `reports/scorer_power/fits/` (100,000 draws,
marked `scale: reduced`) are for the report's scale check only and must never be installed.

**What.** Nothing is staged yet. Once `python scripts/scorer_power.py --full` (10^6 draws per
scorer and length, 5-20 CPU-hours: Hunter's call per the PREREG-budget rule) has written its
records to `reports/calib-staging/`, or after a direct fit:

```bash
python scripts/calibrate.py --preset kn8-cicada:rigid --L 240 --L 120 --out-dir reports/calib-staging
python scripts/calibrate.py --preset kn4-cicada:beam-skip --L 240 --workers 4 --out-dir reports/calib-staging
```

copy the files into `runeforge/scoring/calib/presets/` unchanged. Each record carries the scorer
fingerprint `calib.load` checks (a KN fingerprint covers order, base, dense_levels, discounts and
every table: a rename or a commit never changes it, one changed training rune does), and the
beam records carry what TR-5 asks `calib.load` to check. Only the dense presets
(`kn4-lp-heldout`, `kn4-cicada`, `kn5-cicada`) take a `:beam*` decoder; a sparse or
word-boundary preset with one is refused by `presets.split_preset` and `LaneSpec`, so no such
calibration can exist. The bars at N = 10^6 and 2^32 in `reports/scorer_power.md` are the
reduced-scale ones until this is done, and the report says so.

## TR-8 (2026-10-27): the non-English register stat should use the KN register presets — open

**Frozen path:** `runeforge/stats/decode.py` (`runeforge/stats/*`), line
`NON_ENGLISH_PRESETS = ("latin-ngram3", "old-english-ngram3")`.

**Why.** Every decode's language-agnostic stats record its best non-English register
(`decode.py`, `best non-English register`), so a sweep can be re-read for a non-English
plaintext later. The two order-3 Witten-Bell presets there are the Phase 1 baselines; the
Phase 2 presets of the same corpora are order-8 Kneser-Ney with a 90/10 word split, and the
vowel-dropped register (spec section 3.1; `vowel-dropped-english`, derived from
`english-general`) has no entry at all today.

**What.** Proposed line:

```python
NON_ENGLISH_PRESETS = ("kn8-latin", "kn8-old-english", "kn8-vowel-dropped")
```

Each preset fits in 1-5 s once per process (`presets.get` is cached) and skips when its corpus
is not built (the existing `CorpusMissingError` branch). The stat's scale changes with the
presets (an order-8 model's scores differ from the order-3 ones), so rows written before and
after the change are not comparable on that field: record the preset names with the stat, as
the field already does (`register`). Wait for `reports/scorer_power.md` section 4 (the register
confusion matrix) before approving, so the replacement is a measured gain and not a guess.

## TR-9 (2026-10-27): a `heldout:<corpus>` plant source for lane controls — open

**Frozen path:** `runeforge/runner/control.py`, `plant_source` (`solved[:<id>]` and
`corpus:<name>` today).

**Why.** A corpus-trained KN preset trains on the words `[0, floor(0.9 * n_words))` of its
corpus (`presets.SPLITS`, pinned to the built corpus and checked at `presets.get`); the tail is
held out of every KN preset with a pinned `split` by construction and is what the power harness
plants on (`presets.heldout_stream`). It is **not** held out of the Phase 1 `ngram` presets,
which train on the whole corpus: `check_held_out` refuses `heldout:cicada-english` for
`cicada-ngram3` (no split) and accepts it for `kn4-cicada`. A lane control cannot reach it:
`corpus:cicada-english` is rightly refused for `kn4-cicada` by `check_held_out` (training
text), and the unfrozen `check_held_out` already accepts `heldout:<name>` under that rule, but
the frozen `plant_source` raises `unknown plant source` for it. Until then a KN lane's control plants on `solved:<id>`
(lp-solved is held out of every corpus preset) or on another corpus, which measures power on a
different register than the harness does.

**What.** Proposed branch in `plant_source`, between the `corpus` branch and the `raise`:

```python
if kind == "heldout":
    presets.check_corpus_name(name)
    return presets.heldout_stream(name)[0].astype(np.int64)
```

`heldout_stream` refuses a corpus without a pinned split and a rebuilt corpus whose split
moved, so no test change is needed beyond a case in `tests/test_controls.py` (frozen) that a
`heldout:` plant on its own KN preset (`kn4-cicada`, `heldout:cicada-english`) passes
`check_held_out` and recovers, and that the same source is refused for `cicada-ngram3`
(`tests/test_kn.py` already pins both refusal and acceptance on `check_held_out`).

## TR-10 (2026-10-27): freeze the Kneser-Ney scorer with its tests — open

Spec section 6: the files of a phase are frozen in the commit that turns that phase's tests green.
`tests/test_kn.py` is green (78 tests, including the export round trip, the beam replay parity
for `kn4-lp-heldout` and `kn4-cicada` and WELCOME's 11-of-25 interrupters re-derived under
`kn4-lp-heldout`). Proposed lines for FROZEN.txt:

```
runeforge/scoring/kn.py
runeforge/scoring/kn_fit.py
runeforge/scoring/boundaries.py
tests/test_kn.py
```

`runeforge/scoring/presets.py` stays unfrozen (presets are added there; `SPLITS` is pinned by
the corpus `indices_sha256` and checked at `get`), and so do `scripts/export_kn.py` and
`scripts/scorer_power.py` (regenerating scripts). After the freeze a change to the fit
(discount rule, continuation counts, hash layout) invalidates every staged or installed KN
calibration through the fingerprint, as a change to `runeforge/beam.py` invalidates the beam
ones (TR-5), and the `knx-1` manifests under `reports/kn-export/` are regenerated with
`scripts/export_kn.py`.
