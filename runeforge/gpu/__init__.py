"""Phase 3: CUDA sweep engine (CuPy RawKernel / Numba).

Planned: ``kernels/decrypt_mod29.cu``, ``kernels/score_ngram.cu`` and one
``kernels/prng_<family>.cu`` per generator, each validated against a CPU reference in
``tests/test_prng.py``; ``sweep.py`` runs a lane with chunking, checkpoint/resume and
the family-wise threshold, piping survivors to the oracle. Install with
``pip install -e '.[gpu]'``.
"""
