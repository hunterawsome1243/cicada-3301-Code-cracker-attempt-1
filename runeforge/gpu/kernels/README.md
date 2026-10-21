# CUDA kernels (Phase 3)

One thread = one seed: generate keystream, apply the anti-repeat filter model (as its
inverse on decode), subtract mod 29, score against the n-gram table in constant/texture
memory, early-exit below a running threshold, write survivors above the claim bar.
