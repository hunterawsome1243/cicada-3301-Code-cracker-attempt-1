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
