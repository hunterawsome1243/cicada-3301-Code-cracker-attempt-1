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
runeforge/gpu/parity.py
tests/test_gpu_beam.py
```

Until then a later edit of the kernel only invalidates its parity records: `sweep --backend gpu`
compares the record's `kernel_sha256` with the file. It does not touch any lane evidence.
