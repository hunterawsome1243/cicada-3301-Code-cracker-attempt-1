"""``runeforge gate <lane.yaml>``: would this cipher family even produce LP2's fingerprint?

Simulates the lane's cipher model (generator, combine, filter, interrupts, view) on
Cicada-register English with >= 12 random keys from the lane's seed range and grades each
ciphertext against murphy's C1-C6 constraints (runeforge.stats.fingerprint). A majority
FAIL is ``EXCLUDED (gate)``: it excludes the typical key, not the family -- say so in
``not_covered``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from runeforge import canon
from runeforge.lanes import LaneSpec
from runeforge.runner import pipeline

MIN_KEYS = 12  # SESSION_PROMPT.md section C3: the majority rule needs >= 12 simulated keys


def run_gate(lane: LaneSpec, seeds: int = 12, corpus: str = "cicada-english"):
    from runeforge.stats import fingerprint

    if seeds < MIN_KEYS:
        raise ValueError(f"the gate needs >= {MIN_KEYS} simulated keys, got {seeds}")
    lo, hi = lane.seed_range

    def encrypt(plain: np.ndarray, word_ids: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        seed = pipeline.draw_seeds(rng, lo, hi, 1)[0]
        k = pipeline.keys(lane, seed, 3 * plain.size)
        model_cipher, _ = pipeline.encrypt(lane, plain, k, rng)
        return pipeline.unview(model_cipher, lane.ciphertext_view)

    return fingerprint.gate_cipher(encrypt, seeds=seeds, corpus=corpus)


def write_report(lane: LaneSpec, result, run_dir: Path, lanes_dir: Path | None = None) -> Path:
    """runs/<id>/gate.json and the committed lanes/<id>/gate.json, bound to the lane spec."""
    from runeforge.paths import LANES_DIR
    from runeforge.runner.control import lane_pipeline_sha256

    data = {
        "lane_id": lane.lane_id,
        "numbering": canon.LP2_NUMBERING,
        "verdict_line": result.verdict_line,
        "excluded": result.verdict_line.startswith("GATE FAIL"),
        "n_seeds": len(result.per_seed_rows),
        "lane_pipeline_sha256": lane_pipeline_sha256(lane),
        "fails_per_constraint": result.fails_per_constraint,
        "per_seed_rows": result.per_seed_rows,
    }
    text = json.dumps(data, indent=1, default=str) + "\n"
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "gate.json"
    out.write_text(text, encoding="utf-8")
    lane_dir = (lanes_dir or LANES_DIR) / lane.lane_id
    lane_dir.mkdir(parents=True, exist_ok=True)
    (lane_dir / "gate.json").write_text(text, encoding="utf-8")
    return lane_dir / "gate.json"
