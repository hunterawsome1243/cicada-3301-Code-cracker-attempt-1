"""``runeforge control <lane.yaml>``: the planted positive through the lane's exact pipeline.

For each of ``n_plants`` plants: draw a seed from the lane's own seed range, encipher a
held-out Cicada-register plaintext window (random offset) with the lane's generator,
combine, filter and interrupt model, then search the true seed among ``decoys`` wrong
seeds of the same generator with the lane's decoder and scorer. A plant is IDENTIFIED when
the true seed ranks 1 and its rune-index recovery is >= ``min_recovery``.

Verdict arithmetic (SESSION_PROMPT.md section C2, jens-wedin's floor/ceiling):
* floor   = the lowest planted score among identified plants;
* ceiling = the best score of the same number of trials drawn from the domain-separated
  SHA-256 stream (outside every family a lane searches), same length, same scorer;
* the control PASSES when >= ``min_identified`` of >= 20 plants are identified, the floor
  clears the lane's family-wise bar (when set) and every wrong-key score sits below the
  ceiling; it is INCONCLUSIVE (power) when fewer than half are identified or the gap
  floor - ceiling is under 0.25 nats.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from runeforge import canon, generators
from runeforge.lanes import LaneSpec
from runeforge.runner import pipeline
from runeforge.scoring import presets

NATS_PER_BIT = math.log(2)
MIN_GAP_NATS = 0.25


def plant_source(spec: str) -> np.ndarray:
    """'solved:<id>', 'solved' (all nine) or 'corpus:<name>' -> rune indices."""
    kind, _, name = spec.partition(":")
    if kind == "solved":
        if name:
            return canon.solved_section(name).plain
        return np.concatenate([s.plain for s in canon.load_solved_sections()])
    if kind == "corpus":
        from runeforge import corpus

        return corpus.load(name).runes.astype(np.int64)
    raise ValueError(f"unknown plant source {spec!r}")


@dataclass
class Plant:
    seed: int
    offset: int
    rank: int
    recovery: float
    planted_score: float
    best_decoy: float
    wrong_key_score: float
    ceiling: float
    identified: bool


@dataclass
class ControlReport:
    lane_id: str
    n_plants: int
    identified: int
    floor: float | None
    ceiling: float
    gap_nats: float | None
    wrong_key_max: float
    bar: float | None
    status: str  # passed | failed
    verdict_if_failed: str
    reasons: list[str] = field(default_factory=list)
    plants: list[Plant] = field(default_factory=list)

    def summary(self) -> str:
        floor = "n/a" if self.floor is None else f"{self.floor:.4f}"
        gap = "n/a" if self.gap_nats is None else f"{self.gap_nats:.3f} nats"
        return (
            f"control {self.status.upper()}: "
            f"recovered {self.identified}/{self.n_plants} at rank 1; "
            f"floor {floor} vs ceiling {self.ceiling:.4f} (gap {gap}); "
            f"wrong key max {self.wrong_key_max:.4f}; bar {self.bar}"
        )


def run_control(lane: LaneSpec, seed: int = 3301) -> ControlReport:
    spec = lane.control
    scorer_name, _decoder = presets.split_preset(lane.preset)
    presets.check_held_out(scorer_name, spec.synthetic_page)
    scorer = presets.get(scorer_name)
    source = plant_source(spec.synthetic_page)
    length = lane.window
    if source.size < length + 1:
        raise ValueError(f"plant source has {source.size} runes, window needs {length}")
    rng = np.random.default_rng(seed)
    lo, hi = lane.seed_range
    null_gen = generators.get("sha256-ctr", domain=f"runeforge/control-ceiling/{lane.lane_id}")

    plants: list[Plant] = []
    for i in range(spec.n_plants):
        if i == 0 and isinstance(spec.planted_seed, int) and lo <= spec.planted_seed < hi:
            s_true = spec.planted_seed
        else:
            s_true = int(rng.integers(lo, hi))
        off = int(rng.integers(0, source.size - length))
        plain = source[off : off + length]
        k_true = pipeline.keys(lane, s_true, 3 * length)
        model_cipher, _ = pipeline.encrypt(lane, plain, k_true, rng)
        # the lane decodes view(canonical); for a plant, the model cipher IS that view.
        decoys = rng.integers(lo, hi, spec.decoys)
        decoys = decoys[decoys != s_true]
        seeds = np.concatenate(([s_true], decoys))
        plains = pipeline.decrypt(
            lane, model_cipher[None, :], pipeline.keys_batch(lane, seeds, length)
        )
        scores = pipeline.score_batch(scorer, plains)
        rank = 1 + int((scores[1:] >= scores[0]).sum())
        recovery = float((plains[0] == plain).mean())
        nk = generators.keystream_batch(
            null_gen, list(range(i * 10**6, i * 10**6 + seeds.size)), length
        )
        ceiling = float(
            pipeline.score_batch(scorer, pipeline.decrypt(lane, model_cipher[None, :], nk)).max()
        )
        wrong_score = float(scores[1]) if decoys.size else float("nan")  # a deliberately wrong key
        plants.append(
            Plant(
                seed=s_true,
                offset=off,
                rank=rank,
                recovery=recovery,
                planted_score=float(scores[0]),
                best_decoy=float(scores[1:].max()) if decoys.size else float("nan"),
                wrong_key_score=wrong_score,
                ceiling=ceiling,
                identified=rank == 1 and recovery >= spec.min_recovery,
            )
        )

    ident = [p for p in plants if p.identified]
    floor = min(p.planted_score for p in ident) if ident else None
    ceiling = max(p.ceiling for p in plants)
    gap = None if floor is None else (floor - ceiling) * NATS_PER_BIT
    wrong_max = max(p.wrong_key_score for p in plants)
    bar = lane.family_wise_bar
    reasons = []
    if spec.n_plants < 20:
        reasons.append(f"only {spec.n_plants} plants (>= 20 required)")
    if len(ident) < spec.min_identified * len(plants):
        reasons.append(f"identified {len(ident)}/{len(plants)} < {spec.min_identified:.0%}")
    if floor is not None and bar is not None and floor < bar:
        reasons.append(f"floor {floor:.4f} below the lane's family-wise bar {bar:.4f}")
    if wrong_max >= ceiling:
        reasons.append("a wrong key scored at or above the noise ceiling")
    if gap is not None and gap < MIN_GAP_NATS:
        reasons.append(f"floor - ceiling = {gap:.3f} nats < {MIN_GAP_NATS}")
    status = "failed" if reasons else "passed"
    weak = len(ident) < 0.5 * len(plants) or gap is None or gap < MIN_GAP_NATS
    return ControlReport(
        lane_id=lane.lane_id,
        n_plants=len(plants),
        identified=len(ident),
        floor=floor,
        ceiling=ceiling,
        gap_nats=gap,
        wrong_key_max=wrong_max,
        bar=bar,
        status=status,
        verdict_if_failed="INCONCLUSIVE (power)" if weak or reasons else "",
        reasons=reasons,
        plants=plants,
    )


def write_report(report: ControlReport, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "control.json"
    data = asdict(report)
    data["numbering"] = canon.LP2_NUMBERING
    data["summary"] = report.summary()
    out.write_text(json.dumps(data, indent=1, default=float) + "\n", encoding="utf-8")
    return out
