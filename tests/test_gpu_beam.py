"""The GPU beam kernel (runeforge.gpu.beam_kernel) is a faster copy of runeforge.beam.

.claude/rules/gpu.md: parity before any benchmark counts. These tests need numba (the
``gpu`` extra; CI installs it) but no GPU:

* the CPU njit twin of the kernel's one decode function matches ``beam.decode_batch`` + the
  scorer on >= 10^4 keys per decoder (scores |d| <= 1e-6, objectives too, NaN rows and the
  survivor set identical), with long key runs that force the skip paths;
* the CUDA kernel itself, on numba's simulator (a subprocess with NUMBA_ENABLE_CUDASIM=1);
* ``python -m runeforge.gpu.parity`` on the lane's own keystreams, and its refusals;
* on a machine with a real CUDA device, the kernel on >= 10^4 keys (skipped without one).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

numba = pytest.importorskip("numba")

from runeforge.gpu import beam_kernel as bk  # noqa: E402
from runeforge.gpu import parity  # noqa: E402
from runeforge.scoring import presets  # noqa: E402

DECODERS = ("beam", "beam-skip", "beam-skip-int")
VIEWS = [
    ("raw", "vigenere"),
    ("first-difference", "beaufort"),
    ("chain-increment", "variant-beaufort"),
    ("atbash", "vigenere"),
]
TEMPLATE = "lanes/_template.yaml"


@pytest.fixture(scope="module")
def scorer():
    return presets.get("lp-ngram3-heldout")


def _keys(rng, b: int, length: int, extra: int = 0) -> np.ndarray:
    """Uniform keys with long constant runs in a fifth of the rows (the skip paths need
    k[j] == k[j+1] == ... to be legal), some rows longer than L (the wrap-round fill)."""
    k = rng.integers(0, 29, (b, length + extra))
    for r in range(0, b, 5):
        a = int(rng.integers(0, length - 12))
        k[r, a : a + int(rng.integers(3, 12))] = int(rng.integers(0, 29))
    return k


def _assert_parity(ref, ker, bar=None):
    (rs, ro), (ks, ko) = ref, ker
    assert np.array_equal(np.isnan(rs), np.isnan(ks))
    ok = ~np.isnan(rs)
    assert np.abs(rs[ok] - ks[ok]).max() <= 1e-6
    assert np.abs(ro[ok] - ko[ok]).max() <= 1e-6
    bar = np.nanquantile(rs, 0.99) if bar is None else bar
    assert np.array_equal(np.flatnonzero(rs > bar), np.flatnonzero(ks > bar))


@pytest.mark.parametrize("decoder", DECODERS)
@pytest.mark.parametrize("view,combine", VIEWS)
def test_twin_matches_the_reference_in_every_view(scorer, decoder, view, combine):
    rng = np.random.default_rng(29)
    model = presets.beam_model(decoder, combine, view)
    c = rng.integers(0, 29, 96)
    c[10:30:3] = 0  # canonical F's for the interrupt decoders (in the raw view)
    k = _keys(rng, 200, 96, extra=8)
    _assert_parity(bk.score_reference(c, k, scorer, model), bk.score_cpu(c, k, scorer, model))


def test_twin_decodes_a_planted_key_like_the_reference(scorer):
    """A synthetic Welcome page (held-out text, DIVINITY, every plaintext F an interrupter,
    as in test_beam.py): the high score must match too, not only noise."""
    from runeforge import canon, interrupts
    from runeforge.transforms import Vigenere

    divinity = [23, 10, 1, 10, 9, 10, 16, 26]
    text = canon.solved_section("a-koan-1").plain[:240]
    chosen = np.flatnonzero(text == interrupts.F).tolist()
    cipher = interrupts.encrypt_with_interrupts(text, Vigenere(divinity), chosen)
    rng = np.random.default_rng(3)
    keys = np.vstack([np.resize(divinity, 240), rng.integers(0, 29, (63, 240))])
    model = presets.beam_model("beam")
    ref = bk.score_reference(cipher, keys, scorer, model)
    ker = bk.score_cpu(cipher, keys, scorer, model)
    _assert_parity(ref, ker, bar=-6.0)
    assert int(np.argmax(ker[0])) == 0 and ker[0][0] > -4.5


@pytest.mark.slow
@pytest.mark.parametrize("decoder", DECODERS)
def test_twin_parity_on_ten_thousand_keys(scorer, decoder):
    rng = np.random.default_rng(3301)
    model = presets.beam_model(decoder)
    c = rng.integers(0, 29, 120)
    k = _keys(rng, 10_000, 120)
    _assert_parity(bk.score_reference(c, k, scorer, model), bk.score_cpu(c, k, scorer, model))


def test_kernel_limits_are_refused(scorer):
    from runeforge.beam import BeamModel

    c = np.zeros(10, dtype=np.int64)
    with pytest.raises(ValueError, match="width"):
        bk.score_cpu(c, np.zeros((1, 10)), scorer, BeamModel(width=bk.W_MAX + 1))
    with pytest.raises(ValueError, match="max_skip"):
        bk.score_cpu(c, np.zeros((1, 10)), scorer, BeamModel(p_keep=0.2, max_skip=bk.S_MAX + 1))
    with pytest.raises(ValueError, match="key symbols"):
        bk.score_cpu(c, np.zeros((1, 9)), scorer, presets.beam_model("beam"))
    with pytest.raises(ValueError, match="empty"):
        bk.score_cpu(c[:0], np.zeros((1, 9)), scorer, presets.beam_model("beam"))


def _sim_env() -> dict:
    return {**os.environ, "NUMBA_ENABLE_CUDASIM": "1"}


SIM_SCRIPT = """
import numpy as np
from runeforge.gpu import beam_kernel as bk
from runeforge.scoring import presets
assert bk.simulated() and bk.available()
sc = presets.get("lp-ngram3-heldout")
rng = np.random.default_rng(7)
worst = 0.0
for dec, view, comb in [("beam", "raw", "vigenere"), ("beam-skip", "first-difference",
                         "beaufort"), ("beam-skip-int", "raw", "variant-beaufort")]:
    m = presets.beam_model(dec, comb, view)
    c = rng.integers(0, 29, 60)
    k = rng.integers(0, 29, (70, 64))
    k[::5, 5:15] = 4
    rs, ro = bk.score_reference(c, k, sc, m)
    gs, go = bk.score_gpu(c, k, sc, m, threads=32)  # 3 blocks, the last one partial
    assert np.array_equal(np.isnan(rs), np.isnan(gs))
    worst = max(worst, float(np.nanmax(np.abs(rs - gs))), float(np.nanmax(np.abs(ro - go))))
print(worst)
"""


def test_the_cuda_kernel_on_the_simulator():
    r = subprocess.run(
        [sys.executable, "-c", SIM_SCRIPT], env=_sim_env(), capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr[-2000:]
    assert float(r.stdout.strip()) <= 1e-6


def test_parity_command_on_the_lanes_own_keystreams(tmp_path):
    rc = parity.main([TEMPLATE, "--backend", "cpu-twin", "--seeds", "200", "--out", str(tmp_path)])
    assert rc == 0
    rec = json.loads((tmp_path / "parity.json").read_text())
    assert rec["status"] == "passed" and rec["backend"] == "cpu-twin"
    assert rec["simulated"] is False and rec["numbering"] == "LP2-0-57"
    assert rec["beam_sha256"] == parity.code_pins()["beam_sha256"]
    assert "10^4" in rec["note"]  # 200 seeds are not the rules' parity test
    assert rec["keygen"]["passed"] and rec["keygen"]["seeds"] == 200  # mt19937-py27 has a kernel
    planted = {c["cipher"]: c for c in rec["cases"]}["planted"]
    assert planted["best_seed"] == rec["planted_seed"] == 3301  # the planted key decodes
    seeds = parity.parity_seeds(parity.load_lane(TEMPLATE), 200)
    assert {0, 1, 2**32 - 1, 2**32 - 2, 3301} <= set(seeds) and len(set(seeds)) == 200


def test_no_benchmark_without_a_real_device(tmp_path):
    args = [TEMPLATE, "--backend", "cpu-twin", "--seeds", "50", "--bench", "100"]
    assert parity.main([*args, "--out", str(tmp_path)]) == 2
    assert not (tmp_path / "bench.json").exists()


def test_no_benchmark_on_the_simulator(tmp_path):
    cmd = [sys.executable, "-m", "runeforge.gpu.parity", TEMPLATE, "--seeds", "20"]
    r = subprocess.run(
        [*cmd, "--bench", "100", "--out", str(tmp_path)],
        env=_sim_env(),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2, r.stderr[-2000:]
    rec = json.loads((tmp_path / "parity.json").read_text())
    assert rec["simulated"] is True and rec["status"] == "passed"
    assert not (tmp_path / "bench.json").exists()


def test_a_rigid_lane_has_no_beam_kernel(tmp_path):
    import yaml

    spec = yaml.safe_load(Path(TEMPLATE).read_text())
    spec["preset"] = "lp-ngram3-heldout:rigid"
    spec["filter_model"] = "off"
    p = tmp_path / "rigid.yaml"
    p.write_text(yaml.safe_dump(spec))
    with pytest.raises(ValueError, match="rigid"):
        parity.main([str(p), "--backend", "cpu-twin", "--seeds", "10", "--out", str(tmp_path)])


def _real_device() -> bool:
    if bk.simulated():
        return False
    try:
        return bool(numba.cuda.is_available())
    except Exception:
        return False


@pytest.mark.slow
@pytest.mark.skipif(not _real_device(), reason="no CUDA device")
@pytest.mark.parametrize("decoder", DECODERS)
def test_the_cuda_kernel_on_the_device(scorer, decoder):
    rng = np.random.default_rng(1033)
    model = presets.beam_model(decoder)
    c = rng.integers(0, 29, 240)
    k = _keys(rng, 10_000, 240)
    _assert_parity(bk.score_reference(c, k, scorer, model), bk.score_gpu(c, k, scorer, model))


# ----------------------------------------------------------------------------- the sweep


def _sweep(tmp_path, backend: str):
    from pathlib import Path

    from runeforge.runner import sweep

    lane = parity.load_lane(TEMPLATE)
    return lane, sweep._Sweep(
        lane,
        Path(TEMPLATE),
        tmp_path,
        resume=True,
        smoke=True,
        ledger_path=None,
        max_seeds=None,
        lanes_dir=None,
        override_q5=None,
        stop={"flag": False, "why": ""},
        backend=backend,
    )


def test_the_sweeps_gpu_decode_matches_its_cpu_decode(tmp_path, monkeypatch, scorer):
    """The sweep's GPU path (the generator kernel's keys, the beam kernel's scores, CPU
    re-generation and re-decode of the rows it reports) against its CPU path, with the njit
    twins standing in for the device."""
    from runeforge.gpu import mt_kernel as mk
    from runeforge.runner import pipeline

    monkeypatch.setattr(bk, "score_gpu", bk.score_cpu)
    monkeypatch.setattr(mk, "keys_device", mk.keys_cpu)
    lane, gpu = _sweep(tmp_path, "gpu")
    _, cpu = _sweep(tmp_path, "cpu")
    assert gpu.keys_backend() == "gpu" and cpu.keys_backend() == "cpu"
    cipher = pipeline.lane_cipher(lane)[: lane.window]
    seeds = list(range(3290, 3390))
    g_scores, g_plain = gpu.decode(cipher, seeds, scorer)
    c_scores, c_plain = cpu.decode(cipher, seeds, scorer)
    assert np.abs(g_scores - c_scores).max() <= 1e-6
    for i in (0, int(np.argmax(c_scores)), 99):
        assert np.array_equal(g_plain(i), c_plain(i))


def test_the_sweep_stops_when_the_kernel_disagrees_with_the_cpu(tmp_path, monkeypatch, scorer):
    from runeforge.gpu import mt_kernel as mk
    from runeforge.runner import pipeline

    def off_by_a_little(*a, **kw):
        s, o = bk.score_cpu(*a, **kw)
        return s + 1e-4, o

    def wrong_keys(gen, seeds, n, offset=0, threads=128):
        k = mk.keys_cpu(gen, seeds, n, offset)
        k[:, 100] = (k[:, 100] + 1) % 29  # one symbol off in every row
        return k

    monkeypatch.setattr(bk, "score_gpu", off_by_a_little)
    monkeypatch.setattr(mk, "keys_device", mk.keys_cpu)
    lane, gpu = _sweep(tmp_path, "gpu")
    cipher = pipeline.lane_cipher(lane)[: lane.window]
    _scores, plain_of = gpu.decode(cipher, [1, 2, 3], scorer)
    with pytest.raises(RuntimeError, match="disagree"):
        plain_of(0)
    monkeypatch.setattr(bk, "score_gpu", bk.score_cpu)
    monkeypatch.setattr(mk, "keys_device", wrong_keys)  # a keystream kernel gone wrong
    _scores, plain_of = gpu.decode(cipher, [1, 2, 3], scorer)
    with pytest.raises(RuntimeError, match="disagree"):
        plain_of(1)
    monkeypatch.setattr(bk, "score_gpu", lambda *a, **kw: (np.full(3, np.nan), np.zeros(3)))
    with pytest.raises(RuntimeError, match="NaN"):
        gpu.decode(cipher, [1, 2, 3], scorer)


SWEEP_SIM_SCRIPT = """
import sys
from pathlib import Path
from pathlib import Path
import numpy as np
from runeforge.lanes import load_lane
from runeforge.runner import pipeline, sweep
from runeforge.scoring import presets
lane = load_lane("lanes/_template.yaml")
kw = dict(resume=True, smoke=True, ledger_path=None, max_seeds=None, lanes_dir=None,
          override_q5=None, stop={"flag": False, "why": ""})
gpu = sweep._Sweep(lane, Path("x.yaml"), Path(sys.argv[1]), backend="gpu", **kw)
cpu = sweep._Sweep(lane, Path("x.yaml"), Path(sys.argv[1]), **kw)
sc = presets.get("lp-ngram3-heldout")
c = pipeline.lane_cipher(lane)[: lane.window]
assert gpu.keys_backend() == "gpu"  # mt19937-py27 keys are generated on the (simulated) device
seeds = list(range(3295, 3335))
gs, gp = gpu.decode(c, seeds, sc)
cs, cp = cpu.decode(c, seeds, sc)
assert np.array_equal(gp(5), cp(5))
print(float(np.abs(gs - cs).max()))
"""


def test_the_sweeps_gpu_decode_on_the_simulator(tmp_path):
    r = subprocess.run(
        [sys.executable, "-c", SWEEP_SIM_SCRIPT, str(tmp_path)],
        env=_sim_env(),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    assert float(r.stdout.strip()) <= 1e-6


def _record(tmp_path, monkeypatch, **over):
    """A parity record as the current code and a pretend device would write it."""
    from runeforge.runner import pipeline
    from runeforge.runner.control import lane_pipeline_sha256

    monkeypatch.setattr(bk, "available", lambda: True)
    monkeypatch.setattr(bk, "simulated", lambda: False)
    monkeypatch.setattr(parity, "current_device_name", lambda: "NVIDIA GeForce RTX TEST")
    lane = parity.load_lane(TEMPLATE)
    rec = {
        "status": "passed",
        "backend": "gpu",
        "simulated": False,
        "lane_pipeline_sha256": lane_pipeline_sha256(lane),
        "preset": lane.preset,
        "window": lane.window,
        **parity.code_pins(),
        "device_name": "NVIDIA GeForce RTX TEST",
        "seeds": 10_000,
        "keygen": {"generator": pipeline.generator(lane).spec(), "passed": True},
        **over,
    }
    path = tmp_path / "parity.json"
    path.write_text(json.dumps(rec))
    return lane, path


def test_a_current_real_device_parity_record_lets_the_gpu_backend_run(tmp_path, monkeypatch):
    lane, path = _record(tmp_path, monkeypatch)
    assert parity.record_problems(lane, path) == []


@pytest.mark.parametrize(
    "over,why",
    [
        ({"status": "failed"}, "status"),
        ({"simulated": True}, "simulated"),
        ({"backend": "cpu-twin"}, "backend"),
        ({"seeds": 200}, "10^4"),
        ({"beam_sha256": "0" * 64}, "beam_sha256"),
        ({"kernel_sha256": "0" * 64}, "kernel_sha256"),
        ({"lane_pipeline_sha256": "0" * 64}, "lane_pipeline_sha256"),
        ({"device_name": "another GPU"}, "device_name"),
        ({"mt_kernel_sha256": "0" * 64}, "mt_kernel_sha256"),
        ({"generator_sha256": "0" * 64}, "generator_sha256"),
        ({"keygen": None}, "keygen"),
        ({"keygen": {"generator": {"name": "x"}, "passed": True}}, "generator spec"),
    ],
)
def test_a_stale_or_foreign_parity_record_is_refused(tmp_path, monkeypatch, over, why):
    lane, path = _record(tmp_path, monkeypatch, **over)
    problems = parity.record_problems(lane, path)
    assert any(why in p for p in problems), problems


def test_the_gpu_backend_refusals(tmp_path, monkeypatch):
    lane, path = _record(tmp_path, monkeypatch)
    path.unlink()
    assert any("no readable parity record" in p for p in parity.record_problems(lane, path))
    assert parity.record_problems(lane, path, smoke=True) == []  # smoke: a device is enough
    monkeypatch.setattr(bk, "simulated", lambda: True)
    assert any("simulator" in p for p in parity.record_problems(lane, path))
    monkeypatch.setattr(bk, "available", lambda: False)
    assert any("no CUDA device" in p for p in parity.record_problems(lane, path, smoke=True))
    rigid = lane.model_copy(update={"preset": "lp-ngram3-heldout:rigid"})
    assert any("rigid" in p for p in parity.record_problems(rigid, path, smoke=True))


def test_the_sweep_preflight_applies_the_gpu_checks(tmp_path, monkeypatch):
    from runeforge.runner import sweep

    monkeypatch.setattr(bk, "available", lambda: False)
    lane = parity.load_lane(TEMPLATE)
    probs = sweep.preflight(lane, None, True, tmp_path, backend="gpu")
    assert any("no CUDA device" in p for p in probs)
    assert not any("CUDA" in p for p in sweep.preflight(lane, None, True, tmp_path))
