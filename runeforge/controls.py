"""Plant-and-recover controls (Rule 2: plant before you claim).

An attack lane's null result on the real pages counts only if the same instrument
recovers a planted key on a synthetic page first. This module builds those synthetic
pages from real Cicada-register plaintext (the solved sections) and checks recovery.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from runeforge import canon
from runeforge.interrupts import F, encrypt_with_interrupts
from runeforge.transforms import Transform


def control_plaintext(exclude: Sequence[str] = ()) -> np.ndarray:
    """The solved plaintext (2,979 runes of Cicada's own register), sections concatenated."""
    parts = [s.plain for s in canon.load_solved_sections() if s.id not in exclude]
    return np.concatenate(parts)


@dataclass(frozen=True)
class SyntheticPage:
    plain: np.ndarray
    cipher: np.ndarray
    interrupts: tuple[int, ...]
    transform_spec: dict


def synthetic_page(
    plain,
    transform: Transform,
    interrupt_prob: float = 0.5,
    seed: int = 3301,
) -> SyntheticPage:
    """Encipher ``plain`` under ``transform``; each plaintext F becomes an unencrypted
    interrupter with probability ``interrupt_prob`` (the solved pages use 11/25, 2/5, 1/5)."""
    p = np.asarray(plain, dtype=np.int64)
    rng = np.random.default_rng(seed)
    f_pos = np.flatnonzero(p == F)
    chosen = tuple(int(i) for i in f_pos[rng.random(f_pos.size) < interrupt_prob])
    c = encrypt_with_interrupts(p, transform, chosen)
    return SyntheticPage(p, c, chosen, transform.spec())


@dataclass
class ControlResult:
    name: str
    recovered: bool
    accuracy: float  # fraction of runes the decoder got right
    details: dict = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "passed" if self.recovered else "failed"


def run_control(
    name: str,
    page: SyntheticPage,
    decoder: Callable[[np.ndarray], np.ndarray],
    min_accuracy: float = 1.0,
) -> ControlResult:
    """Run ``decoder`` on the synthetic ciphertext; recovered iff accuracy >= ``min_accuracy``."""
    out = np.asarray(decoder(page.cipher), dtype=np.int64)
    if out.shape != page.plain.shape:
        return ControlResult(name, False, 0.0, {"error": "decoder changed the length"})
    acc = float((out == page.plain).mean())
    return ControlResult(
        name,
        acc >= min_accuracy,
        acc,
        {"n_runes": int(page.plain.size), "n_interrupts": len(page.interrupts)},
    )
