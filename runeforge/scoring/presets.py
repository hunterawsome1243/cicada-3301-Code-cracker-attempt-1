"""Named, reproducible scorers.

A lane, a calibration and a control must all use exactly the same model, so scorers are
referred to by name and rebuilt deterministically from pinned training data. Each preset
records what it was trained on, because a positive control planted on text the scorer
was trained on overstates power: ``check_held_out`` refuses that combination.

Phase 1 baselines (order-3 Witten-Bell n-grams); Phase 2 adds the Kneser-Ney model here.

* ``lp-ngram3``      all nine solved sections' plaintext (always available, tiny)
* ``lp-ngram3-heldout``  the solved sections except A KOAN (1) and THE LOSS OF DIVINITY,
                     so those two (1,533 runes) can host controls without a corpus build
* ``cicada-ngram3``  corpus ``cicada-english`` (Emerson; scripts/build_corpus.py)
* ``general-ngram3`` corpus ``english-general`` (Moby-Dick)
* ``latin-ngram3``, ``old-english-ngram3``  corpora ``latin`` (Caesar) and ``old-english``
                     (Beowulf): the non-English registers of every decode's stats
"""

from __future__ import annotations

from functools import lru_cache

from runeforge.scoring.ngram import NGramScorer

PRESETS: dict[str, dict] = {
    "lp-ngram3": {"order": 3, "train": ["lp-solved"]},
    "lp-ngram3-heldout": {
        "order": 3,
        "train": ["lp-solved"],
        "exclude": ["a-koan-1", "the-loss-of-divinity"],
    },
    "cicada-ngram3": {"order": 3, "train": ["cicada-english"]},
    "general-ngram3": {"order": 3, "train": ["english-general"]},
    # non-English registers, for the per-decode stats (runeforge.stats.decode)
    "latin-ngram3": {"order": 3, "train": ["latin"]},
    "old-english-ngram3": {"order": 3, "train": ["old-english"]},
}
DECODERS = ("rigid",)  # Phase 2 adds the skip-aware beam presets


def names() -> list[str]:
    return list(PRESETS)


def _training_sequences(source: str, exclude: tuple[str, ...] = ()) -> list:
    if source == "lp-solved":
        from runeforge import canon

        return [s.plain for s in canon.load_solved_sections() if s.id not in exclude]
    from runeforge import corpus

    c = corpus.load(source)
    return [c.runes]


@lru_cache(maxsize=8)
def get(name: str) -> NGramScorer:
    """The fitted scorer for a preset name (cached per process)."""
    if name not in PRESETS:
        raise KeyError(f"unknown scorer preset {name!r}; known: {', '.join(PRESETS)}")
    spec = PRESETS[name]
    exclude = tuple(spec.get("exclude", ()))
    seqs = [s for src in spec["train"] for s in _training_sequences(src, exclude)]
    return NGramScorer(spec["order"]).fit(seqs)


def split_preset(preset: str) -> tuple[str, str]:
    """'lp-ngram3:rigid' -> ('lp-ngram3', 'rigid')."""
    scorer, _, decoder = preset.partition(":")
    decoder = decoder or "rigid"
    if scorer not in PRESETS or decoder not in DECODERS:
        raise KeyError(f"unknown preset {preset!r} (scorers {names()}, decoders {DECODERS})")
    return scorer, decoder


def check_corpus_name(name: str) -> None:
    """A plant source names a corpus, never a path: 'corpus:./lp-solved' would load the
    scorer's own training text past check_held_out."""
    from runeforge import corpus

    if name not in corpus.names():
        raise ValueError(f"unknown corpus {name!r}; one of {sorted(corpus.names())}")


def _check_not_a_copy(name: str, trained_on: list[str]) -> None:
    """The same text under another corpus name is still training text."""
    from runeforge import corpus

    sha = corpus.load(name).meta.get("indices_sha256")
    for src in trained_on:
        if src in corpus.names() and corpus.load(src).meta.get("indices_sha256") == sha:
            raise ValueError(f"corpus {name!r} has the same runes as training corpus {src!r}")


def check_held_out(scorer: str, plant_source: str) -> None:
    """Refuse a control whose planted plaintext is part of the scorer's training data."""
    trained_on = PRESETS[scorer]["train"]
    excluded = PRESETS[scorer].get("exclude", [])
    base, _, name = plant_source.partition(":")
    if base == "corpus":
        check_corpus_name(name)
        _check_not_a_copy(name, trained_on)
    elif base != "solved":
        raise ValueError(f"plant source must be 'solved[:<id>]' or 'corpus:<name>', got {base!r}")
    family = "lp-solved" if base == "solved" else name
    if base == "solved" and name and name in excluded:
        return
    if family in trained_on:
        raise ValueError(
            f"control plaintext {plant_source!r} is in the training data of {scorer!r} "
            f"({trained_on}); plant on held-out text or the control overstates power"
        )
