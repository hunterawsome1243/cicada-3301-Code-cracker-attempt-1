"""Transliterated text corpora: rune indices plus a word id per rune.

Gates, positive controls and scorers all need plaintext in rune space, and they must all
draw it from the same pinned, reproducible streams or their numbers are not comparable.
``scripts/build_corpus.py`` builds every corpus offline from SHA-256-pinned vendored texts
(and the canon's solved sections) into ``data/corpora/<name>.npz`` plus ``index.json``;
this module only reads them. Nothing here touches the network or ``data/raw``.

    from runeforge import corpus
    c = corpus.load("cicada-english")             # Corpus(runes, word_ids, meta)
    plain, words = corpus.english_stream(12956)    # exactly n runes, word ids from 0
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from runeforge.gematria import N
from runeforge.paths import CORPORA_DIR

INDEX_FILE = "index.json"
BUILD_HINT = (
    "run `python scripts/build_corpus.py` "
    "(it reads the vendored texts under data/raw; fetch them with scripts/fetch_raw.sh)"
)


class CorpusMissingError(FileNotFoundError):
    """A corpus file has not been built (or the corpora directory does not exist)."""


@dataclass(frozen=True)
class Corpus:
    runes: np.ndarray  # int64 rune indices 0..28 (read-only)
    word_ids: np.ndarray  # int64, non-decreasing, one per rune (read-only)
    meta: dict  # the corpus' index.json entry: register, language, sources, rules, ...

    @property
    def name(self) -> str:
        return self.meta["name"]

    @property
    def n_words(self) -> int:
        return int(self.meta["n_words"])

    def __len__(self) -> int:
        return int(self.runes.size)


def _dir(corpora_dir: Path | None) -> Path:
    return Path(corpora_dir) if corpora_dir is not None else CORPORA_DIR


def corpus_path(name: str, corpora_dir: Path | None = None) -> Path:
    return _dir(corpora_dir) / f"{name}.npz"


def names(corpora_dir: Path | None = None) -> list[str]:
    """Names of the corpora that have been built (from index.json, else the .npz files)."""
    d = _dir(corpora_dir)
    index = d / INDEX_FILE
    if index.exists():
        built = json.loads(index.read_text(encoding="utf-8"))["corpora"]
        return sorted(n for n in built if (d / f"{n}.npz").exists())
    return sorted(p.stem for p in d.glob("*.npz")) if d.is_dir() else []


@lru_cache(maxsize=16)
def _load(path: str, _mtime_ns: int) -> Corpus:
    with np.load(path, allow_pickle=False) as z:
        runes = z["runes"].astype(np.int64)
        word_ids = z["word_ids"].astype(np.int64)
        meta = json.loads(str(z["meta"]))
    if runes.shape != word_ids.shape or runes.ndim != 1:
        raise ValueError(f"{path}: runes and word_ids differ in shape")
    if runes.size and (runes.min() < 0 or runes.max() >= N):
        raise ValueError(f"{path}: rune index out of range 0..28")
    if word_ids.size > 1 and (np.diff(word_ids) < 0).any():
        raise ValueError(f"{path}: word ids are not non-decreasing")
    if meta.get("n_runes") != int(runes.size):
        raise ValueError(f"{path}: n_runes {meta.get('n_runes')} != {runes.size} stored runes")
    runes.setflags(write=False)
    word_ids.setflags(write=False)
    return Corpus(runes, word_ids, meta)


def load(name: str, corpora_dir: Path | None = None) -> Corpus:
    """The built corpus ``name``. Raises :class:`CorpusMissingError` with the build hint."""
    path = corpus_path(name, corpora_dir)
    if not path.exists():
        have = names(corpora_dir)
        raise CorpusMissingError(
            f"corpus {name!r} is not built ({path} missing); {BUILD_HINT}. "
            f"Built: {', '.join(have) if have else 'none'}."
        )
    return _load(str(path), path.stat().st_mtime_ns)


def english_stream(
    n: int, name: str = "cicada-english", offset: int = 0, corpora_dir: Path | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Exactly ``n`` runes of corpus ``name`` from rune ``offset``, with word ids rebased to 0.

    Returns writable copies. The cut may split a word at either end, as murphy's
    ``english_stream`` does. Raises ``ValueError`` if the corpus is shorter than
    ``offset + n``.
    """
    if n <= 0 or offset < 0:
        raise ValueError(f"need n > 0 and offset >= 0 (got n={n}, offset={offset})")
    c = load(name, corpora_dir)
    if offset + n > len(c):
        raise ValueError(
            f"corpus {name!r} has {len(c):,} runes; offset {offset:,} + n {n:,} does not fit"
        )
    runes = c.runes[offset : offset + n].copy()
    word_ids = c.word_ids[offset : offset + n] - c.word_ids[offset]
    return runes, word_ids
