"""The oracle (Rule 3: hits must survive the oracle).

A candidate is a hit only if

  (a) every claimed page scores above the family-wise bar for the lane's trial count
      (and above a size-matched shuffle null),
  (b) the claim decodes ENTIRE pages -- no fragments -- and at least ``min_pages`` of them,
  (c) the rig still reproduces every solved section through the same decode path,
  (d) the decoded plaintext re-enciphers to the canonical runes, rune for rune.

Semantics follow Dukotah/cicada3301 ``verify_solution.py``: re-derive the known solves
first and refuse to judge if that fails; require multiple pages; beat a shuffle null.
The pass/fail bar is the higher of the family-wise bar and ``floor``. An oracle PASS is
one step of HIT_PROTOCOL.md, not a solve.

    python -m runeforge.oracle --selftest
    python -m runeforge.oracle --key-module key.py [--pages 10] [--n-trials N] [--json out.json]
    python -m runeforge.oracle --keystream keys.txt
    python -m runeforge.oracle --regression
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from runeforge import canon
from runeforge.gematria import N, indices_to_latin
from runeforge.interrupts import decode_skip_known, encrypt_with_interrupts
from runeforge.scoring.calibration import gaussian_max_bar, null_scores, shuffle_null
from runeforge.transforms import StreamSubtract, from_method, from_spec

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


def reencipher_matches(
    claim: Claim, decoded: Mapping[int, np.ndarray], cipher_pages: Mapping[int, np.ndarray]
) -> bool:
    """Rule 3(d): encrypt the decoded plaintext forward with the claimed key and interrupt
    positions; the result must equal the canonical ciphertext of every claimed page."""
    t = _transform(claim.method)
    if claim.key_scope == "per_page":
        return all(
            np.array_equal(
                encrypt_with_interrupts(decoded[n], t, claim.interrupts.get(n, [])),
                cipher_pages[n],
            )
            for n in claim.pages
        )
    lengths = [cipher_pages[n].size for n in claim.pages]
    offsets = np.cumsum([0, *lengths])
    plain = np.concatenate([decoded[n] for n in claim.pages])
    inter = [offsets[k] + i for k, n in enumerate(claim.pages) for i in claim.interrupts.get(n, [])]
    cipher = np.concatenate([cipher_pages[n] for n in claim.pages])
    return np.array_equal(encrypt_with_interrupts(plain, t, inter), cipher)


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
        "reencipher": reencipher_matches(claim, decoded, cipher_pages),
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


# --------------------------------------------------------------------------- CLI


def default_scorer() -> Scorer:
    """The registered Phase 1 scorer: a 3-gram over all nine solved sections' plaintext.
    Deterministic and always available; Phase 2's calibrated model replaces it."""
    from runeforge.scoring import NGramScorer

    return NGramScorer(3).fit([s.plain for s in canon.load_solved_sections()])


def load_key_module(path: str | Path, n: int) -> np.ndarray:
    """A claim's key module exposes ``keystream(n) -> list[int]`` (values 0..28) and
    records how the key was made (HIT_PROTOCOL.md section 5)."""
    spec = importlib.util.spec_from_file_location("candidate_key", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load key module {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "keystream"):
        raise SystemExit(f"{path} must expose keystream(n) -> list[int] (values 0..28)")
    return _check_keys(np.asarray(list(mod.keystream(n)), dtype=np.int64), n, str(path))


def load_keystream_file(path: str | Path, n: int) -> np.ndarray:
    """Whitespace- or comma-separated integers 0..28."""
    text = Path(path).read_text(encoding="utf-8").replace(",", " ")
    return _check_keys(np.array([int(t) for t in text.split()], dtype=np.int64), n, str(path))


def _check_keys(keys: np.ndarray, n: int, where: str) -> np.ndarray:
    if keys.size < n:
        raise SystemExit(f"{where}: keystream has {keys.size:,} symbols; the claim needs {n:,}")
    bad = keys[(keys < 0) | (keys >= N)]
    if bad.size:
        raise SystemExit(f"{where}: {bad.size} values outside 0..28 (first: {bad[0]})")
    return keys


def _print_verdict(v: Verdict) -> None:
    for r in v.pages:
        print(
            f"  page {r['page']:2d}  n={r['n_runes']:3d}  score {r['score']:7.3f}"
            f"  bar {r['bar']:7.3f}"
            f"  shuffle max {r['shuffle_max']:7.3f}  {'ABOVE BAR' if r['above_bar'] else ''}"
        )
    for name, ok in v.criteria.items():
        print(f"  {name:16s} {'PASS' if ok else 'FAIL'}")
    for note in v.notes:
        print(f"  note: {note}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m runeforge.oracle",
        description="Rule 3 oracle: regression, full pages, family-wise bar, shuffle null, "
        "re-encipherment. numbering: LP2-0-57.",
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true", help="plant a key; PASS it, FAIL a wrong one")
    g.add_argument("--key-module", help=".py exposing keystream(n) -> list[int]")
    g.add_argument("--keystream", help="file of integers 0..28")
    g.add_argument("--regression", action="store_true", help="only re-derive the solved sections")
    ap.add_argument("--pages", type=int, default=10, help="first N rune-bearing unsolved pages")
    ap.add_argument("--key-scope", choices=("continuous", "per_page"), default="continuous")
    ap.add_argument("--n-trials", type=int, default=1, help="trials of the lane that produced it")
    ap.add_argument("--json", help="write the verdict here")
    a = ap.parse_args(argv)

    if a.regression:
        failures = regression_failures()
        print(f"regression: {'PASS' if not failures else 'FAIL ' + ', '.join(failures)}")
        return 0 if not failures else 2

    if a.selftest:
        r = selftest()
        for name in ("correct", "wrong"):
            print(f"{name} key -> {r[name].status}")
            _print_verdict(r[name])
        verdict = "PASS" if r["passed"] else "FAIL"
        out = {"selftest": verdict, **{k: asdict(r[k]) for k in ("correct", "wrong")}}
        code = 0 if r["passed"] else 2
        line = f"ORACLE SELF-TEST: {verdict}"
    else:
        lp2 = canon.load_lp2()
        pages = [n for n in canon.UNSOLVED_LP2_PAGES if lp2.page(n).n_runes][: a.pages]
        cipher_pages = {n: lp2.page(n).runes for n in pages}
        need = sum(c.size for c in cipher_pages.values())
        if a.key_scope == "per_page":
            need = max(c.size for c in cipher_pages.values())
        keys = (
            load_key_module(a.key_module, need)
            if a.key_module
            else load_keystream_file(a.keystream, need)
        )
        claim = Claim(
            lane_id=Path(a.key_module or a.keystream).stem,
            method=StreamSubtract(keys[:need]).spec(),
            pages=pages,
            n_trials=a.n_trials,
            key_scope=a.key_scope,
        )
        v = verify(claim, default_scorer())
        print(
            f"claim {claim.lane_id}: {len(pages)} pages, key scope {a.key_scope}, N={a.n_trials:,}"
        )
        _print_verdict(v)
        verdict = (
            "PASS" if v.passed else ("REGRESSION BROKEN" if v.status == "rig-broken" else "FAIL")
        )
        out = {"verdict": verdict, "numbering": canon.LP2_NUMBERING, **asdict(v)}
        code = 0 if v.passed else (2 if v.status == "rig-broken" else 1)
        line = f"ORACLE: {verdict}"
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
