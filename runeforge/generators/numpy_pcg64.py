"""``np.random.default_rng(seed).integers(0, 29, n)``: a convenience stream for tests and
controls only.

It is fast and uniform, but numpy does not promise ``Generator`` streams stay fixed across
releases, and no 2012-era author could have produced it, so it is never a searched family
and never the second null (that is ``sha256-ctr``, whose definition is frozen).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from runeforge.generators.base import Generator


@dataclass(frozen=True)
class NumpyPCG64(Generator):
    name: ClassVar[str] = "numpy-pcg64"
    seed_bits: ClassVar[int] = 64

    def _batch(self, seeds: list[int], n: int) -> np.ndarray:
        return np.stack(
            [np.random.default_rng(s).integers(0, 29, n, dtype=np.int64) for s in seeds]
        )
