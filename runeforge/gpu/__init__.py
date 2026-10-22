"""Phase 3: the CUDA sweep engine (numba.cuda).

Built: ``beam_kernel`` -- the beam decoder (``runeforge.beam.decode_batch`` + the n-gram score)
as one CUDA thread per key, with a CPU njit twin compiled from the same function, and
``parity`` -- ``python -m runeforge.gpu.parity <lane.yaml>``, the parity record (>= 10^4 of the
lane's own keys against the numpy reference) and the benchmark that ``runeforge sweep
--backend gpu`` requires (.claude/rules/gpu.md). Keystreams still come from the CPU
generators; a GPU generator per family, each with its own parity test, is not built.
Install with ``pip install -e '.[gpu]'``.
"""
