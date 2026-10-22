# CUDA kernels (Phase 3)

Built: the beam decoder, `runeforge/gpu/beam_kernel.py` (numba.cuda; one thread decodes one
key row and writes its score). One plain-Python function holds the algorithm and is compiled
both as the CUDA device function and as a CPU njit twin; both match `beam.decode_batch` + the
scorer (tests/test_gpu_beam.py). It has no early exit: every key is decoded to the end, so no
seed above the claim bar can be dropped.

Not built: keystream generators on the GPU (`prng_<family>`), which would each need a parity
test against `runeforge/generators` before they count. Until then the sweep generates keys on
the CPU and hands them to the kernel, which caps a lane at the generator's CPU rate.
