# CUDA kernels (Phase 3)

Both kernels are numba.cuda, built from one plain-Python function each that is compiled
both as the CUDA device function and as a CPU njit twin; both compilations must match the
numpy reference in `runeforge/` (tests/test_gpu_beam.py, tests/test_gpu_mt.py), and a lane
needs a parity record made on the device itself (`python -m runeforge.gpu.parity`).

* `runeforge/gpu/beam_kernel.py`: the beam decoder; one thread decodes one key row and writes
  its score. No early exit: every key is decoded to the end, so no seed above the claim bar
  can be dropped.
* `runeforge/gpu/mt_kernel.py`: the `mt19937-py27` keystream; one thread seeds its own 624-word
  state (CPython's `init_by_array` over the 32-bit words of the seed), runs `genrand_int32`
  with its twist, and applies one of 2.7's four reducers (`random29`, `grb5_mod`, `grb5_rej`,
  `shuffle29`). Its rows stay on the device for the beam kernel (`keys_device`).

Not built: kernels for the other generators (each would need the same parity test against
`runeforge/generators` before it counts). A lane on one of them generates keys on the CPU,
which caps it at the generator's CPU rate.

## The Kneser-Ney scorer's export (`knx-1`) and the lookup a `score_ngram.cu` implements

Not built: the kernel itself. What exists is the table it would read and the exact algorithm,
proved on the CPU: `python scripts/export_kn.py --preset <kn preset>` writes
`reports/kn-export/<preset>.npz` (the arrays; gitignored, regenerated) and
`reports/kn-export/<preset>.json` (the manifest; committed), reloads the file and asserts that
the scalar `KNScorer.reference_logprobs` (which probes the exported hash exactly as below)
equals the vectorised `logprobs` bit for bit per position on 1,000 random windows, 100
held-out windows, the all-F window, the max-key window and the longest-probe key of every
sparse level. The manifest carries the same layout fields a kernel needs, the lookup text, the
training pin and the scorer fingerprint (`docs/kn-scorer-design.md` section 4). A kernel
counts only after it reproduces `reference_logprobs` per position on the device (the parity
rule of `.claude/rules/gpu.md`, as for the beam kernel).

### Model shape (from the manifest)

`order` n (1..8), `base` B (29; 30 for a word-boundary model, whose `boundary_symbol` is 29),
`dense_levels` D (1..min(n, 5)). Levels 1..D are complete tables; levels D+1..n are sparse. A
k-gram (x_{i-k+1} .. x_i) packs as `key = sum_j x[i-k+1+j] * B**(k-1-j)`: the oldest symbol
is the most significant digit, the newest the least. The rolling history is the last n-1
symbols, `H <- (H*B + x) mod B**(n-1)` (uint64; max key 30**8 < 2**40), so the (k-1)-symbol
history of a position is `H mod B**(k-1)` and the key of (history, x) is `hist*B + x`.

### Arrays (all 1-D, contiguous, little-endian, in the `.npz`)

| array | dtype | size | meaning |
|---|---|---|---|
| `dense_lp` | float32 | sum_{k<=D} B**k | level k at `levels[k-1].offset`: log2 P_k(x \| (k-1)-history) at every packed k-gram key, unseen grams and histories already resolved |
| `dense_bow` | float32 | B**D (only when D < n) | log2 gamma_{D+1}(h) by packed D-gram key h; 0.0 for a history unseen at level D+1 |
| `hash_keys` | uint64 | sum over sparse levels of `slots` | the open-addressing tables, one per sparse level at `levels[k-1].offset`; `0xFFFFFFFFFFFFFFFF` (`empty_key`) marks a free slot |
| `hash_lp`, `hash_bow` | float32 | same | the slot's log2 P_k(gram) and log2 gamma_{k+1}(gram as a history) (0.0 unseen, and everywhere at k = n) |
| `sorted_keys`, `sorted_lp`, `sorted_bow` | uint64 / float32 | sum of `n_entries` | the same sparse levels as ascending key arrays at `levels[k-1].sorted_offset` (what the CPU `score_batch` searches; a kernel needs the hash arrays only) |
| `discounts` | float64 | 3 n | the modified-KN D1, D2, D3+ per level (recorded, not used at lookup time) |
| `manifest` | str | 1 | the JSON manifest, the same text (indented, trailing newline) as the side file `<stem>.json`; `KNScorer.export` writes both from one string |

Per sparse level the manifest gives `n_entries` M, `slots` S = the next power of two >= 2 M,
`bits` (S = 2**bits), `shift` = 64 - bits, `mult` = `0x9E3779B97F4A7C15`, `max_probe` and
`empty_key`. The table was built by inserting the keys in ascending order with linear probing,
so it is deterministic: the same keys give the same slots.

Hash probe of `key` in a level:

```
slot = ((key * 0x9E3779B97F4A7C15) mod 2**64) >> (64 - bits)      # uint64 wrap-around multiply
for probe in 1 .. max_probe:
    k = hash_keys[offset + slot]
    if k == key:         hit  -> (hash_lp[offset + slot], hash_bow[offset + slot])
    if k == EMPTY:       miss
    slot = (slot + 1) & (slots - 1)
miss                                                              # after max_probe slots
```

### The lookup (section 2.4), per position i with symbol x and history H

```
m   = min(i, n - 1)                  # history symbols available (no start symbol)
acc = 0.0                            # float64
for k = m + 1 down to D + 1:         # the sparse levels, longest context first
    hk = H mod B**(k-1)
    if k - 1 > D:                    # the history itself lives on a sparse level
        (hit_h, bow) = probe(level k-1, hk)
        if not hit_h: continue       # unseen history: gamma = 1, nothing to add
    else:
        bow = dense_bow[hk]          # 0.0 when the D-gram history is unseen at level D+1
    (hit_g, lp) = probe(level k, hk*B + x)
    if hit_g: return acc + float64(lp)
    acc += float64(bow)
kd = min(m + 1, D)
return acc + float64(dense_lp[dense_off[kd-1] + (H mod B**(kd-1))*B + x])
```

then `H = (H*B + x) mod B**(n-1)`. For i < n-1 the levels above m+1 are never visited (a
prefix history uses the lower-order distribution). A dense preset (D == n, B == 29:
`kn4-lp-heldout`, `kn4-cicada`, `kn5-cicada`) has no sparse level and the loop body never
runs; its `dense_lp` reshaped to `(B**i, B)` per level is exactly the `tables` the beam
kernel already gathers from (`docs/kn-scorer-design.md` section 5).

Word-boundary model (`kn8-cicada-wb`, B = 30): the symbol 29 is inserted before every rune
at which the cipher window's word-start mask is True (and at the end when `end_boundary`),
the extended sequence is scored by the same loop, and the window divides by L = the cipher
runes, not the extended length. The mask is window data (`runeforge/scoring/boundaries.py`),
never derived from a decode.

### Float semantics

* Table entries are float32 (`dense_lp`, `dense_bow`, `hash_lp`, `hash_bow`). Each is
  widened to float64 at the moment it is used; nothing is ever added in float32.
* The accumulator is float64, starts at 0.0, and the additions happen in exactly the order
  above: the back-off weights of the levels visited, longest context first, each added as
  soon as its gram probe misses, then the hit's `lp` (or the dense entry) added last, as
  `acc + lp`. No reassociation, no fused multiply-add, no `-ffast-math`: the per-position
  values must equal `KNScorer.reference_logprobs` bit for bit, which is what
  `scripts/export_kn.py` proves for the CPU implementation.
* Window score = sum of the per-position values / L, L = cipher runes, float64. The CPU
  reference sums with `np.sum(axis=1, dtype=float64)` (numpy's pairwise order), so a kernel's
  sequential float64 sum agrees with `score_batch` to float64 rounding (about 1e-13 per
  rune), not necessarily bit for bit; the parity tolerance for the window score is the beam
  kernel's (1e-6 on `tests/test_gpu_beam.py`, 1e-9 on the numpy replay test), while the
  per-position values carry no tolerance.
* Scores are mean log2-probability per cipher rune, negative, higher = more language-like:
  the units of `runeforge/scoring/ngram.py` and of every installed calibration.

### The two exported presets (2026-10-27, `scripts/export_kn.py`, L = 240 windows)

| preset | file | dense_lp | dense_bow | sparse levels: M (slots, bits, max_probe) | parity |
|---|---|---|---|---|---|
| `kn4-cicada` | 2,942,204 B | 732,540 (2.9 MB) | none (D = n) | none | 1,102 windows, bit for bit |
| `kn8-cicada` | 46,211,166 B | 732,540 (2.9 MB) | 707,281 (2.8 MB) | 5: 97,352 (2**18, 18, 13) · 6: 158,160 (2**19, 19, 14) · 7: 203,565 (2**19, 19, 19) · 8: 232,979 (2**19, 19, 22) | 1,106 windows, bit for bit |

On the device `kn8-cicada` needs the hash arrays (1,835,008 slots: 14.7 MB keys + 7.3 MB lp
+ 7.3 MB bow) plus `dense_lp` and `dense_bow` (5.8 MB): about 35 MB, the `sorted_*` arrays
staying on the host. The fingerprints are in the manifests (`reports/kn-export/*.json`); a
kernel's parity record must name the fingerprint it was proved against, as the beam record
names `kernel_sha256`.
