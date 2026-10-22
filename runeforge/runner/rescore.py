"""``runeforge score <lane.yaml> <seed>|<lo>:<hi>``: re-score seeds with the lane's sweep pipeline.

Every SWEEPROW's reproduce command points here: a survivor or crosser row names its seed, a
chunk row its seed range. The numbers come from exactly the calls the sweep makes
(``pipeline.keys_batch``, ``pipeline.decrypt``, the preset's ``score_batch`` over the lane's
window), so a printed score equals the recorded one to floating-point identity.
"""

from __future__ import annotations

import heapq

import numpy as np

from runeforge.lanes import LaneSpec
from runeforge.runner import pipeline
from runeforge.scoring import presets

BATCH = 4096


def score_seeds(lane: LaneSpec, seeds) -> np.ndarray:
    cipher = pipeline.lane_cipher(lane)[: lane.window]
    scorer = presets.get(presets.split_preset(lane.preset)[0])
    keys = pipeline.keys_batch(lane, seeds, cipher.size)
    return pipeline.score_batch(scorer, pipeline.decrypt(lane, cipher[None, :], keys))


def parse_seeds(spec: str) -> tuple[int, int]:
    """'681' -> (681, 682); '0:5000' -> (0, 5000)."""
    lo, sep, hi = spec.partition(":")
    a = int(lo)
    b = int(hi) if sep else a + 1
    if not 0 <= a < b:
        raise ValueError(f"seed range {spec!r} must be lo:hi with 0 <= lo < hi")
    return a, b


def score_range(lane: LaneSpec, lo: int, hi: int, top: int = 5) -> dict:
    best: list[tuple[float, int]] = []
    above_claim = above_fw = 0
    for b in range(lo, hi, BATCH):
        seeds = np.arange(b, min(b + BATCH, hi), dtype=np.int64)
        scores = score_seeds(lane, seeds)
        if lane.claim_bar is not None:
            above_claim += int((scores > lane.claim_bar).sum())
        if lane.family_wise_bar is not None:
            above_fw += int((scores > lane.family_wise_bar).sum())
        for s, v in zip(seeds.tolist(), scores.tolist(), strict=True):
            if len(best) < top:
                heapq.heappush(best, (v, s))
            elif v > best[0][0]:
                heapq.heapreplace(best, (v, s))
    return {
        "lane_id": lane.lane_id,
        "lo": lo,
        "hi": hi,
        "top": [{"seed": s, "score": v} for v, s in sorted(best, reverse=True)],
        "above_claim_bar": above_claim,
        "above_family_wise_bar": above_fw,
        "claim_bar": lane.claim_bar,
        "family_wise_bar": lane.family_wise_bar,
        "numbering": "LP2-0-57",
    }
