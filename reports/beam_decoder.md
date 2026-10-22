# The beam interrupt decoder — instrument report

**Not a solve.** This report is about an instrument: whether a decoder can follow F-interrupters
and anti-repeat key skips, and how hard it is for a wrong key to look like a right one under it.
No key space of the unsolved pages was searched, and nothing here is a decode of LP2.

numbering: "LP2-0-57" · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`
(12,956 runes, LP2 pages 0–55) · code at git `61eb0f5` · numbers from
`python scripts/beam_power.py` → [`beam_decoder.json`](beam_decoder.json) (155 s on 4 CPU cores)
unless stated otherwise.

## 0. Reusable parts

| part | where |
|---|---|
| decoder (batched numpy, plus a scalar reference that matches it path for path) | `runeforge/beam.py` `decode_batch`, `decode_reference`, `decode_record` |
| presets `<scorer>:<decoder>` | `runeforge/scoring/presets.py` `DECODERS`, `DECODER_PARAMS` |
| beam nulls and their fits | `runeforge/scoring/beam_calib.py`, `scripts/calibrate.py --out-dir` |
| six staged calibrations (lp-ngram3-heldout × 3 decoders × L 120, 240) | `reports/calib-staging/` (install: `TOOLBOX_REQUESTS.md` TR-1) |
| the forward model it inverts | `runeforge/runner/pipeline.py` `encrypt` |
| tests | `tests/test_beam.py` (85) |

## 1. What the decoder models

The rigid decoder spends one key symbol per rune. The first interrupter or skip puts every later
rune out of step with the key, so a correct key scores like noise. The beam follows
`pipeline.encrypt` position by position. The canonical runes are fixed by the ciphertext, so the
interrupt and repeat positions are known. Only the plaintext and the key position are hidden.

| decoder | F-interrupters | anti-repeat key skips | for lanes with |
|---|---|---|---|
| `rigid` | no | no | neither |
| `beam` | prior 15/16 | no | `filter_model: off`, `interrupt_prob` > 0 |
| `beam-skip` | no | p_keep 0.19, up to 6 per rune | `anti-repeat`, `interrupt_prob: 0` (the family the gate passes, §3) |
| `beam-skip-int` | prior 15/16 | p_keep 0.19, up to 6 per rune | both |

All presets use beam width 8. An interrupt is allowed only where the canonical rune is F: the
key holds, and the plaintext is F. A skip of s symbols is exact, not guessed: each dropped key
symbol must re-encipher the same rune to a canonical repeat of the previous one, so s skips need
s equal key symbols in a row.

The objective is the scorer's log2-probability plus the log2 transition priors. The lane scores
the returned plaintext with the scorer alone, as it scores a rigid decode.

Where the parameters come from:
- **interrupt_prior 15/16:** the rule of succession on 14 of 14 plaintext F's being interrupters
  in the keyed solved sections.
- **p_keep 0.19:** LP2's 86 doublets against 447 expected.
- **max_skip 6:** more than 6 drops at one rune has probability ~1e-11 per rune.
- **width 8:** §6.

A decoder may not model more than its lane does: `LaneSpec.decoder_problems` refuses
interrupters with `interrupt_prob: 0`, and skips without the filter.

**Key budget.** Every caller that compares a decode with a null passes exactly the window's
length in key symbols. That holds for the control's plants, decoys and ceiling, `runeforge null`,
the sweep and `runeforge score`. A path that uses up its key wraps round to its start
(`k[j mod K]`), and those runes are recorded as fill. Under a wrong key a wrapped decode is as
random as any other.

## 2. Reproduction before power (Rule 1)

Given only the key and no interrupt list, the beam re-derives every keyed solved section, under
three scorers. `general-ngram3` and `cicada-ngram3` never saw Liber Primus text; `lp-ngram3-heldout`
was trained on these three sections, so its rows are mechanics only.

| section | ciphertext ᚠ | published interrupters | beam interrupters | same set | plaintext exact | rigid score → beam score (general-ngram3) |
|---|---|---|---|---|---|---|
| WELCOME | 25 | 11 | 11 | yes | yes | −8.521 → −3.378 |
| A KOAN 2 | 5 | 2 | 2 | yes | yes | −8.089 → −3.137 |
| AN END | 5 | 1 | 1 | yes | yes | −6.183 → −3.621 |

Same set and exact plaintext under all three scorers (`beam_decoder.json`, `solved_sections`;
test `test_the_beam_rederives_the_solved_interrupt_sets_from_the_key_alone`).

**Planted DIVINITY key on a synthetic Welcome page** (spec P2). The plaintext is A KOAN (1), the
first 515 runes, held out of the scorer. It is enciphered with WELCOME's key DIUINITY, and every
plaintext F is an interrupter: 8 of them, the first at rune 53.

| decoder | score (lp-ngram3-heldout) | runes recovered | interrupt set |
|---|---|---|---|
| rigid | −6.644 | 18.3 % | — |
| beam | −3.506 | 100 % | exact |

Dukotah's figures for the same contrast are −6.835 rigid vs −4.170 beam, under their own scorer.
They are quoted only for the shape; their bars are not ours.

## 3. The interrupt rule and LP2's ᚠ count

"WELCOME 11 of 25" counts **ciphertext** ᚠ's that are interrupters. Every **plaintext** F in
the keyed solved sections is an interrupter: 14 of 14 (11/11, 2/2, 1/1). This project's lanes
had defaulted `interrupt_prob` to 0.44, reading the first figure as the second. The default is
now 1.0, and the frozen texts that carry the misreading are TR-4.

Under the every-F rule, the template lane's family fails the fingerprint gate
(`runeforge.runner.gate`, 12 keys of mt19937-py27, anti-repeat):

| interrupt_prob | gate |
|---|---|
| 0.0 | GATE PASS |
| 0.1 | GATE PASS (marginal: C3 on 2 of 12) |
| 0.44 (the misreading) | GATE PASS (marginal: C3 on 3 of 12) |
| 1.0 (the solved sections' rule) | **GATE FAIL: C1 on 12 of 12** |

LP2 pages 0–55 hold 458 ᚠ against 446.8 for uniform runes. If every plaintext F were left
unencrypted, English-register plaintext would put roughly 650 (the solved sections' F rate,
1.6 %) to 780 (the Cicada corpus, 2.7 %) there.

This excludes the typical key of that family, not the family. It says nothing about a
plaintext with almost no F's. The template lane is now `interrupt_prob: 0.0` under `beam-skip`.

## 4. Bars for the beam (staged, TR-1)

A beam picks the best interrupt/skip path through a wrong key, so its wrong-key decodes score
above uniform strings and need their own null. At L = 240 the wrong-key means are:

| decoder | wrong-key mean |
|---|---|
| rigid | −7.167 |
| beam | −6.900 |
| beam-skip | −6.872 |
| beam-skip-int | −6.739 |

(`noise`, 10,000 uniform ciphers each.)

Each fit is a Gumbel fit to the block maxima (block 1,000) of 10⁶ beam decodes under uniform
keys. Fit command:
`python scripts/calibrate.py --preset lp-ngram3-heldout:<decoder> --L 240 --L 120 --workers 3 --out-dir reports/calib-staging`.

| decoder | L | μ_b | β | wrong-key mean | out-of-sample max error |
|---|---|---|---|---|---|
| beam | 240 | −6.4215 | 0.0372 | −6.7819 | 0.016 |
| beam | 120 | −6.1766 | 0.0511 | −6.7058 | 0.066 |
| beam-skip | 240 | −6.4767 | 0.0377 | −6.8693 | 0.027 |
| beam-skip | 120 | −6.3037 | 0.0563 | −6.9038 | 0.011 |
| beam-skip-int | 240 | −6.2949 | 0.0365 | −6.6535 | 0.052 |
| beam-skip-int | 120 | −6.0713 | 0.0502 | −6.5941 | 0.039 |

The out-of-sample checks are the 25,000-draw block mean and the single 10⁶ maximum against
their predictions. In four fits the observed values sit at or below the prediction. For
`beam-skip-int` at L = 240 the 10⁶ maximum is 0.052 above it, and for `beam-skip` at L = 120 it
is 0.011 above. Those are single draws of a Gumbel whose sd is 1.28 β (0.047 and 0.072), so both
are within one sd. Treat the extrapolated bars as accurate to about one β, not better.

**Which ciphers the fits use, and why.** Under a uniform key every decoded rune is uniform,
whatever the cipher symbol. So a window's null depends on the cipher only through the choices it
offers the beam. Three review rounds measured this:

- **Canonical F's.** Each one is a free interrupt-or-not choice for a wrong key. Under `beam`
  the block-max mean rises from −6.59 at 4 F's to −6.31 at 20, and `beam-skip` is flat. The
  interrupt decoders are therefore fitted at the most F's of any lane window that starts at an
  unsolved page and runs on in canonical order: 14 at L = 240 (page 11), 10 at L = 120 (page 43).
  A lane whose window holds more is refused.
- **Doublets.** At a repeat a one-symbol skip deciphers the same rune as no skip, so a doublet
  offers no new choice. LP2 has almost none, and a uniform-cipher fit sat 0.004 below every LP2
  window: offset +0.0043 over 14 windows, spread 0.0020 against a per-window se of 0.0031.
  All fits now draw doublet-free ciphers.
- **Nothing else.** Before paths that used up their key wrapped round it, a key-free fill copied each
  window's own runes into most wrong-key `beam-skip` decodes, and windows sat up to 0.05 (about
  1 β) above uniform ciphers. Round 3 compared all 2,563 distinct L = 240 lane windows (up to
  3 pages, any order) with the fits: every window sits at or below its fit within sampling error,
  in every view and combine. The one window with 15 F's (pages 22, 43) is refused.

Each fit records `decoder_params`, the SHA-256 of `runeforge/beam.py` (`fe88435ebd…`) and
`canonical_F`. `LaneSpec.runnable_problems` refuses a fit when any of them no longer matches.
The frozen `calib.load` does not check them (TR-5).

## 5. Planted-key controls: the power envelope

The control is the frozen `runeforge.runner.control.run_control`, unchanged. The beam reaches it
through `pipeline.decrypt`. Setup:
- plants: 20, each on a random window of held-out A KOAN (1);
- generator: numpy-pcg64 over 2³²;
- decoys: 199 per plant;
- ceiling: 4,000 domain-separated SHA-256 keys, extrapolated to N = 2³².

Two gaps are given: one with the fit's β ("staged", what an installed calibration gives), and
one with the β from the per-plant maxima (what the control uses today, while no fit is
installed). "id." is the number of plants identified, out of 20. The pass bar is ≥ 18/20
identified and a gap ≥ 0.25 nats.

| forward model | L | decoder | id. | median recovery | floor | gap, staged β (nats) | gap, per-plant β (nats) | pairing |
|---|---|---|---|---|---|---|---|---|
| interrupters | 240 | rigid | 0 | 0.194 | — | — | — | allowed |
| interrupters | 240 | **beam** | **20** | 1.000 | −4.206 | 1.089 | 0.848 | allowed |
| interrupters | 120 | rigid | 7 | 0.371 | −4.259 | — | 0.952 | allowed |
| interrupters | 120 | **beam** | **20** | 1.000 | −4.270 | 0.747 | **0.155 (fails)** | allowed |
| anti-repeat | 240 | rigid | 0 | 0.110 | — | — | — | allowed |
| anti-repeat | 240 | beam | 0 | 0.125 | — | — | — | refused |
| anti-repeat | 240 | **beam-skip** | **20** | 0.973 | −4.334 | 1.113 | 1.098 | allowed |
| anti-repeat | 120 | rigid | 0 | 0.208 | — | — | — | allowed |
| anti-repeat | 120 | **beam-skip** | **19** | 0.967 | −4.479 | 0.645 | 0.533 | allowed |
| both | 240 | rigid | 0 | 0.192 | — | — | — | allowed |
| both | 240 | beam | 0 | 0.188 | — | — | — | allowed |
| both | 240 | beam-skip | 1 | 0.738 | −3.633 | — | — | allowed |
| both | 240 | **beam-skip-int** | **20** | 0.988 | −4.189 | 1.100 | 1.132 | allowed |
| both | 120 | rigid | 0 | 0.417 | — | — | — | allowed |
| both | 120 | **beam-skip-int** | **19** | 0.979 | −4.257 | 0.716 | 0.350 | allowed |

`beam_decoder.json` (`controls`) also holds the remaining rows: superset pairings, which pass
but are refused as lanes, and the other subset pairings, which fail.

Reading the table:

- **Every forward model passes under the decoder that matches it, at both windows. The rigid
  decoder passes none.** A filtered lane, which is the family the gate needs, was
  `INCONCLUSIVE (power)` by construction under rigid. It now has a control that passes.
- **The per-plant β is noisy.** The interrupt-only lane at L = 120 identifies 20/20 plants but
  fails its gap under the per-plant β (0.113, against the fit's 0.051). Under the staged fit it
  passes at 0.747 nats. Until TR-1 is installed, a `:beam*` control extrapolates its ceiling with
  that noisy β. The sweep refuses a beam lane whose control did not use the installed fit's β
  (`sweep.beam_control_problems`).
- **Recovery is about 97 %, not 100 %, under the skip models.** About 2.8 % of the window
  (`beam-skip`) or 1.2 % (`beam-skip-int`) is lost at the end to the key budget (fill, §6). The
  rest is genuine ambiguity, where two paths fit the ciphertext equally well.
- **Control fixture:** these controls use numpy-pcg64 as a fast stand-in. The template lane's own
  generator, mt19937-py27 with 999 decoys per plant, passed its scratch control 20/20 under
  `beam-skip-int`, gap 0.99 nats (per-plant β). That run predates review rounds 2–3, so re-run
  it once TR-1 lands.

## 6. Noise, fill, width, throughput

| quantity | value | where in `beam_decoder.json` |
|---|---|---|
| wrong-key mean at L = 240: rigid / beam / beam-skip / beam-skip-int | −7.167 / −6.900 / −6.872 / −6.739 | `noise` |
| fill: share of a planted window lost to the key budget, 200 plants, L = 240 | beam-skip 2.77 %, beam-skip-int 1.22 % | `fill` |
| mean recovery of those plants | beam-skip 0.971, beam-skip-int 0.983 | `fill` |
| control at width 4 / 8 / 16 (beam-skip, anti-repeat, L = 240) | 20/20 each; floor −4.334; observed ceiling −6.462; identical decodes | `width` |
| wrong-key mean at width 4 / 8 / 16 | −6.894 / −6.875 / −6.874 | `width` |
| CPU throughput, one process, L = 240 (rigid ~58,000 keys/s) | beam ~2,400, beam-skip ~1,100, beam-skip-int ~960 keys/s | `noise` |

Width barely matters, so 8 is not a tuned choice.

At ~1,100 keys/s, a 2³² `beam-skip` sweep is about 45 core-days on the CPU. It needs the Phase 3
GPU kernel (parity against `beam.decode_batch`, per `.claude/rules/gpu.md`), or a bounded slice
whose fraction is stated.

## 7. Review record and what is not covered

Three adversarial rounds reviewed the decoder and its integration. Each round used independent
reviewers by dimension, and each finding faced three refuters; a finding stood if at least two
did not refute it.

| round | findings | upheld | of which major | examples |
|---|---|---|---|---|
| 1 | 22 | 15 | 3 | F-rich windows under interrupt-decoder bars; max_skip 2 could not follow 3+ drops at one rune; the beam was not tested against the forward model outside raw/vigenere |
| 2 | 9 | 7 | 2 | the key-free fill made each window's null its own; a decoder modelling more than its lane could file a true key NOISE-CROSSER |
| 3 | 8 | 8 | 0 | a vacuous wrap test; the null not bound to the decoder; stale wording |

Every upheld finding is fixed with a test, or filed as a toolbox request where the fix touches a
frozen file:

| request | what it asks |
|---|---|
| TR-1 | install the bars |
| TR-2 | freeze `beam.py`, `beam_calib.py` and `test_beam.py` |
| TR-3 | the oracle takes a beam decode record and beam per-page bars |
| TR-4 | the 11-of-25 wording |
| TR-5 | `calib.load` binds a fit to its decoder |

not_covered:

- **Scorers:** the six fits cover `lp-ngram3-heldout` only. Other scorers' beam presets have no
  bar. The Phase 2 Kneser-Ney scorer does not exist yet.
- **Windows:** only L = 120 and 240 are fitted.
- **Oracle:** a beam crosser cannot pass the frozen oracle until TR-3, and stops at
  HIT_PROTOCOL step 5.
- **Re-encipher step:** step 6 replays the beam's own record. For the beam's output it is a
  consistency check, not independent evidence.
- **Decoder transition model:** the anti-repeat filter of `pipeline.encrypt`, truncated at 6
  drops per rune, plus F-interrupters. Other skip relations (Dukotah's "exact" relation variants,
  skip-by-two) are not modelled.
- **Register:** English (Cicada register) only, via the scorer.

reopens_if: a scorer change (refit the bars), a decoder change (new decoder name and refit),
TR-1/TR-3 landing (re-run the controls; beam crossers can reach the oracle), or a skip relation
this model does not express.

## 8. Reproduce

```bash
pytest -q tests/test_beam.py                    # 85 tests
python scripts/beam_power.py                    # writes reports/beam_decoder.json (~3 min)
python scripts/calibrate.py --preset lp-ngram3-heldout:beam-skip --L 240 --workers 4 \
    --out-dir reports/calib-staging              # one staged fit (~6 min)
```
