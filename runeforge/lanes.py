"""Lane specification: one YAML file per attack lane in ``lanes/``.

A lane declares its hypothesis, search space, ciphertext view, scorer, bars and the
planted control BEFORE it runs; the runner (Phase 3, ``runeforge sweep``) writes the
pre-registration ledger row from this file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ControlSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planted_seed: int | str
    synthetic_page: str = Field(description="plaintext source, e.g. 'solved:a-koan-1'")
    n_runes: int = 250
    must_recover: bool = True


class LaneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lane_id: str
    hypothesis: str
    family: str
    generator: str
    seed_range: tuple[int, int]
    chunk_size: int = 1 << 20
    ciphertext_view: Literal["raw", "atbash", "chain-increment", "first-difference"] = "raw"
    filter_model: Literal["off", "anti-repeat"] = "off"
    scorer_register: str = "english"
    pages: list[int] = Field(default_factory=lambda: list(range(56)))
    claim_bar: float | None = None  # None until the Phase 2 calibration computes it
    family_wise_bar: float | None = None
    control: ControlSpec
    resume_cursor: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> LaneSpec:
        lo, hi = self.seed_range
        if not 0 <= lo < hi:
            raise ValueError("seed_range must be [lo, hi) with 0 <= lo < hi")
        if self.resume_cursor is not None and not lo <= self.resume_cursor <= hi:
            raise ValueError("resume_cursor outside seed_range")
        return self

    @property
    def n_trials(self) -> int:
        return self.seed_range[1] - self.seed_range[0]

    def runnable_problems(self) -> list[str]:
        """Reasons the sweep runner must refuse this lane (empty = may run)."""
        out = []
        if self.claim_bar is None or self.family_wise_bar is None:
            out.append("bars are not calibrated (Phase 2 scorer power table)")
        if not self.control.must_recover:
            out.append("control does not require recovery (Rule 2)")
        return out


def load_lane(path: Path | str) -> LaneSpec:
    return LaneSpec.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
