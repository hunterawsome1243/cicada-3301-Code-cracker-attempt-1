---
paths:
  - "runeforge/gpu/**"
---

# GPU kernels and sweep jobs

A kernel is a faster copy of a CPU reference, nothing more. Everything it reports is replayed on
the CPU before anyone believes it (HIT_PROTOCOL.md §2: never adjudicate with the kernel that
found the crosser).

## Parity before any benchmark counts

- Every kernel has a numpy CPU reference in `runeforge/` that the tests and
  `runeforge crosser replay <kid> --cpu` use. Same arithmetic: rune index 0–28, mod 29; primes
  only for GP-sums; interrupts and anti-repeat skips are the decoder's job: the lane preset's
  decoder (rigid, or the beam, whose CPU reference is `runeforge/beam.py` `decode_batch` with
  `decode_reference` as its scalar twin) runs in the control, the nulls and the sweep alike.
- Parity test on ≥ 10⁴ seeds (both ends of the seed range, the control's planted seed, random
  seeds): keystreams identical symbol for symbol, scores |Δ| ≤ 1e-6, the survivor set identical.
  Early exit must never drop a seed the CPU reference puts above the claim bar; include seeds whose
  partial score dips below the running threshold and recovers.
- A kernel without a green parity test does not run a lane and has no throughput number.

## Benchmarks

- seeds/s is logged with the exact command, git SHA, GPU name and driver/CUDA version
  (`/usr/lib/wsl/lib/nvidia-smi`), chunk size and window L, to `runs/<id>/bench.json`. A number
  without its command does not count. Spec target ≥ 10⁷ seeds/s on 32-bit families (Dukotah's CPU
  reference: 7.7 × 10⁴/s on six cores).

## Jobs

- GPU sweeps are never Bash-tool children (`claude -p` ends background commands at exit; SIGTERM
  kills the tree). Launch with `runeforge sweep lanes/<id>.yaml --detach` (`setsid nohup … &`),
  which writes `runs/<id>/sweep.pid` and refreshes `runs/<id>/status.json` (`updated_epoch`,
  `deadline_epoch`, `done`, `kill_condition`, resume cursor) every chunk. Checkpoint every chunk;
  `--resume` is the default; resume across a forced kill is tested.
- One GPU job at a time: before launching, read every `runs/*/sweep.pid` and its
  `/proc/<pid>/cmdline`; if one is alive, do not start another.
- Kill only by a PID whose `/proc/<pid>/cmdline` contains `runeforge`: SIGTERM, then SIGKILL after
  60 s. Never `pkill -f`, never kill by name.
- More than 2 GPU-hours needs Hunter's approval in `queue.json`.

## WSL2 + CUDA

- CUDA comes from the Windows driver. Never install a Linux display driver inside WSL; install only
  `cuda-toolkit-12-x`, and the CuPy wheel that matches it (`pip install -e '.[gpu]'`, cupy-cuda12x).
- `/usr/lib/wsl/lib/nvidia-smi` must list the GPU before a launch. Windows must not sleep during a
  sweep (OVERNIGHT_LOOP.md Part 1).
