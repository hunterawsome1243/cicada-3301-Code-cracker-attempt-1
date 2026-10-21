"""The oracle (Rule 3: hits must survive the oracle).

A candidate is a hit only if

  (a) every claimed page scores above the family-wise bar for the lane's trial count
      (and above a size-matched shuffle null),
  (b) the claim decodes ENTIRE pages -- no fragments -- and at least ``min_pages`` of them,
  (c) the rig still reproduces every solved section through the same decode path.

Semantics follow Dukotah/cicada3301 ``verify_solution.py``: re-derive the known solves
first and refuse to judge if that fails; require multiple pages; beat a shuffle null.
The pass/fail bar is the higher of the family-wise bar and ``floor``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import numpy as np

from runeforge import canon
from runeforge.gematria import indices_to_latin
from runeforge.interrupts import decode_skip_known
from runeforge.scoring.calibration import gaussian_max_bar, null_scores, shuffle_null
from runeforge.transforms import from_method, from_spec

Scorer = Callable[[np.ndarray], float]


@dataclass
class Claim:
    """A claimed decryption of LP2 pages.

    ``method`` is a transform spec (``Transform.spec()`` / ``from_spec`` format, or a
    solved-section style ``{"steps": [...]}``). ``key_scope`` says whether the keystream
    restarts on every page or runs on across the claimed pages in order.
    """

    lane_id: str
    method: dict
    pages: list[int]
    interrupts: dict[int, list[int]] = field(default_factory=dict)
    n_trials: int = 1
    key_scope: str = "per_page"  # per_page | continuous


@dataclass
class Verdict:
    passed: bool
    status: str  # hit-verified | negative | rejected | rig-broken
    criteria: dict[str, bool]
    pages: list[dict]
    bar: float | None
    notes: list[str] = field(default_factory=list)


def regression_failures() -> list[str]:
    """Re-decode every solved section through the claim decode path; list failures."""
    failures = []
    for s in canon.load_solved_sections():
        out = decode_skip_known(s.cipher, from_method(s.method), s.interrupts)
        if not np.array_equal(out, s.plain):
            failures.append(s.id)
    return failures


def _transform(method: dict):
    return from_method(method) if "steps" in method and "type" not in method else from_spec(method)


def decode_claim(claim: Claim, cipher_pages: Mapping[int, np.ndarray]) -> dict[int, np.ndarray]:
    t = _transform(claim.method)
    if claim.key_scope == "per_page":
        return {
            n: decode_skip_known(cipher_pages[n], t, claim.interrupts.get(n, []))
            for n in claim.pages
        }
    if claim.key_scope != "continuous":
        raise ValueError("key_scope must be 'per_page' or 'continuous'")
    lengths = [cipher_pages[n].size for n in claim.pages]
    offsets = np.cumsum([0, *lengths])
    flat = np.concatenate([cipher_pages[n] for n in claim.pages])
    inter = [offsets[k] + i for k, n in enumerate(claim.pages) for i in claim.interrupts.get(n, [])]
    out = decode_skip_known(flat, t, inter)
    return {n: out[offsets[k] : offsets[k + 1]] for k, n in enumerate(claim.pages)}


def verify(
    claim: Claim,
    scorer: Scorer,
    cipher_pages: Mapping[int, np.ndarray] | None = None,
    min_pages: int = 2,
    floor: float | None = None,
    n_null: int = 200,
    null_margin: float = 0.0,
    seed: int = 3301,
) -> Verdict:
    """Judge a claim. ``cipher_pages`` defaults to the canon LP2 unsolved pages."""
    notes: list[str] = []
    broken = regression_failures()
    if broken:
        return Verdict(
            False,
            "rig-broken",
            {"regression": False},
            [],
            None,
            [f"solved sections no longer reproduce: {broken}"],
        )

    if cipher_pages is None:
        lp2 = canon.load_lp2()
        cipher_pages = {
            n: lp2.page(n).runes for n in canon.UNSOLVED_LP2_PAGES if lp2.page(n).n_runes
        }
    missing = [n for n in claim.pages if n not in cipher_pages]
    full_pages = not missing and len(set(claim.pages)) == len(claim.pages)
    if missing:
        notes.append(f"pages not available as full unsolved pages: {missing}")
    enough = len(set(claim.pages)) >= min_pages
    if not enough:
        notes.append(f"a hit needs at least {min_pages} independent pages")
    if not full_pages:
        return Verdict(
            False,
            "rejected",
            {"full_pages": False, "min_pages": enough, "regression": True},
            [],
            None,
            notes,
        )

    decoded = decode_claim(claim, cipher_pages)
    rows = []
    for n in claim.pages:
        plain = decoded[n]
        null = null_scores(scorer, plain.size, n=n_null, seed=seed + n)
        bar = gaussian_max_bar(
            float(null.mean()), float(null.std()), max(claim.n_trials, 2) * len(claim.pages)
        )
        if floor is not None:
            bar = max(bar, floor)
        shuf = shuffle_null(scorer, plain, n=n_null, seed=seed + n)
        score = scorer(plain)
        rows.append(
            {
                "page": n,
                "n_runes": int(plain.size),
                "score": score,
                "null_mean": float(null.mean()),
                "null_sd": float(null.std()),
                "bar": bar,
                "shuffle_max": float(shuf.max()),
                "above_bar": score >= bar,
                "beats_shuffle": score > float(shuf.max()) + null_margin,
                "preview": indices_to_latin(plain[:60]),
            }
        )
    criteria = {
        "regression": True,
        "full_pages": True,
        "min_pages": enough,
        "familywise_bar": all(r["above_bar"] for r in rows),
        "beats_shuffle": all(r["beats_shuffle"] for r in rows),
    }
    passed = all(criteria.values())
    return Verdict(
        passed,
        "hit-verified" if passed else "negative",
        criteria,
        rows,
        max(r["bar"] for r in rows),
        notes,
    )


def selftest(
    scorer_factory: Callable[[list[np.ndarray]], Scorer] | None = None, seed: int = 3301
) -> dict:
    """The oracle's own control: on synthetic pages enciphered from held-out solved
    plaintext, it must PASS the planted key and FAIL a wrong one."""
    from runeforge.scoring import NGramScorer
    from runeforge.transforms import StreamSubtract

    held_out = "a-koan-1"
    train = [s.plain for s in canon.load_solved_sections() if s.id != held_out]
    scorer = (scorer_factory or (lambda seqs: NGramScorer(3).fit(seqs)))(train)
    plain = canon.solved_section(held_out).plain
    rng = np.random.default_rng(seed)
    key = rng.integers(0, 29, 4096)
    true_t = StreamSubtract(key)
    pages = {k: true_t.encrypt(plain[k * 250 : (k + 1) * 250]) for k in range(3)}
    wrong = StreamSubtract(np.random.default_rng(seed + 1).integers(0, 29, 4096))
    out = {}
    for name, t in (("correct", true_t), ("wrong", wrong)):
        v = verify(
            Claim(f"selftest-{name}", t.spec(), [0, 1, 2], n_trials=10**6),
            scorer,
            cipher_pages=pages,
        )
        out[name] = v
    ok = out["correct"].passed and not out["wrong"].passed
    return {"passed": ok, "correct": out["correct"], "wrong": out["wrong"]}
