"""CPU reference keystream generators (spec section 4.2).

Every GPU kernel is later checked against these streams, so each one is pinned here to a
reference it does not share code with: ``hashlib`` for ``sha256-ctr``; Dukotah's round19/G3
``gen_py27.py`` (pure Python, itself matched to real CPython 2.7.3 and 2.7.18) and the real
2.7.3 vectors in its ``validation.json`` for ``mt19937-py27``; numpy itself for
``numpy-pcg64``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import time

import numpy as np
import pytest

from runeforge import generators
from runeforge.generators import base, mt19937_py27
from runeforge.sources import DUKOTAH_DIR, raw_path

G3 = f"{DUKOTAH_DIR}/liber-primus/analysis/round19/G3"
MODES = ("random29", "grb5_mod", "grb5_rej", "shuffle29")

ALL = [
    generators.get("sha256-ctr"),
    generators.get("sha256-ctr", domain="runeforge/control-ceiling/TEST"),
    *(generators.get("mt19937-py27", mode=m) for m in MODES),
    *(generators.get("mt19937-py27", mode=m, seed_bits=64) for m in MODES),
    generators.get("numpy-pcg64"),
]
IDS = ["-".join(str(v) for v in g.spec().values()) for g in ALL]


# ----------------------------------------------------------------- shared contract


def test_names_lists_all_three():
    assert generators.names() == ["sha256-ctr", "mt19937-py27", "numpy-pcg64"]


@pytest.mark.parametrize("g", ALL, ids=IDS)
def test_spec_round_trip(g):
    spec = json.loads(json.dumps(g.spec()))
    assert spec["name"] == g.name
    h = generators.get(**spec)
    assert h == g and hash(h) == hash(g)
    assert np.array_equal(h.keystream(3301, 100), g.keystream(3301, 100))


@pytest.mark.parametrize("g", ALL, ids=IDS)
def test_values_dtype_determinism(g):
    k = g.keystream(3301, 1000)
    assert k.dtype == np.int64 and k.shape == (1000,)
    assert k.min() >= 0 and k.max() <= 28
    assert len(np.unique(k)) == 29
    assert np.array_equal(k, generators.get(**g.spec()).keystream(3301, 1000))


@pytest.mark.parametrize("g", ALL, ids=IDS)
def test_prefix_property(g):
    for seed in (0, 3301):
        long = g.keystream(seed, 1500)
        for n in (1, 7, 28, 29, 30, 240, 777):
            assert np.array_equal(g.keystream(seed, n), long[:n]), (seed, n)


@pytest.mark.parametrize("g", ALL, ids=IDS)
def test_distinct_seeds_distinct_streams(g):
    k = generators.keystream_batch(g, range(200), 64)
    assert np.unique(k, axis=0).shape[0] == 200


@pytest.mark.parametrize("g", ALL, ids=IDS)
def test_batch_equals_single(g):
    top = (1 << g.seed_bits) - 1
    seeds = [0, 1, 2, 29, 3301, top - 1, top, *range(5000, 5000 + base.CHUNK + 3)]
    k = generators.keystream_batch(g, np.array(seeds, dtype=np.uint64), 300)
    assert k.shape == (len(seeds), 300) and k.dtype == np.int64
    for i in (0, 1, 2, 3, 4, 5, 6, base.CHUNK + 6, len(seeds) - 1):
        assert np.array_equal(k[i], g.keystream(seeds[i], 300)), seeds[i]
    assert generators.keystream_batch(g, [], 10).shape == (0, 10)
    assert generators.keystream_batch(g, [1, 2], 0).shape == (2, 0)


@pytest.mark.parametrize("g", ALL, ids=IDS)
def test_seed_range_is_enforced(g):
    with pytest.raises(ValueError):
        g.keystream(-1, 5)
    with pytest.raises(ValueError):
        g.keystream(1 << g.seed_bits, 5)
    with pytest.raises(TypeError):
        g.keystream(True, 5)
    with pytest.raises(TypeError):
        g.keystream(1.0, 5)
    with pytest.raises(ValueError):
        g.keystream(1, -1)


def test_get_rejects_bad_names_and_params():
    with pytest.raises(ValueError):
        generators.get("mt19937")
    with pytest.raises(ValueError):
        generators.get("sha256-ctr", key="x")
    with pytest.raises(ValueError):
        generators.get("sha256-ctr", domain=b"bytes")
    with pytest.raises(ValueError):
        generators.get("mt19937-py27", mode="randrange")
    with pytest.raises(ValueError):
        generators.get("mt19937-py27", seed_bits=48)
    assert generators.get("mt19937-py27").spec() == {
        "name": "mt19937-py27",
        "mode": "random29",
        "seed_bits": 32,
    }


def test_rejection_redraw_path_matches():
    """``take_accepted`` with a deliberately tiny first draw takes the redraw branch."""
    seeds = list(range(40))
    sha = generators.get("sha256-ctr")
    assert np.array_equal(base.take_accepted(seeds, 300, sha._draw, 1), sha.batch(seeds, 300))
    rej = generators.get("mt19937-py27", mode="grb5_rej")
    assert np.array_equal(
        base.take_accepted(seeds, 300, mt19937_py27._grb5, 1), rej.batch(seeds, 300)
    )


# ---------------------------------------------------------------------- sha256-ctr

# The definition, written out independently of runeforge/generators/sha256_ctr.py.
SHA_3301_FIRST64 = [
    11, 28, 1, 5, 8, 10, 3, 6, 12, 10, 3, 8, 20, 21, 2, 24, 11, 23, 10, 5, 4, 17,
    25, 23, 2, 15, 16, 2, 16, 0, 16, 28, 6, 11, 28, 11, 22, 28, 20, 8, 22, 28, 17,
    27, 8, 1, 24, 8, 24, 20, 4, 12, 21, 13, 5, 1, 16, 14, 14, 5, 6, 4, 15, 16,
]  # fmt: skip


def sha_reference(seed: int, n: int, domain: str = "runeforge/null/v1") -> list[int]:
    out: list[int] = []
    j = 0
    while len(out) < n:
        block = hashlib.sha256(
            domain.encode("utf-8") + seed.to_bytes(8, "big") + j.to_bytes(8, "big")
        ).digest()
        out.extend(b % 29 for b in block if b < 232)
        j += 1
    return out[:n]


def test_sha256_explicit_vector():
    g = generators.get("sha256-ctr")
    assert sha_reference(3301, 64) == SHA_3301_FIRST64
    assert g.keystream(3301, 64).tolist() == SHA_3301_FIRST64
    for seed, n in ((0, 1), (1, 33), (2**64 - 1, 1000), (123456789, 2900)):
        assert g.keystream(seed, n).tolist() == sha_reference(seed, n), seed
    other = generators.get("sha256-ctr", domain="runeforge/control-ceiling/X")
    assert other.keystream(7, 500).tolist() == sha_reference(7, 500, "runeforge/control-ceiling/X")


def test_sha256_domain_separation():
    a = generators.get("sha256-ctr").keystream(3301, 2000)
    b = generators.get("sha256-ctr", domain="runeforge/null/v2").keystream(3301, 2000)
    assert not np.array_equal(a, b)
    assert (a == b).mean() < 0.06  # chance agreement is 1/29 = 0.034


def chi_square(k: np.ndarray) -> float:
    counts = np.bincount(k, minlength=29)
    e = k.size / 29
    return float(((counts - e) ** 2 / e).sum())


def test_sha256_unbiased():
    """10^5 symbols sit inside the chi-square(28) bulk (P(X > 70) = 1.9e-5); the same bytes
    folded without rejection (0..23 over-weighted 9/8) score far above it, so the check
    has the power to see the bias the rejection removes."""
    g = generators.get("sha256-ctr")
    k = generators.keystream_batch(g, range(100), 1000).ravel()
    assert k.size == 10**5
    assert chi_square(k) < 70.0
    raw = np.frombuffer(
        b"".join(hashlib.sha256(b"fold" + j.to_bytes(8, "big")).digest() for j in range(3125)),
        dtype=np.uint8,
    )
    assert chi_square(raw.astype(np.int64) % 29) > 100


# -------------------------------------------------------------------- mt19937-py27


@pytest.fixture(scope="module")
def gen_py27():
    path = raw_path(f"{G3}/gen_py27.py")
    spec = importlib.util.spec_from_file_location("dukotah_gen_py27", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert list(mod.REDUCER_NAMES) == list(MODES)  # every mode gen_py27 defines
    return mod


SEEDS32 = [0, 1, 2, 29, 3301, 1387498126, 2**31 - 1, 2**31, 2**32 - 2, 2**32 - 1] + [
    int(s) for s in np.random.default_rng(3301).integers(0, 2**32, 190, dtype=np.uint64)
]
SEEDS64 = [2**32, 2**32 + 1, 2**40 + 7, 2**63, 2**64 - 1, 8810433306790406628] + [
    int(s) for s in np.random.default_rng(29).integers(0, 2**64, 54, dtype=np.uint64)
]


@pytest.mark.raw
@pytest.mark.parametrize("mode", MODES)
def test_mt_matches_gen_py27(gen_py27, mode):
    """260 seeds x n = 240, plus 12 seeds at n = 1500 (several MT twists per stream)."""
    for bits, seeds in ((32, SEEDS32), (64, SEEDS64)):
        g = generators.get("mt19937-py27", mode=mode, seed_bits=bits)
        got = generators.keystream_batch(g, seeds, 240)
        for s, row in zip(seeds, got, strict=True):
            assert row.tolist() == gen_py27.keystream(s, mode, 240), (bits, s)
        for s in seeds[:6]:
            assert g.keystream(s, 1500).tolist() == gen_py27.keystream(s, mode, 1500), (bits, s)


@pytest.mark.raw
def test_mt_matches_real_cpython27_vectors():
    """validation.json pins 16-symbol streams measured on real CPython 2.7.3 for string
    seeds. ``random.seed(<str>)`` in 2.7 is ``init_by_array`` over the 32-bit words of the
    unsigned ``hash()``, so each one is also a 64-bit int-seed vector."""
    val = json.loads(raw_path(f"{G3}/validation.json").read_text())
    assert val["verdict"]["all_blocking_gates_pass"] is True
    v4 = val["gates"]["V4_int_float_jumpahead"]["items"]
    assert all(it["streams_ok"] for it in v4.values() if it["kind"] == "int")

    r29 = generators.get("mt19937-py27", mode="random29", seed_bits=64)
    rej = generators.get("mt19937-py27", mode="grb5_rej", seed_bits=64)
    pinned = val["vectors"]["pinned"]
    assert len(pinned) == 7
    for literal, v in pinned.items():
        seed = v["py2_hash_64"] % 2**64
        assert [seed & 0xFFFFFFFF, seed >> 32] == v["seed_key_words_64"], literal
        assert r29.keystream(seed, 16).tolist() == v["py27_random29_first16"], literal
        assert rej.keystream(seed, 16).tolist() == v["py27_grb5_rej_first16"], literal
        assert r29.keystream(seed, 16).tolist() != v["py3_random29_first16"], literal

    cicada = pinned["CICADA3301"]
    built_in = {(s, m): list(w) for s, m, w in mt19937_py27._PINNED}
    assert built_in[(cicada["py2_hash_64"], "random29")] == cicada["py27_random29_first16"]
    assert built_in[(cicada["py2_hash_64"], "grb5_rej")] == cicada["py27_grb5_rej_first16"]


def test_mt_interpreter_guard(monkeypatch):
    mt19937_py27._check_interpreter.cache_clear()
    mt19937_py27._check_interpreter()  # this interpreter reproduces 2.7
    monkeypatch.setattr(
        mt19937_py27, "_words", lambda seeds, m: np.zeros((len(seeds), m), dtype=np.uint32)
    )
    mt19937_py27._check_interpreter.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="no longer reproduces"):
            generators.get("mt19937-py27").keystream(1, 5)
    finally:
        monkeypatch.undo()
        mt19937_py27._check_interpreter.cache_clear()


def test_mt_speed(capsys):
    """Recorded, with a floor ~30x under what a laptop core does, so it never flakes."""
    g = generators.get("mt19937-py27", mode="random29")
    generators.keystream_batch(g, range(100), 240)
    t = time.perf_counter()
    generators.keystream_batch(g, range(10_000), 240)
    rate = 10_000 / (time.perf_counter() - t)
    with capsys.disabled():
        print(f"\nmt19937-py27 random29: {rate:,.0f} seeds/s at n=240 (keystream_batch)")
    assert rate > 1_000


# --------------------------------------------------------------------- numpy-pcg64


def test_pcg64_is_numpy_default_rng():
    g = generators.get("numpy-pcg64")
    for seed in (0, 3301, 2**64 - 1):
        want = np.random.default_rng(seed).integers(0, 29, 500)
        assert np.array_equal(g.keystream(seed, 500), want)
