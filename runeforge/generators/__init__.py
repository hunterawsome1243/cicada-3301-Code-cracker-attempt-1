"""CPU reference keystream generators (spec section 4.2).

Each generator is the *definition* of a keystream family: a seeded lane enciphers its
plants and decodes the real pages with these streams, and every GPU kernel must match them
on 10^4 seeds before its throughput counts. Each one is a frozen dataclass whose ``spec()``
round-trips through ``get``, so a ledger row can name the exact stream it searched::

    g = generators.get("mt19937-py27", mode="random29")
    g.keystream(3301, 240)                       # int64, values 0..28
    generators.keystream_batch(g, seeds, 240)    # shape (len(seeds), 240)
    generators.get(**g.spec()) == g

* ``sha256-ctr``   domain-separated SHA-256 counter stream; the second null, outside every
  searched family.
* ``mt19937-py27`` CPython 2.7 ``random.seed(<int>)`` + MT19937 and 2.7's four reducers.
* ``numpy-pcg64``  numpy's default ``Generator``; tests and controls only.
"""

from __future__ import annotations

import numpy as np

from runeforge.generators.base import Generator
from runeforge.generators.mt19937_py27 import MT19937Py27
from runeforge.generators.numpy_pcg64 import NumpyPCG64
from runeforge.generators.sha256_ctr import Sha256Ctr

__all__ = [
    "Generator",
    "MT19937Py27",
    "NumpyPCG64",
    "Sha256Ctr",
    "get",
    "keystream_batch",
    "names",
]

_REGISTRY: dict[str, type[Generator]] = {
    cls.name: cls for cls in (Sha256Ctr, MT19937Py27, NumpyPCG64)
}


def names() -> list[str]:
    return list(_REGISTRY)


def get(name: str, **params) -> Generator:
    """Build a generator by name; ``params`` are its dataclass fields (see ``spec()``)."""
    try:
        cls = _REGISTRY[name]
    except KeyError:
        raise ValueError(f"unknown generator {name!r}; known: {names()}") from None
    try:
        return cls(**params)
    except TypeError as e:
        raise ValueError(f"bad params for generator {name!r}: {e}") from None


def keystream_batch(g: Generator, seeds, n: int) -> np.ndarray:
    """``g.keystream(s, n)`` for every seed, stacked to shape ``(len(seeds), n)``."""
    return g.batch(seeds, n)
