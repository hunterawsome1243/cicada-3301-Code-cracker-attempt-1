"""Gematria Primus: the 29-rune alphabet of the Liber Primus.

Every cipher operation in runeforge works on rune *indices* 0..28, mod 29. The prime
values (2..109) are used only for GP-sums, never for shift arithmetic.

The table below is verified on ingest against two independent sources
(``tests/test_gematria.py``):

* ``yo-yo-yo-jbo/cicada_tools`` ``core.py`` (``RuneUtils._RUNES``, ``_LATIN``, ``_GP_PRIMES``)
* ``scream314/cicada3301`` and ``Dukotah/cicada3301`` ``liber-primus/PROBLEM.json``

Note on glyphs: the project spec's draft table listed ᛡ at 26 and ᛠ at both 27 and 28.
Every source agrees on 26 = ᚣ (Y), 27 = ᛡ (IA/IO), 28 = ᛠ (EA); this module uses that order.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from runeforge.primes import is_prime

__all__ = [
    "DEFAULT_RULES",
    "LATIN",
    "PRIMES",
    "RUNES",
    "TABLE",
    "N",
    "TransliterationRules",
    "gp_sum",
    "idx_to_latin",
    "idx_to_prime",
    "idx_to_rune",
    "indices_to_latin",
    "indices_to_runes",
    "is_prime",
    "normalize_glyphs",
    "rune_to_idx",
    "runes_to_indices",
    "transliterate_english",
    "transliterate_words",
]


@dataclass(frozen=True)
class RuneInfo:
    idx: int
    rune: str
    latin: str  # canonical transliteration
    prime: int
    aliases: tuple[str, ...] = ()  # other Latin spellings the same rune stands for


TABLE: tuple[RuneInfo, ...] = (
    RuneInfo(0, "ᚠ", "F", 2),
    RuneInfo(1, "ᚢ", "U", 3, ("V",)),
    RuneInfo(2, "ᚦ", "TH", 5),
    RuneInfo(3, "ᚩ", "O", 7),
    RuneInfo(4, "ᚱ", "R", 11),
    RuneInfo(5, "ᚳ", "C", 13, ("K",)),
    RuneInfo(6, "ᚷ", "G", 17),
    RuneInfo(7, "ᚹ", "W", 19),
    RuneInfo(8, "ᚻ", "H", 23),
    RuneInfo(9, "ᚾ", "N", 29),
    RuneInfo(10, "ᛁ", "I", 31),
    RuneInfo(11, "ᛄ", "J", 37),
    RuneInfo(12, "ᛇ", "EO", 41),
    RuneInfo(13, "ᛈ", "P", 43),
    RuneInfo(14, "ᛉ", "X", 47),
    RuneInfo(15, "ᛋ", "S", 53, ("Z",)),
    RuneInfo(16, "ᛏ", "T", 59),
    RuneInfo(17, "ᛒ", "B", 61),
    RuneInfo(18, "ᛖ", "E", 67),
    RuneInfo(19, "ᛗ", "M", 71),
    RuneInfo(20, "ᛚ", "L", 73),
    RuneInfo(21, "ᛝ", "NG", 79, ("ING",)),
    RuneInfo(22, "ᛟ", "OE", 83),
    RuneInfo(23, "ᛞ", "D", 89),
    RuneInfo(24, "ᚪ", "A", 97),
    RuneInfo(25, "ᚫ", "AE", 101),
    RuneInfo(26, "ᚣ", "Y", 103),
    RuneInfo(27, "ᛡ", "IA", 107, ("IO",)),
    RuneInfo(28, "ᛠ", "EA", 109),
)

N: int = len(TABLE)  # 29
RUNES: str = "".join(r.rune for r in TABLE)
LATIN: tuple[str, ...] = tuple(r.latin for r in TABLE)
PRIMES: tuple[int, ...] = tuple(r.prime for r in TABLE)

_RUNE_TO_IDX: dict[str, int] = {r.rune: r.idx for r in TABLE}
_PRIMES_ARR = np.array(PRIMES, dtype=np.int64)

# Codepoint variants used by some transcriptions for the same rune. U+16C2 (ᛂ) for GER/J
# is a typeface convention, not a different reading (Dukotah CONFLICTS-B C-03).
GLYPH_VARIANTS: dict[str, str] = {"ᛂ": "ᛄ"}


def normalize_glyphs(text: str) -> str:
    """Map known codepoint variants onto the canonical glyphs."""
    return "".join(GLYPH_VARIANTS.get(c, c) for c in text)


def is_rune(ch: str) -> bool:
    return ch in _RUNE_TO_IDX


def rune_to_idx(rune: str) -> int:
    try:
        return _RUNE_TO_IDX[GLYPH_VARIANTS.get(rune, rune)]
    except KeyError:
        raise ValueError(f"not a Gematria Primus rune: {rune!r}") from None


def idx_to_rune(idx: int) -> str:
    return TABLE[_check_idx(idx)].rune


def idx_to_latin(idx: int) -> str:
    return TABLE[_check_idx(idx)].latin


def idx_to_prime(idx: int) -> int:
    return TABLE[_check_idx(idx)].prime


def _check_idx(idx: int) -> int:
    i = int(idx)
    if not 0 <= i < N:
        raise ValueError(f"rune index out of range 0..28: {idx}")
    return i


def runes_to_indices(text: str) -> np.ndarray:
    """Indices of every rune in ``text``; everything that is not a rune is ignored."""
    text = normalize_glyphs(text)
    return np.array([_RUNE_TO_IDX[c] for c in text if c in _RUNE_TO_IDX], dtype=np.int64)


def indices_to_runes(indices: Iterable[int]) -> str:
    return "".join(RUNES[_check_idx(i)] for i in indices)


def indices_to_latin(indices: Iterable[int], sep: str = "") -> str:
    return sep.join(LATIN[_check_idx(i)] for i in indices)


def gp_sum(indices: Iterable[int]) -> int:
    """Sum of the Gematria Primus prime values of the given rune indices."""
    arr = np.asarray(list(indices) if not isinstance(indices, np.ndarray) else indices)
    if arr.size == 0:
        return 0
    if arr.min() < 0 or arr.max() >= N:
        raise ValueError("rune index out of range 0..28")
    return int(_PRIMES_ARR[arr].sum())


# --------------------------------------------------------------------------- transliteration


@dataclass(frozen=True)
class TransliterationRules:
    """Data-driven English -> rune spelling rules.

    ``substitutions`` are applied in order to each upper-cased word before matching;
    ``graphemes`` are then matched greedily (longest first) left to right *within* the
    word. Matching never crosses a word boundary. Phase 2 tests alternative rule sets
    by constructing variants of this object.
    """

    substitutions: tuple[tuple[str, str], ...]
    graphemes: tuple[tuple[str, int], ...]

    def ordered_graphemes(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self.graphemes, key=lambda g: -len(g[0])))


def _default_graphemes() -> tuple[tuple[str, int], ...]:
    out: list[tuple[str, int]] = []
    for r in TABLE:
        out.append((r.latin, r.idx))
        # V/K/Z are handled by substitution; the multi-letter aliases are graphemes.
        out.extend((a, r.idx) for a in r.aliases if len(a) > 1)
    return tuple(out)


# The spellings the solved pages use: BOOC (K->C), CNOW, YOV, CWESTIAN (QU->CW),
# THNGS (ING->NG rune), FVNCTIAN (IO->IA rune).
DEFAULT_RULES = TransliterationRules(
    substitutions=(("QU", "CW"), ("Q", "C"), ("K", "C"), ("V", "U"), ("Z", "S")),
    graphemes=_default_graphemes(),
)


def _words(text: str) -> list[str]:
    words, cur = [], []
    for ch in text.upper():
        if "A" <= ch <= "Z":
            cur.append(ch)
        elif cur:
            words.append("".join(cur))
            cur = []
    if cur:
        words.append("".join(cur))
    return words


def transliterate_word(word: str, rules: TransliterationRules = DEFAULT_RULES) -> list[int]:
    w = word.upper()
    for old, new in rules.substitutions:
        w = w.replace(old, new)
    graphemes = rules.ordered_graphemes()
    out: list[int] = []
    i = 0
    while i < len(w):
        for latin, idx in graphemes:
            if w.startswith(latin, i):
                out.append(idx)
                i += len(latin)
                break
        else:
            raise ValueError(f"cannot transliterate {w[i]!r} in {word!r}")
    return out


def transliterate_words(text: str, rules: TransliterationRules = DEFAULT_RULES) -> list[list[int]]:
    """English text -> list of words, each a list of rune indices."""
    return [transliterate_word(w, rules) for w in _words(text)]


def transliterate_english(text: str, rules: TransliterationRules = DEFAULT_RULES) -> list[int]:
    """English text -> flat list of rune indices (word boundaries dropped)."""
    return [i for w in transliterate_words(text, rules) for i in w]


def as_indices(x: Sequence[int] | np.ndarray | str) -> np.ndarray:
    """Coerce runes, a Latin keyword or an index sequence to an int64 index array."""
    if isinstance(x, str):
        if any(is_rune(c) or c in GLYPH_VARIANTS for c in x):
            return runes_to_indices(x)
        return np.array(transliterate_english(x), dtype=np.int64)
    arr = np.asarray(x, dtype=np.int64)
    if arr.size and (arr.min() < 0 or arr.max() >= N):
        raise ValueError("rune index out of range 0..28")
    return arr
