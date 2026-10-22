"""``python -m runeforge.gpu.parity <lane.yaml>``: the beam kernel's parity record and benchmark.

.claude/rules/gpu.md: a kernel without a green parity test does not run a lane and has no
throughput number. This command runs the lane's own keystreams (``pipeline.keys_batch``, the
CPU generator; the kernel never generates keys, so the keystreams are identical by
construction) through the numpy reference (``beam.decode_batch`` + the scorer) and through the
kernel, on two ciphers:

* ``window``: the lane's real window (its pages, view and length), the sweep's own input;
* ``planted``: the control's synthetic page encrypted under the planted seed with the lane's
  forward model (``pipeline.encrypt``), so one key decodes to held-out text and the survivor
  set holds a real high score, not only noise.

Seeds: both ends of the lane's seed range, the control's planted seed, and random seeds (rng
3301) up to ``--seeds``. Pass: every score within 1e-6 of the reference, every objective
within 1e-6, NaN in the same rows, and the same survivor set above the bar (the lane's
``claim_bar``, or the 99th percentile of the reference scores when the lane has none yet,
recorded as such). The kernel has no early exit; every key is decoded to the end.

Writes ``runs/<lane_id>/parity.json`` (``--out`` to change the directory) with the command,
git SHA, the SHA-256 of ``runeforge/beam.py`` and of the kernel, the backend, whether it ran on
the simulator, and the GPU name and driver/CUDA from ``nvidia-smi``. ``--bench N`` then times
the kernel on N keys and writes ``bench.json`` -- only after a passing parity run on a real
device (never on the simulator or the CPU twin, whose numbers say nothing about the GPU).

``--backend cpu-twin`` checks the njit twin instead (no GPU needed); its record says so and
the sweep's GPU backend never accepts it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from runeforge import canon
from runeforge.lanes import LaneSpec, load_lane
from runeforge.ledger import git_sha
from runeforge.runner import pipeline
from runeforge.runner.control import lane_pipeline_sha256, plant_source
from runeforge.scoring import presets

TOL = 1e-6
BATCH = 4096
PARITY_RNG = 3301
NVIDIA_SMI = ("/usr/lib/wsl/lib/nvidia-smi", "nvidia-smi")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_pins() -> dict:
    """What a parity record is bound to: the reference decoder and the kernel source."""
    root = Path(__file__).resolve().parents[1]
    return {
        "beam_sha256": file_sha256(root / "beam.py"),
        "kernel_sha256": file_sha256(root / "gpu" / "beam_kernel.py"),
    }


def nvidia_smi() -> dict:
    """GPU name, driver and CUDA version as nvidia-smi reports them (empty without one)."""
    exe = next((p for p in NVIDIA_SMI if Path(p).exists() or shutil.which(p)), None)
    if exe is None:
        return {}
    out: dict = {"nvidia_smi": exe}
    q = subprocess.run(
        [exe, "--query-gpu=name,driver_version", "--format=csv,noheader"],
        capture_output=True,
        text=True,
    )
    if q.returncode == 0 and q.stdout.strip():
        name, _, driver = q.stdout.strip().splitlines()[0].partition(",")
        out.update(gpu_name=name.strip(), driver_version=driver.strip())
    h = subprocess.run([exe], capture_output=True, text=True)
    for tok in h.stdout.split("|"):
        if "CUDA Version" in tok:
            out["cuda_version"] = tok.split("CUDA Version:")[-1].strip()
    return out


def device_info(backend: str) -> dict:
    from runeforge.gpu import beam_kernel as bk

    info: dict = {"backend": backend, "simulated": backend == "gpu" and bk.simulated()}
    if backend == "gpu" and not info["simulated"]:
        from numba import cuda

        cc = cuda.get_current_device().compute_capability
        info.update(device_name=current_device_name(), compute_capability=list(cc))
        info.update(nvidia_smi())
    return info


def parity_seeds(lane: LaneSpec, n: int) -> list[int]:
    """Both ends of the seed range, the planted seed, then random seeds; ``n`` distinct."""
    lo, hi = lane.seed_range
    ends = min(16, (hi - lo) // 2, n // 4)
    seeds = list(range(lo, lo + ends)) + list(range(hi - ends, hi))
    planted = lane.control.planted_seed
    if isinstance(planted, int) and lo <= planted < hi:
        seeds.append(planted)
    seen = set(seeds)
    rng = np.random.default_rng(PARITY_RNG)
    while len(seeds) < min(n, hi - lo):
        for s in pipeline.draw_seeds(rng, lo, hi, n):
            if s not in seen and len(seeds) < n:
                seen.add(s)
                seeds.append(s)
    return seeds[:n]


def planted_cipher(lane: LaneSpec) -> tuple[np.ndarray, int]:
    """The control's synthetic page under the planted seed (the lane's forward model)."""
    lo, hi = lane.seed_range
    s = lane.control.planted_seed
    if not (isinstance(s, int) and lo <= s < hi):
        s = lo
    plain = plant_source(lane.control.synthetic_page)[: lane.window]
    k = pipeline.keys(lane, s, 3 * lane.window)
    cipher, _ = pipeline.encrypt(lane, plain, k, np.random.default_rng(PARITY_RNG))
    return cipher, s


def _kernel_scores(backend: str, cipher, keys, scorer, model):
    from runeforge.gpu import beam_kernel as bk

    fn = bk.score_gpu if backend == "gpu" else bk.score_cpu
    parts = [fn(cipher, keys[i : i + BATCH], scorer, model) for i in range(0, len(keys), BATCH)]
    return np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts])


def compare(lane, name, cipher, seeds, scorer, model, backend) -> dict:
    from runeforge.gpu import beam_kernel as bk

    keys = pipeline.keys_batch(lane, seeds, lane.window)
    ref_s, ref_o = bk.score_reference(cipher, keys, scorer, model)
    ker_s, ker_o = _kernel_scores(backend, cipher, keys, scorer, model)
    nan_same = bool(np.array_equal(np.isnan(ref_s), np.isnan(ker_s)))
    ok = ~np.isnan(ref_s) & ~np.isnan(ker_s)
    d_s = float(np.abs(ref_s[ok] - ker_s[ok]).max()) if ok.any() else 0.0
    d_o = float(np.abs(ref_o[ok] - ker_o[ok]).max()) if ok.any() else 0.0
    if lane.claim_bar is not None:
        bar, bar_source = float(lane.claim_bar), "claim_bar"
    else:
        bar, bar_source = float(np.nanquantile(ref_s, 0.99)), "reference q0.99 (no claim_bar)"
    surv_ref = sorted(int(seeds[i]) for i in np.flatnonzero(ref_s > bar))
    surv_ker = sorted(int(seeds[i]) for i in np.flatnonzero(ker_s > bar))
    i_best = int(np.nanargmax(ref_s))
    return {
        "cipher": name,
        "keys": len(seeds),
        "max_abs_dscore": d_s,
        "max_abs_dobjective": d_o,
        "nan_rows_identical": nan_same,
        "bar": bar,
        "bar_source": bar_source,
        "survivors": len(surv_ref),
        "survivor_set_identical": surv_ref == surv_ker,
        "best_seed": int(seeds[i_best]),
        "best_score": float(ref_s[i_best]),
        "passed": bool(nan_same and d_s <= TOL and d_o <= TOL and surv_ref == surv_ker),
    }


def run_parity(lane: LaneSpec, n_seeds: int, backend: str) -> dict:
    model = pipeline.beam_model(lane)
    if model is None:
        raise ValueError(f"{lane.lane_id}: {lane.preset} is rigid; this kernel is the beam's")
    scorer = presets.get(presets.split_preset(lane.preset)[0])
    window = pipeline.lane_cipher(lane)[: lane.window]
    seeds = parity_seeds(lane, n_seeds)
    pc, p_seed = planted_cipher(lane)
    if p_seed not in seeds:
        seeds = [p_seed, *seeds[:-1]]
    cases = [
        compare(lane, "window", window, seeds, scorer, model, backend),
        compare(lane, "planted", pc, seeds, scorer, model, backend),
    ]
    return {
        "planted_seed": p_seed,
        "seeds": len(seeds),
        "seed_range": list(lane.seed_range),
        "cases": cases,
        "status": "passed" if all(c["passed"] for c in cases) else "failed",
    }


def bench(lane: LaneSpec, n: int) -> dict:
    """Kernel keys/s on n keys (one launch per BATCH), and end to end with key generation."""
    from runeforge.gpu import beam_kernel as bk

    model = pipeline.beam_model(lane)
    scorer = presets.get(presets.split_preset(lane.preset)[0])
    cipher = pipeline.lane_cipher(lane)[: lane.window]
    lo = lane.seed_range[0]
    t0 = time.perf_counter()
    keys = pipeline.keys_batch(lane, range(lo, lo + n), lane.window)
    t_keys = time.perf_counter() - t0
    bk.score_gpu(cipher, keys[:BATCH], scorer, model)  # compile and warm up
    t0 = time.perf_counter()
    for i in range(0, n, BATCH):
        bk.score_gpu(cipher, keys[i : i + BATCH], scorer, model)
    t_kernel = time.perf_counter() - t0
    return {
        "keys": n,
        "launch_batch": BATCH,
        "kernel_keys_per_s": n / t_kernel,
        "keygen_keys_per_s": n / t_keys,
        "end_to_end_keys_per_s": n / (t_kernel + t_keys),
    }


def current_device_name() -> str | None:
    from numba import cuda

    dev = cuda.get_current_device()
    return dev.name.decode() if isinstance(dev.name, bytes) else str(dev.name)


def record_problems(lane: LaneSpec, path: Path, smoke: bool = False) -> list[str]:
    """Why ``runeforge sweep --backend gpu`` may not run this lane now (empty = it may).

    A real sweep needs ``path`` (``runs/<lane_id>/parity.json``): passed, >= 10^4 seeds, on a
    real device (not the simulator, not the CPU twin), on this lane spec, this
    ``runeforge/beam.py`` and this kernel, and on the device present now. A smoke run (test
    harness) needs only a CUDA device or the simulator; its outputs are marked smoke."""
    if pipeline.beam_model(lane) is None:
        return [f"--backend gpu: {lane.preset} is rigid; the GPU kernel is the beam decoder's"]
    try:
        from runeforge.gpu import beam_kernel as bk
    except ImportError as exc:
        return [f"--backend gpu needs numba (pip install -e '.[gpu]'): {exc}"]
    if not bk.available():
        return ["--backend gpu: no CUDA device (nvidia-smi must list the GPU)"]
    if smoke:
        return []
    if bk.simulated():
        return ["--backend gpu: NUMBA_ENABLE_CUDASIM is set; a lane never runs on the simulator"]
    fix = "run `python -m runeforge.gpu.parity <the lane's yaml>` on this machine first"
    try:
        rec = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return [f"--backend gpu: no readable parity record {path}: {fix}"]
    want = {
        "status": "passed",
        "backend": "gpu",
        "simulated": False,
        "lane_pipeline_sha256": lane_pipeline_sha256(lane),
        "preset": lane.preset,
        "window": lane.window,
        **code_pins(),
        "device_name": current_device_name(),
    }
    problems = [
        f"--backend gpu: parity record {k} is {rec.get(k)!r}, needs {v!r}"
        for k, v in want.items()
        if rec.get(k) != v
    ]
    if not isinstance(rec.get("seeds"), int) or rec["seeds"] < 10_000:
        problems.append(f"--backend gpu: the parity record ran {rec.get('seeds')} seeds (< 10^4)")
    return [*problems, fix] if problems else []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m runeforge.gpu.parity", description=__doc__)
    ap.add_argument("lane", help="lane YAML (its preset must be a :beam* decoder)")
    ap.add_argument("--seeds", type=int, default=10_000, help="keys per cipher (>= 10^4 counts)")
    ap.add_argument("--backend", choices=("gpu", "cpu-twin"), default="gpu")
    ap.add_argument("--bench", type=int, default=0, help="time the kernel on this many keys")
    ap.add_argument("--out", help="output directory (default runs/<lane_id>)")
    args = ap.parse_args(argv)
    lane = load_lane(args.lane)
    if args.backend == "gpu":
        from runeforge.gpu import beam_kernel as bk

        if not bk.available():
            print("no CUDA device (NUMBA_ENABLE_CUDASIM=1 runs the simulator)", file=sys.stderr)
            return 2
    if args.out:
        out_dir = Path(args.out)
    else:
        from runeforge.runner.sweep import run_dir

        out_dir = run_dir(lane)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = shlex.join(["python", "-m", "runeforge.gpu.parity", *(argv or sys.argv[1:])])
    head = {
        "lane_id": lane.lane_id,
        "numbering": canon.LP2_NUMBERING,
        "command": cmd,
        "git_sha": git_sha(),
        "preset": lane.preset,
        "window": lane.window,
        **code_pins(),
        **device_info(args.backend),
        "tolerance": TOL,
        "time_epoch": int(time.time()),
    }
    head["lane_pipeline_sha256"] = lane_pipeline_sha256(lane)
    rec = {**head, **run_parity(lane, args.seeds, args.backend)}
    if rec["seeds"] < 10_000:
        rec["note"] = "fewer than 10^4 seeds: does not count as the rules' parity test"
    (out_dir / "parity.json").write_text(json.dumps(rec, indent=2) + "\n")
    for c in rec["cases"]:
        print(
            f"{c['cipher']:8s} keys {c['keys']:,} max|dscore| {c['max_abs_dscore']:.2e} "
            f"max|dobj| {c['max_abs_dobjective']:.2e} survivors {c['survivors']} "
            f"identical {c['survivor_set_identical']} -> {'PASS' if c['passed'] else 'FAIL'}"
        )
    print(
        f"parity {rec['status'].upper()} ({rec['backend']}, simulated {rec['simulated']}): "
        f"{out_dir / 'parity.json'}"
    )
    if rec["status"] != "passed":
        return 1
    if args.bench:
        if args.backend != "gpu" or rec["simulated"] or rec["seeds"] < 10_000:
            print(
                "no benchmark: a throughput number needs a passing >= 10^4-seed parity run "
                "on a real device",
                file=sys.stderr,
            )
            return 2
        b = {**head, "chunk_size": lane.chunk_size, "L": lane.window, **bench(lane, args.bench)}
        (out_dir / "bench.json").write_text(json.dumps(b, indent=2) + "\n")
        print(
            f"bench: kernel {b['kernel_keys_per_s']:,.0f} keys/s, end to end "
            f"{b['end_to_end_keys_per_s']:,.0f} keys/s: {out_dir / 'bench.json'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
