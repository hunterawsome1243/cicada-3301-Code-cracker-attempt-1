"""``runeforge null <lane.yaml>``: the two nulls a lane's PREREG and RESULTS report.

* Null 1 -- size-matched shuffle of the real runes: each replicate permutes the lane's scored
  window of real (viewed) runes, decodes it with ``trials`` keys of the lane's own generator
  through the lane's decoder and scorer, and keeps the max.
* Null 2 -- a source outside every searched family: the real window decoded with keys from
  the domain-separated SHA-256 stream, ``trials`` per replicate, max kept.

``trials`` is the lane's N when N is small (the small-N rule's null_max is then exactly
"same trial count"); for a large N it is capped and the report says so -- the bar at the
lane's N comes from ``scripts/threshold_for.py``, and the nulls are the sanity check on it.
Written to ``runs/<id>/null.json`` and, committed, ``lanes/<id>/null.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from runeforge import canon, generators
from runeforge.lanes import LaneSpec
from runeforge.runner import pipeline
from runeforge.scoring import presets

MAX_TRIALS = 1000  # per replicate when the lane's N is larger
BATCH = 4096


def _max_scores(lane, scorer, ciphers: np.ndarray, gen, seed_lists) -> np.ndarray:
    out = np.empty(len(ciphers))
    for r, (c, seeds) in enumerate(zip(ciphers, seed_lists, strict=True)):
        best = -np.inf
        for b in range(0, len(seeds), BATCH):
            s = seeds[b : b + BATCH]
            keys = generators.keystream_batch(gen, [int(x) for x in s], lane.key_offset + c.size)
            plains = pipeline.decrypt(lane, c[None, :], keys[:, lane.key_offset :])
            best = max(best, float(pipeline.score_batch(scorer, plains).max()))
        out[r] = best
    return out


def _summary(x: np.ndarray) -> dict:
    return {
        "n": int(x.size),
        "mean": float(x.mean()),
        "sd": float(x.std(ddof=1)) if x.size > 1 else 0.0,
        "max": float(x.max()),
    }


def run_null(lane: LaneSpec, n: int = 200, seed: int = 3301, trials: int | None = None) -> dict:
    if n < 200:
        raise ValueError(f"a null needs n >= 200 replicates (CLAUDE.md, Doctrine), got {n}")
    t = trials or min(lane.n_trials, MAX_TRIALS)
    if t < 1:
        raise ValueError("trials must be >= 1")
    window = pipeline.lane_cipher(lane)[: lane.window]
    if window.size < lane.window:
        raise ValueError(f"the lane's pages hold {window.size} runes, fewer than {lane.window}")
    scorer = presets.get(presets.split_preset(lane.preset)[0])
    rng = np.random.default_rng(seed)
    lo, hi = lane.seed_range
    shuffles = np.stack([rng.permutation(window) for _ in range(n)])
    own = [pipeline.draw_seeds(rng, lo, hi, t) for _ in range(n)]
    null1 = _max_scores(lane, scorer, shuffles, pipeline.generator(lane), own)
    sha = generators.get("sha256-ctr", domain=f"runeforge/null2/{lane.lane_id}")
    sha_seeds = [np.arange(r * t, (r + 1) * t) for r in range(n)]
    null2 = _max_scores(lane, scorer, np.repeat(window[None, :], n, axis=0), sha, sha_seeds)
    from runeforge.runner.control import lane_pipeline_sha256

    return {
        "lane_id": lane.lane_id,
        "numbering": canon.LP2_NUMBERING,
        "window": lane.window,
        "preset": lane.preset,
        "trials_per_replicate": t,
        "lane_n_trials": lane.n_trials,
        "same_trial_count": t == lane.n_trials,
        "seed": seed,
        "null1_shuffle": _summary(null1),
        "null2_sha256": {**_summary(null2), "domain": f"runeforge/null2/{lane.lane_id}"},
        "lane_pipeline_sha256": lane_pipeline_sha256(lane),
    }


def write_report(
    lane: LaneSpec, report: dict, run_dir: Path, lanes_dir: Path | None = None
) -> Path:
    from runeforge.paths import LANES_DIR

    text = json.dumps(report, indent=1) + "\n"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "null.json").write_text(text, encoding="utf-8")
    lane_dir = (lanes_dir or LANES_DIR) / lane.lane_id
    lane_dir.mkdir(parents=True, exist_ok=True)
    (lane_dir / "null.json").write_text(text, encoding="utf-8")
    return lane_dir / "null.json"
