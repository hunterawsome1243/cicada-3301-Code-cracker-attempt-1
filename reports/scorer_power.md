not a solve

# The scorer power harness (`scripts/scorer_power.py`) — instrument report

**Not a solve.** This report measures instruments: how a wrong key scores under each scorer preset, where the bars sit at N = 10^6 and 2^32, and how often a planted correct key clears them. No key space of the unsolved pages was searched and nothing here is a decode of LP2.

numbering: "LP2-0-57" · canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585` (12,956 runes, LP2 pages 0–55) · git `f95a3acea0d51a6296a6d0afc282bd4e6c418fa9` · scale **reduced** · created 2026-10-27T22:20:42+00:00 · `python scripts/scorer_power.py --quick --workers 4` → `reports/scorer_power.json`

This is the **reduced-scale** report: 100,000 null draws per (scorer, L) and 200 plants per cell. The bars are reduced-scale bars until `--full` (10^6 draws, Hunter's call) writes the installable records (TOOLBOX_REQUESTS.md TR-7); the fits under `reports/scorer_power/fits/` are marked `scale` and are never installed.

## 0. Reusable parts

| part | where |
|---|---|
| canon | `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`, 12,956 runes, `LP2-0-57` |
| scorer presets | `runeforge/scoring/presets.py`: ngram lp-ngram3-heldout, cicada-ngram3, general-ngram3; kn kn4-lp-heldout, kn4-cicada, kn5-cicada, kn6-cicada, kn8-cicada, kn8-general, kn8-latin, kn8-old-english, kn8-vowel-dropped, kn8-cicada-wb |
| model | `runeforge/scoring/kn.py`, `runeforge/scoring/kn_fit.py` |
| word-start masks | `runeforge/scoring/boundaries.py` |
| nulls and fits | `runeforge/scoring/calib/__init__.py`, `runeforge/scoring/beam_calib.py` |
| fit records | reports/scorer_power/fits/ (scale-marked, never installable unless full) |
| export | scripts/export_kn.py (knx-1; runeforge/gpu/kernels/README.md) |
| tests | `tests/test_kn.py`, `tests/test_scorer_power.py` |
| validators | `scripts/check_results.py`, `scripts/validate_ledger.py` |
| families (plant/decoy generators) | vigenere-short-key, atbash-shift, totient-stream, sha256-ctr/vigenere/raw, sha256-ctr/vigenere/atbash, sha256-ctr/vigenere/first-difference, sha256-ctr/vigenere/chain-increment, sha256-ctr/beaufort/raw, sha256-ctr/beaufort/atbash, sha256-ctr/beaufort/first-difference, sha256-ctr/beaufort/chain-increment, numpy-pcg64/vigenere/raw, numpy-pcg64/vigenere/atbash, numpy-pcg64/vigenere/first-difference, numpy-pcg64/vigenere/chain-increment, numpy-pcg64/beaufort/raw, numpy-pcg64/beaufort/atbash, numpy-pcg64/beaufort/first-difference, numpy-pcg64/beaufort/chain-increment |

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.reusable` · `python scripts/scorer_power.py --quick --section reusable`*

## 1. Not covered

- scale reduced: 100,000 null draws per (scorer, L) and 200 plants per cell; the 10^6-draw fits that TOOLBOX_REQUESTS.md TR-7 installs are --full
- heldout-solved-sections: L > 500 not covered (1,533 held-out runes)
- cicada-ngram3 x cicada-english: plant text is training text (no split); the cell is not a power
- general-ngram3 x english-general: plant text is training text (no split); the cell is not a power
- general-ngram3 x vowel-dropped-english: plant text is training text (no split); the cell is not a power
- english-general at L = 500: 200 plants at distinct offsets out of 84170 the register holds, but only 169 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- english-general at L = 1000: 200 plants at distinct offsets out of 83670 the register holds, but only 84 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- cicada-english at L = 240: 200 plants at distinct offsets out of 30750 the register holds, but only 129 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- cicada-english at L = 250: 200 plants at distinct offsets out of 30740 the register holds, but only 123 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- cicada-english at L = 263: 200 plants at distinct offsets out of 30727 the register holds, but only 117 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- cicada-english at L = 500: 200 plants at distinct offsets out of 30490 the register holds, but only 61 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- cicada-english at L = 1000: 200 plants at distinct offsets out of 29990 the register holds, but only 30 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- latin at L = 100: 200 plants at distinct offsets out of 11990 the register holds, but only 120 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- latin at L = 240: 200 plants at distinct offsets out of 11850 the register holds, but only 50 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- latin at L = 250: 200 plants at distinct offsets out of 11840 the register holds, but only 48 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- latin at L = 263: 200 plants at distinct offsets out of 11827 the register holds, but only 45 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- latin at L = 500: 200 plants at distinct offsets out of 11590 the register holds, but only 24 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- latin at L = 1000: 200 plants at distinct offsets out of 11090 the register holds, but only 12 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- vowel-dropped-english at L = 500: 200 plants at distinct offsets out of 55932 the register holds, but only 112 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- vowel-dropped-english at L = 1000: 200 plants at distinct offsets out of 55432 the register holds, but only 56 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- old-english at L = 100: 200 plants at distinct offsets out of 8357 the register holds, but only 84 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- old-english at L = 240: 200 plants at distinct offsets out of 8217 the register holds, but only 35 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- old-english at L = 250: 200 plants at distinct offsets out of 8207 the register holds, but only 33 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- old-english at L = 263: 200 plants at distinct offsets out of 8194 the register holds, but only 32 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- old-english at L = 500: 200 plants at distinct offsets out of 7957 the register holds, but only 16 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- old-english at L = 1000: 200 plants at distinct offsets out of 7457 the register holds, but only 8 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- heldout-solved-sections at L = 100: 200 plants at distinct offsets out of 1335 the register holds, but only 14 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- heldout-solved-sections at L = 240: 200 plants at distinct offsets out of 1055 the register holds, but only 6 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- heldout-solved-sections at L = 250: 200 plants at distinct offsets out of 1035 the register holds, but only 6 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- heldout-solved-sections at L = 263: 200 plants at distinct offsets out of 1009 the register holds, but only 4 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- heldout-solved-sections at L = 500: 200 plants at distinct offsets out of 535 the register holds, but only 2 windows can be disjoint, so the plants overlap and their Wilson intervals are nominal (the point estimates stand; the interval is not one over independent plants)
- wrong-key nulls: vigenere-short-key, atbash-shift, totient-stream are outside the 'wrong key = uniform string' claim (a partially matching periodic key leaves structure; a wrong atbash/shift key is a substitution of the plaintext; a wrong totient start is another offset of one non-uniform stream); their KS statistics are reported, not asserted, and the finite families also report the count above the Gumbel bar at N = their key count
- wrong-key nulls of the wb scorer carry the cipher window's own mask while null (a) averages over sampled masks, so their KS statistic measures the mask dependence of section 6 as well; the 'wrong key = uniform string' claim is for the nb scorers
- the power rows measure the scorer on rigid-exact decodes (the true key of an additive family returns the plaintext); interrupters and anti-repeat skips are measured in the beam cells only, at L [120, 240] with lp-ngram3-heldout, kn4-lp-heldout, kn4-cicada; no kn6/kn8 preset pairs with a beam decoder
- mt19937-py27 streams (the template lane's generator) share the combine/view code path of the two stream generators measured and are not drawn here
- kn8-cicada-wb: adjudication/report-only; its null depends on the window's mask (section 6) and no lane names it with any decoder
- no GPU: every number is the numpy path; the CUDA kernel is Phase 3
- no key space of the unsolved pages is searched here: this is an instrument report, not a lane; coverage of LP2 is 0 of every space

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.not_covered` · `python scripts/scorer_power.py --quick --section not_covered`*

## 2. Nulls and bars

Null (a): 100,000 uniform random strings per (scorer, L) (`calib.measure`); Gumbel fit on block maxima (block 1,000), 200-resample bootstrap of the block maxima for the intervals. Null (b): 5,000 wrong-key decodes per family on the real code paths (a finite family enumerates or draws its wrong keys without replacement), KS statistic against (a) (reported; the families marked `in claim: no` are outside the equality claim, section 1). Cells at L [120] are scale-check-only (an installed record exists there; no wrong-key null, no power row).

| scorer | L | null mean | sd | mu_b | beta | blocks | bar@10^6 [CI] | bar@2^32 [CI] | max KS (claim) | max KS (excluded) | check err |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lp-ngram3-heldout | 100 | −7.1579 | 0.2338 | −6.4130 | 0.0771 | 100 | −5.5252 [−5.7103, −5.3710] | −4.8798 [−5.1904, −4.6273] | 0.023 | 0.272 | 0.032 |
| cicada-ngram3 | 100 | −9.4784 | 0.4949 | −7.8964 | 0.1264 | 100 | −6.4415 [−6.6533, −6.2962] | −5.3838 [−5.7642, −5.1207] | 0.021 | 0.255 | 0.119 |
| general-ngram3 | 100 | −9.6780 | 0.5467 | −7.9645 | 0.1492 | 100 | −6.2479 [−6.6072, −5.8512] | −5.0000 [−5.6172, −4.3081] | 0.018 | 0.203 | 0.193 |
| kn4-lp-heldout | 100 | −6.1614 | 0.2105 | −5.5302 | 0.0549 | 100 | −4.8979 [−5.0125, −4.7854] | −4.4383 [−4.6356, −4.2482] | 0.019 | 0.232 | 0.019 |
| kn4-cicada | 100 | −6.6573 | 0.1454 | −6.1604 | 0.0561 | 100 | −5.5143 [−5.6509, −5.3837] | −5.0446 [−5.2795, −4.8247] | 0.021 | 0.194 | 0.021 |
| kn5-cicada | 100 | −6.5495 | 0.1509 | −6.0350 | 0.0501 | 100 | −5.4590 [−5.5476, −5.3737] | −5.0402 [−5.1894, −4.8926] | 0.021 | 0.213 | 0.017 |
| kn6-cicada | 100 | −6.5361 | 0.1549 | −6.0094 | 0.0498 | 100 | −5.4360 [−5.5366, −5.3646] | −5.0191 [−5.1929, −4.8948] | 0.024 | 0.210 | 0.028 |
| kn8-cicada | 100 | −6.5352 | 0.1554 | −6.0056 | 0.0506 | 100 | −5.4228 [−5.5117, −5.3305] | −4.9991 [−5.1497, −4.8402] | 0.025 | 0.210 | 0.026 |
| kn8-general | 100 | −6.5545 | 0.1496 | −6.0496 | 0.0475 | 100 | −5.5029 [−5.5731, −5.4407] | −5.1055 [−5.2237, −5.0034] | 0.018 | 0.168 | 0.071 |
| kn8-latin | 100 | −7.7837 | 0.2871 | −6.8778 | 0.0917 | 100 | −5.8227 [−6.0376, −5.6603] | −5.0557 [−5.4135, −4.7865] | 0.019 | 0.187 | 0.008 |
| kn8-old-english | 100 | −6.4604 | 0.1916 | −5.8593 | 0.0507 | 100 | −5.2763 [−5.3618, −5.1908] | −4.8526 [−5.0006, −4.7075] | 0.020 | 0.235 | 0.075 |
| kn8-vowel-dropped | 100 | −6.8593 | 0.2389 | −6.1066 | 0.0667 | 100 | −5.3387 [−5.4766, −5.1695] | −4.7804 [−5.0143, −4.4885] | 0.021 | 0.206 | 0.054 |
| kn8-cicada-wb | 100 | −7.6540 | 0.2115 | −7.0223 | 0.0734 | 100 | −6.1773 [−6.3010, −6.0629] | −5.5631 [−5.7725, −5.3589] | n/a | 0.668 | 0.086 |
| lp-ngram3-heldout | 120 | −7.1606 | 0.2135 | −6.4712 | 0.0633 | 100 | −5.7427 [−5.8882, −5.6297] | −5.2131 [−5.4596, −5.0209] | n/a | n/a | 0.013 |
| cicada-ngram3 | 120 | −9.4871 | 0.4525 | −8.0263 | 0.1251 | 100 | −6.5870 [−6.8133, −6.3413] | −5.5407 [−5.9359, −5.1226] | n/a | n/a | 0.061 |
| general-ngram3 | 120 | −9.6878 | 0.4996 | −8.1169 | 0.1331 | 100 | −6.5849 [−6.8103, −6.3849] | −5.4712 [−5.8497, −5.1225] | n/a | n/a | 0.027 |
| lp-ngram3-heldout | 240 | −7.1687 | 0.1506 | −6.6905 | 0.0459 | 100 | −6.1625 [−6.2519, −6.0605] | −5.7788 [−5.9303, −5.6030] | 0.019 | 0.274 | 0.016 |
| cicada-ngram3 | 240 | −9.5095 | 0.3213 | −8.4879 | 0.0969 | 100 | −7.3733 [−7.5581, −7.1786] | −6.5630 [−6.8995, −6.2339] | 0.018 | 0.248 | 0.026 |
| general-ngram3 | 240 | −9.7122 | 0.3546 | −8.5847 | 0.1099 | 100 | −7.3198 [−7.5050, −7.1274] | −6.4003 [−6.7108, −6.0789] | 0.015 | 0.256 | 0.069 |
| kn4-lp-heldout | 240 | −6.1667 | 0.1360 | −5.7541 | 0.0397 | 100 | −5.2978 [−5.3678, −5.2469] | −4.9661 [−5.0843, −4.8750] | 0.016 | 0.329 | 0.028 |
| kn4-cicada | 240 | −6.6765 | 0.0937 | −6.3592 | 0.0251 | 100 | −6.0705 [−6.1210, −6.0138] | −5.8605 [−5.9471, −5.7625] | 0.018 | 0.226 | 0.012 |
| kn5-cicada | 240 | −6.5670 | 0.0974 | −6.2459 | 0.0270 | 100 | −5.9355 [−5.9816, −5.8850] | −5.7098 [−5.7868, −5.6225] | 0.020 | 0.276 | 0.017 |
| kn6-cicada | 240 | −6.5532 | 0.1000 | −6.2241 | 0.0285 | 100 | −5.8961 [−5.9572, −5.8497] | −5.6577 [−5.7614, −5.5797] | 0.018 | 0.274 | 0.020 |
| kn8-cicada | 240 | −6.5523 | 0.1004 | −6.2220 | 0.0286 | 100 | −5.8932 [−5.9355, −5.8405] | −5.6543 [−5.7302, −5.5639] | 0.019 | 0.272 | 0.021 |
| kn8-general | 240 | −6.5737 | 0.0963 | −6.2569 | 0.0346 | 100 | −5.8583 [−5.9435, −5.7924] | −5.5685 [−5.7128, −5.4603] | 0.017 | 0.242 | 0.025 |
| kn8-latin | 240 | −7.8021 | 0.1850 | −7.2195 | 0.0543 | 100 | −6.5941 [−6.6681, −6.4999] | −6.1395 [−6.2694, −5.9771] | 0.020 | 0.295 | 0.042 |
| kn8-old-english | 240 | −6.4740 | 0.1241 | −6.0859 | 0.0323 | 100 | −5.7147 [−5.7728, −5.6765] | −5.4449 [−5.5428, −5.3821] | 0.019 | 0.286 | 0.055 |
| kn8-vowel-dropped | 240 | −6.8768 | 0.1540 | −6.3799 | 0.0468 | 100 | −5.8419 [−5.9278, −5.7529] | −5.4508 [−5.5972, −5.2981] | 0.026 | 0.242 | 0.003 |
| kn8-cicada-wb | 240 | −7.6436 | 0.1345 | −7.2513 | 0.0436 | 100 | −6.7496 [−6.8664, −6.6431] | −6.3850 [−6.5848, −6.2009] | n/a | 0.958 | 0.049 |
| lp-ngram3-heldout | 250 | −7.1690 | 0.1480 | −6.6936 | 0.0412 | 100 | −6.2196 [−6.2936, −6.1677] | −5.8750 [−5.9997, −5.7868] | 0.022 | 0.327 | 0.042 |
| cicada-ngram3 | 250 | −9.5102 | 0.3147 | −8.5164 | 0.0998 | 100 | −7.3684 [−7.5554, −7.1763] | −6.5339 [−6.8516, −6.1954] | 0.017 | 0.271 | 0.037 |
| general-ngram3 | 250 | −9.7131 | 0.3475 | −8.6217 | 0.1125 | 100 | −7.3274 [−7.5225, −7.1506] | −6.3865 [−6.7271, −6.0830] | 0.021 | 0.249 | 0.086 |
| kn4-lp-heldout | 250 | −6.1667 | 0.1334 | −5.7614 | 0.0384 | 100 | −5.3190 [−5.3976, −5.2453] | −4.9974 [−5.1305, −4.8733] | 0.021 | 0.278 | 0.016 |
| kn4-cicada | 250 | −6.6770 | 0.0918 | −6.3681 | 0.0306 | 100 | −6.0157 [−6.0689, −5.9713] | −5.7596 [−5.8504, −5.6859] | 0.020 | 0.269 | 0.041 |
| kn5-cicada | 250 | −6.5675 | 0.0954 | −6.2476 | 0.0297 | 100 | −5.9063 [−5.9579, −5.8590] | −5.6583 [−5.7432, −5.5816] | 0.020 | 0.297 | 0.034 |
| kn6-cicada | 250 | −6.5537 | 0.0980 | −6.2266 | 0.0305 | 100 | −5.8760 [−5.9320, −5.8236] | −5.6211 [−5.7165, −5.5345] | 0.020 | 0.300 | 0.041 |
| kn8-cicada | 250 | −6.5528 | 0.0984 | −6.2237 | 0.0305 | 100 | −5.8725 [−5.9281, −5.8237] | −5.6173 [−5.7110, −5.5340] | 0.019 | 0.301 | 0.042 |
| kn8-general | 250 | −6.5743 | 0.0945 | −6.2634 | 0.0326 | 100 | −5.8878 [−5.9445, −5.8344] | −5.6147 [−5.7140, −5.5221] | 0.022 | 0.264 | 0.028 |
| kn8-latin | 250 | −7.8026 | 0.1813 | −7.2275 | 0.0499 | 100 | −6.6535 [−6.7357, −6.5820] | −6.2362 [−6.3772, −6.1113] | 0.023 | 0.252 | 0.015 |
| kn8-old-english | 250 | −6.4743 | 0.1215 | −6.0956 | 0.0356 | 100 | −5.6854 [−5.7450, −5.6316] | −5.3873 [−5.4872, −5.3000] | 0.017 | 0.229 | 0.029 |
| kn8-vowel-dropped | 250 | −6.8773 | 0.1512 | −6.3997 | 0.0445 | 100 | −5.8881 [−5.9682, −5.8185] | −5.5162 [−5.6512, −5.3989] | 0.019 | 0.274 | 0.007 |
| kn8-cicada-wb | 250 | −7.6485 | 0.1316 | −7.2592 | 0.0372 | 100 | −6.8308 [−6.9117, −6.7580] | −6.5194 [−6.6590, −6.3970] | n/a | 0.984 | 0.019 |
| lp-ngram3-heldout | 263 | −7.1694 | 0.1439 | −6.7134 | 0.0389 | 100 | −6.2653 [−6.3518, −6.1700] | −5.9396 [−6.0896, −5.7753] | 0.019 | 0.271 | 0.019 |
| cicada-ngram3 | 263 | −9.5113 | 0.3066 | −8.5382 | 0.0976 | 100 | −7.4153 [−7.6019, −7.2700] | −6.5991 [−6.9166, −6.3629] | 0.019 | 0.251 | 0.044 |
| general-ngram3 | 263 | −9.7143 | 0.3387 | −8.6444 | 0.1094 | 100 | −7.3851 [−7.6009, −7.1781] | −6.4697 [−6.8330, −6.1152] | 0.018 | 0.273 | 0.046 |
| kn4-lp-heldout | 263 | −6.1670 | 0.1300 | −5.7743 | 0.0345 | 100 | −5.3773 [−5.4474, −5.3050] | −5.0886 [−5.2127, −4.9630] | 0.022 | 0.266 | 0.025 |
| kn4-cicada | 263 | −6.6776 | 0.0894 | −6.3813 | 0.0297 | 100 | −6.0395 [−6.0810, −5.9966] | −5.7910 [−5.8608, −5.7182] | 0.018 | 0.205 | 0.030 |
| kn5-cicada | 263 | −6.5680 | 0.0928 | −6.2639 | 0.0313 | 100 | −5.9041 [−5.9573, −5.8656] | −5.6426 [−5.7362, −5.5759] | 0.017 | 0.250 | 0.026 |
| kn6-cicada | 263 | −6.5543 | 0.0953 | −6.2420 | 0.0315 | 100 | −5.8795 [−5.9265, −5.8370] | −5.6160 [−5.7001, −5.5431] | 0.016 | 0.250 | 0.041 |
| kn8-cicada | 263 | −6.5534 | 0.0956 | −6.2399 | 0.0316 | 100 | −5.8760 [−5.9246, −5.8408] | −5.6114 [−5.6960, −5.5512] | 0.016 | 0.250 | 0.039 |
| kn8-general | 263 | −6.5750 | 0.0920 | −6.2741 | 0.0342 | 100 | −5.8803 [−5.9398, −5.8243] | −5.5941 [−5.6957, −5.4939] | 0.017 | 0.251 | 0.012 |
| kn8-latin | 263 | −7.8034 | 0.1770 | −7.2464 | 0.0460 | 100 | −6.7173 [−6.7937, −6.6525] | −6.3327 [−6.4660, −6.2242] | 0.018 | 0.209 | 0.015 |
| kn8-old-english | 263 | −6.4746 | 0.1180 | −6.1102 | 0.0333 | 100 | −5.7267 [−5.7825, −5.6617] | −5.4479 [−5.5448, −5.3339] | 0.019 | 0.282 | 0.016 |
| kn8-vowel-dropped | 263 | −6.8779 | 0.1474 | −6.4152 | 0.0419 | 100 | −5.9329 [−6.0171, −5.8453] | −5.5823 [−5.7265, −5.4337] | 0.017 | 0.258 | 0.027 |
| kn8-cicada-wb | 263 | −7.6421 | 0.1287 | −7.2622 | 0.0426 | 100 | −6.7725 [−6.8469, −6.6963] | −6.4165 [−6.5449, −6.2859] | n/a | 0.928 | 0.025 |
| lp-ngram3-heldout | 500 | −7.1726 | 0.1047 | −6.8474 | 0.0272 | 100 | −6.5338 [−6.5877, −6.4852] | −6.3059 [−6.3982, −6.2234] | 0.018 | 0.306 | 0.010 |
| cicada-ngram3 | 500 | −9.5209 | 0.2230 | −8.8249 | 0.0622 | 100 | −8.1089 [−8.2369, −7.9923] | −7.5885 [−7.8065, −7.3955] | 0.017 | 0.308 | 0.046 |
| general-ngram3 | 500 | −9.7249 | 0.2460 | −8.9537 | 0.0715 | 100 | −8.1314 [−8.2652, −8.0179] | −7.5337 [−7.7585, −7.3429] | 0.019 | 0.266 | 0.091 |
| kn4-lp-heldout | 500 | −6.1685 | 0.0943 | −5.8832 | 0.0231 | 100 | −5.6173 [−5.6600, −5.5796] | −5.4241 [−5.4999, −5.3611] | 0.020 | 0.307 | 0.018 |
| kn4-cicada | 500 | −6.6836 | 0.0649 | −6.4711 | 0.0221 | 100 | −6.2172 [−6.2547, −6.1787] | −6.0327 [−6.0954, −5.9671] | 0.019 | 0.276 | 0.009 |
| kn5-cicada | 500 | −6.5735 | 0.0675 | −6.3551 | 0.0210 | 100 | −6.1136 [−6.1567, −6.0767] | −5.9381 [−6.0116, −5.8742] | 0.019 | 0.275 | 0.003 |
| kn6-cicada | 500 | −6.5597 | 0.0694 | −6.3368 | 0.0221 | 100 | −6.0826 [−6.1284, −6.0372] | −5.8978 [−5.9758, −5.8170] | 0.017 | 0.277 | 0.004 |
| kn8-cicada | 500 | −6.5588 | 0.0696 | −6.3349 | 0.0222 | 100 | −6.0793 [−6.1242, −6.0396] | −5.8935 [−5.9692, −5.8263] | 0.017 | 0.277 | 0.003 |
| kn8-general | 500 | −6.5810 | 0.0668 | −6.3654 | 0.0193 | 100 | −6.1430 [−6.1738, −6.1105] | −5.9813 [−6.0328, −5.9264] | 0.017 | 0.249 | 0.010 |
| kn8-latin | 500 | −7.8087 | 0.1282 | −7.4105 | 0.0357 | 100 | −6.9992 [−7.0596, −6.9539] | −6.7002 [−6.8032, −6.6262] | 0.020 | 0.362 | 0.048 |
| kn8-old-english | 500 | −6.4784 | 0.0862 | −6.2132 | 0.0253 | 100 | −5.9216 [−5.9695, −5.8815] | −5.7096 [−5.7881, −5.6425] | 0.021 | 0.247 | 0.011 |
| kn8-vowel-dropped | 500 | −6.8829 | 0.1070 | −6.5462 | 0.0376 | 100 | −6.1131 [−6.1944, −6.0356] | −5.7983 [−5.9374, −5.6644] | 0.020 | 0.328 | 0.020 |
| kn8-cicada-wb | 500 | −7.6409 | 0.0924 | −7.3684 | 0.0315 | 100 | −7.0063 [−7.0470, −6.9661] | −6.7432 [−6.8131, −6.6718] | n/a | 0.973 | 0.058 |
| lp-ngram3-heldout | 1000 | −7.1742 | 0.0740 | −6.9432 | 0.0222 | 100 | −6.6876 [−6.7279, −6.6483] | −6.5018 [−6.5716, −6.4336] | 0.029 | 0.396 | 0.009 |
| cicada-ngram3 | 1000 | −9.5260 | 0.1576 | −9.0405 | 0.0434 | 100 | −8.5408 [−8.6477, −8.4501] | −8.1775 [−8.3614, −8.0210] | 0.025 | 0.359 | 0.019 |
| general-ngram3 | 1000 | −9.7304 | 0.1741 | −9.1858 | 0.0451 | 100 | −8.6671 [−8.7475, −8.6003] | −8.2901 [−8.4249, −8.1731] | 0.021 | 0.352 | 0.013 |
| kn4-lp-heldout | 1000 | −6.1693 | 0.0666 | −5.9647 | 0.0196 | 100 | −5.7388 [−5.7724, −5.7018] | −5.5746 [−5.6323, −5.5129] | 0.020 | 0.399 | 0.010 |
| kn4-cicada | 1000 | −6.6870 | 0.0458 | −6.5408 | 0.0166 | 100 | −6.3498 [−6.3851, −6.3142] | −6.2110 [−6.2707, −6.1497] | 0.023 | 0.380 | 0.003 |
| kn5-cicada | 1000 | −6.5766 | 0.0477 | −6.4259 | 0.0140 | 100 | −6.2644 [−6.2886, −6.2390] | −6.1470 [−6.1890, −6.1027] | 0.025 | 0.410 | 0.007 |
| kn6-cicada | 1000 | −6.5628 | 0.0490 | −6.4077 | 0.0147 | 100 | −6.2380 [−6.2639, −6.2124] | −6.1147 [−6.1580, −6.0701] | 0.026 | 0.406 | 0.003 |
| kn8-cicada | 1000 | −6.5619 | 0.0492 | −6.4061 | 0.0148 | 100 | −6.2361 [−6.2644, −6.2117] | −6.1126 [−6.1607, −6.0710] | 0.026 | 0.395 | 0.002 |
| kn8-general | 1000 | −6.5843 | 0.0473 | −6.4332 | 0.0140 | 100 | −6.2725 [−6.2999, −6.2503] | −6.1556 [−6.2046, −6.1185] | 0.027 | 0.404 | 0.015 |
| kn8-latin | 1000 | −7.8120 | 0.0908 | −7.5250 | 0.0217 | 100 | −7.2757 [−7.3110, −7.2407] | −7.0945 [−7.1526, −7.0367] | 0.025 | 0.412 | 0.022 |
| kn8-old-english | 1000 | −6.4805 | 0.0607 | −6.2921 | 0.0168 | 100 | −6.0991 [−6.1285, −6.0757] | −5.9588 [−6.0101, −5.9164] | 0.018 | 0.373 | 0.020 |
| kn8-vowel-dropped | 1000 | −6.8856 | 0.0755 | −6.6522 | 0.0229 | 100 | −6.3892 [−6.4456, −6.3415] | −6.1981 [−6.2944, −6.1168] | 0.015 | 0.391 | 0.001 |
| kn8-cicada-wb | 1000 | −7.6390 | 0.0655 | −7.4451 | 0.0230 | 100 | −7.1809 [−7.2222, −7.1396] | −6.9888 [−7.0617, −6.9177] | n/a | 0.992 | 0.009 |

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.nulls.cells[*] (null, fit, bars, ks_max_in_claim, check)` · `python scripts/scorer_power.py --quick --section nulls`*

Scale check: the installed / staged record against this run's refit.

| scorer | L | record | draws | installed mu_b / beta | refit mu_b / beta | delta bar@10^6 | delta bar@2^32 | installed bar in refit CI | fingerprint |
|---|---|---|---|---|---|---|---|---|---|
| lp-ngram3-heldout | 120 | installed `lp-ngram3-heldout__rigid__L120.json` | 1,000,000 | −6.4823 / 0.0600 | −6.4712 / 0.0633 | 0.0494 | 0.0773 | yes | same |
| cicada-ngram3 | 120 | installed `cicada-ngram3__rigid__L120.json` | 1,000,000 | −8.0681 / 0.1267 | −8.0263 / 0.1251 | 0.0233 | 0.0098 | yes | same |
| general-ngram3 | 120 | installed `general-ngram3__rigid__L120.json` | 1,000,000 | −8.1372 / 0.1368 | −8.1169 / 0.1331 | −0.0219 | −0.0525 | yes | same |
| lp-ngram3-heldout | 240 | installed `lp-ngram3-heldout__rigid__L240.json` | 1,000,000 | −6.6942 / 0.0437 | −6.6905 / 0.0459 | 0.0283 | 0.0461 | yes | same |
| cicada-ngram3 | 240 | installed `cicada-ngram3__rigid__L240.json` | 1,000,000 | −8.5054 / 0.0917 | −8.4879 / 0.0969 | 0.0773 | 0.1208 | yes | same |
| general-ngram3 | 240 | installed `general-ngram3__rigid__L240.json` | 1,000,000 | −8.6128 / 0.0980 | −8.5847 / 0.1099 | 0.1654 | 0.2653 | yes | same |

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.nulls.cells[*].scale_check` · `python scripts/scorer_power.py --quick --section nulls`*

Wrong-key nulls per family (null b), the nb cell with the largest KS in the claim (the wb cell's KS carries the mask dependence of section 6 and is printed there):

| family | n | keys | mean | sd | max | KS vs uniform | KS crit 0.05 | in claim | above bar@10^6 | above bar@keys |
|---|---|---|---|---|---|---|---|---|---|---|
| vigenere-short-key | 5000 | 2^32+ | −7.1720 | 0.1036 | −6.4497 | 0.073 | 0.020 | no | 3 | n/a |
| atbash-shift | 57 | 58 | −7.2019 | 0.4322 | −6.1371 | 0.396 | 0.180 | no | 6 | 11 (bar −6.9043) |
| totient-stream | 5000 | 10,000 | −7.1719 | 0.0735 | −6.9007 | 0.015 | 0.020 | no | 0 | 0 (bar −6.7899) |
| sha256-ctr/vigenere/raw | 5000 | 2^32+ | −7.1739 | 0.0733 | −6.8886 | 0.010 | 0.020 | yes | 0 | n/a |
| sha256-ctr/vigenere/atbash | 5000 | 2^32+ | −7.1719 | 0.0737 | −6.8533 | 0.020 | 0.020 | yes | 0 | n/a |
| sha256-ctr/vigenere/first-difference | 5000 | 2^32+ | −7.1733 | 0.0736 | −6.9090 | 0.009 | 0.020 | yes | 0 | n/a |
| sha256-ctr/vigenere/chain-increment | 5000 | 2^32+ | −7.1732 | 0.0731 | −6.9204 | 0.014 | 0.020 | yes | 0 | n/a |
| sha256-ctr/beaufort/raw | 5000 | 2^32+ | −7.1733 | 0.0733 | −6.8721 | 0.010 | 0.020 | yes | 0 | n/a |
| sha256-ctr/beaufort/atbash | 5000 | 2^32+ | −7.1718 | 0.0741 | −6.9171 | 0.015 | 0.020 | yes | 0 | n/a |
| sha256-ctr/beaufort/first-difference | 5000 | 2^32+ | −7.1709 | 0.0738 | −6.9163 | 0.029 | 0.020 | yes | 0 | n/a |
| sha256-ctr/beaufort/chain-increment | 5000 | 2^32+ | −7.1740 | 0.0734 | −6.8560 | 0.009 | 0.020 | yes | 0 | n/a |
| numpy-pcg64/vigenere/raw | 5000 | 2^32+ | −7.1736 | 0.0738 | −6.8314 | 0.010 | 0.020 | yes | 0 | n/a |
| numpy-pcg64/vigenere/atbash | 5000 | 2^32+ | −7.1753 | 0.0726 | −6.8773 | 0.016 | 0.020 | yes | 0 | n/a |
| numpy-pcg64/vigenere/first-difference | 5000 | 2^32+ | −7.1744 | 0.0725 | −6.8661 | 0.017 | 0.020 | yes | 0 | n/a |
| numpy-pcg64/vigenere/chain-increment | 5000 | 2^32+ | −7.1732 | 0.0732 | −6.8851 | 0.014 | 0.020 | yes | 0 | n/a |
| numpy-pcg64/beaufort/raw | 5000 | 2^32+ | −7.1729 | 0.0733 | −6.8130 | 0.013 | 0.020 | yes | 0 | n/a |
| numpy-pcg64/beaufort/atbash | 5000 | 2^32+ | −7.1724 | 0.0745 | −6.9293 | 0.020 | 0.020 | yes | 0 | n/a |
| numpy-pcg64/beaufort/first-difference | 5000 | 2^32+ | −7.1732 | 0.0737 | −6.8981 | 0.017 | 0.020 | yes | 0 | n/a |
| numpy-pcg64/beaufort/chain-increment | 5000 | 2^32+ | −7.1751 | 0.0725 | −6.8865 | 0.018 | 0.020 | yes | 0 | n/a |

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.nulls.cells[scorer=lp-ngram3-heldout, L=1000].wrong_key` · `python scripts/scorer_power.py --quick --section nulls`*

## 3. Power table

200 plants per (register, L): random held-out windows, a random key per family, encrypt, decode with the true key (asserted equal to the plaintext for every rigid additive family), scored under every scorer. Power = share of plants above the bar; Wilson 95 % intervals; power at the bootstrap bars too. The target line is the spec's (>= 0.9 English, >= 0.5 Latin / vowel-dropped), printed per cell, never as a verdict word. A cell whose plant text is training text is marked and is not a power. Plants sit at distinct offsets; where the register holds fewer disjoint windows than plants (the 1,533-rune heldout-solved-sections register at L >= 263, section 1) they overlap and the Wilson interval is nominal.

| register | L | scorer | held out | planted mean (sd, min) | bar@10^6 | power [Wilson] | power @ CI bars | power@2^32 | rank-1 | target |
|---|---|---|---|---|---|---|---|---|---|---|
| english-general | 100 | lp-ngram3-heldout | yes | −4.3090 (0.224, −4.9344) | −5.5252 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.990 | 20/20 | met (>= 0.9) |
| english-general | 100 | cicada-ngram3 | yes | −3.5578 (0.217, −4.4123) | −6.4415 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 100 | general-ngram3 | no | −3.3109 (0.130, −3.7692) | −6.2479 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| english-general | 100 | kn4-lp-heldout | yes | −4.0125 (0.164, −4.4212) | −4.8979 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 100 | kn4-cicada | yes | −3.3571 (0.279, −4.3702) | −5.5143 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 100 | kn5-cicada | yes | −3.2672 (0.311, −4.3194) | −5.4590 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 100 | kn6-cicada | yes | −3.2406 (0.311, −4.2843) | −5.4360 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 100 | kn8-cicada | yes | −3.2301 (0.309, −4.2637) | −5.4228 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 100 | kn8-general | yes | −2.5993 (0.283, −3.2973) | −5.5029 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 100 | kn8-latin | yes | −5.8261 (0.427, −7.0944) | −5.8227 | 0.480 [0.412, 0.549] | 0.665 / 0.335 | 0.040 | 20/20 | not met |
| english-general | 100 | kn8-old-english | yes | −4.8373 (0.178, −5.2752) | −5.2763 | 1.000 [0.981, 1.000] | 1.000 / 0.990 | 0.530 | 20/20 | met (>= 0.9) |
| english-general | 100 | kn8-vowel-dropped | yes | −5.4276 (0.195, −5.8829) | −5.3387 | 0.355 [0.292, 0.423] | 0.600 / 0.095 | 0.000 | 20/20 | not met |
| english-general | 100 | kn8-cicada-wb | yes | −3.2236 (0.345, −4.4658) | −6.1773 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 240 | lp-ngram3-heldout | yes | −4.3200 (0.177, −4.7470) | −6.1625 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 240 | cicada-ngram3 | yes | −3.5776 (0.167, −4.1801) | −7.3733 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 240 | general-ngram3 | no | −3.3083 (0.113, −3.7618) | −7.3198 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| english-general | 240 | kn4-lp-heldout | yes | −4.0196 (0.117, −4.3296) | −5.2978 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 240 | kn4-cicada | yes | −3.3842 (0.196, −4.0283) | −6.0705 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 240 | kn5-cicada | yes | −3.2823 (0.216, −3.9839) | −5.9355 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 240 | kn6-cicada | yes | −3.2494 (0.221, −3.9960) | −5.8961 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 240 | kn8-cicada | yes | −3.2369 (0.220, −3.9528) | −5.8932 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 240 | kn8-general | yes | −2.5844 (0.237, −3.1339) | −5.8583 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 240 | kn8-latin | yes | −5.8597 (0.292, −6.6838) | −6.5941 | 0.995 [0.972, 0.999] | 0.995 / 0.985 | 0.825 | 20/20 | met (>= 0.9) |
| english-general | 240 | kn8-old-english | yes | −4.8175 (0.138, −5.2810) | −5.7147 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 240 | kn8-vowel-dropped | yes | −5.4496 (0.124, −5.7734) | −5.8419 | 1.000 [0.981, 1.000] | 1.000 / 0.995 | 0.495 | 20/20 | met (>= 0.9) |
| english-general | 240 | kn8-cicada-wb | yes | −3.2260 (0.270, −4.2305) | −6.7496 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 250 | lp-ngram3-heldout | yes | −4.3268 (0.168, −4.7309) | −6.2196 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 250 | cicada-ngram3 | yes | −3.5625 (0.141, −3.9563) | −7.3684 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 250 | general-ngram3 | no | −3.3029 (0.097, −3.5915) | −7.3274 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| english-general | 250 | kn4-lp-heldout | yes | −4.0223 (0.118, −4.3401) | −5.3190 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 250 | kn4-cicada | yes | −3.3662 (0.194, −3.8423) | −6.0157 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 250 | kn5-cicada | yes | −3.2681 (0.223, −3.8065) | −5.9063 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 250 | kn6-cicada | yes | −3.2341 (0.222, −3.7967) | −5.8760 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 250 | kn8-cicada | yes | −3.2227 (0.222, −3.7750) | −5.8725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 250 | kn8-general | yes | −2.5955 (0.229, −3.1373) | −5.8878 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 250 | kn8-latin | yes | −5.8701 (0.264, −6.7155) | −6.6535 | 0.995 [0.972, 0.999] | 1.000 / 0.995 | 0.915 | 20/20 | met (>= 0.9) |
| english-general | 250 | kn8-old-english | yes | −4.8295 (0.143, −5.1993) | −5.6854 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 250 | kn8-vowel-dropped | yes | −5.4488 (0.122, −5.7704) | −5.8881 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.705 | 20/20 | met (>= 0.9) |
| english-general | 250 | kn8-cicada-wb | yes | −3.2017 (0.252, −3.9494) | −6.8308 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 263 | lp-ngram3-heldout | yes | −4.3537 (0.165, −4.8799) | −6.2653 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 263 | cicada-ngram3 | yes | −3.5865 (0.152, −4.0503) | −7.4153 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 263 | general-ngram3 | no | −3.3173 (0.103, −3.6043) | −7.3851 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| english-general | 263 | kn4-lp-heldout | yes | −4.0409 (0.115, −4.4010) | −5.3773 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 263 | kn4-cicada | yes | −3.3807 (0.192, −3.8373) | −6.0395 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 263 | kn5-cicada | yes | −3.2784 (0.213, −3.7814) | −5.9041 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 263 | kn6-cicada | yes | −3.2509 (0.216, −3.7732) | −5.8795 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 263 | kn8-cicada | yes | −3.2354 (0.214, −3.7553) | −5.8760 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 263 | kn8-general | yes | −2.5811 (0.225, −3.1156) | −5.8803 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 263 | kn8-latin | yes | −5.8346 (0.286, −6.4845) | −6.7173 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.965 | 20/20 | met (>= 0.9) |
| english-general | 263 | kn8-old-english | yes | −4.8543 (0.132, −5.1665) | −5.7267 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 263 | kn8-vowel-dropped | yes | −5.4558 (0.109, −5.6996) | −5.9329 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.880 | 20/20 | met (>= 0.9) |
| english-general | 263 | kn8-cicada-wb | yes | −3.2241 (0.254, −3.9570) | −6.7725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | lp-ngram3-heldout | yes | −4.3263 (0.118, −4.6386) | −6.5338 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | cicada-ngram3 | yes | −3.5519 (0.110, −3.8531) | −8.1089 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | general-ngram3 | no | −3.3024 (0.076, −3.5195) | −8.1314 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| english-general | 500 | kn4-lp-heldout | yes | −4.0219 (0.085, −4.2426) | −5.6173 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | kn4-cicada | yes | −3.3648 (0.155, −3.7534) | −6.2172 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | kn5-cicada | yes | −3.2597 (0.172, −3.6765) | −6.1136 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | kn6-cicada | yes | −3.2298 (0.175, −3.6841) | −6.0826 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | kn8-cicada | yes | −3.2172 (0.173, −3.6665) | −6.0793 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | kn8-general | yes | −2.5754 (0.183, −3.0380) | −6.1430 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | kn8-latin | yes | −5.8645 (0.218, −6.3530) | −6.9992 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | kn8-old-english | yes | −4.8426 (0.097, −5.1447) | −5.9216 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | kn8-vowel-dropped | yes | −5.4505 (0.092, −5.6973) | −6.1131 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 500 | kn8-cicada-wb | yes | −3.1923 (0.208, −3.8319) | −7.0063 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | lp-ngram3-heldout | yes | −4.3420 (0.103, −4.6203) | −6.6876 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | cicada-ngram3 | yes | −3.5670 (0.097, −3.8394) | −8.5408 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | general-ngram3 | no | −3.3105 (0.071, −3.4637) | −8.6671 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| english-general | 1000 | kn4-lp-heldout | yes | −4.0315 (0.074, −4.2049) | −5.7388 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | kn4-cicada | yes | −3.3721 (0.130, −3.7235) | −6.3498 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | kn5-cicada | yes | −3.2701 (0.143, −3.6283) | −6.2644 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | kn6-cicada | yes | −3.2377 (0.146, −3.6183) | −6.2380 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | kn8-cicada | yes | −3.2256 (0.144, −3.5930) | −6.2361 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | kn8-general | yes | −2.6008 (0.175, −2.9179) | −6.2725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | kn8-latin | yes | −5.8587 (0.160, −6.2334) | −7.2757 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | kn8-old-english | yes | −4.8395 (0.069, −5.0267) | −6.0991 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | kn8-vowel-dropped | yes | −5.4518 (0.061, −5.5936) | −6.3892 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| english-general | 1000 | kn8-cicada-wb | yes | −3.2083 (0.176, −3.7174) | −7.1809 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 100 | lp-ngram3-heldout | yes | −4.1980 (0.234, −4.9585) | −5.5252 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.995 | 20/20 | met (>= 0.9) |
| cicada-english | 100 | cicada-ngram3 | no | −3.1930 (0.143, −3.5515) | −6.4415 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| cicada-english | 100 | general-ngram3 | yes | −3.3725 (0.145, −3.8481) | −6.2479 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 100 | kn4-lp-heldout | yes | −3.9329 (0.177, −4.4235) | −4.8979 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 100 | kn4-cicada | yes | −2.8310 (0.234, −3.5266) | −5.5143 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 100 | kn5-cicada | yes | −2.6188 (0.265, −3.3811) | −5.4590 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 100 | kn6-cicada | yes | −2.5692 (0.267, −3.3305) | −5.4360 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 100 | kn8-cicada | yes | −2.5651 (0.272, −3.3238) | −5.4228 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 100 | kn8-general | yes | −2.7498 (0.238, −3.3635) | −5.5029 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 100 | kn8-latin | yes | −5.5043 (0.429, −6.9434) | −5.8227 | 0.765 [0.702, 0.818] | 0.900 / 0.650 | 0.150 | 20/20 | not met |
| cicada-english | 100 | kn8-old-english | yes | −4.8036 (0.208, −5.4040) | −5.2763 | 0.995 [0.972, 0.999] | 0.995 / 0.975 | 0.635 | 20/20 | met (>= 0.9) |
| cicada-english | 100 | kn8-vowel-dropped | yes | −5.4129 (0.231, −6.2351) | −5.3387 | 0.420 [0.354, 0.489] | 0.605 / 0.115 | 0.005 | 19/20 | not met |
| cicada-english | 100 | kn8-cicada-wb | yes | −2.4762 (0.281, −3.4672) | −6.1773 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | lp-ngram3-heldout | yes | −4.2004 (0.184, −4.8182) | −6.1625 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | cicada-ngram3 | no | −3.1969 (0.097, −3.5609) | −7.3733 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| cicada-english | 240 | general-ngram3 | yes | −3.3734 (0.097, −3.6415) | −7.3198 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | kn4-lp-heldout | yes | −3.9332 (0.137, −4.2843) | −5.2978 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | kn4-cicada | yes | −2.8327 (0.186, −3.5873) | −6.0705 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | kn5-cicada | yes | −2.6103 (0.203, −3.4196) | −5.9355 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | kn6-cicada | yes | −2.5542 (0.207, −3.4009) | −5.8961 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | kn8-cicada | yes | −2.5467 (0.210, −3.4005) | −5.8932 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | kn8-general | yes | −2.7400 (0.182, −3.2699) | −5.8583 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | kn8-latin | yes | −5.5689 (0.295, −6.3806) | −6.5941 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.965 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | kn8-old-english | yes | −4.8232 (0.140, −5.1294) | −5.7147 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | kn8-vowel-dropped | yes | −5.4240 (0.161, −5.7725) | −5.8419 | 1.000 [0.981, 1.000] | 1.000 / 0.985 | 0.545 | 20/20 | met (>= 0.9) |
| cicada-english | 240 | kn8-cicada-wb | yes | −2.4450 (0.220, −3.3977) | −6.7496 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | lp-ngram3-heldout | yes | −4.1985 (0.166, −4.7903) | −6.2196 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | cicada-ngram3 | no | −3.2092 (0.104, −3.6258) | −7.3684 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| cicada-english | 250 | general-ngram3 | yes | −3.3836 (0.105, −3.6615) | −7.3274 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | kn4-lp-heldout | yes | −3.9270 (0.128, −4.2786) | −5.3190 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | kn4-cicada | yes | −2.8523 (0.176, −3.6273) | −6.0157 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | kn5-cicada | yes | −2.6332 (0.198, −3.5078) | −5.9063 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | kn6-cicada | yes | −2.5771 (0.203, −3.5145) | −5.8760 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | kn8-cicada | yes | −2.5653 (0.204, −3.4653) | −5.8725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | kn8-general | yes | −2.7428 (0.169, −3.3353) | −5.8878 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | kn8-latin | yes | −5.5336 (0.272, −6.2294) | −6.6535 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | kn8-old-english | yes | −4.7919 (0.143, −5.1449) | −5.6854 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | kn8-vowel-dropped | yes | −5.3925 (0.154, −5.7949) | −5.8881 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.780 | 20/20 | met (>= 0.9) |
| cicada-english | 250 | kn8-cicada-wb | yes | −2.4601 (0.214, −3.4939) | −6.8308 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | lp-ngram3-heldout | yes | −4.2135 (0.162, −4.7502) | −6.2653 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | cicada-ngram3 | no | −3.1996 (0.098, −3.4925) | −7.4153 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| cicada-english | 263 | general-ngram3 | yes | −3.3742 (0.094, −3.7204) | −7.3851 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | kn4-lp-heldout | yes | −3.9354 (0.125, −4.2678) | −5.3773 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | kn4-cicada | yes | −2.8280 (0.183, −3.5651) | −6.0395 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | kn5-cicada | yes | −2.6098 (0.196, −3.4313) | −5.9041 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | kn6-cicada | yes | −2.5621 (0.195, −3.3936) | −5.8795 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | kn8-cicada | yes | −2.5519 (0.196, −3.3767) | −5.8760 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | kn8-general | yes | −2.7279 (0.165, −3.2477) | −5.8803 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | kn8-latin | yes | −5.5148 (0.279, −6.1960) | −6.7173 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | kn8-old-english | yes | −4.8091 (0.140, −5.1629) | −5.7267 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | kn8-vowel-dropped | yes | −5.4148 (0.147, −5.8064) | −5.9329 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.855 | 20/20 | met (>= 0.9) |
| cicada-english | 263 | kn8-cicada-wb | yes | −2.4494 (0.205, −3.3778) | −6.7725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | lp-ngram3-heldout | yes | −4.2244 (0.125, −4.6003) | −6.5338 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | cicada-ngram3 | no | −3.2012 (0.076, −3.4185) | −8.1089 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| cicada-english | 500 | general-ngram3 | yes | −3.3842 (0.078, −3.5758) | −8.1314 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | kn4-lp-heldout | yes | −3.9486 (0.089, −4.1724) | −5.6173 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | kn4-cicada | yes | −2.8255 (0.136, −3.3095) | −6.2172 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | kn5-cicada | yes | −2.5953 (0.144, −3.1727) | −6.1136 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | kn6-cicada | yes | −2.5380 (0.139, −3.1590) | −6.0826 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | kn8-cicada | yes | −2.5285 (0.141, −3.1237) | −6.0793 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | kn8-general | yes | −2.7214 (0.128, −3.1217) | −6.1430 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | kn8-latin | yes | −5.5136 (0.195, −6.0489) | −6.9992 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | kn8-old-english | yes | −4.8154 (0.107, −5.1133) | −5.9216 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | kn8-vowel-dropped | yes | −5.4240 (0.113, −5.6536) | −6.1131 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 500 | kn8-cicada-wb | yes | −2.4194 (0.150, −3.0780) | −7.0063 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | lp-ngram3-heldout | yes | −4.2150 (0.091, −4.4629) | −6.6876 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | cicada-ngram3 | no | −3.1986 (0.053, −3.3497) | −8.5408 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| cicada-english | 1000 | general-ngram3 | yes | −3.3781 (0.052, −3.5112) | −8.6671 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | kn4-lp-heldout | yes | −3.9425 (0.064, −4.0889) | −5.7388 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | kn4-cicada | yes | −2.8299 (0.104, −3.1649) | −6.3498 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | kn5-cicada | yes | −2.5988 (0.105, −2.9877) | −6.2644 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | kn6-cicada | yes | −2.5414 (0.099, −2.9308) | −6.2380 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | kn8-cicada | yes | −2.5318 (0.101, −2.9105) | −6.2361 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | kn8-general | yes | −2.7263 (0.090, −2.9718) | −6.2725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | kn8-latin | yes | −5.5232 (0.137, −5.8628) | −7.2757 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | kn8-old-english | yes | −4.8170 (0.088, −5.0186) | −6.0991 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | kn8-vowel-dropped | yes | −5.4205 (0.093, −5.6394) | −6.3892 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| cicada-english | 1000 | kn8-cicada-wb | yes | −2.4229 (0.108, −2.8785) | −7.1809 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| latin | 100 | lp-ngram3-heldout | yes | −4.8018 (0.214, −5.5166) | −5.5252 | 1.000 [0.981, 1.000] | 1.000 / 0.995 | 0.675 | 20/20 | met (>= 0.5) |
| latin | 100 | cicada-ngram3 | yes | −4.2785 (0.276, −5.1237) | −6.4415 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 100 | general-ngram3 | yes | −4.3074 (0.305, −5.4733) | −6.2479 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.975 | 20/20 | met (>= 0.5) |
| latin | 100 | kn4-lp-heldout | yes | −4.4155 (0.136, −4.8348) | −4.8979 | 1.000 [0.981, 1.000] | 1.000 / 0.995 | 0.550 | 20/20 | met (>= 0.5) |
| latin | 100 | kn4-cicada | yes | −4.3461 (0.236, −4.9329) | −5.5143 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 100 | kn5-cicada | yes | −4.3141 (0.228, −4.8149) | −5.4590 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 100 | kn6-cicada | yes | −4.2457 (0.208, −4.7276) | −5.4360 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 100 | kn8-cicada | yes | −4.2017 (0.206, −4.7010) | −5.4228 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 100 | kn8-general | yes | −4.2763 (0.212, −4.8612) | −5.5029 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 100 | kn8-latin | yes | −2.3191 (0.249, −3.2136) | −5.8227 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 100 | kn8-old-english | yes | −4.9434 (0.189, −5.4788) | −5.2763 | 0.950 [0.910, 0.973] | 0.985 / 0.895 | 0.320 | 20/20 | met (>= 0.5) |
| latin | 100 | kn8-vowel-dropped | yes | −5.5621 (0.187, −6.0131) | −5.3387 | 0.110 [0.074, 0.161] | 0.350 / 0.015 | 0.000 | 20/20 | not met |
| latin | 100 | kn8-cicada-wb | yes | −4.7335 (0.262, −5.5128) | −6.1773 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | lp-ngram3-heldout | yes | −4.8332 (0.142, −5.2940) | −6.1625 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | cicada-ngram3 | yes | −4.2890 (0.202, −4.9671) | −7.3733 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | general-ngram3 | yes | −4.3331 (0.218, −5.0280) | −7.3198 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | kn4-lp-heldout | yes | −4.4272 (0.090, −4.6816) | −5.2978 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | kn4-cicada | yes | −4.3551 (0.163, −4.7632) | −6.0705 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | kn5-cicada | yes | −4.3297 (0.152, −4.6939) | −5.9355 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | kn6-cicada | yes | −4.2597 (0.143, −4.6340) | −5.8961 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | kn8-cicada | yes | −4.2128 (0.144, −4.5782) | −5.8932 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | kn8-general | yes | −4.2863 (0.144, −4.7493) | −5.8583 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | kn8-latin | yes | −2.2775 (0.221, −2.8947) | −6.5941 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | kn8-old-english | yes | −4.9166 (0.119, −5.2866) | −5.7147 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 240 | kn8-vowel-dropped | yes | −5.5885 (0.121, −5.8672) | −5.8419 | 0.980 [0.950, 0.992] | 1.000 / 0.960 | 0.140 | 20/20 | met (>= 0.5) |
| latin | 240 | kn8-cicada-wb | yes | −4.7250 (0.160, −5.1574) | −6.7496 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | lp-ngram3-heldout | yes | −4.8233 (0.137, −5.2766) | −6.2196 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | cicada-ngram3 | yes | −4.2722 (0.181, −4.9940) | −7.3684 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | general-ngram3 | yes | −4.3132 (0.198, −5.0429) | −7.3274 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | kn4-lp-heldout | yes | −4.4197 (0.087, −4.6634) | −5.3190 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | kn4-cicada | yes | −4.3480 (0.146, −4.7540) | −6.0157 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | kn5-cicada | yes | −4.3331 (0.143, −4.6934) | −5.9063 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | kn6-cicada | yes | −4.2589 (0.131, −4.6514) | −5.8760 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | kn8-cicada | yes | −4.2102 (0.130, −4.6013) | −5.8725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | kn8-general | yes | −4.2751 (0.130, −4.7312) | −5.8878 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | kn8-latin | yes | −2.2894 (0.207, −2.8767) | −6.6535 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | kn8-old-english | yes | −4.9237 (0.111, −5.2310) | −5.6854 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 250 | kn8-vowel-dropped | yes | −5.5805 (0.124, −5.9318) | −5.8881 | 0.990 [0.964, 0.997] | 1.000 / 0.975 | 0.290 | 20/20 | met (>= 0.5) |
| latin | 250 | kn8-cicada-wb | yes | −4.7218 (0.154, −5.1005) | −6.8308 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | lp-ngram3-heldout | yes | −4.8351 (0.156, −5.3001) | −6.2653 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | cicada-ngram3 | yes | −4.2846 (0.195, −4.9462) | −7.4153 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | general-ngram3 | yes | −4.3086 (0.209, −4.9968) | −7.3851 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | kn4-lp-heldout | yes | −4.4301 (0.094, −4.6945) | −5.3773 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | kn4-cicada | yes | −4.3541 (0.161, −4.7949) | −6.0395 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | kn5-cicada | yes | −4.3375 (0.144, −4.7140) | −5.9041 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | kn6-cicada | yes | −4.2614 (0.135, −4.6520) | −5.8795 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | kn8-cicada | yes | −4.2146 (0.135, −4.5903) | −5.8760 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | kn8-general | yes | −4.2765 (0.141, −4.7247) | −5.8803 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | kn8-latin | yes | −2.2596 (0.188, −2.6988) | −6.7173 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | kn8-old-english | yes | −4.9320 (0.106, −5.2015) | −5.7267 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 263 | kn8-vowel-dropped | yes | −5.5745 (0.106, −5.8977) | −5.9329 | 1.000 [0.981, 1.000] | 1.000 / 0.990 | 0.520 | 19/20 | met (>= 0.5) |
| latin | 263 | kn8-cicada-wb | yes | −4.7230 (0.151, −5.1495) | −6.7725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | lp-ngram3-heldout | yes | −4.8111 (0.121, −5.1598) | −6.5338 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | cicada-ngram3 | yes | −4.2649 (0.150, −4.8233) | −8.1089 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | general-ngram3 | yes | −4.2957 (0.161, −4.7695) | −8.1314 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | kn4-lp-heldout | yes | −4.4143 (0.075, −4.6071) | −5.6173 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | kn4-cicada | yes | −4.3406 (0.126, −4.6932) | −6.2172 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | kn5-cicada | yes | −4.3218 (0.116, −4.6160) | −6.1136 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | kn6-cicada | yes | −4.2436 (0.107, −4.5632) | −6.0826 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | kn8-cicada | yes | −4.1996 (0.107, −4.5079) | −6.0793 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | kn8-general | yes | −4.2714 (0.106, −4.5858) | −6.1430 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | kn8-latin | yes | −2.2506 (0.159, −2.6697) | −6.9992 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | kn8-old-english | yes | −4.9238 (0.078, −5.1585) | −5.9216 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | kn8-vowel-dropped | yes | −5.5713 (0.080, −5.7617) | −6.1131 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 500 | kn8-cicada-wb | yes | −4.7019 (0.117, −4.9801) | −7.0063 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | lp-ngram3-heldout | yes | −4.8215 (0.087, −5.1003) | −6.6876 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | cicada-ngram3 | yes | −4.2732 (0.107, −4.6449) | −8.5408 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | general-ngram3 | yes | −4.3172 (0.110, −4.6305) | −8.6671 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | kn4-lp-heldout | yes | −4.4197 (0.053, −4.5715) | −5.7388 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | kn4-cicada | yes | −4.3412 (0.089, −4.6368) | −6.3498 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | kn5-cicada | yes | −4.3223 (0.083, −4.5698) | −6.2644 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | kn6-cicada | yes | −4.2507 (0.076, −4.4842) | −6.2380 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | kn8-cicada | yes | −4.2029 (0.078, −4.4376) | −6.2361 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | kn8-general | yes | −4.2732 (0.072, −4.5308) | −6.2725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | kn8-latin | yes | −2.2747 (0.117, −2.5692) | −7.2757 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | kn8-old-english | yes | −4.9294 (0.047, −5.0246) | −6.0991 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | kn8-vowel-dropped | yes | −5.5844 (0.051, −5.6808) | −6.3892 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| latin | 1000 | kn8-cicada-wb | yes | −4.7148 (0.072, −4.8991) | −7.1809 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 100 | lp-ngram3-heldout | yes | −5.6434 (0.230, −6.2802) | −5.5252 | 0.295 [0.236, 0.362] | 0.600 / 0.110 | 0.005 | 20/20 | not met |
| vowel-dropped-english | 100 | cicada-ngram3 | yes | −6.7595 (0.436, −8.0587) | −6.4415 | 0.225 [0.173, 0.288] | 0.425 / 0.125 | 0.005 | 20/20 | not met |
| vowel-dropped-english | 100 | general-ngram3 | no | −6.9229 (0.461, −8.3075) | −6.2479 | 0.070 [0.042, 0.114] | 0.250 / 0.010 | 0.000 | 20/20 | not applicable: trained-on text |
| vowel-dropped-english | 100 | kn4-lp-heldout | yes | −4.9628 (0.152, −5.3724) | −4.8979 | 0.345 [0.283, 0.413] | 0.635 / 0.120 | 0.005 | 20/20 | not met |
| vowel-dropped-english | 100 | kn4-cicada | yes | −6.0161 (0.251, −6.6005) | −5.5143 | 0.015 [0.005, 0.043] | 0.065 / 0.010 | 0.005 | 15/20 | not met |
| vowel-dropped-english | 100 | kn5-cicada | yes | −5.8686 (0.211, −6.3083) | −5.4590 | 0.010 [0.003, 0.036] | 0.065 / 0.010 | 0.005 | 17/20 | not met |
| vowel-dropped-english | 100 | kn6-cicada | yes | −5.8384 (0.199, −6.3037) | −5.4360 | 0.010 [0.003, 0.036] | 0.055 / 0.010 | 0.000 | 17/20 | not met |
| vowel-dropped-english | 100 | kn8-cicada | yes | −5.8254 (0.204, −6.2997) | −5.4228 | 0.015 [0.005, 0.043] | 0.050 / 0.010 | 0.000 | 17/20 | not met |
| vowel-dropped-english | 100 | kn8-general | yes | −5.9597 (0.207, −6.4411) | −5.5029 | 0.010 [0.003, 0.036] | 0.025 / 0.005 | 0.005 | 15/20 | not met |
| vowel-dropped-english | 100 | kn8-latin | yes | −7.2493 (0.361, −8.2810) | −5.8227 | 0.000 [0.000, 0.019] | 0.005 / 0.000 | 0.000 | 3/20 | not met |
| vowel-dropped-english | 100 | kn8-old-english | yes | −5.7851 (0.175, −6.2763) | −5.2763 | 0.000 [0.000, 0.019] | 0.015 / 0.000 | 0.000 | 17/20 | not met |
| vowel-dropped-english | 100 | kn8-vowel-dropped | yes | −3.4593 (0.277, −4.1989) | −5.3387 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 100 | kn8-cicada-wb | yes | −7.3351 (0.465, −8.5820) | −6.1773 | 0.010 [0.003, 0.036] | 0.010 / 0.010 | 0.000 | 19/20 | not met |
| vowel-dropped-english | 240 | lp-ngram3-heldout | yes | −5.6522 (0.160, −6.0281) | −6.1625 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.790 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 240 | cicada-ngram3 | yes | −6.7715 (0.323, −7.5590) | −7.3733 | 0.965 [0.930, 0.983] | 0.995 / 0.900 | 0.260 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 240 | general-ngram3 | no | −6.9286 (0.337, −7.7257) | −7.3198 | 0.860 [0.805, 0.901] | 0.970 / 0.715 | 0.080 | 20/20 | not applicable: trained-on text |
| vowel-dropped-english | 240 | kn4-lp-heldout | yes | −4.9676 (0.111, −5.2259) | −5.2978 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.490 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 240 | kn4-cicada | yes | −6.0336 (0.184, −6.4721) | −6.0705 | 0.550 [0.481, 0.617] | 0.660 / 0.395 | 0.170 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 240 | kn5-cicada | yes | −5.8883 (0.154, −6.2279) | −5.9355 | 0.615 [0.546, 0.680] | 0.710 / 0.465 | 0.130 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 240 | kn6-cicada | yes | −5.8504 (0.152, −6.1792) | −5.8961 | 0.625 [0.556, 0.689] | 0.735 / 0.485 | 0.095 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 240 | kn8-cicada | yes | −5.8381 (0.156, −6.1735) | −5.8932 | 0.645 [0.577, 0.708] | 0.725 / 0.490 | 0.120 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 240 | kn8-general | yes | −5.9735 (0.158, −6.3302) | −5.8583 | 0.225 [0.173, 0.288] | 0.395 / 0.145 | 0.015 | 20/20 | not met |
| vowel-dropped-english | 240 | kn8-latin | yes | −7.2639 (0.255, −7.8233) | −6.5941 | 0.000 [0.000, 0.019] | 0.000 / 0.000 | 0.000 | 13/20 | not met |
| vowel-dropped-english | 240 | kn8-old-english | yes | −5.7947 (0.125, −6.1450) | −5.7147 | 0.265 [0.209, 0.330] | 0.435 / 0.200 | 0.000 | 20/20 | not met |
| vowel-dropped-english | 240 | kn8-vowel-dropped | yes | −3.4617 (0.207, −3.9823) | −5.8419 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 240 | kn8-cicada-wb | yes | −7.3634 (0.314, −8.2568) | −6.7496 | 0.030 [0.014, 0.064] | 0.065 / 0.010 | 0.000 | 20/20 | not met |
| vowel-dropped-english | 250 | lp-ngram3-heldout | yes | −5.6496 (0.133, −5.9989) | −6.2196 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.975 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 250 | cicada-ngram3 | yes | −6.7352 (0.276, −7.3818) | −7.3684 | 0.990 [0.964, 0.997] | 1.000 / 0.960 | 0.245 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 250 | general-ngram3 | no | −6.8956 (0.296, −7.6321) | −7.3274 | 0.935 [0.892, 0.962] | 0.985 / 0.800 | 0.045 | 20/20 | not applicable: trained-on text |
| vowel-dropped-english | 250 | kn4-lp-heldout | yes | −4.9669 (0.088, −5.2329) | −5.3190 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.620 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 250 | kn4-cicada | yes | −6.0280 (0.161, −6.4241) | −6.0157 | 0.460 [0.392, 0.529] | 0.600 / 0.320 | 0.045 | 19/20 | not met |
| vowel-dropped-english | 250 | kn5-cicada | yes | −5.8877 (0.135, −6.2002) | −5.9063 | 0.545 [0.476, 0.613] | 0.710 / 0.380 | 0.050 | 19/20 | met (>= 0.5) |
| vowel-dropped-english | 250 | kn6-cicada | yes | −5.8484 (0.133, −6.1742) | −5.8760 | 0.585 [0.516, 0.651] | 0.740 / 0.375 | 0.055 | 19/20 | met (>= 0.5) |
| vowel-dropped-english | 250 | kn8-cicada | yes | −5.8355 (0.134, −6.1662) | −5.8725 | 0.615 [0.546, 0.680] | 0.750 / 0.450 | 0.060 | 19/20 | met (>= 0.5) |
| vowel-dropped-english | 250 | kn8-general | yes | −5.9695 (0.135, −6.3190) | −5.8878 | 0.250 [0.195, 0.314] | 0.410 / 0.135 | 0.015 | 19/20 | not met |
| vowel-dropped-english | 250 | kn8-latin | yes | −7.2861 (0.244, −7.8378) | −6.6535 | 0.005 [0.001, 0.028] | 0.015 / 0.000 | 0.000 | 13/20 | not met |
| vowel-dropped-english | 250 | kn8-old-english | yes | −5.7976 (0.116, −6.0574) | −5.6854 | 0.175 [0.129, 0.234] | 0.290 / 0.095 | 0.000 | 19/20 | not met |
| vowel-dropped-english | 250 | kn8-vowel-dropped | yes | −3.4599 (0.205, −3.9210) | −5.8881 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 250 | kn8-cicada-wb | yes | −7.3614 (0.307, −8.1128) | −6.8308 | 0.045 [0.024, 0.083] | 0.090 / 0.025 | 0.000 | 20/20 | not met |
| vowel-dropped-english | 263 | lp-ngram3-heldout | yes | −5.6853 (0.126, −5.9740) | −6.2653 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.995 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 263 | cicada-ngram3 | yes | −6.8219 (0.243, −7.4255) | −7.4153 | 0.995 [0.972, 0.999] | 1.000 / 0.975 | 0.155 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 263 | general-ngram3 | no | −6.9857 (0.277, −7.7080) | −7.3851 | 0.925 [0.880, 0.954] | 0.985 / 0.755 | 0.035 | 20/20 | not applicable: trained-on text |
| vowel-dropped-english | 263 | kn4-lp-heldout | yes | −4.9888 (0.081, −5.1820) | −5.3773 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.870 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 263 | kn4-cicada | yes | −6.0711 (0.140, −6.3990) | −6.0395 | 0.385 [0.320, 0.454] | 0.505 / 0.275 | 0.035 | 20/20 | not met |
| vowel-dropped-english | 263 | kn5-cicada | yes | −5.9216 (0.113, −6.2052) | −5.9041 | 0.400 [0.335, 0.469] | 0.610 / 0.290 | 0.010 | 20/20 | not met |
| vowel-dropped-english | 263 | kn6-cicada | yes | −5.8836 (0.111, −6.1496) | −5.8795 | 0.470 [0.402, 0.539] | 0.640 / 0.320 | 0.010 | 20/20 | not met |
| vowel-dropped-english | 263 | kn8-cicada | yes | −5.8717 (0.113, −6.1452) | −5.8760 | 0.500 [0.431, 0.569] | 0.655 / 0.360 | 0.015 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 263 | kn8-general | yes | −6.0083 (0.117, −6.2683) | −5.8803 | 0.150 [0.107, 0.206] | 0.265 / 0.070 | 0.000 | 19/20 | not met |
| vowel-dropped-english | 263 | kn8-latin | yes | −7.3346 (0.236, −8.0706) | −6.7173 | 0.000 [0.000, 0.019] | 0.015 / 0.000 | 0.000 | 10/20 | not met |
| vowel-dropped-english | 263 | kn8-old-english | yes | −5.8164 (0.099, −6.0671) | −5.7267 | 0.155 [0.111, 0.212] | 0.345 / 0.070 | 0.000 | 20/20 | not met |
| vowel-dropped-english | 263 | kn8-vowel-dropped | yes | −3.4536 (0.211, −4.0483) | −5.9329 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 263 | kn8-cicada-wb | yes | −7.4480 (0.270, −8.3012) | −6.7725 | 0.000 [0.000, 0.019] | 0.000 / 0.000 | 0.000 | 20/20 | not met |
| vowel-dropped-english | 500 | lp-ngram3-heldout | yes | −5.6757 (0.104, −5.8968) | −6.5338 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 500 | cicada-ngram3 | yes | −6.7938 (0.198, −7.3285) | −8.1089 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 500 | general-ngram3 | no | −6.9592 (0.212, −7.5147) | −8.1314 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| vowel-dropped-english | 500 | kn4-lp-heldout | yes | −4.9824 (0.069, −5.1524) | −5.6173 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 500 | kn4-cicada | yes | −6.0514 (0.123, −6.3373) | −6.2172 | 0.925 [0.880, 0.954] | 0.955 / 0.860 | 0.420 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 500 | kn5-cicada | yes | −5.9042 (0.104, −6.1279) | −6.1136 | 0.985 [0.957, 0.995] | 1.000 / 0.950 | 0.605 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 500 | kn6-cicada | yes | −5.8682 (0.101, −6.0919) | −6.0826 | 0.985 [0.957, 0.995] | 1.000 / 0.960 | 0.595 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 500 | kn8-cicada | yes | −5.8559 (0.104, −6.0838) | −6.0793 | 0.995 [0.972, 0.999] | 1.000 / 0.965 | 0.640 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 500 | kn8-general | yes | −5.9905 (0.103, −6.1783) | −6.1430 | 0.930 [0.886, 0.958] | 0.990 / 0.875 | 0.425 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 500 | kn8-latin | yes | −7.3122 (0.200, −7.7390) | −6.9992 | 0.065 [0.038, 0.108] | 0.115 / 0.050 | 0.000 | 14/20 | not met |
| vowel-dropped-english | 500 | kn8-old-english | yes | −5.8136 (0.077, −5.9981) | −5.9216 | 0.915 [0.868, 0.946] | 0.975 / 0.795 | 0.090 | 19/20 | met (>= 0.5) |
| vowel-dropped-english | 500 | kn8-vowel-dropped | yes | −3.4437 (0.182, −3.9011) | −6.1131 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 500 | kn8-cicada-wb | yes | −7.4034 (0.231, −8.0205) | −7.0063 | 0.040 [0.020, 0.077] | 0.050 / 0.030 | 0.000 | 20/20 | not met |
| vowel-dropped-english | 1000 | lp-ngram3-heldout | yes | −5.6689 (0.066, −5.8036) | −6.6876 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 1000 | cicada-ngram3 | yes | −6.8030 (0.137, −7.1248) | −8.5408 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 1000 | general-ngram3 | no | −6.9654 (0.150, −7.2845) | −8.6671 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | not applicable: trained-on text |
| vowel-dropped-english | 1000 | kn4-lp-heldout | yes | −4.9772 (0.046, −5.0966) | −5.7388 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 1000 | kn4-cicada | yes | −6.0581 (0.090, −6.2532) | −6.3498 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.955 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 1000 | kn5-cicada | yes | −5.9113 (0.069, −6.0565) | −6.2644 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 1000 | kn6-cicada | yes | −5.8731 (0.069, −6.0151) | −6.2380 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 1000 | kn8-cicada | yes | −5.8607 (0.070, −6.0065) | −6.2361 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 1000 | kn8-general | yes | −5.9999 (0.071, −6.1489) | −6.2725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 19/20 | met (>= 0.5) |
| vowel-dropped-english | 1000 | kn8-latin | yes | −7.3172 (0.114, −7.6068) | −7.2757 | 0.330 [0.269, 0.398] | 0.430 / 0.260 | 0.035 | 18/20 | not met |
| vowel-dropped-english | 1000 | kn8-old-english | yes | −5.8114 (0.055, −5.9445) | −6.0991 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 1000 | kn8-vowel-dropped | yes | −3.4205 (0.145, −3.7537) | −6.3892 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.5) |
| vowel-dropped-english | 1000 | kn8-cicada-wb | yes | −7.3881 (0.182, −7.8821) | −7.1809 | 0.110 [0.074, 0.161] | 0.170 / 0.065 | 0.010 | 20/20 | not met |
| old-english | 100 | lp-ngram3-heldout | yes | −5.3963 (0.241, −5.9187) | −5.5252 | 0.710 [0.644, 0.768] | 0.895 / 0.455 | 0.030 | 20/20 | no target in the spec |
| old-english | 100 | cicada-ngram3 | yes | −5.6151 (0.405, −6.6057) | −6.4415 | 0.995 [0.972, 0.999] | 1.000 / 0.980 | 0.305 | 20/20 | no target in the spec |
| old-english | 100 | general-ngram3 | yes | −5.6723 (0.486, −6.8141) | −6.2479 | 0.875 [0.822, 0.914] | 0.990 / 0.640 | 0.080 | 20/20 | no target in the spec |
| old-english | 100 | kn4-lp-heldout | yes | −4.8010 (0.176, −5.1885) | −4.8979 | 0.700 [0.633, 0.759] | 0.860 / 0.485 | 0.015 | 20/20 | no target in the spec |
| old-english | 100 | kn4-cicada | yes | −5.2699 (0.266, −5.8219) | −5.5143 | 0.810 [0.750, 0.858] | 0.935 / 0.625 | 0.240 | 20/20 | no target in the spec |
| old-english | 100 | kn5-cicada | yes | −5.1977 (0.219, −5.6945) | −5.4590 | 0.875 [0.822, 0.914] | 0.960 / 0.750 | 0.270 | 20/20 | no target in the spec |
| old-english | 100 | kn6-cicada | yes | −5.1270 (0.208, −5.5969) | −5.4360 | 0.940 [0.898, 0.965] | 0.995 / 0.870 | 0.340 | 20/20 | no target in the spec |
| old-english | 100 | kn8-cicada | yes | −5.1052 (0.215, −5.5786) | −5.4228 | 0.950 [0.910, 0.973] | 0.990 / 0.830 | 0.345 | 20/20 | no target in the spec |
| old-english | 100 | kn8-general | yes | −5.1712 (0.223, −5.6820) | −5.5029 | 0.950 [0.910, 0.973] | 0.970 / 0.875 | 0.380 | 20/20 | no target in the spec |
| old-english | 100 | kn8-latin | yes | −6.2640 (0.386, −7.4864) | −5.8227 | 0.140 [0.099, 0.195] | 0.280 / 0.055 | 0.000 | 19/20 | no target in the spec |
| old-english | 100 | kn8-old-english | yes | −3.0613 (0.294, −3.7198) | −5.2763 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 100 | kn8-vowel-dropped | yes | −5.8829 (0.234, −6.4513) | −5.3387 | 0.015 [0.005, 0.043] | 0.045 / 0.005 | 0.000 | 18/20 | no target in the spec |
| old-english | 100 | kn8-cicada-wb | yes | −5.8928 (0.275, −6.5710) | −6.1773 | 0.815 [0.755, 0.863] | 0.940 / 0.680 | 0.130 | 20/20 | no target in the spec |
| old-english | 240 | lp-ngram3-heldout | yes | −5.4041 (0.151, −5.7118) | −6.1625 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 240 | cicada-ngram3 | yes | −5.6104 (0.234, −6.2305) | −7.3733 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 240 | general-ngram3 | yes | −5.6865 (0.296, −6.4228) | −7.3198 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.995 | 20/20 | no target in the spec |
| old-english | 240 | kn4-lp-heldout | yes | −4.7996 (0.103, −5.0206) | −5.2978 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.965 | 20/20 | no target in the spec |
| old-english | 240 | kn4-cicada | yes | −5.2656 (0.153, −5.7488) | −6.0705 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 240 | kn5-cicada | yes | −5.2009 (0.144, −5.6459) | −5.9355 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 240 | kn6-cicada | yes | −5.1307 (0.132, −5.5549) | −5.8961 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 240 | kn8-cicada | yes | −5.1081 (0.137, −5.5533) | −5.8932 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 240 | kn8-general | yes | −5.1730 (0.135, −5.5155) | −5.8583 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 240 | kn8-latin | yes | −6.3112 (0.249, −6.8873) | −6.5941 | 0.860 [0.805, 0.901] | 0.900 / 0.755 | 0.245 | 20/20 | no target in the spec |
| old-english | 240 | kn8-old-english | yes | −3.0410 (0.203, −3.6437) | −5.7147 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 240 | kn8-vowel-dropped | yes | −5.8967 (0.145, −6.2747) | −5.8419 | 0.325 [0.264, 0.393] | 0.555 / 0.170 | 0.000 | 20/20 | no target in the spec |
| old-english | 240 | kn8-cicada-wb | yes | −5.8727 (0.184, −6.4008) | −6.7496 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.995 | 20/20 | no target in the spec |
| old-english | 250 | lp-ngram3-heldout | yes | −5.4420 (0.137, −5.7270) | −6.2196 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 250 | cicada-ngram3 | yes | −5.6608 (0.231, −6.2992) | −7.3684 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 250 | general-ngram3 | yes | −5.7391 (0.298, −6.5275) | −7.3274 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.995 | 20/20 | no target in the spec |
| old-english | 250 | kn4-lp-heldout | yes | −4.8255 (0.102, −5.0248) | −5.3190 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.990 | 20/20 | no target in the spec |
| old-english | 250 | kn4-cicada | yes | −5.2983 (0.153, −5.6460) | −6.0157 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 250 | kn5-cicada | yes | −5.2216 (0.133, −5.5722) | −5.9063 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 250 | kn6-cicada | yes | −5.1474 (0.123, −5.4766) | −5.8760 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 250 | kn8-cicada | yes | −5.1262 (0.128, −5.4712) | −5.8725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 250 | kn8-general | yes | −5.1969 (0.124, −5.5447) | −5.8878 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 250 | kn8-latin | yes | −6.3506 (0.254, −6.9320) | −6.6535 | 0.870 [0.816, 0.910] | 0.915 / 0.800 | 0.355 | 20/20 | no target in the spec |
| old-english | 250 | kn8-old-english | yes | −3.0360 (0.197, −3.6316) | −5.6854 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 250 | kn8-vowel-dropped | yes | −5.9166 (0.134, −6.2732) | −5.8881 | 0.365 [0.301, 0.434] | 0.645 / 0.195 | 0.005 | 20/20 | no target in the spec |
| old-english | 250 | kn8-cicada-wb | yes | −5.9003 (0.164, −6.2788) | −6.8308 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | lp-ngram3-heldout | yes | −5.4214 (0.141, −5.7123) | −6.2653 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | cicada-ngram3 | yes | −5.6352 (0.215, −6.0532) | −7.4153 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | general-ngram3 | yes | −5.7130 (0.279, −6.2467) | −7.3851 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | kn4-lp-heldout | yes | −4.8190 (0.104, −5.0736) | −5.3773 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | kn4-cicada | yes | −5.2836 (0.146, −5.6336) | −6.0395 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | kn5-cicada | yes | −5.2059 (0.124, −5.5768) | −5.9041 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | kn6-cicada | yes | −5.1321 (0.115, −5.4706) | −5.8795 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | kn8-cicada | yes | −5.1111 (0.120, −5.4675) | −5.8760 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | kn8-general | yes | −5.1827 (0.122, −5.4825) | −5.8803 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | kn8-latin | yes | −6.3349 (0.269, −6.9858) | −6.7173 | 0.910 [0.862, 0.942] | 0.975 / 0.840 | 0.510 | 20/20 | no target in the spec |
| old-english | 263 | kn8-old-english | yes | −3.0508 (0.204, −3.6235) | −5.7267 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 263 | kn8-vowel-dropped | yes | −5.9123 (0.127, −6.2023) | −5.9329 | 0.525 [0.456, 0.593] | 0.780 / 0.245 | 0.015 | 20/20 | no target in the spec |
| old-english | 263 | kn8-cicada-wb | yes | −5.8847 (0.170, −6.2862) | −6.7725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | lp-ngram3-heldout | yes | −5.4281 (0.097, −5.6634) | −6.5338 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | cicada-ngram3 | yes | −5.6482 (0.161, −5.9981) | −8.1089 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | general-ngram3 | yes | −5.7383 (0.197, −6.1067) | −8.1314 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | kn4-lp-heldout | yes | −4.8190 (0.070, −5.0052) | −5.6173 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | kn4-cicada | yes | −5.2886 (0.112, −5.5523) | −6.2172 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | kn5-cicada | yes | −5.2219 (0.101, −5.4903) | −6.1136 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | kn6-cicada | yes | −5.1463 (0.090, −5.3960) | −6.0826 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | kn8-cicada | yes | −5.1244 (0.095, −5.3882) | −6.0793 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | kn8-general | yes | −5.1942 (0.094, −5.3849) | −6.1430 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | kn8-latin | yes | −6.3381 (0.197, −6.6890) | −6.9992 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | kn8-old-english | yes | −3.0319 (0.148, −3.4663) | −5.9216 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 500 | kn8-vowel-dropped | yes | −5.9215 (0.095, −6.1198) | −6.1131 | 0.995 [0.972, 0.999] | 1.000 / 0.895 | 0.120 | 20/20 | no target in the spec |
| old-english | 500 | kn8-cicada-wb | yes | −5.9082 (0.117, −6.2038) | −7.0063 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | lp-ngram3-heldout | yes | −5.4243 (0.048, −5.5208) | −6.6876 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | cicada-ngram3 | yes | −5.6332 (0.074, −5.8349) | −8.5408 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | general-ngram3 | yes | −5.7094 (0.112, −5.9752) | −8.6671 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | kn4-lp-heldout | yes | −4.8171 (0.035, −4.8971) | −5.7388 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | kn4-cicada | yes | −5.2717 (0.059, −5.4019) | −6.3498 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | kn5-cicada | yes | −5.2023 (0.060, −5.3384) | −6.2644 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | kn6-cicada | yes | −5.1306 (0.049, −5.2609) | −6.2380 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | kn8-cicada | yes | −5.1079 (0.052, −5.2440) | −6.2361 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | kn8-general | yes | −5.1847 (0.051, −5.3074) | −6.2725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | kn8-latin | yes | −6.3125 (0.155, −6.5886) | −7.2757 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | kn8-old-english | yes | −3.0136 (0.134, −3.4064) | −6.0991 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | kn8-vowel-dropped | yes | −5.9173 (0.064, −6.0457) | −6.3892 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| old-english | 1000 | kn8-cicada-wb | yes | −5.8829 (0.065, −6.0552) | −7.1809 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | no target in the spec |
| heldout-solved-sections | 100 | lp-ngram3-heldout | yes | −3.8561 (0.403, −4.8595) | −5.5252 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 100 | cicada-ngram3 | yes | −3.3257 (0.142, −3.6216) | −6.4415 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 100 | general-ngram3 | yes | −3.3775 (0.175, −3.7811) | −6.2479 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 100 | kn4-lp-heldout | yes | −3.5961 (0.346, −4.2657) | −4.8979 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 100 | kn4-cicada | yes | −2.9142 (0.108, −3.2380) | −5.5143 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 100 | kn5-cicada | yes | −2.7170 (0.153, −3.2000) | −5.4590 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 100 | kn6-cicada | yes | −2.6890 (0.152, −3.0934) | −5.4360 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 100 | kn8-cicada | yes | −2.6775 (0.155, −3.1123) | −5.4228 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 100 | kn8-general | yes | −2.7968 (0.132, −3.2385) | −5.5029 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 100 | kn8-latin | yes | −5.8193 (0.326, −6.5054) | −5.8227 | 0.425 [0.359, 0.494] | 0.740 / 0.255 | 0.020 | 20/20 | not met |
| heldout-solved-sections | 100 | kn8-old-english | yes | −4.8803 (0.190, −5.2906) | −5.2763 | 0.990 [0.964, 0.997] | 1.000 / 0.950 | 0.420 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 100 | kn8-vowel-dropped | yes | −5.5600 (0.146, −5.9738) | −5.3387 | 0.055 [0.031, 0.096] | 0.330 / 0.000 | 0.000 | 20/20 | not met |
| heldout-solved-sections | 100 | kn8-cicada-wb | yes | −2.6307 (0.184, −2.9966) | −6.1773 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | lp-ngram3-heldout | yes | −3.8723 (0.272, −4.2799) | −6.1625 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | cicada-ngram3 | yes | −3.3222 (0.081, −3.5194) | −7.3733 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | general-ngram3 | yes | −3.3741 (0.135, −3.5955) | −7.3198 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | kn4-lp-heldout | yes | −3.6176 (0.241, −3.9600) | −5.2978 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | kn4-cicada | yes | −2.8978 (0.064, −3.0851) | −6.0705 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | kn5-cicada | yes | −2.6662 (0.086, −2.9270) | −5.9355 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | kn6-cicada | yes | −2.6517 (0.078, −2.8519) | −5.8961 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | kn8-cicada | yes | −2.6427 (0.090, −2.8485) | −5.8932 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | kn8-general | yes | −2.7856 (0.079, −2.9852) | −5.8583 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | kn8-latin | yes | −5.8951 (0.199, −6.2563) | −6.5941 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.850 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | kn8-old-english | yes | −4.8823 (0.139, −5.1454) | −5.7147 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | kn8-vowel-dropped | yes | −5.5786 (0.084, −5.7736) | −5.8419 | 1.000 [0.981, 1.000] | 1.000 / 0.960 | 0.020 | 19/20 | met (>= 0.9) |
| heldout-solved-sections | 240 | kn8-cicada-wb | yes | −2.5772 (0.107, −2.8101) | −6.7496 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | lp-ngram3-heldout | yes | −3.8707 (0.276, −4.2358) | −6.2196 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | cicada-ngram3 | yes | −3.3150 (0.073, −3.5162) | −7.3684 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | general-ngram3 | yes | −3.3771 (0.131, −3.5868) | −7.3274 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | kn4-lp-heldout | yes | −3.6138 (0.243, −3.9249) | −5.3190 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | kn4-cicada | yes | −2.8868 (0.058, −3.0595) | −6.0157 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | kn5-cicada | yes | −2.6609 (0.083, −2.9026) | −5.9063 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | kn6-cicada | yes | −2.6475 (0.077, −2.8453) | −5.8760 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | kn8-cicada | yes | −2.6386 (0.089, −2.8443) | −5.8725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | kn8-general | yes | −2.7764 (0.074, −2.9587) | −5.8878 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | kn8-latin | yes | −5.9032 (0.185, −6.2349) | −6.6535 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | kn8-old-english | yes | −4.8821 (0.136, −5.1298) | −5.6854 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | kn8-vowel-dropped | yes | −5.5833 (0.084, −5.7930) | −5.8881 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.235 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 250 | kn8-cicada-wb | yes | −2.5706 (0.113, −2.8016) | −6.8308 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | lp-ngram3-heldout | yes | −3.8745 (0.263, −4.2459) | −6.2653 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | cicada-ngram3 | yes | −3.3200 (0.069, −3.4944) | −7.4153 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | general-ngram3 | yes | −3.3618 (0.126, −3.5749) | −7.3851 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | kn4-lp-heldout | yes | −3.6162 (0.232, −3.9196) | −5.3773 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | kn4-cicada | yes | −2.8988 (0.062, −3.0497) | −6.0395 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | kn5-cicada | yes | −2.6692 (0.083, −2.8994) | −5.9041 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | kn6-cicada | yes | −2.6485 (0.076, −2.8327) | −5.8795 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | kn8-cicada | yes | −2.6384 (0.086, −2.8316) | −5.8760 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | kn8-general | yes | −2.7780 (0.070, −2.9617) | −5.8803 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | kn8-latin | yes | −5.8691 (0.173, −6.2297) | −6.7173 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | kn8-old-english | yes | −4.9005 (0.136, −5.1250) | −5.7267 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | kn8-vowel-dropped | yes | −5.5699 (0.083, −5.8024) | −5.9329 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 0.640 | 19/20 | met (>= 0.9) |
| heldout-solved-sections | 263 | kn8-cicada-wb | yes | −2.5711 (0.105, −2.8217) | −6.7725 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | lp-ngram3-heldout | yes | −3.8635 (0.203, −4.1468) | −6.5338 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | cicada-ngram3 | yes | −3.3126 (0.040, −3.3809) | −8.1089 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | general-ngram3 | yes | −3.3629 (0.121, −3.5339) | −8.1314 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | kn4-lp-heldout | yes | −3.6079 (0.184, −3.8481) | −5.6173 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | kn4-cicada | yes | −2.8865 (0.044, −2.9863) | −6.2172 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | kn5-cicada | yes | −2.6494 (0.047, −2.7734) | −6.1136 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | kn6-cicada | yes | −2.6359 (0.045, −2.7490) | −6.0826 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | kn8-cicada | yes | −2.6245 (0.065, −2.7464) | −6.0793 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | kn8-general | yes | −2.7714 (0.043, −2.8574) | −6.1430 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | kn8-latin | yes | −5.9016 (0.084, −6.0868) | −6.9992 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | kn8-old-english | yes | −4.8900 (0.101, −5.0369) | −5.9216 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | kn8-vowel-dropped | yes | −5.5823 (0.063, −5.7027) | −6.1131 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |
| heldout-solved-sections | 500 | kn8-cicada-wb | yes | −2.5539 (0.043, −2.6823) | −7.0063 | 1.000 [0.981, 1.000] | 1.000 / 1.000 | 1.000 | 20/20 | met (>= 0.9) |

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.power.rows[*] (claim.power, claim.ci, family.power, rank1)` · `python scripts/scorer_power.py --quick --section power` · 200 plants per cell*

## 4. Register confusion matrix

L = 100: planted mean under each scorer (power at the bar@10^6 in brackets; `t` = trained-on text, not a power)

| register \ scorer | cicada-ngram3 | general-ngram3 | kn4-cicada | kn4-lp-heldout | kn5-cicada | kn6-cicada | kn8-cicada | kn8-cicada-wb | kn8-general | kn8-latin | kn8-old-english | kn8-vowel-dropped | lp-ngram3-heldout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| english-general | −3.558 (1.00) | −3.311 (1.00) t | −3.357 (1.00) | −4.013 (1.00) | −3.267 (1.00) | −3.241 (1.00) | −3.230 (1.00) | −3.224 (1.00) | −2.599 (1.00) | −5.826 (0.48) | −4.837 (1.00) | −5.428 (0.35) | −4.309 (1.00) |
| cicada-english | −3.193 (1.00) t | −3.373 (1.00) | −2.831 (1.00) | −3.933 (1.00) | −2.619 (1.00) | −2.569 (1.00) | −2.565 (1.00) | −2.476 (1.00) | −2.750 (1.00) | −5.504 (0.77) | −4.804 (0.99) | −5.413 (0.42) | −4.198 (1.00) |
| latin | −4.278 (1.00) | −4.307 (1.00) | −4.346 (1.00) | −4.416 (1.00) | −4.314 (1.00) | −4.246 (1.00) | −4.202 (1.00) | −4.733 (1.00) | −4.276 (1.00) | −2.319 (1.00) | −4.943 (0.95) | −5.562 (0.11) | −4.802 (1.00) |
| vowel-dropped-english | −6.760 (0.23) | −6.923 (0.07) t | −6.016 (0.01) | −4.963 (0.34) | −5.869 (0.01) | −5.838 (0.01) | −5.825 (0.01) | −7.335 (0.01) | −5.960 (0.01) | −7.249 (0.00) | −5.785 (0.00) | −3.459 (1.00) | −5.643 (0.29) |
| old-english | −5.615 (0.99) | −5.672 (0.88) | −5.270 (0.81) | −4.801 (0.70) | −5.198 (0.88) | −5.127 (0.94) | −5.105 (0.95) | −5.893 (0.81) | −5.171 (0.95) | −6.264 (0.14) | −3.061 (1.00) | −5.883 (0.01) | −5.396 (0.71) |
| heldout-solved-sections | −3.326 (1.00) | −3.377 (1.00) | −2.914 (1.00) | −3.596 (1.00) | −2.717 (1.00) | −2.689 (1.00) | −2.677 (1.00) | −2.631 (1.00) | −2.797 (1.00) | −5.819 (0.42) | −4.880 (0.99) | −5.560 (0.06) | −3.856 (1.00) |

best held-out scorer per register: english-general → kn8-general, cicada-english → kn8-cicada-wb, latin → kn8-latin, vowel-dropped-english → kn8-vowel-dropped, old-english → kn8-old-english, heldout-solved-sections → kn8-cicada-wb

L = 240: planted mean under each scorer (power at the bar@10^6 in brackets; `t` = trained-on text, not a power)

| register \ scorer | cicada-ngram3 | general-ngram3 | kn4-cicada | kn4-lp-heldout | kn5-cicada | kn6-cicada | kn8-cicada | kn8-cicada-wb | kn8-general | kn8-latin | kn8-old-english | kn8-vowel-dropped | lp-ngram3-heldout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| english-general | −3.578 (1.00) | −3.308 (1.00) t | −3.384 (1.00) | −4.020 (1.00) | −3.282 (1.00) | −3.249 (1.00) | −3.237 (1.00) | −3.226 (1.00) | −2.584 (1.00) | −5.860 (0.99) | −4.817 (1.00) | −5.450 (1.00) | −4.320 (1.00) |
| cicada-english | −3.197 (1.00) t | −3.373 (1.00) | −2.833 (1.00) | −3.933 (1.00) | −2.610 (1.00) | −2.554 (1.00) | −2.547 (1.00) | −2.445 (1.00) | −2.740 (1.00) | −5.569 (1.00) | −4.823 (1.00) | −5.424 (1.00) | −4.200 (1.00) |
| latin | −4.289 (1.00) | −4.333 (1.00) | −4.355 (1.00) | −4.427 (1.00) | −4.330 (1.00) | −4.260 (1.00) | −4.213 (1.00) | −4.725 (1.00) | −4.286 (1.00) | −2.278 (1.00) | −4.917 (1.00) | −5.589 (0.98) | −4.833 (1.00) |
| vowel-dropped-english | −6.772 (0.96) | −6.929 (0.86) t | −6.034 (0.55) | −4.968 (1.00) | −5.888 (0.61) | −5.850 (0.62) | −5.838 (0.65) | −7.363 (0.03) | −5.974 (0.23) | −7.264 (0.00) | −5.795 (0.27) | −3.462 (1.00) | −5.652 (1.00) |
| old-english | −5.610 (1.00) | −5.686 (1.00) | −5.266 (1.00) | −4.800 (1.00) | −5.201 (1.00) | −5.131 (1.00) | −5.108 (1.00) | −5.873 (1.00) | −5.173 (1.00) | −6.311 (0.86) | −3.041 (1.00) | −5.897 (0.33) | −5.404 (1.00) |
| heldout-solved-sections | −3.322 (1.00) | −3.374 (1.00) | −2.898 (1.00) | −3.618 (1.00) | −2.666 (1.00) | −2.652 (1.00) | −2.643 (1.00) | −2.577 (1.00) | −2.786 (1.00) | −5.895 (1.00) | −4.882 (1.00) | −5.579 (1.00) | −3.872 (1.00) |

best held-out scorer per register: english-general → kn8-general, cicada-english → kn8-cicada-wb, latin → kn8-latin, vowel-dropped-english → kn8-vowel-dropped, old-english → kn8-old-english, heldout-solved-sections → kn8-cicada-wb

L = 250: planted mean under each scorer (power at the bar@10^6 in brackets; `t` = trained-on text, not a power)

| register \ scorer | cicada-ngram3 | general-ngram3 | kn4-cicada | kn4-lp-heldout | kn5-cicada | kn6-cicada | kn8-cicada | kn8-cicada-wb | kn8-general | kn8-latin | kn8-old-english | kn8-vowel-dropped | lp-ngram3-heldout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| english-general | −3.562 (1.00) | −3.303 (1.00) t | −3.366 (1.00) | −4.022 (1.00) | −3.268 (1.00) | −3.234 (1.00) | −3.223 (1.00) | −3.202 (1.00) | −2.595 (1.00) | −5.870 (0.99) | −4.830 (1.00) | −5.449 (1.00) | −4.327 (1.00) |
| cicada-english | −3.209 (1.00) t | −3.384 (1.00) | −2.852 (1.00) | −3.927 (1.00) | −2.633 (1.00) | −2.577 (1.00) | −2.565 (1.00) | −2.460 (1.00) | −2.743 (1.00) | −5.534 (1.00) | −4.792 (1.00) | −5.393 (1.00) | −4.199 (1.00) |
| latin | −4.272 (1.00) | −4.313 (1.00) | −4.348 (1.00) | −4.420 (1.00) | −4.333 (1.00) | −4.259 (1.00) | −4.210 (1.00) | −4.722 (1.00) | −4.275 (1.00) | −2.289 (1.00) | −4.924 (1.00) | −5.580 (0.99) | −4.823 (1.00) |
| vowel-dropped-english | −6.735 (0.99) | −6.896 (0.94) t | −6.028 (0.46) | −4.967 (1.00) | −5.888 (0.55) | −5.848 (0.58) | −5.835 (0.61) | −7.361 (0.04) | −5.969 (0.25) | −7.286 (0.01) | −5.798 (0.17) | −3.460 (1.00) | −5.650 (1.00) |
| old-english | −5.661 (1.00) | −5.739 (1.00) | −5.298 (1.00) | −4.826 (1.00) | −5.222 (1.00) | −5.147 (1.00) | −5.126 (1.00) | −5.900 (1.00) | −5.197 (1.00) | −6.351 (0.87) | −3.036 (1.00) | −5.917 (0.36) | −5.442 (1.00) |
| heldout-solved-sections | −3.315 (1.00) | −3.377 (1.00) | −2.887 (1.00) | −3.614 (1.00) | −2.661 (1.00) | −2.648 (1.00) | −2.639 (1.00) | −2.571 (1.00) | −2.776 (1.00) | −5.903 (1.00) | −4.882 (1.00) | −5.583 (1.00) | −3.871 (1.00) |

best held-out scorer per register: english-general → kn8-general, cicada-english → kn8-cicada-wb, latin → kn8-latin, vowel-dropped-english → kn8-vowel-dropped, old-english → kn8-old-english, heldout-solved-sections → kn8-cicada-wb

L = 263: planted mean under each scorer (power at the bar@10^6 in brackets; `t` = trained-on text, not a power)

| register \ scorer | cicada-ngram3 | general-ngram3 | kn4-cicada | kn4-lp-heldout | kn5-cicada | kn6-cicada | kn8-cicada | kn8-cicada-wb | kn8-general | kn8-latin | kn8-old-english | kn8-vowel-dropped | lp-ngram3-heldout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| english-general | −3.587 (1.00) | −3.317 (1.00) t | −3.381 (1.00) | −4.041 (1.00) | −3.278 (1.00) | −3.251 (1.00) | −3.235 (1.00) | −3.224 (1.00) | −2.581 (1.00) | −5.835 (1.00) | −4.854 (1.00) | −5.456 (1.00) | −4.354 (1.00) |
| cicada-english | −3.200 (1.00) t | −3.374 (1.00) | −2.828 (1.00) | −3.935 (1.00) | −2.610 (1.00) | −2.562 (1.00) | −2.552 (1.00) | −2.449 (1.00) | −2.728 (1.00) | −5.515 (1.00) | −4.809 (1.00) | −5.415 (1.00) | −4.213 (1.00) |
| latin | −4.285 (1.00) | −4.309 (1.00) | −4.354 (1.00) | −4.430 (1.00) | −4.338 (1.00) | −4.261 (1.00) | −4.215 (1.00) | −4.723 (1.00) | −4.277 (1.00) | −2.260 (1.00) | −4.932 (1.00) | −5.574 (1.00) | −4.835 (1.00) |
| vowel-dropped-english | −6.822 (0.99) | −6.986 (0.93) t | −6.071 (0.39) | −4.989 (1.00) | −5.922 (0.40) | −5.884 (0.47) | −5.872 (0.50) | −7.448 (0.00) | −6.008 (0.15) | −7.335 (0.00) | −5.816 (0.15) | −3.454 (1.00) | −5.685 (1.00) |
| old-english | −5.635 (1.00) | −5.713 (1.00) | −5.284 (1.00) | −4.819 (1.00) | −5.206 (1.00) | −5.132 (1.00) | −5.111 (1.00) | −5.885 (1.00) | −5.183 (1.00) | −6.335 (0.91) | −3.051 (1.00) | −5.912 (0.53) | −5.421 (1.00) |
| heldout-solved-sections | −3.320 (1.00) | −3.362 (1.00) | −2.899 (1.00) | −3.616 (1.00) | −2.669 (1.00) | −2.649 (1.00) | −2.638 (1.00) | −2.571 (1.00) | −2.778 (1.00) | −5.869 (1.00) | −4.901 (1.00) | −5.570 (1.00) | −3.874 (1.00) |

best held-out scorer per register: english-general → kn8-general, cicada-english → kn8-cicada-wb, latin → kn8-latin, vowel-dropped-english → kn8-vowel-dropped, old-english → kn8-old-english, heldout-solved-sections → kn8-cicada-wb

L = 500: planted mean under each scorer (power at the bar@10^6 in brackets; `t` = trained-on text, not a power)

| register \ scorer | cicada-ngram3 | general-ngram3 | kn4-cicada | kn4-lp-heldout | kn5-cicada | kn6-cicada | kn8-cicada | kn8-cicada-wb | kn8-general | kn8-latin | kn8-old-english | kn8-vowel-dropped | lp-ngram3-heldout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| english-general | −3.552 (1.00) | −3.302 (1.00) t | −3.365 (1.00) | −4.022 (1.00) | −3.260 (1.00) | −3.230 (1.00) | −3.217 (1.00) | −3.192 (1.00) | −2.575 (1.00) | −5.864 (1.00) | −4.843 (1.00) | −5.451 (1.00) | −4.326 (1.00) |
| cicada-english | −3.201 (1.00) t | −3.384 (1.00) | −2.825 (1.00) | −3.949 (1.00) | −2.595 (1.00) | −2.538 (1.00) | −2.528 (1.00) | −2.419 (1.00) | −2.721 (1.00) | −5.514 (1.00) | −4.815 (1.00) | −5.424 (1.00) | −4.224 (1.00) |
| latin | −4.265 (1.00) | −4.296 (1.00) | −4.341 (1.00) | −4.414 (1.00) | −4.322 (1.00) | −4.244 (1.00) | −4.200 (1.00) | −4.702 (1.00) | −4.271 (1.00) | −2.251 (1.00) | −4.924 (1.00) | −5.571 (1.00) | −4.811 (1.00) |
| vowel-dropped-english | −6.794 (1.00) | −6.959 (1.00) t | −6.051 (0.93) | −4.982 (1.00) | −5.904 (0.98) | −5.868 (0.98) | −5.856 (0.99) | −7.403 (0.04) | −5.991 (0.93) | −7.312 (0.07) | −5.814 (0.92) | −3.444 (1.00) | −5.676 (1.00) |
| old-english | −5.648 (1.00) | −5.738 (1.00) | −5.289 (1.00) | −4.819 (1.00) | −5.222 (1.00) | −5.146 (1.00) | −5.124 (1.00) | −5.908 (1.00) | −5.194 (1.00) | −6.338 (1.00) | −3.032 (1.00) | −5.922 (0.99) | −5.428 (1.00) |
| heldout-solved-sections | −3.313 (1.00) | −3.363 (1.00) | −2.887 (1.00) | −3.608 (1.00) | −2.649 (1.00) | −2.636 (1.00) | −2.625 (1.00) | −2.554 (1.00) | −2.771 (1.00) | −5.902 (1.00) | −4.890 (1.00) | −5.582 (1.00) | −3.864 (1.00) |

best held-out scorer per register: english-general → kn8-general, cicada-english → kn8-cicada-wb, latin → kn8-latin, vowel-dropped-english → kn8-vowel-dropped, old-english → kn8-old-english, heldout-solved-sections → kn8-cicada-wb

L = 1000: planted mean under each scorer (power at the bar@10^6 in brackets; `t` = trained-on text, not a power)

| register \ scorer | cicada-ngram3 | general-ngram3 | kn4-cicada | kn4-lp-heldout | kn5-cicada | kn6-cicada | kn8-cicada | kn8-cicada-wb | kn8-general | kn8-latin | kn8-old-english | kn8-vowel-dropped | lp-ngram3-heldout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| english-general | −3.567 (1.00) | −3.311 (1.00) t | −3.372 (1.00) | −4.031 (1.00) | −3.270 (1.00) | −3.238 (1.00) | −3.226 (1.00) | −3.208 (1.00) | −2.601 (1.00) | −5.859 (1.00) | −4.840 (1.00) | −5.452 (1.00) | −4.342 (1.00) |
| cicada-english | −3.199 (1.00) t | −3.378 (1.00) | −2.830 (1.00) | −3.942 (1.00) | −2.599 (1.00) | −2.541 (1.00) | −2.532 (1.00) | −2.423 (1.00) | −2.726 (1.00) | −5.523 (1.00) | −4.817 (1.00) | −5.421 (1.00) | −4.215 (1.00) |
| latin | −4.273 (1.00) | −4.317 (1.00) | −4.341 (1.00) | −4.420 (1.00) | −4.322 (1.00) | −4.251 (1.00) | −4.203 (1.00) | −4.715 (1.00) | −4.273 (1.00) | −2.275 (1.00) | −4.929 (1.00) | −5.584 (1.00) | −4.821 (1.00) |
| vowel-dropped-english | −6.803 (1.00) | −6.965 (1.00) t | −6.058 (1.00) | −4.977 (1.00) | −5.911 (1.00) | −5.873 (1.00) | −5.861 (1.00) | −7.388 (0.11) | −6.000 (1.00) | −7.317 (0.33) | −5.811 (1.00) | −3.420 (1.00) | −5.669 (1.00) |
| old-english | −5.633 (1.00) | −5.709 (1.00) | −5.272 (1.00) | −4.817 (1.00) | −5.202 (1.00) | −5.131 (1.00) | −5.108 (1.00) | −5.883 (1.00) | −5.185 (1.00) | −6.312 (1.00) | −3.014 (1.00) | −5.917 (1.00) | −5.424 (1.00) |

best held-out scorer per register: english-general → kn8-general, cicada-english → kn8-cicada-wb, latin → kn8-latin, vowel-dropped-english → kn8-vowel-dropped, old-english → kn8-old-english

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.confusion.lengths[L].matrix` · `python scripts/scorer_power.py --quick --section confusion`*

## 5. Beam cells

Nulls: 25,000 draws per (scorer, decoder, L) for the beam decoders (`beam_calib` decodes under uniform keys of doublet-free ciphers at the fit's canonical F count); the rigid rows reuse the nulls section's cell at the same (scorer, L) where it exists (one rigid bar per (scorer, L) in this report; the `draws` column says which), and are uniform strings at the beam draw count otherwise.

| scorer | decoder | L | draws | canonical F | null mean | sd | mu_b | beta | bar@10^6 [CI] | bar@2^32 | scale check (delta bar@10^6) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lp-ngram3-heldout | rigid | 120 | 100,000 | n/a | −7.1606 | 0.2135 | −6.4712 | 0.0633 | −5.7427 [−5.8882, −5.6297] | −5.2131 | installed 0.0494 |
| lp-ngram3-heldout | beam | 120 | 25,000 | 10 | −6.7070 | 0.1584 | −6.1673 | 0.0510 | −5.5801 [−5.7691, −5.4618] | −5.1532 | staged 0.0084 |
| lp-ngram3-heldout | beam-skip | 120 | 25,000 | n/a | −6.9052 | 0.1948 | −6.3077 | 0.0478 | −5.7572 [−5.8861, −5.6770] | −5.3571 | staged −0.1015 |
| lp-ngram3-heldout | beam-skip-int | 120 | 25,000 | 10 | −6.5952 | 0.1596 | −6.0628 | 0.0383 | −5.6220 [−5.7435, −5.5351] | −5.3015 | staged −0.1286 |
| kn4-lp-heldout | rigid | 120 | 25,000 | n/a | −6.1616 | 0.1928 | −5.5840 | 0.0474 | −5.0384 [−5.2047, −4.8998] | −4.6418 | none |
| kn4-lp-heldout | beam | 120 | 25,000 | 10 | −5.7558 | 0.1317 | −5.3332 | 0.0404 | −4.8688 [−5.0695, −4.6964] | −4.5312 | none |
| kn4-lp-heldout | beam-skip | 120 | 25,000 | n/a | −5.9379 | 0.1684 | −5.4547 | 0.0348 | −5.0544 [−5.1211, −4.9942] | −4.7635 | none |
| kn4-lp-heldout | beam-skip-int | 120 | 25,000 | 10 | −5.6676 | 0.1296 | −5.2687 | 0.0294 | −4.9302 [−5.0590, −4.7939] | −4.6842 | none |
| kn4-cicada | rigid | 120 | 25,000 | n/a | −6.6631 | 0.1323 | −6.2096 | 0.0441 | −5.7023 [−5.8378, −5.6068] | −5.3335 | none |
| kn4-cicada | beam | 120 | 25,000 | 10 | −6.3874 | 0.1125 | −5.9940 | 0.0366 | −5.5733 [−5.6442, −5.5155] | −5.2675 | none |
| kn4-cicada | beam-skip | 120 | 25,000 | n/a | −6.4986 | 0.1278 | −6.0688 | 0.0642 | −5.3303 [−5.5809, −5.1021] | −4.7935 | none |
| kn4-cicada | beam-skip-int | 120 | 25,000 | 10 | −6.3094 | 0.1158 | −5.9044 | 0.0451 | −5.3854 [−5.5965, −5.2345] | −5.0082 | none |
| lp-ngram3-heldout | rigid | 240 | 100,000 | n/a | −7.1687 | 0.1506 | −6.6905 | 0.0459 | −6.1625 [−6.2519, −6.0605] | −5.7788 | installed 0.0283 |
| lp-ngram3-heldout | beam | 240 | 25,000 | 14 | −6.7825 | 0.1087 | −6.4315 | 0.0325 | −6.0569 [−6.2057, −5.8916] | −5.7846 | staged −0.0633 |
| lp-ngram3-heldout | beam-skip | 240 | 25,000 | n/a | −6.8699 | 0.1266 | −6.4748 | 0.0346 | −6.0768 [−6.2762, −5.9161] | −5.7875 | staged −0.0334 |
| lp-ngram3-heldout | beam-skip-int | 240 | 25,000 | 14 | −6.6546 | 0.1096 | −6.3043 | 0.0503 | −5.7258 [−6.0372, −5.4280] | −5.3053 | staged 0.1486 |
| kn4-lp-heldout | rigid | 240 | 100,000 | n/a | −6.1667 | 0.1360 | −5.7541 | 0.0397 | −5.2978 [−5.3678, −5.2469] | −4.9661 | none |
| kn4-lp-heldout | beam | 240 | 25,000 | 14 | −5.8198 | 0.0910 | −5.5309 | 0.0279 | −5.2104 [−5.2998, −5.1390] | −4.9774 | none |
| kn4-lp-heldout | beam-skip | 240 | 25,000 | n/a | −5.9039 | 0.1086 | −5.5796 | 0.0276 | −5.2616 [−5.3937, −5.1324] | −5.0304 | none |
| kn4-lp-heldout | beam-skip-int | 240 | 25,000 | 14 | −5.7172 | 0.0901 | −5.4341 | 0.0372 | −5.0060 [−5.1510, −4.8847] | −4.6948 | none |
| kn4-cicada | rigid | 240 | 100,000 | n/a | −6.6765 | 0.0937 | −6.3592 | 0.0251 | −6.0705 [−6.1210, −6.0138] | −5.8605 | none |
| kn4-cicada | beam | 240 | 25,000 | 14 | −6.4451 | 0.0769 | −6.1748 | 0.0209 | −5.9345 [−5.9852, −5.8952] | −5.7597 | none |
| kn4-cicada | beam-skip | 240 | 25,000 | n/a | −6.4850 | 0.0838 | −6.2069 | 0.0209 | −5.9661 [−6.0581, −5.8860] | −5.7911 | none |
| kn4-cicada | beam-skip-int | 240 | 25,000 | 14 | −6.3579 | 0.0797 | −6.0946 | 0.0276 | −5.7772 [−5.8761, −5.6954] | −5.5465 | none |

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.beam.nulls[*]` · `python scripts/scorer_power.py --quick --section beam`*

Plants: held-out solved-section text through `pipeline.encrypt` under the forward model, decoded with the true seed and the decoys by the preset's decoder (`pipeline.decrypt`); identified = rank 1 and recovery >= 0.90. A pairing the lane spec refuses (`decoder_problems`) is still measured and marked.

| scorer | decoder | forward model | L | identified | rank-1 | median recovery | planted mean (min) | best decoy | power@10^6 [Wilson] | power@2^32 | runnable |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lp-ngram3-heldout | rigid | interrupts | 120 | 12/50 | 35/50 | 0.358 | −5.6067 (−7.3898) | −6.3761 | 0.480 [0.348, 0.615] | 0.360 | yes |
| lp-ngram3-heldout | rigid | anti-repeat | 120 | 2/50 | 30/50 | 0.300 | −6.0998 (−7.3759) | −6.2691 | 0.420 [0.294, 0.558] | 0.180 | yes |
| lp-ngram3-heldout | rigid | anti-repeat + interrupts | 120 | 3/50 | 33/50 | 0.300 | −6.1676 (−7.3759) | −6.3392 | 0.260 [0.159, 0.396] | 0.140 | yes |
| lp-ngram3-heldout | beam | interrupts | 120 | 50/50 | 50/50 | 1.000 | −3.9052 (−4.6799) | −5.8982 | 1.000 [0.929, 1.000] | 1.000 | yes |
| lp-ngram3-heldout | beam | anti-repeat | 120 | 3/50 | 31/50 | 0.275 | −6.0487 (−7.1663) | −6.1462 | 0.220 [0.128, 0.352] | 0.120 | no |
| lp-ngram3-heldout | beam | anti-repeat + interrupts | 120 | 4/50 | 36/50 | 0.367 | −5.7206 (−7.0661) | −6.2497 | 0.400 [0.276, 0.538] | 0.280 | yes |
| lp-ngram3-heldout | beam-skip | interrupts | 120 | 12/50 | 37/50 | 0.371 | −5.4561 (−7.2108) | −6.2519 | 0.500 [0.366, 0.634] | 0.400 | no |
| lp-ngram3-heldout | beam-skip | anti-repeat | 120 | 50/50 | 50/50 | 0.975 | −4.0010 (−4.8533) | −6.2181 | 1.000 [0.929, 1.000] | 1.000 | yes |
| lp-ngram3-heldout | beam-skip | anti-repeat + interrupts | 120 | 19/50 | 44/50 | 0.833 | −4.7420 (−6.9580) | −6.2295 | 0.840 [0.715, 0.917] | 0.780 | yes |
| lp-ngram3-heldout | beam-skip-int | interrupts | 120 | 50/50 | 50/50 | 1.000 | −3.9022 (−4.6975) | −6.0892 | 1.000 [0.929, 1.000] | 1.000 | no |
| lp-ngram3-heldout | beam-skip-int | anti-repeat | 120 | 49/50 | 50/50 | 0.967 | −4.0107 (−4.8025) | −5.9692 | 1.000 [0.929, 1.000] | 1.000 | no |
| lp-ngram3-heldout | beam-skip-int | anti-repeat + interrupts | 120 | 50/50 | 50/50 | 0.983 | −3.9733 (−4.7362) | −6.0375 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-lp-heldout | rigid | interrupts | 120 | 12/50 | 35/50 | 0.383 | −4.9574 (−6.2790) | −5.4961 | 0.440 [0.312, 0.577] | 0.360 | yes |
| kn4-lp-heldout | rigid | anti-repeat | 120 | 2/50 | 30/50 | 0.246 | −5.4065 (−6.4503) | −5.5009 | 0.300 [0.191, 0.438] | 0.160 | yes |
| kn4-lp-heldout | rigid | anti-repeat + interrupts | 120 | 1/50 | 35/50 | 0.304 | −5.2921 (−6.1824) | −5.4850 | 0.280 [0.175, 0.417] | 0.200 | yes |
| kn4-lp-heldout | beam | interrupts | 120 | 50/50 | 50/50 | 1.000 | −3.6204 (−4.1455) | −5.4076 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-lp-heldout | beam | anti-repeat | 120 | 1/50 | 20/50 | 0.208 | −5.4082 (−6.1287) | −5.3933 | 0.180 [0.098, 0.308] | 0.120 | no |
| kn4-lp-heldout | beam | anti-repeat + interrupts | 120 | 8/50 | 43/50 | 0.467 | −4.8040 (−6.2175) | −5.4061 | 0.460 [0.330, 0.596] | 0.360 | yes |
| kn4-lp-heldout | beam-skip | interrupts | 120 | 12/50 | 34/50 | 0.388 | −4.8322 (−6.1889) | −5.3493 | 0.500 [0.366, 0.634] | 0.420 | no |
| kn4-lp-heldout | beam-skip | anti-repeat | 120 | 50/50 | 50/50 | 0.967 | −3.7197 (−4.3364) | −5.3287 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-lp-heldout | beam-skip | anti-repeat + interrupts | 120 | 17/50 | 48/50 | 0.838 | −4.1721 (−5.9254) | −5.3343 | 0.880 [0.762, 0.944] | 0.860 | yes |
| kn4-lp-heldout | beam-skip-int | interrupts | 120 | 50/50 | 50/50 | 1.000 | −3.6207 (−4.1455) | −5.2713 | 1.000 [0.929, 1.000] | 1.000 | no |
| kn4-lp-heldout | beam-skip-int | anti-repeat | 120 | 50/50 | 50/50 | 0.975 | −3.7021 (−4.2331) | −5.2801 | 1.000 [0.929, 1.000] | 1.000 | no |
| kn4-lp-heldout | beam-skip-int | anti-repeat + interrupts | 120 | 50/50 | 50/50 | 0.983 | −3.6669 (−4.1946) | −5.2654 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-cicada | rigid | interrupts | 120 | 12/50 | 42/50 | 0.379 | −4.8832 (−6.8092) | −6.1689 | 0.580 [0.442, 0.706] | 0.500 | yes |
| kn4-cicada | rigid | anti-repeat | 120 | 2/50 | 34/50 | 0.204 | −5.7806 (−6.8600) | −6.0706 | 0.320 [0.208, 0.458] | 0.240 | yes |
| kn4-cicada | rigid | anti-repeat + interrupts | 120 | 2/50 | 38/50 | 0.267 | −5.6342 (−6.6857) | −6.0914 | 0.420 [0.294, 0.558] | 0.260 | yes |
| kn4-cicada | beam | interrupts | 120 | 50/50 | 50/50 | 1.000 | −2.9017 (−3.1586) | −6.0013 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-cicada | beam | anti-repeat | 120 | 4/50 | 35/50 | 0.217 | −5.5860 (−6.7367) | −6.0330 | 0.340 [0.224, 0.478] | 0.220 | no |
| kn4-cicada | beam | anti-repeat + interrupts | 120 | 4/50 | 36/50 | 0.379 | −5.1763 (−6.6224) | −5.9375 | 0.600 [0.462, 0.724] | 0.460 | yes |
| kn4-cicada | beam-skip | interrupts | 120 | 12/50 | 40/50 | 0.362 | −4.8189 (−6.6405) | −5.9467 | 0.540 [0.404, 0.670] | 0.440 | no |
| kn4-cicada | beam-skip | anti-repeat | 120 | 50/50 | 50/50 | 0.975 | −3.0329 (−3.3113) | −5.9604 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-cicada | beam-skip | anti-repeat + interrupts | 120 | 18/50 | 50/50 | 0.846 | −3.8234 (−6.2033) | −5.9267 | 0.900 [0.786, 0.957] | 0.840 | yes |
| kn4-cicada | beam-skip-int | interrupts | 120 | 50/50 | 50/50 | 1.000 | −2.9016 (−3.1586) | −5.8775 | 1.000 [0.929, 1.000] | 1.000 | no |
| kn4-cicada | beam-skip-int | anti-repeat | 120 | 50/50 | 50/50 | 0.971 | −3.0348 (−3.3247) | −5.8802 | 1.000 [0.929, 1.000] | 1.000 | no |
| kn4-cicada | beam-skip-int | anti-repeat + interrupts | 120 | 50/50 | 50/50 | 0.983 | −2.9647 (−3.2688) | −5.9483 | 1.000 [0.929, 1.000] | 1.000 | yes |
| lp-ngram3-heldout | rigid | interrupts | 240 | 0/50 | 33/50 | 0.221 | −6.2826 (−7.2216) | −6.6814 | 0.360 [0.241, 0.499] | 0.240 | yes |
| lp-ngram3-heldout | rigid | anti-repeat | 240 | 0/50 | 21/50 | 0.123 | −6.6718 (−7.3018) | −6.6278 | 0.160 [0.083, 0.285] | 0.100 | yes |
| lp-ngram3-heldout | rigid | anti-repeat + interrupts | 240 | 0/50 | 26/50 | 0.167 | −6.5877 (−7.5384) | −6.5321 | 0.240 [0.143, 0.374] | 0.080 | yes |
| lp-ngram3-heldout | beam | interrupts | 240 | 50/50 | 50/50 | 1.000 | −3.8577 (−4.2743) | −6.3733 | 1.000 [0.929, 1.000] | 1.000 | yes |
| lp-ngram3-heldout | beam | anti-repeat | 240 | 1/50 | 25/50 | 0.156 | −6.4065 (−7.1489) | −6.4279 | 0.180 [0.098, 0.308] | 0.160 | no |
| lp-ngram3-heldout | beam | anti-repeat + interrupts | 240 | 2/50 | 39/50 | 0.240 | −5.9399 (−6.8982) | −6.4197 | 0.440 [0.312, 0.577] | 0.360 | yes |
| lp-ngram3-heldout | beam-skip | interrupts | 240 | 0/50 | 33/50 | 0.233 | −6.0743 (−6.9315) | −6.3712 | 0.420 [0.294, 0.558] | 0.300 | no |
| lp-ngram3-heldout | beam-skip | anti-repeat | 240 | 50/50 | 50/50 | 0.971 | −3.9512 (−4.3367) | −6.3551 | 1.000 [0.929, 1.000] | 1.000 | yes |
| lp-ngram3-heldout | beam-skip | anti-repeat + interrupts | 240 | 5/50 | 50/50 | 0.735 | −4.7767 (−6.0897) | −6.4255 | 0.980 [0.895, 0.996] | 0.960 | yes |
| lp-ngram3-heldout | beam-skip-int | interrupts | 240 | 50/50 | 50/50 | 1.000 | −3.8583 (−4.2744) | −6.3121 | 1.000 [0.929, 1.000] | 1.000 | no |
| lp-ngram3-heldout | beam-skip-int | anti-repeat | 240 | 50/50 | 50/50 | 0.971 | −3.9417 (−4.3644) | −6.2992 | 1.000 [0.929, 1.000] | 1.000 | no |
| lp-ngram3-heldout | beam-skip-int | anti-repeat + interrupts | 240 | 50/50 | 50/50 | 0.988 | −3.9015 (−4.2888) | −6.1722 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-lp-heldout | rigid | interrupts | 240 | 0/50 | 32/50 | 0.215 | −5.5159 (−6.2723) | −5.7154 | 0.300 [0.191, 0.438] | 0.240 | yes |
| kn4-lp-heldout | rigid | anti-repeat | 240 | 0/50 | 21/50 | 0.123 | −5.8302 (−6.3821) | −5.6674 | 0.100 [0.043, 0.214] | 0.040 | yes |
| kn4-lp-heldout | rigid | anti-repeat + interrupts | 240 | 0/50 | 34/50 | 0.227 | −5.6391 (−6.3212) | −5.6182 | 0.180 [0.098, 0.308] | 0.060 | yes |
| kn4-lp-heldout | beam | interrupts | 240 | 50/50 | 50/50 | 1.000 | −3.6091 (−3.9569) | −5.4178 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-lp-heldout | beam | anti-repeat | 240 | 1/50 | 26/50 | 0.135 | −5.4654 (−6.0266) | −5.4525 | 0.240 [0.143, 0.374] | 0.200 | no |
| kn4-lp-heldout | beam | anti-repeat + interrupts | 240 | 1/50 | 41/50 | 0.246 | −5.3263 (−6.1110) | −5.4212 | 0.320 [0.208, 0.458] | 0.140 | yes |
| kn4-lp-heldout | beam-skip | interrupts | 240 | 0/50 | 35/50 | 0.229 | −5.3154 (−6.1058) | −5.5215 | 0.380 [0.259, 0.518] | 0.280 | no |
| kn4-lp-heldout | beam-skip | anti-repeat | 240 | 50/50 | 50/50 | 0.975 | −3.6820 (−4.0230) | −5.5432 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-lp-heldout | beam-skip | anti-repeat + interrupts | 240 | 7/50 | 49/50 | 0.765 | −4.3316 (−5.7746) | −5.5439 | 0.960 [0.865, 0.989] | 0.900 | yes |
| kn4-lp-heldout | beam-skip-int | interrupts | 240 | 50/50 | 50/50 | 1.000 | −3.6072 (−3.9569) | −5.4300 | 1.000 [0.929, 1.000] | 1.000 | no |
| kn4-lp-heldout | beam-skip-int | anti-repeat | 240 | 50/50 | 50/50 | 0.971 | −3.6900 (−4.0536) | −5.3897 | 1.000 [0.929, 1.000] | 1.000 | no |
| kn4-lp-heldout | beam-skip-int | anti-repeat + interrupts | 240 | 50/50 | 50/50 | 0.983 | −3.6402 (−3.9890) | −5.3784 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-cicada | rigid | interrupts | 240 | 0/50 | 38/50 | 0.210 | −5.6885 (−6.9093) | −6.2955 | 0.580 [0.442, 0.706] | 0.460 | yes |
| kn4-cicada | rigid | anti-repeat | 240 | 1/50 | 30/50 | 0.156 | −6.0381 (−6.8486) | −6.3092 | 0.360 [0.241, 0.499] | 0.280 | yes |
| kn4-cicada | rigid | anti-repeat + interrupts | 240 | 0/50 | 36/50 | 0.208 | −5.9912 (−6.7246) | −6.2851 | 0.500 [0.366, 0.634] | 0.420 | yes |
| kn4-cicada | beam | interrupts | 240 | 50/50 | 50/50 | 1.000 | −2.9010 (−3.0308) | −6.1315 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-cicada | beam | anti-repeat | 240 | 0/50 | 36/50 | 0.148 | −5.9016 (−6.5409) | −6.1688 | 0.380 [0.259, 0.518] | 0.280 | no |
| kn4-cicada | beam | anti-repeat + interrupts | 240 | 2/50 | 42/50 | 0.240 | −5.5245 (−6.5115) | −6.1506 | 0.600 [0.462, 0.724] | 0.440 | yes |
| kn4-cicada | beam-skip | interrupts | 240 | 0/50 | 39/50 | 0.210 | −5.5440 (−6.5758) | −6.1703 | 0.620 [0.482, 0.741] | 0.480 | no |
| kn4-cicada | beam-skip | anti-repeat | 240 | 50/50 | 50/50 | 0.975 | −3.0124 (−3.1845) | −6.1163 | 1.000 [0.929, 1.000] | 1.000 | yes |
| kn4-cicada | beam-skip | anti-repeat + interrupts | 240 | 2/50 | 49/50 | 0.673 | −4.2967 (−6.2333) | −6.1720 | 0.960 [0.865, 0.989] | 0.940 | yes |
| kn4-cicada | beam-skip-int | interrupts | 240 | 50/50 | 50/50 | 1.000 | −2.9009 (−3.0308) | −6.0341 | 1.000 [0.929, 1.000] | 1.000 | no |
| kn4-cicada | beam-skip-int | anti-repeat | 240 | 50/50 | 50/50 | 0.975 | −3.0097 (−3.1491) | −6.0826 | 1.000 [0.929, 1.000] | 1.000 | no |
| kn4-cicada | beam-skip-int | anti-repeat + interrupts | 240 | 50/50 | 50/50 | 0.988 | −2.9623 (−3.1026) | −6.0651 | 1.000 [0.929, 1.000] | 1.000 | yes |

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.beam.cells[*]` · `python scripts/scorer_power.py --quick --section beam` · 50 plants x 99 decoys per cell*

## 6. Boundaries

`kn8-cicada-wb` at L = 240: null (d) under the 54 page-start masks (1,851 strings each) and under masks sampled from the LP2 word-length histogram (the nulls table's wb row). Boundary log-probs are summed and divided by L = cipher runes; the `score_boundaries=False` variant is measured once.

| null | n | mean | sd | mu_b | beta | bar@10^6 [CI] | bar@2^32 |
|---|---|---|---|---|---|---|---|
| page-start masks | 99954 | −7.6477 | 0.1356 | −7.3391 | 0.0752 | −6.4739 [−6.6129, −6.3609] | −5.8450 |
| sampled masks | 100000 | −7.6436 | 0.1345 | −7.2513 | 0.0436 | −6.7496 [−6.8664, −6.6431] | −6.3850 |

Mask dependence: per-mask means range [−7.8871, −7.4114], sd of the mask means 0.0944 = 0.696 pooled sd; bar@10^6 page-start minus sampled 0.2757.

| variant | planted mean | separation (null sd units) | power@10^6 [Wilson] |
|---|---|---|---|
| boundaries summed (wb) | −3.2260 | 32.60 | 1.000 [0.981, 1.000] |
| score_boundaries=False (wb, measured once) | −3.0034 | 35.72 | 1.000 [0.981, 1.000] |
| no boundary model (kn8-cicada) | −3.2369 | 33.03 | 1.000 [0.981, 1.000] |

Gain of summing the boundaries over the variant: −3.12 null-sd units (english-general, L = 240, 200 plants).

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.boundaries (page_start_masks, sampled_masks, dependence, gain)` · `python scripts/scorer_power.py --quick --section boundaries`*

Wrong-key nulls of the wb scorer (`kn8-cicada-wb`, L = 1000): the decodes carry the cipher window's own mask while null (a) averages over sampled masks, so these KS statistics measure the mask dependence as well and are outside the 'wrong key = uniform string' claim (section 1).

| family | n | keys | mean | sd | max | KS vs uniform | KS crit 0.05 | in claim | above bar@10^6 | above bar@keys |
|---|---|---|---|---|---|---|---|---|---|---|
| vigenere-short-key | 5000 | 2^32+ | −7.7184 | 0.0662 | −7.1899 | 0.476 | 0.020 | no | 0 | n/a |
| atbash-shift | 57 | 58 | −7.8866 | 0.2124 | −7.2815 | 0.746 | 0.180 | no | 0 | 1 (bar −7.4049) |
| totient-stream | 5000 | 10,000 | −7.7343 | 0.0488 | −7.5397 | 0.603 | 0.020 | no | 0 | 0 (bar −7.2866) |
| sha256-ctr/vigenere/raw | 5000 | 2^32+ | −7.9018 | 0.0503 | −7.6965 | 0.977 | 0.020 | no | 0 | n/a |
| sha256-ctr/vigenere/atbash | 5000 | 2^32+ | −7.7308 | 0.0485 | −7.5526 | 0.593 | 0.020 | no | 0 | n/a |
| sha256-ctr/vigenere/first-difference | 5000 | 2^32+ | −7.7731 | 0.0486 | −7.5719 | 0.764 | 0.020 | no | 0 | n/a |
| sha256-ctr/vigenere/chain-increment | 5000 | 2^32+ | −7.9475 | 0.0497 | −7.7807 | 0.992 | 0.020 | no | 0 | n/a |
| sha256-ctr/beaufort/raw | 5000 | 2^32+ | −7.7381 | 0.0494 | −7.5560 | 0.618 | 0.020 | no | 0 | n/a |
| sha256-ctr/beaufort/atbash | 5000 | 2^32+ | −7.6276 | 0.0481 | −7.4675 | 0.132 | 0.020 | no | 0 | n/a |
| sha256-ctr/beaufort/first-difference | 5000 | 2^32+ | −7.8749 | 0.0493 | −7.6725 | 0.960 | 0.020 | no | 0 | n/a |
| sha256-ctr/beaufort/chain-increment | 5000 | 2^32+ | −7.7418 | 0.0494 | −7.5277 | 0.636 | 0.020 | no | 0 | n/a |
| numpy-pcg64/vigenere/raw | 5000 | 2^32+ | −7.8887 | 0.0495 | −7.6962 | 0.970 | 0.020 | no | 0 | n/a |
| numpy-pcg64/vigenere/atbash | 5000 | 2^32+ | −7.6762 | 0.0479 | −7.5071 | 0.284 | 0.020 | no | 0 | n/a |
| numpy-pcg64/vigenere/first-difference | 5000 | 2^32+ | −7.7353 | 0.0479 | −7.5530 | 0.614 | 0.020 | no | 0 | n/a |
| numpy-pcg64/vigenere/chain-increment | 5000 | 2^32+ | −7.7860 | 0.0492 | −7.6105 | 0.803 | 0.020 | no | 0 | n/a |
| numpy-pcg64/beaufort/raw | 5000 | 2^32+ | −7.7598 | 0.0486 | −7.5879 | 0.718 | 0.020 | no | 0 | n/a |
| numpy-pcg64/beaufort/atbash | 5000 | 2^32+ | −7.7610 | 0.0491 | −7.5795 | 0.719 | 0.020 | no | 0 | n/a |
| numpy-pcg64/beaufort/first-difference | 5000 | 2^32+ | −7.8242 | 0.0496 | −7.6361 | 0.894 | 0.020 | no | 0 | n/a |
| numpy-pcg64/beaufort/chain-increment | 5000 | 2^32+ | −7.7214 | 0.0490 | −7.5466 | 0.539 | 0.020 | no | 0 | n/a |

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.nulls.cells[scorer=kn8-cicada-wb, L=1000].wrong_key` · `python scripts/scorer_power.py --quick --section nulls`*

## 7. Order and discounts

| preset | model | order | B | D | train | runes | discounts D1/D2/D3+ per level | source per level | sparse entries | table MB |
|---|---|---|---|---|---|---|---|---|---|---|
| lp-ngram3-heldout | ngram | 3 | n/a | n/a | the seven solved sections | n/a | n/a | n/a | n/a | n/a |
| cicada-ngram3 | ngram | 3 | n/a | n/a | cicada-english | n/a | n/a | n/a | n/a | n/a |
| general-ngram3 | ngram | 3 | n/a | n/a | english-general | n/a | n/a | n/a | n/a | n/a |
| kn4-lp-heldout | kn | 4 | 29 | 4 | the seven solved sections | 1,444 | 0.143/0.143/0.143; 0.469/1.190/1.704; 0.735/1.548/1.589; 0.751/1.482/1.320 | partial:D2<-D1,D3<-D2, modified-kn, modified-kn, modified-kn | [] | 2.9 |
| kn4-cicada | kn | 4 | 29 | 4 | cicada-english | 275,694 | 0.500/0.500/0.500; 0.455/0.392/1.340; 0.473/1.037/1.480; 0.541/1.049/1.521 | fallback-0.5, modified-kn, modified-kn, modified-kn | [] | 2.9 |
| kn5-cicada | kn | 5 | 29 | 5 | cicada-english | 275,694 | 0.500/0.500/0.500; 0.455/0.392/1.340; 0.473/1.037/1.480; 0.563/1.121/1.560; 0.635/1.129/1.516 | fallback-0.5, modified-kn, modified-kn, modified-kn, modified-kn | [] | 85.0 |
| kn6-cicada | kn | 6 | 29 | 4 | cicada-english | 275,694 | 0.500/0.500/0.500; 0.455/0.392/1.340; 0.473/1.037/1.480; 0.563/1.121/1.560; 0.692/1.239/1.703; 0.733/1.213/1.540 | fallback-0.5, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn | [97352, 158160] | 9.8 |
| kn8-cicada | kn | 8 | 29 | 4 | cicada-english | 275,694 | 0.500/0.500/0.500; 0.455/0.392/1.340; 0.473/1.037/1.480; 0.563/1.121/1.560; 0.692/1.239/1.703; 0.802/1.331/1.609; 0.876/1.403/1.587; 0.875/1.340/1.558 | fallback-0.5, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn | [97352, 158160, 203565, 232979] | 16.8 |
| kn8-general | kn | 8 | 29 | 4 | english-general | 792,378 | 0.500/0.500/0.500; 0.415/0.549/1.499; 0.456/1.027/1.509; 0.530/1.064/1.571; 0.648/1.173/1.647; 0.763/1.266/1.655; 0.846/1.332/1.683; 0.845/1.282/1.612 | fallback-0.5, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn | [195449, 367791, 516472, 620813] | 33.0 |
| kn8-latin | kn | 8 | 29 | 4 | latin | 108,202 | 0.333/0.333/0.333; 0.461/1.017/0.050; 0.540/0.827/0.924; 0.595/1.035/1.582; 0.705/1.195/1.692; 0.805/1.290/1.699; 0.869/1.369/1.690; 0.845/1.312/1.491 | partial:D2<-D1,D3<-D2, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn | [39060, 59693, 75633, 86879] | 9.9 |
| kn8-old-english | kn | 8 | 29 | 4 | old-english | 75,324 | 0.500/0.500/0.500; 0.371/1.259/1.913; 0.488/0.945/1.690; 0.627/1.181/1.702; 0.770/1.301/1.842; 0.872/1.414/1.891; 0.929/1.549/1.920; 0.921/1.503/1.885 | fallback-0.5, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn | [44562, 58524, 66111, 70077] | 9.6 |
| kn8-vowel-dropped | kn | 8 | 29 | 4 | vowel-dropped-english | 527,298 | 0.500/0.500/0.500; 0.385/0.942/1.741; 0.431/0.994/1.740; 0.521/1.080/1.568; 0.677/1.245/1.703; 0.834/1.365/1.718; 0.920/1.483/1.790; 0.944/1.489/1.820 | fallback-0.5, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn | [237779, 385849, 465114, 499882] | 31.2 |
| kn8-cicada-wb | kn | 8 | 30 | 4 | cicada-english | 343,017 | 0.500/0.500/0.500; 0.493/0.437/2.033; 0.491/1.061/1.619; 0.601/1.111/1.488; 0.673/1.114/1.625; 0.752/1.210/1.582; 0.806/1.261/1.521; 0.756/1.218/1.494 | fallback-0.5, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn, modified-kn | [53484, 101333, 155840, 208057] | 14.9 |

Order comparison at L = 240, register cicada-english:

| scorer | order | null mean | null sd | beta | bar@10^6 | planted mean | separation (sd units) | power@10^6 |
|---|---|---|---|---|---|---|---|---|
| lp-ngram3-heldout | 3 | −7.1687 | 0.1506 | 0.0459 | −6.1625 | −4.2004 | 19.70 | 1.000 |
| cicada-ngram3 | 3 | −9.5095 | 0.3213 | 0.0969 | −7.3733 | −3.1969 | 19.65 | 1.000 |
| general-ngram3 | 3 | −9.7122 | 0.3546 | 0.1099 | −7.3198 | −3.3734 | 17.88 | 1.000 |
| kn4-lp-heldout | 4 | −6.1667 | 0.1360 | 0.0397 | −5.2978 | −3.9332 | 16.43 | 1.000 |
| kn4-cicada | 4 | −6.6765 | 0.0937 | 0.0251 | −6.0705 | −2.8327 | 41.01 | 1.000 |
| kn5-cicada | 5 | −6.5670 | 0.0974 | 0.0270 | −5.9355 | −2.6103 | 40.63 | 1.000 |
| kn6-cicada | 6 | −6.5532 | 0.1000 | 0.0285 | −5.8961 | −2.5542 | 39.98 | 1.000 |
| kn8-cicada | 8 | −6.5523 | 0.1004 | 0.0286 | −5.8932 | −2.5467 | 39.91 | 1.000 |
| kn8-general | 8 | −6.5737 | 0.0963 | 0.0346 | −5.8583 | −2.7400 | 39.80 | 1.000 |
| kn8-latin | 8 | −7.8021 | 0.1850 | 0.0543 | −6.5941 | −5.5689 | 12.07 | 1.000 |
| kn8-old-english | 8 | −6.4740 | 0.1241 | 0.0323 | −5.7147 | −4.8232 | 13.30 | 1.000 |
| kn8-vowel-dropped | 8 | −6.8768 | 0.1540 | 0.0468 | −5.8419 | −5.4240 | 9.43 | 1.000 |
| kn8-cicada-wb | 8 | −7.6436 | 0.1345 | 0.0436 | −6.7496 | −2.4450 | 38.66 | 1.000 |

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.order.presets[*], sections.order.comparison[*]` · `python scripts/scorer_power.py --quick --section order`*

## 8. Throughput

| scorer | order | D | table MB | keys/s L=240 | keys/s L=1000 |
|---|---|---|---|---|---|
| lp-ngram3-heldout | n/a | n/a | n/a | 258,719 | 69,228 |
| cicada-ngram3 | n/a | n/a | n/a | 294,286 | 71,443 |
| general-ngram3 | n/a | n/a | n/a | 283,219 | 64,249 |
| kn4-lp-heldout | 4 | 4 | 2.9 | 71,244 | 17,812 |
| kn4-cicada | 4 | 4 | 2.9 | 79,499 | 19,351 |
| kn5-cicada | 5 | 5 | 85.0 | 66,590 | 15,014 |
| kn6-cicada | 6 | 4 | 9.8 | 30,480 | 6,554 |
| kn8-cicada | 8 | 4 | 16.8 | 17,310 | 4,265 |
| kn8-general | 8 | 4 | 33.0 | 15,282 | 4,105 |
| kn8-latin | 8 | 4 | 9.9 | 17,951 | 4,456 |
| kn8-old-english | 8 | 4 | 9.6 | 19,330 | 4,434 |
| kn8-vowel-dropped | 8 | 4 | 31.2 | 16,975 | 4,002 |
| kn8-cicada-wb | 8 | 4 | 14.9 | 13,261 | 3,260 |
| kn8-cicada@D5 | 8 | 5 | 176.5 | 18,980 | 4,382 |

- D = 4 vs 5, sparse (kn8-cicada pinned at D = 4 vs the same fit with five dense levels (ad hoc)): D = 5 runs at 1.10x the D = 4 keys/s at L = 240 and 1.03x at L = 1000, with 176.5 MB of tables against 16.8 MB.
- D = 4 vs 5, dense (the dense kn4-cicada vs kn5-cicada): D = 5 runs at 0.84x the D = 4 keys/s at L = 240 and 0.78x at L = 1000, with 85.0 MB of tables against 2.9 MB.

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.throughput.rows[*].keys_per_s_L240, .d4_vs_d5` · `python scripts/scorer_power.py --quick --section throughput` · score_batch, best of two timings, 20,000 / 5,000 rows, host x86_64*

## 9. The three conditionals and reopens_if

- key space swept: none of LP2: the families (section 2) are the plant/decoy generators of the measurement; no seed range of any lane was searched
- decoder transition model: rigid (one key symbol per rune) for every power row; beam, beam-skip and beam-skip-int at width 8 (presets.DECODER_PARAMS) in the beam cells, with the three dense scorers only
- adjudicator register: the scorers listed in section 0: Cicada-English, general English, Latin, Old English and vowel-dropped English registers (kn8-*), plus the Phase 1 order-3 baselines; power is reported per register x scorer (section 4)
- Latin power at L = 240 (best held-out scorer lp-ngram3-heldout): 1.000 [0.981, 1.000] at the bar@10^6 (`sections.conditionals.latin_power_at_240`)
- standing conditional: every later negative is English-register-first: a Latin or other non-English plaintext is detected only to the power this table measures for that register (SESSION_PROMPT.md section B)
- reopens_if:
  - a scorer's fingerprint changes (a refit, a corpus rebuild that moves the split)
  - the --full run moves a bar by more than its bootstrap interval
  - a lane needs a length, register or decoder pairing not in this table
  - a word-boundary conditioning rule is staged (the wb null is mask-dependent)
  - a beam-compatible kn6/kn8 export lands on the GPU (the dense/sparse split moves)

*numbering LP2-0-57 · canon `023312066df4…` · git `f95a3acea0d5` · scale reduced · N_claim = 10^6, N_family = 2^32, alpha = 0.01 · JSON `sections.conditionals` · `python scripts/scorer_power.py --quick --section conditionals`*

## 10. Reproduce

- `python scripts/scorer_power.py --quick --workers 4` at git `f95a3acea0d51a6296a6d0afc282bd4e6c418fa9`; canon SHA-256 `023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585`, numbering `LP2-0-57`; Python 3.13.16, numpy 2.5.4; `runeforge/beam.py` SHA-256 `4cd3d7ba59e6…`
- fit records: `reports/scorer_power/fits/` (scale-marked; never installable unless full)
- one section: `python scripts/scorer_power.py --quick --section reusable`, `python scripts/scorer_power.py --quick --section not_covered`, `python scripts/scorer_power.py --quick --section nulls`, `python scripts/scorer_power.py --quick --section power`, `python scripts/scorer_power.py --quick --section confusion`, `python scripts/scorer_power.py --quick --section beam`, `python scripts/scorer_power.py --quick --section boundaries`, `python scripts/scorer_power.py --quick --section order`, `python scripts/scorer_power.py --quick --section throughput`, `python scripts/scorer_power.py --quick --section conditionals`, `python scripts/scorer_power.py --quick --section reproduce`
- render only: `python scripts/scorer_power.py --render-only --out reports/scorer_power.json`
- timings (s): reusable 0.0, nulls 327.0, power 24.0, confusion 0.0, beam 150.9, boundaries 8.4, order 3.7, throughput 48.2, not_covered 0.0, conditionals 0.0, reproduce 0.0
- do-not-re-run list: none (this harness writes no ledger row; its numbers are regenerated, never cited as coverage)
