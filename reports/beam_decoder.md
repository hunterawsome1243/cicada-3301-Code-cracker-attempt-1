# The beam interrupt decoder — instrument report

**Not a solve.** This report is about an instrument: whether a decoder can follow F-interrupters
and anti-repeat key skips, and how hard it is for a wrong key to look like a right one under it.
No key space of the unsolved pages was searched, and nothing here is a decode of LP2.

numbering: "LP2-0-57" · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`
(12,956 runes, LP2 pages 0–55) · decoder `runeforge/beam.py` SHA-256 `4cd3d7ba59…` (the numbers
below were computed at `a855814af3…`; the two differ in comments and docstrings only) · numbers from
`python scripts/beam_power.py` at git `6faf29d` → [`beam_decoder.json`](beam_decoder.json) (780 s,
one process, on a 4-core host; the JSON section is named after each number) unless a line says
otherwise.

## 0. Reusable parts

| part | where |
|---|---|
| decoder (batched numpy, plus a scalar reference that matches it path for path) | `runeforge/beam.py` `decode_batch`, `decode_reference`, `decode_record` |
| presets `<scorer>:<decoder>` | `runeforge/scoring/presets.py` `DECODERS`, `DECODER_PARAMS` |
| beam nulls and their fits | `runeforge/scoring/beam_calib.py`, `scripts/calibrate.py --out-dir` |
| six staged calibrations (lp-ngram3-heldout × 3 decoders × L 120, 240) | `reports/calib-staging/` (to install: `TOOLBOX_REQUESTS.md` TR-1) |
| the forward model it inverts | `runeforge/runner/pipeline.py` `encrypt` |
| tests | `tests/test_beam.py` (87; one marked slow, six cases need `data/raw`) |
| every number below, unless a line says otherwise | `scripts/beam_power.py`; the staged fits: `scripts/calibrate.py --out-dir reports/calib-staging`; review-round and audit scratch figures (§4, §5) have no committed regenerator |

## 1. What the decoder models

The rigid decoder spends one key symbol per rune. The first interrupter or skip puts every later
rune out of step with the key. When that happens early in the window, a correct key scores near
noise. Rigid controls identify 0/20 at L = 240, and 7/20 at L = 120 under interrupters
(`controls`).

The beam follows `pipeline.encrypt` position by position. The ciphertext fixes the canonical
runes, so two kinds of position are known: the candidate interrupt positions (every canonical
ᚠ) and the kept-repeat positions. Which ᚠ's are interrupters, where the key skipped, the
plaintext and the key position are all hidden.

| decoder | F-interrupters | anti-repeat key skips | for lanes with |
|---|---|---|---|
| `rigid` | no | no | neither |
| `beam` | prior 15/16 | no | `filter_model: off`, `interrupt_prob` > 0 |
| `beam-skip` | no | p_keep 0.19, up to 6 per rune | `anti-repeat`, `interrupt_prob: 0` (the family the gate passes, §3) |
| `beam-skip-int` | prior 15/16 | p_keep 0.19, up to 6 per rune | both |

All presets use beam width 8. An interrupt is allowed only where the canonical rune is F. At an
interrupt the key holds and the plaintext is F.

A skip of s symbols is exact, not guessed. Each dropped key symbol must re-encipher the same rune
to a canonical repeat of the previous one, so s skips need s equal key symbols in a row.

The objective is the scorer's log2-probability plus the log2 transition priors. The lane scores
the returned plaintext with the scorer alone, as it scores a rigid decode.

Where the parameters come from:
- **interrupt prior 15/16:** the rule of succession on 14 of 14 plaintext F's being interrupters
  in the keyed solved sections (§3).
- **p_keep 0.19:** LP2's 86 doublets against 447 expected (CLAUDE.md).
- **max_skip 6:** more than 6 drops at one rune has probability (0.81/29)⁷ ≈ 1.3·10⁻¹¹ per rune
  under a uniform key.
- **width 8:** see §6.

A decoder may not model more than its lane does. `LaneSpec.decoder_problems` refuses
interrupters on a lane with `interrupt_prob: 0`, and skips on a lane without the filter.

**Key budget.** Every caller that compares a decode with a null passes exactly the window's
length in key symbols: the control's plants, decoys and ceiling, `runeforge null`, the sweep, and
`runeforge score`. A path that uses up its key wraps round to the start of it (`k[j mod K]`), and
those runes are recorded as fill. Under a wrong key a wrapped decode is as random as any other.

## 2. Reproduction before power (Rule 1)

Given only the key and no interrupt list, the beam re-derives every keyed solved section
(`solved_sections`). Three scorers were run. `lp-ngram3-heldout` was trained on these three
sections, so its rows show the mechanics only. `general-ngram3` and `cicada-ngram3` never saw
Liber Primus text.

| section | ciphertext ᚠ | published interrupters | beam interrupters | same set | plaintext exact | rigid score → beam score (general-ngram3) |
|---|---|---|---|---|---|---|
| WELCOME | 25 | 11 | 11 | yes | yes | −8.521 → −3.378 |
| A KOAN 2 | 5 | 2 | 2 | yes | yes | −8.089 → −3.137 |
| AN END | 5 | 1 | 1 | yes | yes | −6.183 → −3.621 |

The interrupt set is the same and the plaintext exact under all three scorers. The two non-LP
scorers are also pinned by `test_the_beam_rederives_the_solved_interrupt_sets_from_the_key_alone`
(6 cases, needs `data/raw`).

**Planted DIVINITY key on a synthetic Welcome page** (spec P2; `planted_divinity`). The
plaintext is A KOAN (1), the first 515 runes, held out of the scorer. It is enciphered with
WELCOME's key DIUINITY, and every plaintext F is an interrupter: 8 of them, the first at rune 53.

| decoder | score (lp-ngram3-heldout) | runes recovered | interrupt set |
|---|---|---|---|
| rigid | −6.644 | 18.3 % | — |
| beam | −3.506 | 100 % | exact |

Dukotah measured an analogous contrast under the anti-repeat filter (key skips, not
interrupters; a skip-aware beam, 98.9 % of runes; `data/raw/dukotah/PAPER.md` §3): −6.835 rigid vs
−4.170 beam, under their own scorer. It is quoted for the shape only. Their bars are not ours,
and CLAUDE.md's attribution of that pair to the interrupt rule is TR-4.

## 3. The interrupt rule and LP2's ᚠ count

"WELCOME 11 of 25" counts **ciphertext** ᚠ's that are interrupters. Every **plaintext** F in
the keyed solved sections is an interrupter: 14 of 14 (11/11, 2/2, 1/1;
`test_every_plaintext_f_in_the_keyed_sections_is_an_interrupter`, from
`canon.load_solved_sections()`). This project's lanes had defaulted
`interrupt_prob` to 0.44, reading the first figure as the second. The default is now 1.0, and
the frozen texts that carry the misreading are TR-4.

Under the every-F rule the template lane's family fails the fingerprint gate
(`gate_template_family`: `runeforge.runner.gate`, 12 keys of mt19937-py27, anti-repeat):

| interrupt_prob | gate |
|---|---|
| 0.0 | GATE PASS |
| 0.1 | GATE PASS (marginal: C3 on 2 of 12) |
| 0.44 (the misreading) | GATE PASS (marginal: C3 on 3 of 12) |
| 1.0 (the solved sections' rule) | **GATE FAIL: C1 on 12 of 12** |

LP2 pages 0–55 hold 458 ᚠ, against 446.8 for uniform runes (`lp2_F`). If every plaintext F were
left unencrypted, the expected count would be E = f·N + (1 − f)·N/29, with N = 12,956:

| plaintext F rate f | source | expected ᚠ |
|---|---|---|
| 1.61 % | 48 of 2,977, solved sections' plaintext | 648 |
| 2.70 % | 8,268 of 306,683, the cicada-english corpus (Emerson in Cicada register) | 784 |

(`lp2_F.if_every_plaintext_F_unencrypted`.)

This excludes the typical key of that family, not the family. It says nothing about a
plaintext with almost no F's. The template lane is now `interrupt_prob: 0.0` under `beam-skip`.

## 4. Bars for the beam (staged, TR-1)

A beam picks the best interrupt/skip path through a wrong key, so its wrong-key decodes score
above uniform strings and need their own null. At L = 240 (`noise`, 10,000 uniform ciphers each),
the wrong-key means are:

| decoder | wrong-key mean |
|---|---|
| rigid | −7.167 |
| beam | −6.900 |
| beam-skip | −6.872 |
| beam-skip-int | −6.739 |

Each fit is a Gumbel fit to the block maxima (block 1,000) of 10⁶ beam decodes under uniform keys:
`python scripts/calibrate.py --preset lp-ngram3-heldout:<decoder> --L 240 --L 120 --workers 4 --out-dir reports/calib-staging`
(`reports/calib-staging/*.json`; 1–5 min per fit).

| decoder | L | μ_b | β | wrong-key mean | 25k-block mean − predicted | 10⁶ max − predicted |
|---|---|---|---|---|---|---|
| beam | 240 | −6.4215 | 0.0372 | −6.7819 | −0.005 | **+0.016** |
| beam | 120 | −6.1766 | 0.0511 | −6.7058 | −0.015 | −0.066 |
| beam-skip | 240 | −6.4767 | 0.0377 | −6.8693 | **+0.0003** | −0.027 |
| beam-skip | 120 | −6.3037 | 0.0563 | −6.9038 | −0.007 | **+0.011** |
| beam-skip-int | 240 | −6.2949 | 0.0365 | −6.6535 | **+0.003** | **+0.052** |
| beam-skip-int | 120 | −6.0713 | 0.0502 | −6.5941 | −0.011 | −0.039 |

The last two columns are scale checks on the same 10⁶ draws the fit used, not independent draws:
the 25,000-block mean and the single 10⁶ maximum, each against the fit's prediction. Bold marks
an observed value above the prediction, which is the anti-conservative side.

The 10⁶ maximum is above its prediction in three fits:

| fit | 10⁶ maximum above prediction |
|---|---|
| beam-skip-int, L = 240 | +0.052 (1.1 Gumbel sd, 1.4 β) |
| beam, L = 240 | +0.016 (0.34 sd) |
| beam-skip, L = 120 | +0.011 (0.15 sd) |

A Gumbel sd is 1.28 β. The largest errors in either direction are 1.3–1.4 β, so treat the
extrapolated bars as accurate to about 1.5 β, not better.

**Which ciphers the fits use, and why.** Under a uniform key every decoded rune is uniform,
whatever the cipher symbol. A window's null therefore depends on the cipher only through the
choices it offers the beam. Three things were checked.

**Canonical F's.** Each canonical F is a free interrupt-or-not choice for a wrong key. On
doublet-free ciphers at L = 240 (`fcount`, 50 blocks each, se ≈ 0.007), the block-max mean is:

| canonical F's | beam | beam-skip |
|---|---|---|
| 4 | −6.573 | −6.459 |
| 14 | −6.398 | −6.451 |
| 20 | −6.319 | −6.458 |

The interrupt decoders are therefore fitted at the most F's of any lane window that starts at an
unsolved page and runs on in canonical order: 14 at L = 240 (page 11) and 10 at L = 120 (page 43;
`beam_calib.canonical_f`). A lane whose window holds more is refused.

**Doublets.** At a repeat, a one-symbol skip deciphers the same rune as no skip, so a doublet
offers no new choice. LP2 has almost none (86 in 12,956). Under `beam-skip` at L = 120 (`doublets`,
8,000 keys per window), every fourth page-start window sits 0.0043 above uniform ciphers on
average, with spread 0.0023 over 14 windows. Doublet-free ciphers sit 0.0047 above uniform ones,
so all fits draw doublet-free ciphers, with F's never adjacent.

**Every page-start window against its fit** (`windows`). For each decoder at L = 120 and 240,
each of the 54 page-start windows was decoded under 2,000 wrong keys and compared with 20,000
draws of that fit's ciphers.

| decoder | L | largest window z | windows above z = 2 | mean z |
|---|---|---|---|---|
| beam | 240 | +0.18 (page 11, 14 F's) | 0 | −41.6 |
| beam | 120 | −9.5 | 0 | −51.3 |
| beam-skip-int | 240 | −0.57 (page 11, 14 F's) | 0 | −31.2 |
| beam-skip-int | 120 | −8.6 | 0 | −40.8 |
| beam-skip | 240 | +2.44 | 2 | +0.42 |
| beam-skip | 120 | +1.95 | 0 | −0.10 |

The interrupt decoders sit at or below their fits in every window.

- **L = 240:** the most F-rich window (page 11, 14 F's) sits at the fit, as built.
- **L = 120:** even the most F-rich window (page 43, 10 F's, the count the fit uses) sits well
  below it (z −9.5 and −8.6, about 0.03 in score, ~0.65 β). Where the F's fall matters as well as
  how many there are. For the 54 page-start windows at L = 120 these bars are conservative by at
  least that much: less power, not more false positives. The other 160 of the 214 L = 120 lane
  windows were not compared (§7).

Under `beam-skip`, about 1.2 windows above z = 2 would be expected by chance. The +0.42 mean z
is about 1.3 times its own uncertainty, so it is not significant. That uncertainty is ±0.33 z:
±0.30 from the one fit mean all 54 windows share, ±0.13 from the windows' own 2,000-key samples.
Its size is about 0.001 in score, 0.03 β.

Two further comparisons are review-round scratch measurements, with no regenerator committed:

- **Review round 3** compared 2,563 of the 2,875 distinct L = 240 lane windows: every window of
  up to 3 pages, in any order. Every one sits at or below its fit within sampling error, in every
  view and combine. The 312 four-page windows were not compared (not_covered). The one window
  with 15 F's (pages 22, 43) is refused by the F check.
- **Review round 2:** before paths that used up their key wrapped round it, a key-free fill
  copied each window's own runes into most wrong-key `beam-skip` decodes. Windows then sat up to
  0.05 (about 1 β) above uniform ciphers.

Each fit records `decoder_params`, the SHA-256 of `runeforge/beam.py` and `canonical_F`.
`LaneSpec.runnable_problems` refuses a fit when any of them no longer matches. The frozen
`calib.load` does not check them (TR-5).

## 5. Planted-key controls: the power envelope

The control is the frozen `runeforge.runner.control.run_control`, unchanged; the beam reaches it
through `pipeline.decrypt` (`controls`). Setup:

- plants: 20, each on a random window of held-out A KOAN (1);
- generator: numpy-pcg64 over 2³²;
- decoys: 199 per plant;
- ceiling: 4,000 domain-separated SHA-256 keys, extrapolated to N = 2³².

The table gives two gaps. "Gap, staged β" is what an installed fit gives. "Gap, control's β" is
what `run_control` uses today: the per-plant maxima for `:beam*` rows, and the installed rigid
calibration for rigid rows. "id." is the number of plants identified, out of 20. The pass bar
is ≥ 18/20 identified and a gap ≥ 0.25 nats. "Lane" says whether `LaneSpec.decoder_problems`
allows the pairing.

The pass bar is ≥ 18/20 plants identified (rank 1 and recovery ≥ 0.90) and a gap ≥ 0.25 nats.
Two more conditions apply:
- the decoys' maximum is within 5 β of the null maximum over as many keys;
- the floor is above the lane's family-wise bar, when one is set.

The staged-β column applies the identification and gap conditions only. Report audit 4 (`b68f006`) re-ran
the six matched pairings and the template lane with `control._beta` returning the staged β:
every one passes all conditions (gaps 1.089, 0.747, 1.113, 0.645, 1.100, 0.716 and 1.114). That
re-run is a scratch measurement; `run_control` does it itself once TR-1 installs the fits.

| forward model | L | decoder | id. | median recovery | floor | gap, staged β (nats) | gap, control's β (nats) | lane |
|---|---|---|---|---|---|---|---|---|
| interrupters | 240 | rigid | 0 | 0.194 | — | — | — | allowed |
| interrupters | 240 | **beam** | **20** | 1.000 | −4.206 | 1.089 | 0.848 | allowed |
| interrupters | 120 | rigid | 7 | 0.371 | −4.259 | — | 0.952 (fails on id.) | allowed |
| interrupters | 120 | **beam** | **20** | 1.000 | −4.270 | 0.747 | **0.155 (fails)** | allowed |
| anti-repeat | 240 | rigid | 0 | 0.110 | — | — | — | allowed |
| anti-repeat | 240 | **beam-skip** | **20** | 0.973 | −4.334 | 1.113 | 1.098 | allowed |
| anti-repeat | 120 | rigid | 0 | 0.208 | — | — | — | allowed |
| anti-repeat | 120 | **beam-skip** | **19** | 0.967 | −4.479 | 0.645 | 0.533 | allowed |
| both | 240 | rigid | 0 | 0.192 | — | — | — | allowed |
| both | 240 | beam | 0 | 0.188 | — | — | — | allowed |
| both | 240 | beam-skip | 1 | 0.738 | −3.633 (one plant) | 1.523 | 1.431 (fails on id.) | allowed |
| both | 240 | **beam-skip-int** | **20** | 0.988 | −4.189 | 1.100 | 1.132 | allowed |
| both | 120 | rigid | 0 | 0.417 | — | — | — | allowed |
| both | 120 | **beam-skip-int** | **19** | 0.979 | −4.257 | 0.716 | 0.350 | allowed |

`controls` in the JSON also holds the remaining rows:
- superset pairings, which pass but are refused as lanes;
- the other subset pairings, which fail;
- mismatched pairings (interrupters under `beam-skip`, anti-repeat under `beam`), which fail and
  are refused.

Reading the table:

- **Every forward model passes under the decoder that matches it, at both windows, with the
  staged fits' β. The rigid decoder passes none.** Under today's per-plant β, the
  interrupt-only lane at L = 120 fails its gap: 0.155 nats, from β 0.113 against the fit's 0.051.
  Until TR-1 is installed, a `:beam*` control extrapolates with that noisy β. The sweep refuses a
  beam lane whose control did not use the installed fit's β (`sweep.beam_control_problems`).
- **A filtered lane** (the family the gate needs) was `INCONCLUSIVE (power)` by construction under
  the rigid decoder. Under `beam-skip` its control now passes.
- **Recovery is about 97 % under `beam-skip` and about 98 % under `beam-skip-int`, not 100 %.**
  (`beam-skip`: 0.967–0.973 in controls, 0.971 in `fill`; `beam-skip-int`: 0.979–0.988 and
  0.983.) About 2.8 % or 1.2 % of the window is lost at its end to the key budget (fill, §6). The
  rest is genuine ambiguity, where two paths fit the ciphertext equally well.
- **The template lane's own control** (`template_control`: `lanes/_template.yaml` in memory,
  mt19937-py27, `lp-ngram3-heldout:beam-skip`, 999 decoys per plant, L = 240): 20/20 identified,
  median recovery 0.975, floor −4.306, observed ceiling −6.376 over 20,000 null keys.
  - Gap with the per-plant β (0.0322): 1.160 nats.
  - Gap with the staged β (0.0377): (−4.306 + 6.376 − 0.0377·ln(2³²/20,000))·ln 2 = 1.114 nats.
  - This is not lane evidence: no `lanes/<id>/control.json` and no ledger row. Re-run it as
    `runeforge control` once TR-1 lands.

## 6. Noise, fill, width, throughput

| quantity | value | JSON section |
|---|---|---|
| wrong-key mean at L = 240: rigid / beam / beam-skip / beam-skip-int | −7.167 / −6.900 / −6.872 / −6.739 | `noise` |
| fill: share of a planted window lost to the key budget, 200 plants, L = 240 | beam-skip 2.77 %, beam-skip-int 1.22 % | `fill` |
| mean recovery of those plants | beam-skip 0.971, beam-skip-int 0.983 | `fill` |
| control at width 4 / 8 / 16 (beam-skip, anti-repeat, L = 240) | 20/20 each; floor −4.334 and observed ceiling −6.462 at every width | `width` |
| wrong-key mean at width 4 / 8 / 16 | −6.894 / −6.875 / −6.874 | `width` |
| throughput, decode + score, one process, L = 240 | rigid ≥ 10⁵; beam ~2,500, beam-skip ~1,240, beam-skip-int ~1,000 keys/s | `noise` |

Width barely matters, so 8 is not a tuned choice. The planted decodes are identical at widths 4, 8
and 16: rank, recovery and score, checked in review. The wrong-key decodes differ slightly, as
the noise means show.

A 2³² `beam-skip` sweep at ~1,240 keys/s is about 40 core-days on the CPU (2³² / 1,240 s). It
needs the Phase 3 GPU kernel (parity against `beam.decode_batch`, per `.claude/rules/gpu.md`), or a
bounded slice whose fraction is stated.

The kernel is built (`runeforge/gpu/beam_kernel.py`) but has not run on a GPU, so it has no
throughput number yet. On the template lane's own keystreams (10⁴ seeds: both ends of the
range, planted seed 3301, random seeds; the lane's window and a planted synthetic page), its
CPU twin matches the numpy decoder with max |Δscore| = 0 and identical survivor sets
(`python -m runeforge.gpu.parity lanes/_template.yaml --backend cpu-twin`). The CUDA kernel
matches on numba's simulator too (`tests/test_gpu_beam.py`). The `mt19937-py27` keystream has
a kernel of the same construction (`runeforge/gpu/mt_kernel.py`; its twin equals the CPU
generator symbol for symbol in all four reducers, `tests/test_gpu_mt.py`), so the template
lane's keys are generated and scored on the device. The parity run that counts, and the
benchmark, must be made on the RTX:
`python -m runeforge.gpu.parity lanes/<id>.yaml --bench 1048576`.

## 7. Review record and what is not covered

The decoder and its integration went through three adversarial review rounds, and this report
through repeated claim-by-claim audits. The table records each round that changed the code or
the report. A later round that upholds nothing changes nothing, and appears only in the commit
log (`git log --grep 'audit'`). Each round used independent reviewers by dimension. Each finding
faced three refuters, and it stood if at least two did not refute it.

| round | findings | upheld | of which major | examples |
|---|---|---|---|---|
| 1 | 22 | 15 | 3 | F-rich windows under interrupt-decoder bars; max_skip 2 could not follow 3+ drops at one rune; no test against the forward model outside raw/vigenere |
| 2 | 9 | 7 | 2 | the key-free fill made each window's null its own; a decoder modelling more than its lane could file a true key NOISE-CROSSER |
| 3 | 8 | 8 | 0 | a vacuous wrap test; the null not bound to the decoder; stale wording |
| report audit 1 (`956cd28`, `56bdbe5`) | 23 | 20 | 3 | the scale checks overstated; an unbacked template-control figure; Dukotah's pair misattributed |
| report audit 2 (`0201052`) | 22 | 20 | 0 | at L = 120 the F-richest window sits ~0.65 β below its fit; TR-5 open, not fixed; a test pins 14/14 |
| report audit 3 (`c29edd8`) | 10 | 9 | 0 | the audit record itself; conservativeness claimed beyond the compared windows; a banned word in code comments |
| report audit 4 (`b68f006`) | 8 | 6 | 0 | L = 120 conservativeness scoped to the 54 page-start windows; the control's full pass bar and the staged-β re-run; the 15-F window in not_covered |
| report audit 5 | 10 | 8 | 0 | this table's own rows; §0's "every number regenerated"; the gate-passing family stated too narrowly |

Round 2 also reported two round-1 fixes as unresolved:
- `beam-skip`'s cipher independence was fixed in round 2 (wrap-round, doublet-free fits; `2e4519d`).
- The calibration binding outside the lane check is still open. It was filed as TR-5 right after
  round 1 (`a881f1c`). Round 2 added `sweep.beam_control_problems`, so the control's β is bound,
  but `calib.load` and `threshold_for` stay unbound until TR-5 is installed.

How the findings were handled:
- every upheld code finding is fixed with a test;
- wording findings are fixed in place;
- fixes that touch a frozen file are filed as toolbox requests:

| request | what it asks |
|---|---|
| TR-1 | install the bars |
| TR-2 | freeze `beam.py`, `beam_calib.py` and `test_beam.py` |
| TR-3 | the oracle takes a beam decode record and beam per-page bars |
| TR-4 | the 11-of-25 wording, and the attribution of Dukotah's pair |
| TR-5 | `calib.load` binds a fit to its decoder |

not_covered:

- **Scorers:** the six fits cover `lp-ngram3-heldout` only. Other scorers' beam presets have no
  bar. The Phase 2 Kneser-Ney scorer does not exist yet.
- **Windows:** only L = 120 and 240 are fitted. Not compared with their fits:
  - the 312 four-page L = 240 lane windows;
  - at L = 120, 160 of the 214 distinct lane windows (two-page windows outside canonical order,
    after pages 49, 51 or 55). Only the 54 page-start windows were compared (`windows`).
  - the one L = 240 window with 15 canonical F's (pages 22, 43). `beam` and `beam-skip-int`
    refuse it, since no bar is fitted above canonical_F 14.
- **Oracle:** a beam crosser cannot pass the frozen oracle until TR-3, and stops at HIT_PROTOCOL
  step 5.
- **Re-encipher step:** step 6 replays the beam's own record. For the beam's output it is a
  consistency check, not independent evidence.
- **Decoder transition model:** the anti-repeat filter of `pipeline.encrypt`, truncated at 6 drops
  per rune, plus F-interrupters. Other skip relations (Dukotah's "exact" relation variants,
  skip-by-two) are not modelled.
- **Register:** English (Cicada register) only, via the scorer.

reopens_if: a scorer change (refit the bars), a decoder change (new decoder name and refit),
TR-1/TR-3 landing (re-run the controls; beam crossers can reach the oracle), or a skip relation
this model does not express.

## 8. Reproduce

```bash
pytest -q tests/test_beam.py                    # 87 tests (-m "not slow" skips one)
python scripts/beam_power.py                    # writes reports/beam_decoder.json (~13 min, one process)
python scripts/calibrate.py --preset lp-ngram3-heldout:beam-skip --L 240 --workers 4 \
    --out-dir reports/calib-staging              # one staged fit (~5 min)
```
