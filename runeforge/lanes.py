"""Lane specification: one YAML file per attack lane in ``lanes/``.

A lane declares its hypothesis, search space, ciphertext view, scorer, bars and the
planted control BEFORE it runs. ``runeforge ledger append --lane lanes/<id>.yaml`` writes the
pre-registration ledger row from this file; ``runnable_problems`` is what ``runeforge lane``
prints and ``runeforge sweep`` refuses on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# SESSION_PROMPT.md section C2's pass bar. A lane may raise it, never lower it.
MIN_PLANTS = 20
MIN_DECOYS = 99
MIN_RECOVERY = 0.90
MIN_IDENTIFIED = 0.90


class ControlSpec(BaseModel):
    """The planted positive (SESSION_PROMPT.md section C2): >= 20 plants in the real shape,
    each recovered at rank 1 among ``decoys`` wrong seeds with rune-index recovery >= 0.90."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _pass_bar(self) -> ControlSpec:
        low = [
            f"{k} {v} < {floor}"
            for k, v, floor in (
                ("n_plants", self.n_plants, MIN_PLANTS),
                ("decoys", self.decoys, MIN_DECOYS),
                ("min_recovery", self.min_recovery, MIN_RECOVERY),
                ("min_identified", self.min_identified, MIN_IDENTIFIED),
            )
            if v < floor
        ]
        if low:
            raise ValueError(
                "the control's pass bar may be raised, never lowered (SESSION_PROMPT.md C2): "
                + ", ".join(low)
            )
        return self

    planted_seed: int | str
    synthetic_page: str = Field(
        description="held-out plaintext: 'solved:<section-id>', 'solved' or 'corpus:<name>'"
    )
    n_runes: int | None = None  # if given, must equal the lane's window
    must_recover: bool = True
    n_plants: int = 20
    decoys: int = 999
    min_recovery: float = 0.90
    min_identified: float = 0.90


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wall_clock_hours: float | None = None
    gpu_hours_cap: float = 0.0
    max_seeds: int | None = None


class KillCondition(BaseModel):
    """Q5 of the Aiming Test, machine-checkable: evaluated once at ``at_fraction`` of the slice."""

    model_config = ConfigDict(extra="forbid")

    at_fraction: float = 0.10
    min_seeds_per_s: float | None = None
    max_crossers: int | None = None


class LaneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lane_id: str
    hypothesis: str
    family: str
    category: Literal["instrument", "bounded", "redteam", "closeout"] | None = None
    prereg: str | None = None
    generator: str
    generator_params: dict[str, Any] = Field(default_factory=dict)
    seed_range: tuple[int, int]
    chunk_size: int = 1 << 20
    ciphertext_view: Literal["raw", "atbash", "chain-increment", "first-difference"] = "raw"
    combine: Literal["vigenere", "variant-beaufort", "beaufort"] = "vigenere"
    key_offset: int = 0
    filter_model: Literal["off", "anti-repeat"] = "off"
    # anti-repeat filter: a repeat survives with this probability; LP2 measures 86 doublets
    # against 447 expected, 86/447 = 0.19 (CLAUDE.md: p_keep 0.18-0.19)
    p_keep: float = 0.19
    # P(a plaintext F is written as an unencrypted interrupter). The rule (CLAUDE.md) and the
    # keyed solved sections say every one is: 14 of 14 plaintext F's (WELCOME 11/11, A KOAN 2
    # 2/2, AN END 1/1). "11 of 25" is the share of CIPHERTEXT F's that are interrupters.
    interrupt_prob: float = 1.0
    scorer_register: str = "english"
    preset: str = "lp-ngram3:rigid"  # <scorer>:<decoder>, see runeforge.scoring.presets
    window: int = 240  # runes of the selected stream that are scored
    pages: list[int] = Field(default_factory=lambda: list(range(56)))
    claim_bar: float | None = None  # survivors above it are written (screening bar)
    family_wise_bar: float | None = None  # threshold_for(N) at this lane's true N: crossers
    control: ControlSpec
    budget: Budget = Field(default_factory=Budget)
    kill_condition: KillCondition = Field(default_factory=KillCondition)
    resume_cursor: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("preset")
    @classmethod
    def _known_preset(cls, v):
        from runeforge.scoring import presets

        try:
            presets.split_preset(v)
        except KeyError as exc:
            raise ValueError(str(exc).strip('"')) from None
        return v

    @field_validator("filter_model", mode="before")
    @classmethod
    def _yaml_off(cls, v):
        return "off" if v is False else v  # YAML 1.1 reads a bare `off` as false

    @model_validator(mode="after")
    def _check(self) -> LaneSpec:
        lo, hi = self.seed_range
        if not 0 <= lo < hi:
            raise ValueError("seed_range must be [lo, hi) with 0 <= lo < hi")
        if self.resume_cursor is not None and not lo <= self.resume_cursor <= hi:
            raise ValueError("resume_cursor outside seed_range")
        if not 0 <= self.p_keep <= 1 or not 0 <= self.interrupt_prob <= 1:
            raise ValueError("p_keep and interrupt_prob are probabilities")
        if self.window < 20:
            raise ValueError("window too short to score")
        if self.key_offset < 0:
            raise ValueError("key_offset must be >= 0")
        if self.control.n_runes is not None and self.control.n_runes != self.window:
            raise ValueError(
                f"control.n_runes {self.control.n_runes} != window {self.window}: plants are "
                "exactly one scored window long (drop n_runes or make them equal)"
            )
        return self

    @property
    def n_trials(self) -> int:
        return self.seed_range[1] - self.seed_range[0]

    def stream_runes(self) -> int:
        """Runes on the lane's pages (the length the sweep can score)."""
        from runeforge import canon

        lp2 = canon.load_lp2()
        return sum(lp2.page(n).n_runes for n in self.pages if n in canon.UNSOLVED_LP2_PAGES)

    def decoder_problems(self) -> list[str]:
        """A beam decoder may not model steps the lane's hypothesis rules out: its records would
        hold them, and crosser step 6 could not adjudicate a true key (review round 2)."""
        from runeforge.scoring import presets

        scorer, _, decoder = self.preset.partition(":")  # not split_preset: that refuses first
        decoder = decoder or "rigid"
        params = presets.DECODER_PARAMS[decoder]
        out = []
        # belt and braces with presets.split_preset (docs/kn-scorer-design.md section 5):
        # runeforge.beam reads dense (29**i, 29) tables, which a sparse or word-boundary
        # Kneser-Ney scorer does not have
        if presets.is_wb(scorer):
            out.append(
                f"scorer {scorer} is a word-boundary model: adjudication and reports only this "
                "phase, no lane decoder"
            )
        if decoder != "rigid" and not presets.beam_compatible(scorer):
            out.append(
                f"scorer {scorer} has sparse levels (no dense tables): it pairs with the rigid "
                f"decoder only; the beam decoders take {presets.dense_presets()}"
            )
        if params.get("interrupt_prob", 0) > 0 and not self.interrupt_prob:
            out.append(
                f"decoder {decoder} models F-interrupters but the lane's interrupt_prob is 0: "
                "pick a decoder without interrupts (beam-skip, or rigid)"
            )
        if params.get("p_keep") is not None and (
            self.filter_model != "anti-repeat" or self.p_keep >= 1
        ):
            out.append(
                f"decoder {decoder} models anti-repeat key skips but the lane has no filter "
                "(filter_model off, or p_keep 1): pick a decoder without skips (beam, or rigid)"
            )
        return out

    def small_n_nulls(self, lanes_dir: Path | None = None) -> dict:
        """For N below the calibration block, threshold_for's small-N rule max(floor,
        null_max + 0.5, null2_max + 0.5) needs the lane's own nulls: the committed
        lanes/<id>/null.json of `runeforge null`, when it ran on this lane spec at the lane's
        own trial count, with this scorer and (for a beam preset) this decoder, which
        `runeforge null` records. Empty otherwise (threshold_for then refuses, saying so)."""
        import json

        from runeforge.paths import LANES_DIR
        from runeforge.runner.control import lane_pipeline_sha256
        from runeforge.runner.sweep import pins
        from runeforge.scoring import calib, presets

        if self.n_trials >= calib.BLOCK:
            return {}
        path = (lanes_dir or LANES_DIR) / self.lane_id / "null.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except (FileNotFoundError, ValueError):
            return {}
        scorer = presets.get(presets.split_preset(self.preset)[0])
        if data.get("scorer_fingerprint") != scorer.fingerprint():
            return {}
        if data.get("decoder") != pins(self, smoke=False).get("decoder"):
            return {}
        # the nulls do not depend on the bars, and the small-N bar comes from the nulls: a
        # null run before the bars were set (they are part of the pipeline hash) still counts
        unbarred = self.model_copy(update={"claim_bar": None, "family_wise_bar": None})
        if data.get("lane_pipeline_sha256") not in (
            lane_pipeline_sha256(self),
            lane_pipeline_sha256(unbarred),
        ):
            return {}
        if not data.get("same_trial_count"):
            return {}
        return {
            "null_max": float(data["null1_shuffle"]["max"]),
            "null2_max": float(data["null2_sha256"]["max"]),
        }

    def runnable_problems(
        self, check_bar_vs_threshold: bool = True, lanes_dir: Path | None = None
    ) -> list[str]:
        """Reasons the sweep runner must refuse this lane (empty = may run).

        ``check_bar_vs_threshold=False`` (the sweep's ``--smoke`` test harness only) skips
        the family_wise_bar >= threshold_for(N) comparison, so toy lanes can force crossers."""
        from runeforge.scoring import calib

        out = []
        have = self.stream_runes()
        if have < self.window:
            out.append(
                f"the lane's pages hold {have} runes, fewer than window {self.window}: the bar, "
                "the control and the calibration would be for the wrong length"
            )
        out.extend(self.decoder_problems())
        if self.claim_bar is None or self.family_wise_bar is None:
            out.append("bars are not calibrated (scripts/threshold_for.py at the lane's true N)")
        else:
            if self.claim_bar > self.family_wise_bar:
                out.append("claim_bar (screening) must not exceed family_wise_bar")
            try:
                t = calib.threshold_for(
                    self.n_trials, self.preset, self.window, **self.small_n_nulls(lanes_dir)
                )
            except (FileNotFoundError, ValueError) as exc:
                out.append(f"no bar for this lane's N, preset and window: {exc}")
            else:
                if check_bar_vs_threshold and self.family_wise_bar < t.bar - 1e-6:
                    out.append(
                        f"family_wise_bar {self.family_wise_bar:.4f} is below "
                        f"threshold_for(N={self.n_trials:,}, {self.preset}, L={self.window}) = "
                        f"{t.bar:.4f}; at that bar the slice expects more false positives than "
                        "the rule allows"
                    )
            from runeforge import canon
            from runeforge.scoring import beam_calib

            window = canon.load_lp2().stream(self.pages)[: self.window]
            out.extend(beam_calib.calibration_problems(self.preset, self.window, window))
        if not self.control.must_recover:
            out.append("control does not require recovery (Rule 2)")
        return out


def load_lane(path: Path | str) -> LaneSpec:
    return LaneSpec.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
