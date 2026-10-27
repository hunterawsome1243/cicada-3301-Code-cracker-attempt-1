"""The GPU mt19937-py27 keystream kernel (runeforge.gpu.mt_kernel) is a faster copy of
runeforge.generators.mt19937_py27, the CPU reference that defines the stream.

.claude/rules/gpu.md: keystreams identical symbol for symbol before anything else counts.
These tests need numba but no GPU:

* the CPU njit twin of the kernel's one row function equals ``generators.keystream_batch``
  in all four 2.7 reducers, for 32- and 64-bit seeds (both ends of each range, the pinned
  CPython 2.7.3 vectors' seeds, random seeds), with a key offset, and over streams that cross
  several MT twists; >= 10^4 seeds per mode (slow);
* the CUDA kernel itself on numba's simulator, and its rows fed to the beam kernel on the
  device without a host copy;
* refusals (another generator, a seed outside the range);
* on a machine with a real CUDA device, the kernel on >= 10^4 seeds (skipped without one).
"""

from __future__ import annotations

import os
import subprocess
import sys

import numpy as np
import pytest

numba = pytest.importorskip("numba")

from runeforge import generators  # noqa: E402
from runeforge.gpu import mt_kernel as mk  # noqa: E402

MODES = tuple(mk.MODES)
SEEDS32 = [0, 1, 2, 29, 3301, 1387498126, 2**31 - 1, 2**31, 2**32 - 2, 2**32 - 1]
SEEDS64 = [2**32, 2**32 + 1, 2**40 + 7, 2**63, 2**64 - 1, 8810433306790406628]


def _seeds(bits: int, n: int, rng_seed: int = 3301) -> list[int]:
    rng = np.random.default_rng(rng_seed)
    fixed = SEEDS32 if bits == 32 else SEEDS64
    return fixed + [int(s) for s in rng.integers(0, 2**bits, n, dtype=np.uint64)]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bits", (32, 64))
def test_twin_equals_the_reference_across_twists(mode, bits):
    """n = 1500 crosses several twists in every mode (random29 uses 2 words per symbol)."""
    g = generators.get("mt19937-py27", mode=mode, seed_bits=bits)
    seeds = _seeds(bits, 100)
    assert np.array_equal(generators.keystream_batch(g, seeds, 1500), mk.keys_cpu(g, seeds, 1500))


@pytest.mark.parametrize("mode", MODES)
def test_twin_with_a_key_offset(mode):
    g = generators.get("mt19937-py27", mode=mode)
    seeds = _seeds(32, 50)
    ref = generators.keystream_batch(g, seeds, 300)
    assert np.array_equal(ref[:, 37:], mk.keys_cpu(g, seeds, 263, offset=37))
    assert np.array_equal(ref[:, 299:], mk.keys_cpu(g, seeds, 1, offset=299))
    assert mk.keys_cpu(g, seeds, 0).shape == (len(seeds), 0)
    assert mk.keys_cpu(g, [], 10).shape == (0, 10)


def test_twin_over_the_crosser_records_length():
    """13,000 symbols: the full-page decode record's scale, about 40 twists in random29."""
    for mode in MODES:
        g = generators.get("mt19937-py27", mode=mode)
        seeds = SEEDS32[:6]
        assert np.array_equal(
            generators.keystream_batch(g, seeds, 13_000), mk.keys_cpu(g, seeds, 13_000)
        ), mode


@pytest.mark.slow
@pytest.mark.parametrize("mode", MODES)
def test_twin_parity_on_ten_thousand_seeds(mode):
    g = generators.get("mt19937-py27", mode=mode, seed_bits=64)
    seeds = _seeds(32, 5_000) + _seeds(64, 5_000, rng_seed=29)
    assert np.array_equal(generators.keystream_batch(g, seeds, 240), mk.keys_cpu(g, seeds, 240))


def test_refusals():
    g = generators.get("mt19937-py27")
    with pytest.raises(ValueError, match="outside"):
        mk.keys_cpu(g, [2**32], 10)  # a 32-bit generator's seed range, as the reference
    with pytest.raises(ValueError, match="outside"):
        mk.keys_cpu(g, [-1], 10)
    with pytest.raises(ValueError, match="no GPU kernel"):
        mk.keys_cpu(generators.get("numpy-pcg64"), [1], 10)
    with pytest.raises(ValueError, match=">= 0"):
        mk.keys_cpu(g, [1], -1)
    assert mk.supports(g) and not mk.supports(generators.get("sha256-ctr", domain="x"))


SIM_SCRIPT = """
import numpy as np
from runeforge import generators
from runeforge.gpu import beam_kernel as bk, mt_kernel as mk
from runeforge.scoring import presets
assert bk.simulated()
rng = np.random.default_rng(5)
for mode in mk.MODES:
    for bits in (32, 64):
        g = generators.get("mt19937-py27", mode=mode, seed_bits=bits)
        rand = rng.integers(0, 2**bits, 30, dtype=np.uint64)
        seeds = [0, 2**bits - 1, 3301] + [int(s) for s in rand]
        ref = generators.keystream_batch(g, seeds, 70)
        assert np.array_equal(ref, mk.keys_gpu(g, seeds, 70, threads=16)), (mode, bits)
        off = mk.keys_gpu(g, seeds, 61, offset=9, threads=16)
        assert np.array_equal(ref[:, 9:], off), (mode, bits)
# device rows straight into the beam kernel
g = generators.get("mt19937-py27", mode="random29")
sc = presets.get("lp-ngram3-heldout")
m = presets.beam_model("beam-skip")
c = rng.integers(0, 29, 40)
seeds = list(range(3290, 3310))
dk = mk.keys_device(g, seeds, 40)
assert bk.on_device(dk) and not bk.on_device(np.zeros(2))
gs, go = bk.score_gpu(c, dk, sc, m, threads=8)
rs, ro = bk.score_reference(c, generators.keystream_batch(g, seeds, 40), sc, m)
print(max(float(np.abs(gs - rs).max()), float(np.abs(go - ro).max())))
"""


def test_the_cuda_kernel_on_the_simulator_and_its_rows_feed_the_beam_kernel():
    r = subprocess.run(
        [sys.executable, "-c", SIM_SCRIPT],
        env={**os.environ, "NUMBA_ENABLE_CUDASIM": "1"},
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    assert float(r.stdout.strip()) <= 1e-6


def test_device_keys_are_checked_by_the_beam_kernel(monkeypatch):
    """A device array of the wrong width or dtype is refused before the launch."""
    from runeforge.beam import BeamModel
    from runeforge.gpu import beam_kernel as bk
    from runeforge.scoring import presets

    class Dev:
        def __init__(self, shape, dtype):
            self.shape, self.dtype, self.ndim = shape, np.dtype(dtype), len(shape)

        def copy_to_host(self):
            return None

    monkeypatch.setattr(bk, "available", lambda: True)
    sc = presets.get("lp-ngram3-heldout")
    with pytest.raises(ValueError, match="device keys"):
        bk.score_gpu(np.zeros(10, dtype=np.int64), Dev((4, 9), np.int64), sc, BeamModel())
    with pytest.raises(ValueError, match="device keys"):
        bk.score_gpu(np.zeros(10, dtype=np.int64), Dev((4, 10), np.int32), sc, BeamModel())


def _real_device() -> bool:
    from runeforge.gpu import beam_kernel as bk

    if bk.simulated():
        return False
    try:
        return bool(numba.cuda.is_available())
    except Exception:
        return False


@pytest.mark.slow
@pytest.mark.skipif(not _real_device(), reason="no CUDA device")
@pytest.mark.parametrize("mode", MODES)
def test_the_cuda_kernel_on_the_device(mode):
    g = generators.get("mt19937-py27", mode=mode, seed_bits=64)
    seeds = _seeds(32, 5_000) + _seeds(64, 5_000, rng_seed=29)
    assert np.array_equal(generators.keystream_batch(g, seeds, 240), mk.keys_gpu(g, seeds, 240))
    few = seeds[:64]
    assert np.array_equal(generators.keystream_batch(g, few, 13_000), mk.keys_gpu(g, few, 13_000))
