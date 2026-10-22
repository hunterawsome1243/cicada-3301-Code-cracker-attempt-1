"""``runeforge control <lane.yaml>``: the planted positive through the lane's exact pipeline.

For each of ``n_plants`` plants: draw a seed from the lane's own seed range, encipher a
held-out Cicada-register plaintext window (random offset) with the lane's generator,
combine, filter and interrupt model, then search the true seed among ``decoys`` wrong
seeds of the same generator with the lane's decoder and scorer. A plant is IDENTIFIED when
the true seed ranks 1 and its rune-index recovery is >= ``min_recovery``.

Verdict arithmetic (SESSION_PROMPT.md section C2, jens-wedin's floor/ceiling):
* floor   = the lowest planted score among identified plants;
* ceiling = the best score of keys from the domain-separated SHA-256 stream (outside every
  family a lane searches), same length, same scorer, extrapolated to the lane's own number
  of trials: the control measures n_plants x (decoys + 1) of them and adds
  beta ln(N / measured), beta from the preset's calibration (else from the per-plant maxima);
* the control PASSES only when >= ``min_identified`` (>= 0.90) of >= 20 plants are
  identified, the floor clears the lane's family-wise bar (when set), floor - ceiling is at
  least 0.25 nats, and the generator's wrong keys score like noise (the decoys' max sits
  within 5 beta of a null max over as many keys). Anything else is INCONCLUSIVE (power).

The result is the lane's Rule 2 evidence. ``write_report`` writes it to
``runs/<id>/control.json`` and, committed, to ``lanes/<id>/control.json`` plus an immutable
``lanes/<id>/control-<sha12>.json`` the ledger row points at; ``control_problems`` is what
the sweep checks before it runs.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from runeforge import canon, generators
from runeforge.lanes import LaneSpec
from runeforge.runner import pipeline
from runeforge.scoring import presets

NATS_PER_BIT = math.log(2)
MIN_GAP_NATS = 0.25
WRONG_KEY_BETAS = 5.0  # decoy max vs matched null max: logistic(0, beta) tail 1/(1+e^5) = 0.7 %
# the fields that decide what the sweep computes; a control is evidence only for these
PIPELINE_FIELDS = (
    "lane_id",
    "generator",
    "generator_params",
    "seed_range",
    "ciphertext_view",
    "combine",
    "key_offset",
    "filter_model",
    "p_keep",
    "interrupt_prob",
    "preset",
    "window",
    "pages",
    "claim_bar",
    "family_wise_bar",
    "control",
)


def lane_pipeline_sha256(lane: LaneSpec) -> str:
    spec = lane.model_dump(include=set(PIPELINE_FIELDS), mode="json")
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


def plant_source(spec: str) -> np.ndarray:
    """'solved:<id>', 'solved' (all nine) or 'corpus:<name>' -> rune indices."""
    kind, _, name = spec.partition(":")
    if kind == "solved":
        if name:
            return canon.solved_section(name).plain
        return np.concatenate([s.plain for s in canon.load_solved_sections()])
    if kind == "corpus":
        from runeforge import corpus

        presets.check_corpus_name(name)
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
    ceiling: float  # extrapolated to the lane's N
    gap_nats: float | None
    wrong_key_max: float  # the decoys' max over n_plants x decoys wrong keys
    bar: float | None
    status: str  # passed | failed
    verdict_if_failed: str
    reasons: list[str] = field(default_factory=list)
    plants: list[Plant] = field(default_factory=list)
    ceiling_observed: float = float("nan")  # max over the measured null keys
    ceiling_trials: int = 0  # how many null keys were measured
    lane_trials: int = 0  # N the ceiling is extrapolated to
    beta: float = float("nan")
    beta_source: str = ""

    def summary(self) -> str:
        floor = "n/a" if self.floor is None else f"{self.floor:.4f}"
        gap = "n/a" if self.gap_nats is None else f"{self.gap_nats:.3f} nats"
        bar = "n/a" if self.bar is None else f"{self.bar:.4f}"
        return (
            f"control {self.status.upper()}: "
            f"recovered {self.identified}/{self.n_plants} at rank 1; "
            f"floor {floor} vs ceiling {self.ceiling:.4f} at N={self.lane_trials:,} "
            f"(observed {self.ceiling_observed:.4f} over {self.ceiling_trials:,}; gap {gap}); "
            f"wrong-key max {self.wrong_key_max:.4f}; bar {bar}"
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
    measured = spec.n_plants * (spec.decoys + 1)
    observed = max(p.ceiling for p in plants)
    beta, beta_source = _beta(lane, [p.ceiling for p in plants])
    n_lane = lane.n_trials
    ceiling = observed + beta * math.log(max(n_lane, measured) / measured)
    gap = None if floor is None else (floor - ceiling) * NATS_PER_BIT
    decoy_max = max(p.best_decoy for p in plants)
    bar = lane.family_wise_bar
    reasons = []
    if spec.n_plants < 20:
        reasons.append(f"only {spec.n_plants} plants (>= 20 required)")
    if len(ident) < max(spec.min_identified, 0.5) * len(plants):
        reasons.append(f"identified {len(ident)}/{len(plants)} < {spec.min_identified:.0%}")
    if floor is None:
        reasons.append("no plant identified: there is no floor")
    if floor is not None and bar is not None and floor < bar:
        reasons.append(f"floor {floor:.4f} below the lane's family-wise bar {bar:.4f}")
    if decoy_max > observed + WRONG_KEY_BETAS * beta:
        reasons.append(
            f"the generator's wrong keys do not score like noise: decoy max {decoy_max:.4f} > "
            f"null max {observed:.4f} + {WRONG_KEY_BETAS:g} beta over as many keys"
        )
    if gap is not None and gap < MIN_GAP_NATS:
        reasons.append(f"floor - ceiling = {gap:.3f} nats < {MIN_GAP_NATS}")
    status = "failed" if reasons else "passed"  # a failed control is never lowered into a pass
    return ControlReport(
        lane_id=lane.lane_id,
        n_plants=len(plants),
        identified=len(ident),
        floor=floor,
        ceiling=ceiling,
        gap_nats=gap,
        wrong_key_max=decoy_max,
        bar=bar,
        status=status,
        verdict_if_failed="INCONCLUSIVE (power)" if reasons else "",
        reasons=reasons,
        plants=plants,
        ceiling_observed=observed,
        ceiling_trials=measured,
        lane_trials=n_lane,
        beta=beta,
        beta_source=beta_source,
    )


def _beta(lane: LaneSpec, plant_maxima: list[float]) -> tuple[float, str]:
    """Gumbel scale for extrapolating the ceiling: the preset's calibration at this window
    if there is one, else a moment estimate from the per-plant null maxima."""
    from runeforge.scoring import calib

    try:
        return float(calib.load(lane.preset, lane.window)["fit"]["beta"]), "calibration"
    except (FileNotFoundError, ValueError, KeyError):
        sd = float(np.std(plant_maxima, ddof=1)) if len(plant_maxima) > 1 else 0.0
        return sd * math.sqrt(6) / math.pi, "per-plant maxima"


def write_report(
    report: ControlReport, lane: LaneSpec, run_dir: Path, lanes_dir: Path | None = None
) -> dict:
    """Write the control's evidence; return the ``control_detail`` a ledger row records.

    ``runs/<id>/control.json`` is the working copy; ``lanes/<id>/control.json`` (latest)
    and ``lanes/<id>/control-<sha12>.json`` (immutable, the one a ledger row cites) are
    committed, so the evidence survives in every clone."""
    from runeforge.ledger import git_sha
    from runeforge.paths import LANES_DIR, REPO_ROOT

    data = asdict(report)
    data["numbering"] = canon.LP2_NUMBERING
    data["summary"] = report.summary()
    data["lane_pipeline_sha256"] = lane_pipeline_sha256(lane)
    data["git_sha"] = git_sha()
    data["recorded"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    text = json.dumps(data, indent=1, default=float) + "\n"
    sha = hashlib.sha256(text.encode()).hexdigest()
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "control.json").write_text(text, encoding="utf-8")
    lane_dir = (lanes_dir or LANES_DIR) / lane.lane_id
    lane_dir.mkdir(parents=True, exist_ok=True)
    frozen = lane_dir / f"control-{sha[:12]}.json"
    frozen.write_text(text, encoding="utf-8")
    (lane_dir / "control.json").write_text(text, encoding="utf-8")
    try:
        cited = frozen.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        cited = str(frozen)
    return {
        "path": cited,
        "sha256": sha,
        "status": report.status,
        "lane_pipeline_sha256": data["lane_pipeline_sha256"],
        "summary": data["summary"],
    }


def control_problems(lane: LaneSpec, row, lanes_dir: Path | None = None) -> list[str]:
    """Rule 2 for the sweep: the lane's latest control passed, ran on the lane spec as it is
    now, and is the one the ledger row cites. ``row`` is the lane's latest LedgerRow."""
    from runeforge.paths import LANES_DIR

    path = (lanes_dir or LANES_DIR) / lane.lane_id / "control.json"
    if not path.exists():
        return [f"Rule 2: no {path} -- run `runeforge control` on this lane first"]
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    out = []
    if data.get("status") != "passed":
        out.append(f"Rule 2: the control in {path} did not pass (INCONCLUSIVE (power))")
    if data.get("lane_pipeline_sha256") != lane_pipeline_sha256(lane):
        out.append(
            "Rule 2: the lane spec changed since its control ran; re-run `runeforge control`"
        )
    detail = getattr(row, "control_detail", None) if row is not None else None
    sha = hashlib.sha256(text.encode()).hexdigest()
    if row is None or row.positive_control != "passed":
        out.append("Rule 2: the ledger does not record a passing positive control")
    elif not isinstance(detail, dict) or detail.get("sha256") != sha:
        out.append(
            "Rule 2: the ledger's control_detail does not cite this control.json "
            "(`runeforge control` records it)"
        )
    return out
