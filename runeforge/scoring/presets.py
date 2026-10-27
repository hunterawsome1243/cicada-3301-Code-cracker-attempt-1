"""Named, reproducible scorers.

A lane, a calibration and a control must all use exactly the same model, so scorers are
referred to by name and rebuilt deterministically from pinned training data. Each preset
records what it was trained on, because a positive control planted on text the scorer
was trained on overstates power: ``check_held_out`` refuses that combination.

Phase 1 baselines (order-3 Witten-Bell n-grams); Phase 2 adds the Kneser-Ney model here.
A preset is ``<scorer>:<decoder>``; the decoders are listed in ``DECODERS`` below.

* ``lp-ngram3``      all nine solved sections' plaintext (always available, tiny)
* ``lp-ngram3-heldout``  the solved sections except A KOAN (1) and THE LOSS OF DIVINITY,
                     so those two (1,533 runes) can host controls without a corpus build
* ``cicada-ngram3``  corpus ``cicada-english`` (Emerson; scripts/build_corpus.py)
* ``general-ngram3`` corpus ``english-general`` (Moby-Dick)
* ``latin-ngram3``, ``old-english-ngram3``  corpora ``latin`` (Caesar) and ``old-english``
                     (Beowulf): the non-English registers of every decode's stats

Phase 2 (``model: "kn"``, docs/kn-scorer-design.md section 3): interpolated modified
Kneser-Ney presets ``kn4-lp-heldout``, ``kn4-cicada``, ``kn5-cicada`` (dense: every level a
complete table, so they pair with the beam decoders too), ``kn6-cicada``, ``kn8-cicada``,
``kn8-general``, ``kn8-latin``, ``kn8-old-english``, ``kn8-vowel-dropped`` (order 6/8, four
dense levels and sorted sparse tables above: rigid decoder only) and ``kn8-cicada-wb`` (the
word-boundary model: adjudication and reports only, refused by ``split_preset`` with every
decoder). A corpus-trained KN preset trains on the words ``[0, floor(0.9 * n_words))`` of its
corpus (``SPLITS``, pinned to the built corpus and checked at ``get``); the tail is the
held-out text of its plants (``heldout_stream``). ``beam_compatible(name)`` says which
presets take a beam decoder; ``scripts/export_kn.py --preset <name>`` writes a KN preset's
``knx-1`` table and manifest (``reports/kn-export/``) and proves them against the scorer.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from runeforge.scoring.kn import KNScorer
from runeforge.scoring.ngram import NGramScorer

# The 90/10 word split of every corpus a KN preset trains on: train_words = floor(0.9 *
# n_words), pinned to the built corpus (its word count and indices_sha256 from
# data/corpora/index.json). A rebuilt corpus that moved the split is refused at get(), never
# silently refit. vowel-dropped-english is derived from english-general and shares its word
# ids, so the two splits cut the same words.
SPLIT_RULE = "words [0, floor(0.9*n_words)) train"
SPLITS: dict[str, dict] = {
    "cicada-english": {
        "rule": SPLIT_RULE,
        "train_words": 67322,
        "n_words": 74803,
        "indices_sha256": "6786ad18d89ee6ce3116690a9b0ba6bb2e1076d7ad154e77ff607b0799ae3281",
    },
    "english-general": {
        "rule": SPLIT_RULE,
        "train_words": 193211,
        "n_words": 214679,
        "indices_sha256": "50841fea4eb7285f3670f655818e61623e6c792bd219ad9ae82fb192dadd1a3a",
    },
    "latin": {
        "rule": SPLIT_RULE,
        "train_words": 18464,
        "n_words": 20516,
        "indices_sha256": "2336a3cc122176b0d46dc324842995b94b0523a2105b6dfa4849c0f42500746c",
    },
    "old-english": {
        "rule": SPLIT_RULE,
        "train_words": 17380,
        "n_words": 19312,
        "indices_sha256": "93e666cb9d42c07bf7ea5ac1964919fd6013997b91d91c19dc48a7a0786fbcd9",
    },
    "vowel-dropped-english": {
        "rule": SPLIT_RULE,
        "train_words": 193211,
        "n_words": 214679,
        "indices_sha256": "f3d872dea69e6fab0fb0faf03f0d219448594b70521fc988e99c84f8c6b48b5d",
    },
}
BOUNDARY = 29  # the word-boundary symbol of a wb model (base 30)


def _kn(order: int, dense_levels: int, corpus_name: str, boundary: int | None = None) -> dict:
    return {
        "model": "kn",
        "order": order,
        "dense_levels": dense_levels,
        "train": [corpus_name],
        "split": SPLITS[corpus_name],
        "boundary": boundary,
    }


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
    # Phase 2 Kneser-Ney (docs/kn-scorer-design.md section 3); model "ngram" is the default
    "kn4-lp-heldout": {
        "model": "kn",
        "order": 4,
        "dense_levels": 4,
        "train": ["lp-solved"],
        "exclude": ["a-koan-1", "the-loss-of-divinity"],
        "boundary": None,
    },
    "kn4-cicada": _kn(4, 4, "cicada-english"),
    "kn5-cicada": _kn(5, 5, "cicada-english"),
    "kn6-cicada": _kn(6, 4, "cicada-english"),
    "kn8-cicada": _kn(8, 4, "cicada-english"),
    "kn8-general": _kn(8, 4, "english-general"),
    "kn8-latin": _kn(8, 4, "latin"),
    "kn8-old-english": _kn(8, 4, "old-english"),
    "kn8-vowel-dropped": _kn(8, 4, "vowel-dropped-english"),
    "kn8-cicada-wb": _kn(8, 4, "cicada-english", boundary=BOUNDARY),
}
DECODERS = ("rigid", "beam", "beam-skip", "beam-skip-int")
# The beam decoders' transition model (runeforge.beam.BeamModel), fixed per decoder NAME: the
# beam calibrations (staged in reports/calib-staging/, installed under scoring/calib/presets/ by
# TOOLBOX_REQUESTS.md TR-1) and every control's evidence were measured with exactly these
# values, and neither records them in the lane spec, so a change is a new name
# (tests/test_beam.py pins them). Pick the one that matches the lane's forward model (its
# filter_model and interrupt_prob); the lane's own p_keep / interrupt_prob drive its plants and
# gate, the decoder's priors stay these:
#   beam           F-interrupters only (spec section 2.4 beam(scorer, width)): every canonical F
#                  is an interrupt-or-not choice; filter_model off
#   beam-skip      the anti-repeat filter's key skips only, no interrupters: the template lane's
#                  family, which passes the fingerprint gate cleanly (interrupt rates 0.1 and
#                  0.44 pass marginally, 1.0 fails: LP2 0-55 holds 458 F's against 447 uniform;
#                  reports/beam_decoder.md section 3)
#   beam-skip-int  both: pipeline.encrypt's model, truncated at max_skip drops per rune
# interrupt_prob 15/16: every plaintext F in the keyed solved sections is an interrupter
# (14 of 14), so the rule of succession gives (14 + 1) / (14 + 2). It is kept below 1 so a
# path that deciphers a plaintext F pays 4 bits rather than dying (a wrong key's beam would
# otherwise run out of paths). p_keep 0.19 is LP2's 86 / 447 doublets. max_skip 6: more drops at
# one rune has probability ~(0.81/29)**7 ~ 1e-11 per rune under a uniform key (runeforge.beam).
# width 8: the anti-repeat planted-key control (beam-skip, L = 240) recovers the same at widths
# 4, 8 and 16 and the null barely moves with it (scripts/beam_power.py, section width); the keyed
# solved sections decode exactly at widths 4-16 too (tests/test_beam.py covers 4 and 8).
DECODER_PARAMS: dict[str, dict] = {
    "rigid": {},
    "beam": {"width": 8, "interrupt_prob": 15 / 16, "p_keep": None, "max_skip": 0},
    "beam-skip": {"width": 8, "interrupt_prob": 0.0, "p_keep": 0.19, "max_skip": 6},
    "beam-skip-int": {"width": 8, "interrupt_prob": 15 / 16, "p_keep": 0.19, "max_skip": 6},
}


def names() -> list[str]:
    return list(PRESETS)


def _training_sequences(source: str, exclude: tuple[str, ...] = ()) -> list:
    if source == "lp-solved":
        from runeforge import canon

        return [s.plain for s in canon.load_solved_sections() if s.id not in exclude]
    from runeforge import corpus

    c = corpus.load(source)
    return [c.runes]


def model_of(name: str) -> str:
    """'ngram' (Phase 1 Witten-Bell) or 'kn' (Phase 2 Kneser-Ney)."""
    return PRESETS[name].get("model", "ngram")


def is_wb(name: str) -> bool:
    return PRESETS[name].get("boundary") is not None


def beam_compatible(name: str) -> bool:
    """Whether the preset exposes dense (29**i, 29) tables for the beam decoders: every ngram
    preset; a KN preset iff B == 29 and every level is dense (D == n)."""
    spec = PRESETS[name]
    if spec.get("model", "ngram") == "ngram":
        return True
    return spec.get("boundary") is None and spec["dense_levels"] == spec["order"]


def dense_presets() -> list[str]:
    return [n for n in PRESETS if beam_compatible(n)]


def _check_split(corpus_name: str):
    """The built corpus must still be the one the split was pinned to."""
    from runeforge import corpus

    if corpus_name not in SPLITS:
        raise KeyError(f"no held-out split is defined for corpus {corpus_name!r}")
    split = SPLITS[corpus_name]
    c = corpus.load(corpus_name)
    want = (9 * c.n_words) // 10
    sha = c.meta.get("indices_sha256")
    if c.n_words != split["n_words"] or want != split["train_words"]:
        raise ValueError(
            f"corpus {corpus_name!r} has {c.n_words} words (floor(0.9 n) = {want}) but the "
            f"pinned split says {split['n_words']} / {split['train_words']}: the corpus was "
            "rebuilt and the split moved; re-pin SPLITS deliberately, never refit silently"
        )
    if sha != split["indices_sha256"]:
        raise ValueError(
            f"corpus {corpus_name!r} indices_sha256 {sha} != the pinned {split['indices_sha256']}"
        )
    return c, split


def training_slice(corpus_name: str) -> tuple[np.ndarray, np.ndarray]:
    """(runes, word_ids) of the training words ``[0, train_words)`` of a corpus: one
    contiguous prefix of the stream."""
    c, split = _check_split(corpus_name)
    n = int(np.searchsorted(c.word_ids, split["train_words"]))
    return c.runes[:n], c.word_ids[:n]


def heldout_stream(corpus_name: str) -> tuple[np.ndarray, np.ndarray]:
    """(runes, word_ids rebased to 0) of the held-out tail (words >= train_words): the plant
    text of every KN preset trained on ``corpus_name`` (and of a corpus derived from it)."""
    c, split = _check_split(corpus_name)
    n = int(np.searchsorted(c.word_ids, split["train_words"]))
    return c.runes[n:].copy(), c.word_ids[n:] - split["train_words"]


def _kn_sequences(spec: dict) -> list[np.ndarray]:
    """The training sequences of a KN preset: one per solved section for lp-solved; the
    training slice of a corpus; for a wb model every word boundary-marked
    (``[29] + runes(word)`` per word, one trailing 29)."""
    from runeforge.scoring import boundaries

    exclude = tuple(spec.get("exclude", ()))
    out = []
    for src in spec["train"]:
        if src == "lp-solved":
            out.extend(_training_sequences(src, exclude))
            continue
        runes, word_ids = training_slice(src)
        if spec.get("boundary") is None:
            out.append(runes)
        else:
            starts = boundaries.corpus_starts(word_ids)
            ext = np.full(runes.size + int(starts.sum()) + 1, spec["boundary"], dtype=np.int64)
            ext[np.arange(runes.size) + np.cumsum(starts)] = runes
            out.append(ext)
    return out


@lru_cache(maxsize=16)
def get(name: str) -> NGramScorer | KNScorer:
    """The fitted scorer for a preset name (cached per process)."""
    if name not in PRESETS:
        raise KeyError(f"unknown scorer preset {name!r}; known: {', '.join(PRESETS)}")
    spec = PRESETS[name]
    if spec.get("model", "ngram") == "ngram":
        exclude = tuple(spec.get("exclude", ()))
        seqs = [s for src in spec["train"] for s in _training_sequences(src, exclude)]
        return NGramScorer(spec["order"]).fit(seqs)
    from runeforge.scoring import kn_fit

    boundary = spec.get("boundary")
    seqs = _kn_sequences(spec)
    est = kn_fit.estimate(
        seqs,
        spec["order"],
        base=30 if boundary is not None else 29,
        dense_levels=spec["dense_levels"],
        boundary=boundary,
        pinned_discounts=spec.get("discounts"),
    )
    training = {
        "preset": name,
        "corpora": list(spec["train"]),
        "exclude": list(spec.get("exclude", [])),
        "split": spec.get("split"),
        "n_runes": est.n_runes,
        "n_sequences": len(seqs),
        "indices_sha256s": _training_shas(spec),
    }
    return KNScorer.from_estimate(est, training)


def _training_shas(spec: dict) -> dict:
    from runeforge import corpus

    out = {}
    for src in spec["train"]:
        if src != "lp-solved" and src in corpus.names():
            out[src] = corpus.load(src).meta.get("indices_sha256")
    return out


def split_preset(preset: str) -> tuple[str, str]:
    """'lp-ngram3:rigid' -> ('lp-ngram3', 'rigid'). A sparse KN scorer with a beam decoder
    and a wb scorer with any decoder are refused (docs/kn-scorer-design.md section 5)."""
    scorer, _, decoder = preset.partition(":")
    decoder = decoder or "rigid"
    if scorer not in PRESETS or decoder not in DECODERS:
        raise KeyError(f"unknown preset {preset!r} (scorers {names()}, decoders {DECODERS})")
    if is_wb(scorer):
        raise KeyError(
            f"preset {preset!r}: a word-boundary scorer is adjudication/report-only this phase "
            f"(its null depends on the window's word-start mask); no lane names it with any "
            f"decoder. The rigid decoder takes {[n for n in PRESETS if not is_wb(n)]}; the beam "
            f"decoders take the dense presets {dense_presets()}"
        )
    if decoder != "rigid" and not beam_compatible(scorer):
        raise KeyError(
            f"preset {preset!r}: {scorer} has sparse levels and no dense tables, so it pairs "
            f"with the rigid decoder only; the beam decoders take the dense presets "
            f"{dense_presets()}"
        )
    return scorer, decoder


def beam_model(decoder: str, combine: str = "vigenere", view: str = "raw"):
    """The ``runeforge.beam.BeamModel`` of a decoder name, or None for the rigid decoder."""
    if decoder not in DECODERS:
        raise KeyError(f"unknown decoder {decoder!r}; known: {DECODERS}")
    if decoder == "rigid":
        return None
    from runeforge.beam import BeamModel

    return BeamModel(combine=combine, view=view, **DECODER_PARAMS[decoder])


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


def _derived_family(name: str) -> set[str]:
    """A corpus and the one it was derived from (vowel-dropped-english is english-general's
    text with the same word ids) are one family: training on either covers the other."""
    from runeforge import corpus

    fam = {name}
    if name in corpus.names():
        parent = corpus.load(name).meta.get("derived_from")
        if parent:
            fam.add(parent)
    for other in corpus.names():
        if other != name and corpus.load(other).meta.get("derived_from") == name:
            fam.add(other)
    return fam


def check_held_out(scorer: str, plant_source: str) -> None:
    """Refuse a control whose planted plaintext is part of the scorer's training data.

    ``corpus:<name>`` is refused for every name in ``train`` and for a corpus derived from
    (or the parent of) one; ``solved:<id>`` passes only for an excluded section of an lp-solved
    scorer; ``heldout:<name>`` (the 90/10 tail of ``SPLITS``, TOOLBOX_REQUESTS.md TR-9) is held
    out of every KN preset with a pinned ``split`` by construction, and is refused for a preset
    that trains on the whole corpus (or its derived family): the Phase 1 ``ngram`` presets have
    no split, so the tail is their training text."""
    trained_on = PRESETS[scorer]["train"]
    excluded = PRESETS[scorer].get("exclude", [])
    base, _, name = plant_source.partition(":")
    if base == "corpus":
        check_corpus_name(name)
        _check_not_a_copy(name, trained_on)
        for src in trained_on:
            if src != name and src in _derived_family(name):
                raise ValueError(
                    f"corpus {name!r} is derived from (or the source of) training corpus "
                    f"{src!r} of {scorer!r}: the same words under another transliteration"
                )
    elif base == "heldout":
        check_corpus_name(name)
        if name not in SPLITS:
            raise ValueError(f"no held-out split is defined for corpus {name!r} (SPLITS)")
        fam = _derived_family(name)
        if any(src in fam for src in trained_on) and PRESETS[scorer].get("split") is None:
            raise ValueError(
                f"{scorer!r} trains on all of {name!r} (no 90/10 split; its training is "
                f"{trained_on}): the tail is training text; plant on another corpus or a "
                f"solved section"
            )
        return
    elif base != "solved":
        raise ValueError(
            "plant source must be 'solved[:<id>]', 'corpus:<name>' or 'heldout:<name>', "
            f"got {base!r}"
        )
    family = "lp-solved" if base == "solved" else name
    if base == "solved" and name and name in excluded:
        return
    if family in trained_on:
        raise ValueError(
            f"control plaintext {plant_source!r} is in the training data of {scorer!r} "
            f"({trained_on}); plant on held-out text or the control overstates power"
        )
