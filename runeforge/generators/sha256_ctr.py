"""Domain-separated SHA-256 counter stream: the null "from a source outside every family".

CLAUDE.md requires every small-N threshold to carry a second null drawn from a source that
no lane searches. A keyed hash in counter mode is that source: no PRNG family, running key,
prime stream or vocabulary key reproduces it, and the ``domain`` string separates one
control's null from another's (the control ceiling uses ``runeforge/control-ceiling/<lane>``).

Definition (frozen; a change is a new domain or a new generator, never an edit)::

    block_j = sha256(domain.encode("utf-8") + seed.to_bytes(8, "big") + j.to_bytes(8, "big"))
    symbols = [b % 29 for b in block_0 + block_1 + ... if b < 232]      # 232 = 8 * 29

Rejecting bytes >= 232 makes every symbol exactly uniform on 0..28 (a plain ``b % 29``
over 0..255 would over-weight 0..23 by 9/8). Expected yield is 29 symbols per block.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from runeforge.generators.base import Generator, take_accepted

DEFAULT_DOMAIN = "runeforge/null/v1"
ACCEPT_BELOW = 232  # 8 * 29


@dataclass(frozen=True)
class Sha256Ctr(Generator):
    name: ClassVar[str] = "sha256-ctr"
    seed_bits: ClassVar[int] = 64
    domain: str = DEFAULT_DOMAIN

    def __post_init__(self) -> None:
        if not isinstance(self.domain, str):
            raise TypeError("sha256-ctr: domain must be a str")

    def _draw(self, seeds: list[int], blocks: int) -> tuple[np.ndarray, np.ndarray]:
        dom = self.domain.encode("utf-8")
        ctr = [j.to_bytes(8, "big") for j in range(blocks)]
        parts = []
        for s in seeds:
            head = hashlib.sha256(dom + s.to_bytes(8, "big"))
            for c in ctr:
                h = head.copy()
                h.update(c)
                parts.append(h.digest())
        b = np.frombuffer(b"".join(parts), dtype=np.uint8).reshape(len(seeds), 32 * blocks)
        return (b % 29).astype(np.int64), b < ACCEPT_BELOW

    def _batch(self, seeds: list[int], n: int) -> np.ndarray:
        need = n * 256 / ACCEPT_BELOW + 4 * math.sqrt(n) + 8  # bytes, ~4 sd of margin
        return take_accepted(seeds, n, self._draw, math.ceil(need / 32))
