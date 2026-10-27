"""Phase 3: the CUDA sweep engine (numba.cuda).

Built:

* ``beam_kernel`` -- the beam decoder (``runeforge.beam.decode_batch`` + the n-gram score) as
  one CUDA thread per key, with a CPU njit twin compiled from the same function;
* ``mt_kernel`` -- the ``mt19937-py27`` keystream (CPython 2.7 ``random.seed(<int>)`` and the
  four 2.7 reducers, ``runeforge.generators.mt19937_py27``) as one thread per seed, writing
  its rows on the device for the beam kernel; the same twin construction;
* ``parity`` -- ``python -m runeforge.gpu.parity <lane.yaml>``, the parity record (>= 10^4 of
  the lane's own seeds against the numpy reference: scores, survivor set, and the keystreams
  symbol for symbol) and the benchmark that ``runeforge sweep --backend gpu`` requires
  (.claude/rules/gpu.md).

Other generators (``sha256-ctr``, ``numpy-pcg64``) have no kernel; a lane on one of them
generates its keys on the CPU and scores them on the device. Install with
``pip install -e '.[gpu]'``.
"""
