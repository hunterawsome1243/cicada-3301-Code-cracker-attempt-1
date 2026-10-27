#!/usr/bin/env python3
"""The scorer power harness (docs/kn-scorer-design.md section 6): nulls, bars and planted-key
power of every scorer preset, measured, and the report that publishes them.

    python scripts/scorer_power.py [--quick | --full | --smoke] [--workers 4] [--section NAME ...]
        [--out reports/scorer_power.json] [--fits-dir DIR] [--render-only]

Writes the JSON (``--out``) and renders the markdown next to it (``reports/scorer_power.md``
by default; line 1 "not a solve"; the banned-word list of scripts/check_results.py is run over
the text before it is written). Read-only with respect to lanes and the ledger: every family
runs on a toy LaneSpec in memory and nothing under lanes/ or ledger/ is read or written.

Scales (``--quick`` is the default; ``--smoke`` is what tests/test_scorer_power.py runs):

* quick   100,000 null draws per (scorer, L), 200 plants per cell, beam cells 50 plants x 99
          decoys, beam nulls 25,000, 2,000 wb masks; the fits go to reports/scorer_power/fits/
          marked ``scale: reduced`` and are never installable (TOOLBOX_REQUESTS.md TR-7).
* full    10^6 draws, 1,000 plants, 200-plant beam cells, 10^6-draw beam nulls; the records
          also go to reports/calib-staging/ (Hunter installs them, TR-7). 5-20 CPU-hours:
          Hunter's call (the PREREG-budget rule).
* smoke   one register, L = 100, three scorers, 2,000 draws, 5 plants; under a minute.

Sections (``--section`` runs a subset and merges it into an existing JSON of the same scale):
reusable, not_covered, nulls, power, confusion, beam, boundaries, order, throughput,
conditionals, reproduce. ``power`` and ``boundaries`` read the bars of ``nulls``; ``beam``
reuses the ``nulls`` cell for the rigid decoder at a shared L; ``confusion`` and ``order`` are
derived from ``nulls`` and ``power``; ``not_covered`` and ``conditionals`` read ``power`` and
are computed after the measured sections (COMPUTE_ORDER) and recomputed whenever they already
exist, so their content never depends on the run order; the rendered order stays SECTIONS.

Memory: a null cell holds the fitted preset (``presets.get`` is cached per process) and
``calib.measure``'s 50,000-row chunks; ``KNScorer.score_batch`` scores them in row chunks of
``kn.ROW_CHUNK_POSITIONS`` positions, so a worker's working set stays near the preset's tables
plus a few hundred MB. Wrong-key decodes are cached per worker (int8) across the scorers of a
length.

Kill condition (Aiming Test Q5): the heaviest null cell runs first, alone, and the run aborts
with the reason when it exceeds the scale's cell budget (10 % of the run budget).
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import platform
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_results  # noqa: E402  (BANNED, SOLVED_OK, PATHLIKE: the one list, imported)

from runeforge import canon  # noqa: E402
from runeforge.gematria import N as ALPHABET  # noqa: E402
from runeforge.lanes import LaneSpec  # noqa: E402
from runeforge.runner import pipeline  # noqa: E402
from runeforge.scoring import beam_calib, boundaries, calib, presets  # noqa: E402
from runeforge.transforms import Atbash, Compose, Shift, TotientPrimeStream, Vigenere  # noqa: E402

CANON_SHA256 = "023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585"
NUMBERING = canon.LP2_NUMBERING
SEED = 3301
N_CLAIM = 10**6  # a 30-minute CPU screen's trial count
N_FAMILY = 2**32  # the lanes' typical seed space
ALPHA = 0.01
BOOTSTRAP = 200
BLOCK = calib.BLOCK
STAGING = ROOT / "reports" / "calib-staging"
REPORTS = ROOT / "reports"
KS_C05 = 1.358  # Kolmogorov two-sample critical constant at alpha 0.05, reported, never asserted

SOLVED_REGISTER = "heldout-solved-sections"
HELDOUT_SECTIONS = ("a-koan-1", "the-loss-of-divinity")
REGISTERS = [
    "english-general",
    "cicada-english",
    "latin",
    "vowel-dropped-english",
    "old-english",
    SOLVED_REGISTER,
]
# the spec's target line (section 3.3): power >= 0.9 English, >= 0.5 Latin / vowel-dropped
# The spec's target (section 3.3) is for the claim scorer (an English-register scorer); the
# non-English register presets are adjudicator registers, not claim scorers, so no target applies.
REGISTER_SCORERS = ("kn8-latin", "kn8-old-english", "kn8-vowel-dropped")
TARGETS = {
    "english-general": 0.9,
    "cicada-english": 0.9,
    SOLVED_REGISTER: 0.9,
    "latin": 0.5,
    "vowel-dropped-english": 0.5,
    "old-english": None,
}
LENGTHS = [100, 240, 250, 263, 500, 1000]
SOLVED_MAX_L = 500  # the two held-out sections hold 1,533 runes
SCORERS = [
    "lp-ngram3-heldout",
    "cicada-ngram3",
    "general-ngram3",
    "kn4-lp-heldout",
    "kn4-cicada",
    "kn5-cicada",
    "kn6-cicada",
    "kn8-cicada",
    "kn8-general",
    "kn8-latin",
    "kn8-old-english",
    "kn8-vowel-dropped",
    "kn8-cicada-wb",
]
BEAM_SCORERS = ["lp-ngram3-heldout", "kn4-lp-heldout", "kn4-cicada"]
BEAM_LENGTHS = [120, 240]
MODELS = {  # the forward models of the beam cells (scripts/beam_power.py MODELS)
    "interrupts": {"filter_model": "off", "interrupt_prob": 1.0},
    "anti-repeat": {"filter_model": "anti-repeat", "interrupt_prob": 0.0},
    "anti-repeat + interrupts": {"filter_model": "anti-repeat", "interrupt_prob": 1.0},
}
VIEWS = ("raw", "atbash", "first-difference", "chain-increment")
SECTIONS = [
    "reusable",
    "not_covered",
    "nulls",
    "power",
    "confusion",
    "beam",
    "boundaries",
    "order",
    "throughput",
    "conditionals",
    "reproduce",
]
DERIVED = ["not_covered", "conditionals"]  # read power/nulls: computed after them, recomputed
COMPUTE_ORDER = [x for x in SECTIONS if x not in DERIVED and x != "reproduce"] + [
    *DERIVED,
    "reproduce",
]


# ----------------------------------------------------------------------------- scales


@dataclass
class Scale:
    name: str
    registers: list[str]
    lengths: list[int]
    scorers: list[str]
    draws: int  # uniform null draws per (scorer, L)
    wrong_key_draws: int  # wrong-key decodes per family and L
    plants: int  # plants per (register, L)
    rank_subset: int  # plants per cell ranked against decoys
    decoys: int
    beam_scorers: list[str]
    beam_lengths: list[int]
    beam_plants: int
    beam_decoys: int
    beam_draws: int
    wb_masks: int
    boundary_length: int
    throughput_rows: tuple[int, int]  # rows at L 240 and 1000
    kill_seconds: float  # the heaviest null cell's budget (10 % of the run budget)
    stage: bool = False  # write 10^6-draw records to reports/calib-staging
    # extra rigid-null lengths run only for scorers with an installed / staged record there,
    # so every installed record (L 120 and 240) meets a refit: the scale check of section 6
    scale_check_lengths: list[int] = field(default_factory=list)


SCALES = {
    "reduced": Scale(
        "reduced",
        REGISTERS,
        LENGTHS,
        SCORERS,
        draws=100_000,
        wrong_key_draws=5_000,
        plants=200,
        rank_subset=20,
        decoys=99,
        beam_scorers=BEAM_SCORERS,
        beam_lengths=BEAM_LENGTHS,
        beam_plants=50,
        beam_decoys=99,
        beam_draws=25_000,
        wb_masks=2_000,
        boundary_length=240,
        throughput_rows=(20_000, 5_000),
        kill_seconds=12 * 60,
        scale_check_lengths=[120],
    ),
    "full": Scale(
        "full",
        REGISTERS,
        LENGTHS,
        SCORERS,
        draws=1_000_000,
        wrong_key_draws=20_000,
        plants=1_000,
        rank_subset=50,
        decoys=99,
        beam_scorers=BEAM_SCORERS,
        beam_lengths=BEAM_LENGTHS,
        beam_plants=200,
        beam_decoys=99,
        beam_draws=1_000_000,
        wb_masks=10_000,
        boundary_length=240,
        throughput_rows=(20_000, 5_000),
        kill_seconds=2 * 3600,
        stage=True,
        scale_check_lengths=[120],
    ),
    "smoke": Scale(
        "smoke",
        ["cicada-english"],
        [100],
        ["lp-ngram3-heldout", "kn4-cicada", "kn8-cicada-wb"],
        draws=2_000,
        wrong_key_draws=200,
        plants=5,
        rank_subset=5,
        decoys=19,
        beam_scorers=["lp-ngram3-heldout", "kn4-cicada"],
        beam_lengths=[120],
        beam_plants=5,
        beam_decoys=19,
        beam_draws=2_000,
        wb_masks=50,
        boundary_length=100,
        throughput_rows=(2_000, 500),
        kill_seconds=60,
    ),
}


# ----------------------------------------------------------------------------- small maths


def rng_for(*tags: int) -> np.random.Generator:
    """Deterministic per cell: the stream depends on the cell's tags, never on the workers."""
    return np.random.default_rng([SEED, *[int(t) for t in tags]])


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson 95 % interval of a binomial proportion."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def ks_stat(a: np.ndarray, b: np.ndarray) -> float:
    """Two-sample Kolmogorov-Smirnov statistic sup |F_a - F_b| (a reported number)."""
    a, b = np.sort(np.asarray(a, dtype=np.float64)), np.sort(np.asarray(b, dtype=np.float64))
    if a.size == 0 or b.size == 0:
        return float("nan")
    grid = np.concatenate([a, b])
    fa = np.searchsorted(a, grid, side="right") / a.size
    fb = np.searchsorted(b, grid, side="right") / b.size
    return float(np.abs(fa - fb).max())


def ks_crit(n: int, m: int) -> float:
    return KS_C05 * math.sqrt((n + m) / (n * m)) if n and m else float("nan")


def bar_at(mu_b: float, beta: float, n_trials: int, alpha: float = ALPHA) -> float:
    """calib.threshold_for's Gumbel bar: the 1 - alpha quantile of the max of N draws."""
    return mu_b + beta * math.log(n_trials / BLOCK) - beta * math.log(-math.log(1 - alpha))


def gumbel(blocks: np.ndarray) -> tuple[float, float]:
    """calib._gumbel_fit, guarded for the smoke scale's two block maxima."""
    if blocks.size < 2:
        return float(blocks.mean()) if blocks.size else float("nan"), float("nan")
    return calib._gumbel_fit(blocks)


def fit_scores(scores: np.ndarray, draws: int, rng: np.random.Generator) -> dict:
    """Block maxima (block 1,000) -> Gumbel (mu_b, beta), the bars at N_CLAIM and N_FAMILY
    with 200-resample bootstrap intervals, and calib's out-of-sample check when it applies."""
    n_blocks = max(scores.size // BLOCK, 1)
    blocks = scores[: n_blocks * BLOCK].reshape(n_blocks, -1).max(axis=1)
    mu_b, beta = gumbel(blocks)
    boot = {"claim": [], "family": []}
    if blocks.size >= 2:
        for _ in range(BOOTSTRAP):
            m, b = gumbel(rng.choice(blocks, blocks.size, replace=True))
            boot["claim"].append(bar_at(m, b, N_CLAIM))
            boot["family"].append(bar_at(m, b, N_FAMILY))
    bars = {}
    for key, n_trials in (("claim", N_CLAIM), ("family", N_FAMILY)):
        bs = np.asarray(boot[key])
        bars[key] = {
            "N": n_trials,
            "alpha": ALPHA,
            "bar": bar_at(mu_b, beta, n_trials) if np.isfinite(beta) else float("nan"),
            "ci": (
                [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
                if bs.size
                else [float("nan"), float("nan")]
            ),
            "bootstrap": int(bs.size),
            "expected_false_positives": -math.log(1 - ALPHA),  # N * P(single clears)
        }
    check: dict = {}
    if scores.size % calib.CHECK_BLOCK == 0 and scores.size >= calib.CHECK_BLOCK and beta > 0:
        cb = scores.reshape(-1, calib.CHECK_BLOCK).max(axis=1)
        k_check = calib.CHECK_BLOCK / BLOCK
        pred_check = mu_b + beta * (math.log(k_check) + calib.EULER_GAMMA)
        pred_all = mu_b + beta * (math.log(draws / BLOCK) + calib.EULER_GAMMA)
        check = {
            f"mean_max_{calib.CHECK_BLOCK}": float(cb.mean()),
            f"predicted_mean_max_{calib.CHECK_BLOCK}": pred_check,
            f"max_{draws}": float(scores.max()),
            f"predicted_mean_max_{draws}": pred_all,
            "max_error": float(
                max(abs(cb.mean() - pred_check), abs(float(scores.max()) - pred_all))
            ),
        }
    return {
        "null": {
            "n": int(scores.size),
            "mean": float(scores.mean()),
            "sd": float(scores.std()),
            "min": float(scores.min()),
            "max": float(scores.max()),
        },
        "fit": {"block": BLOCK, "mu_block": mu_b, "beta": beta, "n_blocks": int(blocks.size)},
        "bars": bars,
        "check": check,
    }


def fit_record(
    scorer, scorer_name: str, decoder: str, length: int, fit: dict, scale: str, extra: dict
) -> dict:
    """A calibration record in calib.calibrate's layout (calib.load / threshold_for read
    ``preset``, ``L``, ``scorer_fingerprint``, ``fit.mu_block``, ``fit.beta``), plus the
    scale, the bootstrap bars and ``installable`` (false unless the scale is full)."""
    draws = fit["null"]["n"]
    rec = {
        "preset": f"{scorer_name}:{decoder}",
        "scorer": scorer_name,
        "decoder": decoder,
        "L": length,
        "units": "mean log2-probability per rune (higher = more language-like)",
        "scorer_fingerprint": scorer.fingerprint(),
        "method": f"Gumbel MoM fit to {fit['fit']['n_blocks']} block maxima of {BLOCK} "
        + ("uniform random strings" if decoder == "rigid" else f"beam decodes ({decoder})")
        + f"; max of N = k*{BLOCK} is Gumbel(mu_b + beta ln k, beta); null mean/sd over every "
        f"one of the {draws:,} draws (calib.calibrate's record uses its first 10,000)",
        "draws": draws,
        "seed": SEED,
        "null": {
            "n": int(draws),
            "mean": fit["null"]["mean"],
            "sd": fit["null"]["sd"],
        },
        "fit": fit["fit"],
        "check": fit["check"],
        "bars": fit["bars"],
        "scale": scale,
        "installable": scale == "full",
        "written_by": "scripts/scorer_power.py",
        "numbering": NUMBERING,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    rec.update(extra)
    return rec


def write_record(rec: dict, fits_dir: Path, stage: bool) -> list[str]:
    name = calib.path_for(rec["preset"], rec["L"]).name
    fits_dir.mkdir(parents=True, exist_ok=True)
    (fits_dir / name).write_text(json.dumps(rec, indent=1, default=_json) + "\n", "utf-8")
    out = [_rel(fits_dir / name)]
    if stage:
        STAGING.mkdir(parents=True, exist_ok=True)
        (STAGING / name).write_text(json.dumps(rec, indent=1, default=_json) + "\n", "utf-8")
        out.append(_rel(STAGING / name))
    return out


def _json(x):
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    raise TypeError(f"not JSON-able: {type(x)}")


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def _map(fn, jobs: list, workers: int) -> list:
    if workers <= 1 or len(jobs) <= 1:
        return [fn(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, jobs))


# ----------------------------------------------------------------------------- registers


def register_text(name: str) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int]]]:
    """(runes, word-start mask, contiguous segments) of a register's held-out text: the 90/10
    tail of a corpus (presets.heldout_stream) or the two held-out solved sections with the
    word structure of their LP1 pages (a-koan-1: LP1 6-9; the-loss-of-divinity: LP1 10-13)."""
    if name != SOLVED_REGISTER:
        runes, ids = presets.heldout_stream(name)
        return runes, boundaries.corpus_starts(ids), [(0, int(runes.size))]
    lp1 = canon.load_lp1()
    runes, starts, segs, pos = [], [], [], 0
    for sid in HELDOUT_SECTIONS:
        s = canon.solved_section(sid)
        lens = np.array([len(w) for p in s.pages for w in lp1.page(p).words()], dtype=np.int64)
        if int(lens.sum()) != s.plain.size:
            raise RuntimeError(f"{sid}: LP1 word lengths sum to {lens.sum()}, not {s.plain.size}")
        m = np.zeros(s.plain.size, dtype=bool)
        m[np.concatenate(([0], np.cumsum(lens[:-1])))] = True
        runes.append(s.plain)
        starts.append(m)
        segs.append((pos, pos + s.plain.size))
        pos += s.plain.size
    return np.concatenate(runes), np.concatenate(starts), segs


def plant_windows(register: str, length: int, n: int, tag: int) -> dict:
    """Up to ``n`` windows of ``length`` runes of the register's held-out text at distinct
    random offsets (drawn without replacement; never across a section join), with their
    word-start masks. ``n_offsets`` is the number of distinct offsets the register holds at
    this length and ``n_disjoint`` the number of non-overlapping windows: when ``n`` exceeds
    ``n_offsets`` the draw is capped there, and a small ``n_disjoint`` means the windows
    overlap (the 1,533-rune heldout-solved-sections register at L >= 263), so a Wilson interval is
    nominal, not an interval over independent plants."""
    runes, starts, segs = register_text(register)
    rng = rng_for(1, REGISTERS.index(register), length, tag)
    room = [max(b - a - length + 1, 0) for a, b in segs]
    pool = np.concatenate([np.arange(a, a + r) for (a, _), r in zip(segs, room, strict=True)])
    if pool.size == 0:
        raise ValueError(f"register {register} holds no window of {length} runes")
    offs = np.sort(rng.choice(pool, size=min(n, pool.size), replace=False))
    offs = offs[rng.permutation(offs.size)]
    return {
        "plains": np.stack([runes[o : o + length] for o in offs]),
        "starts": np.stack([starts[o : o + length] for o in offs]),
        "offsets": offs,
        "n_offsets": int(pool.size),
        "n_disjoint": int(sum((b - a) // length for a, b in segs)),
    }


def held_out(scorer: str, register: str) -> bool:
    """Whether the register's plant text is outside the scorer's training data: a corpus
    (or one of its derived family) in ``train`` is held out only through a pinned split (its
    tail); the two solved sections only when the scorer excludes them."""
    spec = presets.PRESETS[scorer]
    train = spec["train"]
    if register == SOLVED_REGISTER:
        if "lp-solved" not in train:
            return True
        return all(s in spec.get("exclude", []) for s in HELDOUT_SECTIONS)
    family = presets._derived_family(register)
    return all(src not in family for src in train) or spec.get("split") is not None


# ----------------------------------------------------------------------------- families


@dataclass(frozen=True)
class Family:
    name: str
    kind: str  # transform | lane
    generator: str = ""
    combine: str = "vigenere"
    view: str = "raw"
    in_equality_claim: bool = True  # KS vs the uniform null: a claim, or reported only
    n_keys: int | None = None  # a finite key space (wrong keys enumerated / drawn without
    # replacement, and the count above the Gumbel bar at N = n_keys reported); None = 2^32+
    note: str = ""


ATBASH_SHIFT_KEYS = [(atbash, n) for atbash in (False, True) for n in range(ALPHABET)]
TOTIENT_STARTS = 10_000


def families() -> list[Family]:
    out = [
        Family(
            "vigenere-short-key",
            "transform",
            in_equality_claim=False,
            note="period 8-13; a wrong key of the same period matches 1/29 of its symbols",
        ),
        Family(
            "atbash-shift",
            "transform",
            in_equality_claim=False,
            n_keys=len(ATBASH_SHIFT_KEYS),
            note="58 keys: shift 0-28 with or without atbash; every wrong key is a "
            "monoalphabetic substitution of the plaintext, not a uniform string, so the family "
            "is outside the equality claim; its 57 wrong keys are enumerated",
        ),
        Family(
            "totient-stream",
            "transform",
            in_equality_claim=False,
            n_keys=TOTIENT_STARTS,
            note="phi(p) = p - 1 over the primes from start (10,000 starts); a wrong key is "
            "another offset of the same deterministic stream (p - 1 mod 29 is never 28 past "
            "p = 29), so the family is outside the equality claim; wrong keys drawn without "
            "replacement",
        ),
    ]
    for gen in ("sha256-ctr", "numpy-pcg64"):
        for combine in ("vigenere", "beaufort"):
            for view in VIEWS:
                out.append(Family(f"{gen}/{combine}/{view}", "lane", gen, combine, view))
    return out


FAMILIES = families()


def toy_lane(length: int, preset: str = "lp-ngram3-heldout:rigid", **over) -> LaneSpec:
    """scripts/beam_power.py's toy LaneSpec (lane id SCORER-POWER): in memory, never a file."""
    spec = {
        "lane_id": "SCORER-POWER",
        "hypothesis": "power envelope (scripts/scorer_power.py)",
        "family": "prng",
        "generator": "numpy-pcg64",
        "seed_range": [0, 2**32],
        "window": length,
        "pages": [0, 1, 2, 3, 4, 5],
        "preset": preset,
        "filter_model": "off",
        "interrupt_prob": 0.0,
        "control": {"planted_seed": 3301, "synthetic_page": "solved:a-koan-1", "decoys": 99},
    }
    spec.update(over)
    return LaneSpec(**spec)


def _transform(fam: Family, key):
    if fam.name == "vigenere-short-key":
        return Vigenere(list(key))
    if fam.name == "atbash-shift":
        atbash, n = key
        return Compose([Atbash(), Shift(int(n))]) if atbash else Shift(int(n))
    return TotientPrimeStream(int(key))


def _draw_key(fam: Family, rng: np.random.Generator):
    if fam.name == "vigenere-short-key":
        return tuple(int(x) for x in rng.integers(0, ALPHABET, int(rng.integers(8, 14))))
    if fam.name == "atbash-shift":
        return (bool(rng.random() < 0.5), int(rng.integers(0, ALPHABET)))
    if fam.name == "totient-stream":
        return int(rng.integers(0, 10_000))
    return pipeline.draw_seeds(rng, 0, 2**32, 1)[0]


def fam_encrypt(fam: Family, lane: LaneSpec | None, plain: np.ndarray, rng) -> tuple:
    """(cipher, key) on the real code paths: ``transforms`` or ``pipeline.encrypt``."""
    key = _draw_key(fam, rng)
    if fam.kind == "transform":
        return _transform(fam, key).encrypt(plain), key
    k = pipeline.keys(lane, key, plain.size)
    cipher, _ = pipeline.encrypt(lane, plain, k, rng)
    return cipher, key


def fam_decrypt(fam: Family, lane: LaneSpec | None, cipher: np.ndarray, key) -> np.ndarray:
    if fam.kind == "transform":
        return _transform(fam, key).decrypt(cipher)
    return pipeline.decrypt(lane, cipher, pipeline.keys(lane, key, cipher.size)[None, :])[0]


def fam_wrong_decodes(fam: Family, lane, cipher: np.ndarray, key, n: int, rng) -> np.ndarray:
    """``n`` decodes of ``cipher`` under wrong keys of the family (never the true one)."""
    if fam.kind == "lane":
        seeds = [s for s in pipeline.draw_seeds(rng, 0, 2**32, n + 2) if s != key][:n]
        return pipeline.decrypt(lane, cipher, pipeline.keys_batch(lane, seeds, cipher.size))
    if fam.name == "atbash-shift":  # finite: every wrong key once, in key order
        keys = [k for k in ATBASH_SHIFT_KEYS if k != key][:n]
    elif fam.name == "totient-stream":  # finite: distinct starts, without replacement
        others = np.array([k for k in range(TOTIENT_STARTS) if k != key])
        keys = [int(k) for k in rng.choice(others, size=min(n, others.size), replace=False)]
    else:
        keys = []
        while len(keys) < n:
            k = _draw_key(fam, rng)
            if k != key:
                keys.append(k)
    return np.stack([_transform(fam, k).decrypt(cipher) for k in keys])


def fam_lane(fam: Family, length: int) -> LaneSpec | None:
    if fam.kind != "lane":
        return None
    return toy_lane(length, generator=fam.generator, combine=fam.combine, ciphertext_view=fam.view)


# ----------------------------------------------------------------------------- scoring helpers


def score_rows(scorer, plains: np.ndarray, starts: np.ndarray, wb: bool) -> np.ndarray:
    """Scores of rows that each carry their own mask (a wb scorer batches one mask)."""
    if not wb:
        return scorer.score_batch(plains)
    return np.array([scorer.score(p, starts=s) for p, s in zip(plains, starts, strict=True)])


def get_scorer(name: str):
    return presets.get(name)


def uniform_scores(scorer, length: int, draws: int, mask_pool=None, n_masks: int = 0):
    """Null (a): uniform random strings; calib.measure when the draw count is one it accepts
    (a multiple of 25,000), the same loop otherwise. A wb scorer scores them under
    ``n_masks`` masks drawn from the LP2 word-length histogram, ``draws // n_masks`` each."""
    if mask_pool is None:
        if draws % calib.CHECK_BLOCK == 0:
            return calib.measure(scorer, length, draws, seed=SEED)
        rng = np.random.default_rng(SEED)
        return scorer.score_batch(rng.integers(0, ALPHABET, (draws, length)))
    rng = np.random.default_rng(SEED)
    mrng = rng_for(2, length)
    per = max(draws // n_masks, 1)
    out = []
    while sum(o.size for o in out) < draws:
        starts = boundaries.sample_starts(mrng, length, mask_pool)
        out.append(scorer.score_batch(rng.integers(0, ALPHABET, (per, length)), starts=starts))
    return np.concatenate(out)[:draws]


@functools.lru_cache(maxsize=2 * len(FAMILIES))
def wrong_key_decodes(fam_index: int, length: int, n: int, register: str) -> tuple:
    """Null (b): one held-out window of ``register`` enciphered under a true key of the
    family and decoded under ``n`` wrong keys (fewer for a finite family: ``Family.n_keys``);
    (decodes as int8, the window's mask). Deterministic in (family, L, n, register) and
    independent of the scorer, so it is cached per process (one length's families fit the
    cache) and every scorer of a length scores the same arrays; callers never mutate them."""
    fam = FAMILIES[fam_index]
    lane = fam_lane(fam, length)
    w = plant_windows(register, length, 1, 900 + fam_index)
    plain, starts = w["plains"][0], w["starts"][0]
    rng = rng_for(3, fam_index, length)
    cipher, key = fam_encrypt(fam, lane, plain, rng)
    if not np.array_equal(fam_decrypt(fam, lane, cipher, key), plain):
        raise RuntimeError(f"{fam.name}: the true key does not decode its own cipher")
    dec = fam_wrong_decodes(fam, lane, cipher, key, n, rng)
    return np.ascontiguousarray(dec, dtype=np.int8), starts


# ----------------------------------------------------------------------------- section: nulls


def null_cell(args) -> dict:
    scorer_name, length, cfg_d, fits_dir, scale_check_only = args
    cfg = Scale(**cfg_d)
    t0 = time.time()
    scorer = get_scorer(scorer_name)
    wb = presets.is_wb(scorer_name)
    pool = boundaries.lp2_word_lengths() if wb else None
    scores = uniform_scores(scorer, length, cfg.draws, pool, cfg.wb_masks)
    fit = fit_scores(scores, cfg.draws, rng_for(4, SCORERS.index(scorer_name), length))
    mu_b, beta = fit["fit"]["mu_block"], fit["fit"]["beta"]
    wrong = []
    for i, fam in enumerate(FAMILIES if not scale_check_only else []):
        dec, starts = wrong_key_decodes(i, length, cfg.wrong_key_draws, cfg.registers[0])
        s = scorer.score_batch(dec, starts=starts) if wb else scorer.score_batch(dec)
        finite = fam.n_keys is not None and math.isfinite(beta)
        bar_keys = bar_at(mu_b, beta, fam.n_keys) if finite else None
        wrong.append(
            {
                "family": fam.name,
                "n": int(s.size),
                "n_keys": fam.n_keys,
                "mean": float(s.mean()),
                "sd": float(s.std()),
                "max": float(s.max()),
                "ks_vs_uniform": ks_stat(s, scores),
                "ks_crit_05": ks_crit(s.size, scores.size),
                # the wb cell is outside the claim as a whole: its decodes carry the window's
                # own mask while null (a) averages over sampled masks (section 6)
                "in_equality_claim": fam.in_equality_claim and not wb,
                "above_claim_bar": int((s > fit["bars"]["claim"]["bar"]).sum()),
                "bar_at_n_keys": bar_keys,
                "above_bar_at_n_keys": int((s > bar_keys).sum()) if finite else None,
            }
        )
    claimed = [w for w in wrong if w["in_equality_claim"]]
    mask = (
        f"{cfg.wb_masks} masks sampled from the LP2 word-length histogram "
        f"(boundaries.sample_starts), {max(cfg.draws // cfg.wb_masks, 1)} strings each"
        if wb
        else None
    )
    rec = fit_record(
        scorer,
        scorer_name,
        "rigid",
        length,
        fit,
        cfg.name,
        {"null_source": "scripts/scorer_power.py uniform_scores", "mask": mask},
    )
    written = write_record(rec, Path(fits_dir), cfg.stage and not wb)
    cell = {
        "scorer": scorer_name,
        "L": length,
        "decoder": "rigid",
        "draws": cfg.draws,
        "mask": mask,
        "scale_check_only": bool(scale_check_only),
        **fit,
        "wrong_key": wrong,
        "ks_max_in_claim": max((w["ks_vs_uniform"] for w in claimed), default=float("nan")),
        "ks_max_excluded": max(
            (w["ks_vs_uniform"] for w in wrong if not w["in_equality_claim"]), default=None
        ),
        "ks_max_all": max((w["ks_vs_uniform"] for w in wrong), default=None),
        "scale_check": scale_check(scorer, f"{scorer_name}:rigid", length, fit),
        "fit_record": written,
        "seconds": round(time.time() - t0, 1),
    }
    return cell


def scale_check(scorer, preset: str, length: int, fit: dict) -> dict | None:
    """The installed (runeforge/scoring/calib/presets) or staged (reports/calib-staging)
    record at this preset and length against this run's refit: the scale check."""
    rec, where = None, None
    try:
        rec, where = calib.load(preset, length, check_fingerprint=False), "installed"
    except (FileNotFoundError, ValueError):
        p = STAGING / calib.path_for(preset, length).name
        if p.exists():
            rec, where = json.loads(p.read_text("utf-8")), "staged"
    if rec is None:
        return None
    mu_i, beta_i = rec["fit"]["mu_block"], rec["fit"]["beta"]
    mu_r, beta_r = fit["fit"]["mu_block"], fit["fit"]["beta"]
    return {
        "source": where,
        "file": calib.path_for(preset, length).name,
        "installed_draws": rec.get("draws"),
        "installed_mu_block": mu_i,
        "installed_beta": beta_i,
        "installed_bar_claim": bar_at(mu_i, beta_i, N_CLAIM),
        "installed_bar_family": bar_at(mu_i, beta_i, N_FAMILY),
        "refit_mu_block": mu_r,
        "refit_beta": beta_r,
        "refit_bar_claim": fit["bars"]["claim"]["bar"],
        "delta_bar_claim": fit["bars"]["claim"]["bar"] - bar_at(mu_i, beta_i, N_CLAIM),
        "delta_bar_family": fit["bars"]["family"]["bar"] - bar_at(mu_i, beta_i, N_FAMILY),
        "installed_bar_claim_in_refit_ci": (
            fit["bars"]["claim"]["ci"][0]
            <= bar_at(mu_i, beta_i, N_CLAIM)
            <= fit["bars"]["claim"]["ci"][1]
        ),
        "fingerprint_matches": rec.get("scorer_fingerprint") == scorer.fingerprint(),
    }


def _has_record(preset: str, length: int) -> bool:
    """An installed (calib presets) or staged record exists for this preset and L."""
    try:
        calib.load(preset, length, check_fingerprint=False)
        return True
    except (FileNotFoundError, ValueError):
        return (STAGING / calib.path_for(preset, length).name).exists()


def section_nulls(cfg: Scale, workers: int, fits_dir: Path) -> dict:
    jobs = [
        (s, length, asdict(cfg), str(fits_dir), False)
        for length in sorted(cfg.lengths, reverse=True)
        for s in cfg.scorers
    ]
    # scale-check-only cells: the installed records at lengths outside cfg.lengths (L = 120)
    jobs += [
        (s, length, asdict(cfg), str(fits_dir), True)
        for length in sorted(cfg.scale_check_lengths, reverse=True)
        if length not in cfg.lengths
        for s in cfg.scorers
        if _has_record(f"{s}:rigid", length)
    ]
    # the heaviest cell first and alone: the kill condition at 10 % of the budget
    heavy = max(jobs, key=lambda j: j[1] * (presets.PRESETS[j[0]].get("order", 3)))
    t0 = time.time()
    first = null_cell(heavy)
    dt = time.time() - t0
    print(f"  smoke cell {heavy[0]} L={heavy[1]}: {dt:.1f} s (budget {cfg.kill_seconds} s)")
    if dt > cfg.kill_seconds:
        raise SystemExit(
            f"kill condition: the heaviest null cell ({heavy[0]} L={heavy[1]}) took {dt:.0f} s, "
            f"over the {cfg.kill_seconds:.0f} s cell budget (10 % of the run budget); aborting"
        )
    rest = [j for j in jobs if j != heavy]
    cells = [first, *_map(null_cell, rest, workers)]
    cells.sort(key=lambda c: (c["L"], cfg.scorers.index(c["scorer"])))
    for c in cells:
        print(
            f"  null {c['scorer']:18s} L={c['L']:4d} mean {c['null']['mean']:.4f} "
            f"sd {c['null']['sd']:.4f} mu_b {c['fit']['mu_block']:.4f} beta "
            f"{c['fit']['beta']:.4f} bar@1e6 {c['bars']['claim']['bar']:.4f} "
            f"KS<= {c['ks_max_in_claim']:.4f} ({c['seconds']} s)",
            flush=True,
        )
    return {
        "draws_per_cell": cfg.draws,
        "wrong_key_draws_per_family": cfg.wrong_key_draws,
        "scale_check_lengths": [x for x in cfg.scale_check_lengths if x not in cfg.lengths],
        "families": [asdict(f) for f in FAMILIES],
        "cells": cells,
    }


# ----------------------------------------------------------------------------- section: power


def power_cell(args) -> dict:
    register, length, cfg_d = args
    cfg = Scale(**cfg_d)
    t0 = time.time()
    w = plant_windows(register, length, cfg.plants, 0)
    plains, starts = w["plains"], w["starts"]
    n_plants = int(plains.shape[0])  # cfg.plants, capped at the register's distinct offsets
    rng = rng_for(5, REGISTERS.index(register), length)
    fam_rows = []
    for fam in FAMILIES:
        lane = fam_lane(fam, length)
        exact = 0
        for p in plains:
            cipher, key = fam_encrypt(fam, lane, p, rng)
            exact += bool(np.array_equal(fam_decrypt(fam, lane, cipher, key), p))
        fam_rows.append({"family": fam.name, "plants": n_plants, "decode_exact": exact})
    if any(r["decode_exact"] != n_plants for r in fam_rows):
        bad = [r for r in fam_rows if r["decode_exact"] != r["plants"]]
        raise RuntimeError(f"a rigid additive family did not decode its own plants: {bad}")
    # rank-1 over decoys for a subset: plant j through family j mod n_families
    subset = min(cfg.rank_subset, n_plants)
    decoy_sets = []
    for j in range(subset):
        fam = FAMILIES[j % len(FAMILIES)]
        lane = fam_lane(fam, length)
        cipher, key = fam_encrypt(fam, lane, plains[j], rng)
        decoy_sets.append((fam.name, fam_wrong_decodes(fam, lane, cipher, key, cfg.decoys, rng)))
    rows = {}
    for name in cfg.scorers:
        scorer = get_scorer(name)
        wb = presets.is_wb(name)
        planted = score_rows(scorer, plains, starts, wb)
        rank1 = 0
        for j, (_fam, dec) in enumerate(decoy_sets):
            d = scorer.score_batch(dec, starts=starts[j]) if wb else scorer.score_batch(dec)
            rank1 += bool(planted[j] > d.max())
        rows[name] = {
            "planted": [round(float(x), 5) for x in planted],
            "planted_mean": float(planted.mean()),
            "planted_sd": float(planted.std()),
            "planted_min": float(planted.min()),
            "planted_max": float(planted.max()),
            "held_out": held_out(name, register),
            "rank1": {"n": subset, "rank1": rank1, "decoys": cfg.decoys},
        }
    return {
        "register": register,
        "L": length,
        "n_plants": n_plants,
        "n_offsets": w["n_offsets"],
        "n_disjoint": w["n_disjoint"],
        "families": fam_rows,
        "scorers": rows,
        "seconds": round(time.time() - t0, 1),
    }


def _power_at(planted: np.ndarray, bar: float) -> dict:
    if not np.isfinite(bar):
        return {"bar": bar, "power": float("nan"), "k": 0, "n": int(planted.size), "ci": None}
    k = int((planted > bar).sum())
    lo, hi = wilson(k, planted.size)
    return {"bar": bar, "power": k / planted.size, "k": k, "n": int(planted.size), "ci": [lo, hi]}


def derive_power(cells: list[dict], nulls: dict | None, cfg: Scale) -> list[dict]:
    """One row per (register, L, scorer) with the power at the nulls' bars."""
    bars = {}
    for c in (nulls or {}).get("cells", []):
        bars[(c["scorer"], c["L"])] = c["bars"]
    rows = []
    for cell in cells:
        for name, r in cell["scorers"].items():
            planted = np.asarray(r["planted"], dtype=np.float64)
            b = bars.get((name, cell["L"]))
            row = {
                "register": cell["register"],
                "L": cell["L"],
                "scorer": name,
                "n_plants": cell["n_plants"],
                "n_offsets": cell.get("n_offsets"),
                "n_disjoint": cell.get("n_disjoint"),
                "held_out": r["held_out"],
                "planted_mean": r["planted_mean"],
                "planted_sd": r["planted_sd"],
                "planted_min": r["planted_min"],
                "rank1": r["rank1"],
                "families": [f["family"] for f in cell["families"]],
                "bars_from": "nulls" if b else None,
            }
            if b:
                row["claim"] = _power_at(planted, b["claim"]["bar"])
                row["claim_ci_low_bar"] = _power_at(planted, b["claim"]["ci"][0])
                row["claim_ci_high_bar"] = _power_at(planted, b["claim"]["ci"][1])
                row["family"] = _power_at(planted, b["family"]["bar"])
                row["family_ci_high_bar"] = _power_at(planted, b["family"]["ci"][1])
                target = TARGETS.get(cell["register"])
                row["target"] = target
                row["target_line"] = (
                    "no target in the spec"
                    if target is None
                    else (
                        "n/a: register scorer, not a claim scorer"
                        if name in REGISTER_SCORERS
                        else ("not applicable: trained-on text" if not r["held_out"] else "")
                    )
                    or (f"met (>= {target})" if row["claim"]["power"] >= target else "not met")
                )
            rows.append(row)
    return rows


def section_power(cfg: Scale, workers: int, nulls: dict | None) -> dict:
    jobs = [
        (r, length, asdict(cfg))
        for r in cfg.registers
        for length in cfg.lengths
        if r != SOLVED_REGISTER or length <= SOLVED_MAX_L
    ]
    cells = _map(power_cell, jobs, workers)
    rows = derive_power(cells, nulls, cfg)
    for row in rows:
        if "claim" in row:
            print(
                f"  power {row['register']:24s} L={row['L']:4d} {row['scorer']:18s} "
                f"planted {row['planted_mean']:.4f} bar {row['claim']['bar']:.4f} "
                f"power {row['claim']['power']:.3f} held_out={row['held_out']} "
                f"{row['target_line']}",
                flush=True,
            )
    return {"plants_per_cell": cfg.plants, "cells": cells, "rows": rows}


# ----------------------------------------------------------------------------- section: confusion


def section_confusion(power: dict | None, cfg: Scale) -> dict | None:
    """The register confusion matrix: register x scorer at every L (planted mean and power
    at the claim bar), the adjudicator-register conditional measured."""
    if not power:
        return None
    out = {"lengths": {}}
    for length in cfg.lengths:
        rows = [r for r in power["rows"] if r["L"] == length]
        if not rows:
            continue
        matrix = {}
        for r in rows:
            matrix.setdefault(r["register"], {})[r["scorer"]] = {
                "planted_mean": r["planted_mean"],
                "power_claim": r.get("claim", {}).get("power"),
                "held_out": r["held_out"],
            }
        best = {}
        for reg, by in matrix.items():
            ho = {s: v for s, v in by.items() if v["held_out"]}
            if ho:
                best[reg] = max(ho, key=lambda s: ho[s]["planted_mean"])
        out["lengths"][str(length)] = {"matrix": matrix, "best_held_out_scorer": best}
    return out


# ----------------------------------------------------------------------------- section: beam


def beam_null_scores(scorer_name: str, decoder: str, length: int, draws: int, workers: int):
    """Null (c): beam_calib's draws (deterministic per chunk, doublet-free ciphers at the
    fit's canonical F count), any draw count; beam_calib.measure's own loop needs a multiple
    of 25,000."""
    n_f = beam_calib.canonical_f(length) if beam_calib.uses_interrupts(decoder) else None
    jobs = [
        (scorer_name, decoder, length, SEED, i, min(beam_calib.CHUNK, draws - start), n_f)
        for i, start in enumerate(range(0, draws, beam_calib.CHUNK))
    ]
    return np.concatenate(_map(beam_calib._chunk, jobs, workers)), n_f


def beam_plant_cell(args) -> dict:
    scorer_name, decoder, model_name, length, cfg_d = args
    cfg = Scale(**cfg_d)
    t0 = time.time()
    lane = toy_lane(length, preset=f"{scorer_name}:{decoder}", **MODELS[model_name])
    scorer = get_scorer(scorer_name)
    w = plant_windows(SOLVED_REGISTER, length, cfg.beam_plants, 7)
    rng = rng_for(6, BEAM_SCORERS.index(scorer_name), presets.DECODERS.index(decoder), length)
    plants = []
    for plain in w["plains"]:
        s_true = pipeline.draw_seeds(rng, 0, 2**32, 1)[0]
        k_true = pipeline.keys(lane, s_true, 3 * length)
        cipher, _ = pipeline.encrypt(lane, plain, k_true, rng)
        decoys = [d for d in pipeline.draw_seeds(rng, 0, 2**32, cfg.beam_decoys) if d != s_true]
        seeds = [s_true, *decoys]
        plains = pipeline.decrypt(lane, cipher[None, :], pipeline.keys_batch(lane, seeds, length))
        scores = scorer.score_batch(plains)
        plants.append(
            {
                "planted": float(scores[0]),
                "best_decoy": float(scores[1:].max()),
                "rank": 1 + int((scores[1:] >= scores[0]).sum()),
                "recovery": float((plains[0] == plain).mean()),
            }
        )
    planted = np.array([p["planted"] for p in plants])
    rec = [p["recovery"] for p in plants]
    return {
        "scorer": scorer_name,
        "decoder": decoder,
        "forward_model": model_name,
        "L": length,
        "n_plants": len(plants),
        "decoys": cfg.beam_decoys,
        "plant_text": SOLVED_REGISTER,
        "rank1": int(sum(p["rank"] == 1 for p in plants)),
        "identified": int(sum(p["rank"] == 1 and p["recovery"] >= 0.9 for p in plants)),
        "median_recovery": float(np.median(rec)),
        "planted": [round(float(x), 5) for x in planted],
        "planted_mean": float(planted.mean()),
        "planted_min": float(planted.min()),
        "best_decoy_max": float(max(p["best_decoy"] for p in plants)),
        "runnable_pairing": not lane.decoder_problems(),
        "seconds": round(time.time() - t0, 1),
    }


def section_beam(cfg: Scale, workers: int, fits_dir: Path, null_section: dict | None) -> dict:
    nulls = []
    null_by = {(c["scorer"], c["L"]): c for c in (null_section or {}).get("cells", [])}
    for length in cfg.beam_lengths:
        for scorer_name in cfg.beam_scorers:
            scorer = get_scorer(scorer_name)
            for decoder in presets.DECODERS:
                t0 = time.time()
                reused = null_by.get((scorer_name, length)) if decoder == "rigid" else None
                if reused is not None:
                    # one rigid bar per (scorer, L) in a report: the nulls section's cell
                    nulls.append(
                        {
                            "scorer": scorer_name,
                            "decoder": "rigid",
                            "L": length,
                            "draws": reused["draws"],
                            "canonical_F": None,
                            **{k: reused[k] for k in ("null", "fit", "bars", "check")},
                            "scale_check": reused["scale_check"],
                            "fit_record": reused["fit_record"],
                            "null_source": f"sections.nulls.cells[scorer={scorer_name}, "
                            f"L={length}] (reused, {reused['draws']:,} draws)",
                            "seconds": 0.0,
                        }
                    )
                    continue
                if decoder == "rigid":
                    scores, n_f = uniform_scores(scorer, length, cfg.beam_draws), None
                    extra = {"null_source": "scripts/scorer_power.py uniform_scores"}
                else:
                    scores, n_f = beam_null_scores(
                        scorer_name, decoder, length, cfg.beam_draws, workers
                    )
                    extra = {
                        "decoder_params": presets.DECODER_PARAMS[decoder],
                        "beam_sha256": beam_calib.beam_sha256(),
                        "canonical_F": n_f,
                        "doublets": "none",
                        "null_source": "runeforge.scoring.beam_calib._chunk",
                    }
                fit = fit_scores(scores, cfg.beam_draws, rng_for(8, length, len(nulls)))
                rec = fit_record(scorer, scorer_name, decoder, length, fit, cfg.name, extra)
                written = write_record(rec, fits_dir, cfg.stage) if decoder != "rigid" else []
                nulls.append(
                    {
                        "scorer": scorer_name,
                        "decoder": decoder,
                        "L": length,
                        "draws": cfg.beam_draws,
                        "canonical_F": n_f,
                        **fit,
                        "scale_check": scale_check(scorer, f"{scorer_name}:{decoder}", length, fit),
                        "fit_record": written,
                        "null_source": extra["null_source"],
                        "seconds": round(time.time() - t0, 1),
                    }
                )
                print(
                    f"  beam null {scorer_name:18s} {decoder:13s} L={length} mean "
                    f"{fit['null']['mean']:.4f} bar@1e6 {fit['bars']['claim']['bar']:.4f} "
                    f"({nulls[-1]['seconds']} s)",
                    flush=True,
                )
    jobs = [
        (s, d, m, length, asdict(cfg))
        for length in cfg.beam_lengths
        for s in cfg.beam_scorers
        for d in presets.DECODERS
        for m in MODELS
    ]
    cells = _map(beam_plant_cell, jobs, workers)
    bars = {(n["scorer"], n["decoder"], n["L"]): n["bars"] for n in nulls}
    for c in cells:
        b = bars[(c["scorer"], c["decoder"], c["L"])]
        planted = np.asarray(c["planted"])
        c["claim"] = _power_at(planted, b["claim"]["bar"])
        c["claim_ci_high_bar"] = _power_at(planted, b["claim"]["ci"][1])
        c["family"] = _power_at(planted, b["family"]["bar"])
        print(
            f"  beam cell {c['scorer']:18s} {c['decoder']:13s} {c['forward_model']:24s} "
            f"L={c['L']} identified {c['identified']}/{c['n_plants']} power@1e6 "
            f"{c['claim']['power']:.2f} ({c['seconds']} s)",
            flush=True,
        )
    return {"draws": cfg.beam_draws, "nulls": nulls, "cells": cells}


# ----------------------------------------------------------------------------- section: boundaries


def _page_start_masks(length: int) -> list[tuple[int, np.ndarray]]:
    lp2 = canon.load_lp2()
    pages = [p for p in canon.UNSOLVED_LP2_PAGES if lp2.page(p).n_runes]
    out = []
    for i, p in enumerate(pages):
        if sum(lp2.page(q).n_runes for q in pages[i:]) >= length:
            out.append((p, boundaries.window_starts(pages[i:], length)))
    return out


def _variant_scores(scorer, plains: np.ndarray, starts: np.ndarray, shared: bool) -> np.ndarray:
    """The score_boundaries=False variant: the boundary positions' log-probs left out of the
    sum (the divisor stays L = cipher runes)."""
    out = np.empty(plains.shape[0])
    for j, p in enumerate(plains):
        s = starts if shared else starts[j]
        lp = scorer.logprobs(p, starts=s)
        ext = scorer.boundary_extend(p, s)
        out[j] = lp[ext != scorer.boundary].sum() / p.size
    return out


def section_boundaries(cfg: Scale, nulls: dict | None) -> dict | None:
    """Null (d) and the boundary gain for the wb scorer at ``cfg.boundary_length``."""
    wb_names = [s for s in cfg.scorers if presets.is_wb(s)]
    if not wb_names:
        return {"skipped": "no word-boundary scorer in this scale's scorer list"}
    name, length = wb_names[0], cfg.boundary_length
    scorer = get_scorer(name)
    t0 = time.time()
    masks = _page_start_masks(length)
    per = max(min(cfg.draws // max(len(masks), 1), 5_000), 50)
    rng = np.random.default_rng(SEED + 1)
    per_mask, pooled = [], []
    for page, m in masks:
        s = scorer.score_batch(rng.integers(0, ALPHABET, (per, length)), starts=m)
        per_mask.append(
            {"page": page, "words": int(m.sum()), "mean": float(s.mean()), "sd": float(s.std())}
        )
        pooled.append(s)
    pooled = np.concatenate(pooled)
    page_fit = fit_scores(pooled, pooled.size, rng_for(9, length, 1))
    means = np.array([r["mean"] for r in per_mask])
    sampled = None
    for c in (nulls or {}).get("cells", []):
        if c["scorer"] == name and c["L"] == length:
            sampled = {k: c[k] for k in ("null", "fit", "bars", "mask")}
    if sampled is None:
        pool = boundaries.lp2_word_lengths()
        s = uniform_scores(scorer, length, cfg.draws, pool, cfg.wb_masks)
        f = fit_scores(s, cfg.draws, rng_for(9, length, 2))
        sampled = {**{k: f[k] for k in ("null", "fit", "bars")}, "mask": "sampled (recomputed)"}
    # the boundary gain: plants of the first register at this length, with their true masks
    register = cfg.registers[0]
    w = plant_windows(register, length, cfg.plants, 0)
    planted = score_rows(scorer, w["plains"], w["starts"], True)
    planted_var = _variant_scores(scorer, w["plains"], w["starts"], shared=False)
    n_var = min(pooled.size, 10_000)
    rng = np.random.default_rng(SEED + 2)
    var_null = []
    for _page, m in masks:
        k = max(n_var // len(masks), 1)
        var_null.append(_variant_scores(scorer, rng.integers(0, ALPHABET, (k, length)), m, True))
    var_null = np.concatenate(var_null)
    var_fit = fit_scores(var_null, var_null.size, rng_for(9, length, 3))

    def sep(p, null):
        return float((p.mean() - null["mean"]) / null["sd"]) if null["sd"] > 0 else float("nan")

    gain = {
        "register": register,
        "L": length,
        "n_plants": int(planted.size),
        "with_boundaries": {
            "planted_mean": float(planted.mean()),
            "separation_sd_units": sep(planted, page_fit["null"]),
            "power_claim": _power_at(planted, page_fit["bars"]["claim"]["bar"]),
            "null": "page-start masks",
        },
        "score_boundaries_false": {
            "planted_mean": float(planted_var.mean()),
            "null": var_fit["null"],
            "fit": var_fit["fit"],
            "separation_sd_units": sep(planted_var, var_fit["null"]),
            "power_claim": _power_at(planted_var, var_fit["bars"]["claim"]["bar"]),
            "measured_once": True,
        },
    }
    nb = [s for s in cfg.scorers if s.startswith("kn8-cicada") and not presets.is_wb(s)]
    if nb:
        nbs = get_scorer(nb[0])
        null_nb = None
        for c in (nulls or {}).get("cells", []):
            if c["scorer"] == nb[0] and c["L"] == length:
                null_nb = c
        if null_nb is None:
            s = uniform_scores(nbs, length, min(cfg.draws, 25_000))
            null_nb = fit_scores(s, s.size, rng_for(9, length, 4))
        p_nb = nbs.score_batch(w["plains"])
        gain["no_boundary_model"] = {
            "scorer": nb[0],
            "planted_mean": float(p_nb.mean()),
            "separation_sd_units": sep(p_nb, null_nb["null"]),
            "power_claim": _power_at(p_nb, null_nb["bars"]["claim"]["bar"]),
        }
    gain["gain_separation_vs_variant"] = (
        gain["with_boundaries"]["separation_sd_units"]
        - gain["score_boundaries_false"]["separation_sd_units"]
    )
    return {
        "scorer": name,
        "L": length,
        "page_start_masks": {
            "n_masks": len(masks),
            "draws_per_mask": per,
            "per_mask": per_mask,
            "mean_of_means": float(means.mean()),
            "sd_of_means": float(means.std(ddof=1)) if means.size > 1 else float("nan"),
            "range_of_means": [float(means.min()), float(means.max())],
            **page_fit,
        },
        "sampled_masks": sampled,
        "dependence": {
            "sd_of_mask_means_over_pooled_sd": (
                float(means.std(ddof=1) / page_fit["null"]["sd"])
                if means.size > 1 and page_fit["null"]["sd"] > 0
                else float("nan")
            ),
            "bar_claim_page_start_minus_sampled": (
                page_fit["bars"]["claim"]["bar"] - sampled["bars"]["claim"]["bar"]
            ),
        },
        "gain": gain,
        "seconds": round(time.time() - t0, 1),
    }


# ----------------------------------------------------------------------------- section: order


def section_order(cfg: Scale, nulls: dict | None, power: dict | None) -> dict:
    """Per KN preset: order, dense levels, training size, discounts and their source; the
    order comparison at the reference length from the nulls and power sections."""
    ref_l = 240 if 240 in cfg.lengths else cfg.lengths[0]
    presets_out = []
    for name in cfg.scorers:
        spec = presets.PRESETS[name]
        s = get_scorer(name)
        row = {
            "preset": name,
            "model": presets.model_of(name),
            "order": spec["order"],
            "train": spec["train"],
            "exclude": spec.get("exclude", []),
            "beam_compatible": presets.beam_compatible(name),
        }
        if presets.model_of(name) == "kn":
            row.update(
                {
                    "base": s.base,
                    "dense_levels": s.dense_levels,
                    "boundary": s.boundary,
                    "n_runes": s.training.get("n_runes"),
                    "split": spec.get("split", {}).get("rule") if spec.get("split") else None,
                    "discounts": [[round(float(x), 4) for x in r] for r in s.discounts],
                    "discount_source": s.discount_source,
                    "sparse_entries": [int(x.keys.size) for x in s.sparse],
                    "table_bytes": _table_bytes(s),
                    "fingerprint": s.fingerprint(),
                }
            )
        presets_out.append(row)
    comparison = []
    null_by = {(c["scorer"], c["L"]): c for c in (nulls or {}).get("cells", [])}
    pow_by = {(r["scorer"], r["L"], r["register"]): r for r in (power or {}).get("rows", [])}
    register = "cicada-english" if "cicada-english" in cfg.registers else cfg.registers[0]
    for name in cfg.scorers:
        c = null_by.get((name, ref_l))
        p = pow_by.get((name, ref_l, register))
        comparison.append(
            {
                "scorer": name,
                "order": presets.PRESETS[name]["order"],
                "L": ref_l,
                "register": register,
                "null_mean": c["null"]["mean"] if c else None,
                "null_sd": c["null"]["sd"] if c else None,
                "beta": c["fit"]["beta"] if c else None,
                "bar_claim": c["bars"]["claim"]["bar"] if c else None,
                "planted_mean": p["planted_mean"] if p else None,
                "power_claim": p["claim"]["power"] if p and "claim" in p else None,
                "separation_sd_units": (
                    (p["planted_mean"] - c["null"]["mean"]) / c["null"]["sd"]
                    if p and c and c["null"]["sd"] > 0
                    else None
                ),
            }
        )
    return {"presets": presets_out, "comparison": comparison, "reference_L": ref_l}


def _table_bytes(s) -> int:
    n = sum(t.nbytes for t in s.dense_lp)
    if s.dense_bow is not None:
        n += s.dense_bow.nbytes
    return n + sum(x.keys.nbytes + x.lp.nbytes + x.bow.nbytes for x in s.sparse)


# ----------------------------------------------------------------------------- section: throughput


def _time_scorer(s, name: str, wb: bool, cfg: Scale, rng, pool) -> dict:
    row = {"scorer": name, "model": "kn" if hasattr(s, "dense_levels") else "ngram"}
    if row["model"] == "kn":
        row.update(
            {"order": s.order, "dense_levels": s.dense_levels, "table_bytes": _table_bytes(s)}
        )
    for length, n in zip((240, 1000), cfg.throughput_rows, strict=True):
        x = rng.integers(0, ALPHABET, (n, length))
        starts = boundaries.sample_starts(rng_for(10, length), length, pool) if wb else None
        kw = {"starts": starts} if wb else {}
        s.score_batch(x[:50], **kw)
        best = math.inf
        for _ in range(2):
            t0 = time.perf_counter()
            s.score_batch(x, **kw)
            best = min(best, time.perf_counter() - t0)
        row[f"keys_per_s_L{length}"] = n / best
        row[f"rows_L{length}"] = n
    print(
        f"  throughput {name:18s} L240 {row['keys_per_s_L240']:,.0f} keys/s "
        f"L1000 {row['keys_per_s_L1000']:,.0f} keys/s",
        flush=True,
    )
    return row


def _kn8_d5():
    """kn8-cicada refitted with five dense levels (82 MB level 5): the D = 4 vs 5 comparison
    of the design's section 0, an ad-hoc model that is never a preset."""
    from runeforge.scoring import kn_fit
    from runeforge.scoring.kn import KNScorer

    spec = presets.PRESETS["kn8-cicada"]
    est = kn_fit.estimate(presets._kn_sequences(spec), 8, base=29, dense_levels=5, boundary=None)
    return KNScorer.from_estimate(est, {"preset": "kn8-cicada@D5", "corpora": spec["train"]})


def _ratio(a: dict, b: dict) -> dict:
    return {
        "D4": a,
        "D5": b,
        "ratio_L240": b["keys_per_s_L240"] / a["keys_per_s_L240"],
        "ratio_L1000": b["keys_per_s_L1000"] / a["keys_per_s_L1000"],
    }


def section_throughput(cfg: Scale) -> dict:
    """score_batch keys/s per scorer at L 240 and 1000 (best of two timings after a warm
    call). D = 4 vs 5: kn8-cicada (D = 4, pinned) against the same fit with five dense
    levels (``sparse``), and the dense kn4-cicada against kn5-cicada (``dense``)."""
    rng = np.random.default_rng(SEED)
    pool = boundaries.lp2_word_lengths()
    rows = [
        _time_scorer(get_scorer(name), name, presets.is_wb(name), cfg, rng, pool)
        for name in cfg.scorers
    ]
    by = {r["scorer"]: r for r in rows}
    d45 = {}
    if "kn8-cicada" in by:
        t0 = time.time()
        d5 = _time_scorer(_kn8_d5(), "kn8-cicada@D5", False, cfg, rng, pool)
        d5["ad_hoc"] = "kn8-cicada refitted with dense_levels=5; not a preset"
        d5["fit_and_time_seconds"] = round(time.time() - t0, 1)
        rows.append(d5)
        d45["sparse"] = _ratio(by["kn8-cicada"], d5)
    if "kn4-cicada" in by and "kn5-cicada" in by:
        d45["dense"] = _ratio(by["kn4-cicada"], by["kn5-cicada"])
    return {
        "rows": rows,
        "d4_vs_d5": d45 or None,
        "host": platform.processor() or platform.machine(),
    }


# ----------------------------------------------------------------------------- static sections


def section_reusable(cfg: Scale) -> dict:
    return {
        "canon": {"sha256": CANON_SHA256, "runes": 12956, "numbering": NUMBERING},
        "scorers": {
            "module": "runeforge/scoring/presets.py",
            "ngram": [s for s in cfg.scorers if presets.model_of(s) == "ngram"],
            "kn": [s for s in cfg.scorers if presets.model_of(s) == "kn"],
        },
        "model": ["runeforge/scoring/kn.py", "runeforge/scoring/kn_fit.py"],
        "boundaries": "runeforge/scoring/boundaries.py",
        "nulls": ["runeforge/scoring/calib/__init__.py", "runeforge/scoring/beam_calib.py"],
        "fits": "reports/scorer_power/fits/ (scale-marked, never installable unless full)",
        "export": "scripts/export_kn.py (knx-1; runeforge/gpu/kernels/README.md)",
        "tests": ["tests/test_kn.py", "tests/test_scorer_power.py"],
        "validators": ["scripts/check_results.py", "scripts/validate_ledger.py"],
        "families": [f.name for f in FAMILIES],
    }


def section_not_covered(cfg: Scale, data: dict) -> list[str]:
    out = []
    if cfg.name != "full":
        out.append(
            f"scale {cfg.name}: {cfg.draws:,} null draws per (scorer, L) and {cfg.plants} plants "
            "per cell; the 10^6-draw fits that TOOLBOX_REQUESTS.md TR-7 installs are --full"
        )
    if cfg.name == "smoke":
        out.append("smoke: one register, one length, three scorers; nothing here is a measurement")
    missing_s = [s for s in SCORERS if s not in cfg.scorers]
    if missing_s:
        out.append(f"scorers not run at this scale: {', '.join(missing_s)}")
    missing_r = [r for r in REGISTERS if r not in cfg.registers]
    if missing_r:
        out.append(f"registers not run at this scale: {', '.join(missing_r)}")
    missing_l = [x for x in LENGTHS if x not in cfg.lengths]
    if missing_l:
        out.append(f"lengths not run at this scale: {missing_l}")
    if SOLVED_REGISTER in cfg.registers:
        out.append(f"{SOLVED_REGISTER}: L > {SOLVED_MAX_L} not covered (1,533 held-out runes)")
    trained = sorted(
        {
            (r["scorer"], r["register"])
            for r in data.get("power", {}).get("rows", [])
            if not r["held_out"]
        }
        if data.get("power")
        else set()
    )
    for s, r in trained:
        out.append(f"{s} x {r}: plant text is training text (no split); the cell is not a power")
    overlap = sorted(
        {
            (c["register"], c["L"], c["n_plants"], c["n_offsets"], c["n_disjoint"])
            for c in (data.get("power") or {}).get("cells", [])
            if c.get("n_disjoint") is not None and c["n_disjoint"] < c["n_plants"]
        },
        key=lambda t: (REGISTERS.index(t[0]), t[1]),
    )
    for reg, length, n_pl, n_off, n_dis in overlap:
        out.append(
            f"{reg} at L = {length}: {n_pl} plants at distinct offsets out of {n_off} the "
            f"register holds, but only {n_dis} windows can be disjoint, so the plants overlap "
            "and their Wilson intervals are nominal (the point estimates stand; the interval "
            "is not one over independent plants)"
        )
    excluded = [f.name for f in FAMILIES if not f.in_equality_claim]
    out.append(
        f"wrong-key nulls: {', '.join(excluded)} are outside the 'wrong key = uniform string' "
        "claim (a partially matching periodic key leaves structure; a wrong atbash/shift key "
        "is a substitution of the plaintext; a wrong totient start is another offset of one "
        "non-uniform stream); their KS statistics are reported, not asserted, and the finite "
        "families also report the count above the Gumbel bar at N = their key count"
    )
    if any(presets.is_wb(s) for s in cfg.scorers):
        out.append(
            "wrong-key nulls of the wb scorer carry the cipher window's own mask while null (a) "
            "averages over sampled masks, so their KS statistic measures the mask dependence "
            "of section 6 as well; the 'wrong key = uniform string' claim is for the nb scorers"
        )
    out.append(
        "the power rows measure the scorer on rigid-exact decodes (the true key of an "
        "additive family returns the plaintext); interrupters and anti-repeat skips are "
        f"measured in the beam cells only, at L {cfg.beam_lengths} with "
        f"{', '.join(cfg.beam_scorers)}; no kn6/kn8 preset pairs with a beam decoder"
    )
    out.append(
        "mt19937-py27 streams (the template lane's generator) share the combine/view code "
        "path of the two stream generators measured and are not drawn here"
    )
    out.append(
        "kn8-cicada-wb: adjudication/report-only; its null depends on the window's mask "
        "(section 6) and no lane names it with any decoder"
    )
    out.append("no GPU: every number is the numpy path; the CUDA kernel is Phase 3")
    out.append(
        "no key space of the unsolved pages is searched here: this is an instrument "
        "report, not a lane; coverage of LP2 is 0 of every space"
    )
    return out


def section_conditionals(cfg: Scale, data: dict) -> dict:
    rows = data.get("power", {}).get("rows", []) if data.get("power") else []
    latin = [
        r
        for r in rows
        if r["register"] == "latin"
        and r["held_out"]
        and "claim" in r
        and r["L"] == 240
        and r["scorer"] not in REGISTER_SCORERS  # the claim scorers only (English register)
    ]
    best_latin = max(latin, key=lambda r: r["claim"]["power"]) if latin else None
    return {
        "key_space_swept": (
            "none of LP2: the families (section 2) are the plant/decoy generators of the "
            "measurement; no seed range of any lane was searched"
        ),
        "decoder_transition_model": (
            "rigid (one key symbol per rune) for every power row; beam, beam-skip and "
            "beam-skip-int at width 8 (presets.DECODER_PARAMS) in the beam cells, with the "
            "three dense scorers only"
        ),
        "adjudicator_register": (
            "the scorers listed in section 0: Cicada-English, general English, Latin, "
            "Old English and vowel-dropped English registers (kn8-*), plus the Phase 1 "
            "order-3 baselines; power is reported per register x scorer (section 4)"
        ),
        "latin_power_at_240": (
            None
            if best_latin is None
            else {
                "scorer": best_latin["scorer"],
                "power": best_latin["claim"]["power"],
                "ci": best_latin["claim"]["ci"],
            }
        ),
        "standing_conditional": (
            "every later negative is English-register-first: a Latin or other non-English "
            "plaintext is detected only to the power this table measures for that register "
            "(SESSION_PROMPT.md section B)"
        ),
        "reopens_if": [
            "a scorer's fingerprint changes (a refit, a corpus rebuild that moves the split)",
            "the --full run moves a bar by more than its bootstrap interval",
            "a lane needs a length, register or decoder pairing not in this table",
            "a word-boundary conditioning rule is staged (the wb null is mask-dependent)",
            "a beam-compatible kn6/kn8 export lands on the GPU (the dense/sparse split moves)",
        ],
    }


def section_reproduce(
    cfg: Scale, argv: list[str], timings: dict, fits_dir: Path, carry: list[str] | None = None
) -> dict:
    """``carry`` is the run's own ``--out`` / ``--fits-dir`` / ``--workers`` (when given), so
    the per-section commands merge into this run's JSON and not into the default path."""
    tail = "".join(f" {a}" for a in (carry or []))
    return {
        "command": "python scripts/scorer_power.py " + " ".join(argv),
        "git_sha": _git_sha(),
        "canon_sha256": CANON_SHA256,
        "numbering": NUMBERING,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "beam_sha256": beam_calib.beam_sha256(),
        "fits_dir": _rel(fits_dir),
        "staging_dir": _rel(STAGING) if cfg.stage else None,
        "section_commands": {
            s: f"python scripts/scorer_power.py --{'quick' if cfg.name == 'reduced' else cfg.name}"
            f" --section {s}{tail}"
            for s in SECTIONS
        },
        "timings_s": timings,
        "scale": asdict(cfg),
    }


def _git_sha() -> str | None:
    r = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return r.stdout.strip() or None


# ----------------------------------------------------------------------------- renderer


def fmt(x, nd: int = 4) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, int):
        return f"{x:,}"
    if isinstance(x, float):
        return f"{x:.{nd}f}".replace("-", "−") if math.isfinite(x) else "n/a"
    if isinstance(x, list) and len(x) == 2 and all(isinstance(v, int | float) for v in x):
        return f"[{fmt(x[0], nd)}, {fmt(x[1], nd)}]"
    return str(x)


def mb(n) -> str:
    return fmt(n / 1e6, 1) if n else "n/a"


def pw(p: dict, nd: int = 3) -> str:
    """power [Wilson]"""
    return f"{fmt(p['power'], nd)} {fmt(p['ci'], nd)}"


def bar_ci(b: dict) -> str:
    return f"{fmt(b['bar'])} {fmt(b['ci'])}"


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def banned_lines(text: str) -> list[str]:
    """The banned-word check of scripts/check_results.py (its BANNED list and the two
    exemptions it applies), line by line."""

    def blank(m):
        return " " * len(m[0])

    out = []
    for i, line in enumerate(text.splitlines(), 1):
        window = check_results.SOLVED_OK.sub(blank, check_results.PATHLIKE.sub(blank, line))
        out += [
            f"line {i}: banned word '{m[1].lower()}'" for m in check_results.BANNED.finditer(window)
        ]
    return out


def _cap(data: dict, key: str, section: str, extra: str = "") -> str:
    """The caption under every table (design section 6): numbering, canon SHA-256, git SHA,
    scale, N, the JSON key and the regenerating command."""
    rp = data["sections"].get("reproduce")
    cmd = (
        rp["section_commands"][section]
        if rp
        else f"python scripts/scorer_power.py --section {section}"
    )
    tail = f" · {extra}" if extra else ""
    git = (data.get("git_sha") or "uncommitted")[:12]
    return (
        f"*numbering {NUMBERING} · canon `{CANON_SHA256[:12]}…` · git `{git}` · "
        f"scale {data['scale']} · N_claim = 10^6, N_family = 2^32, alpha = {ALPHA} · "
        f"JSON `{key}` · `{cmd}`{tail}*"
    )


def _train_name(t: str, p: dict) -> str:
    if t != "lp-solved":
        return t
    return "the seven solved sections" if p["exclude"] else "the nine solved sections"


def _row_null(c):
    chk = fmt(c["check"].get("max_error"), 3) if c["check"] else "n/a"
    return [
        c["scorer"], c["L"], fmt(c["null"]["mean"]), fmt(c["null"]["sd"]),
        fmt(c["fit"]["mu_block"]), fmt(c["fit"]["beta"]), c["fit"]["n_blocks"],
        bar_ci(c["bars"]["claim"]), bar_ci(c["bars"]["family"]),
        fmt(c["ks_max_in_claim"], 3), fmt(c["ks_max_excluded"], 3), chk,
    ]  # fmt: skip


def _row_scale(c):
    k = c["scale_check"]
    return [
        c["scorer"], c["L"], f"{k['source']} `{k['file']}`", fmt(k["installed_draws"]),
        f"{fmt(k['installed_mu_block'])} / {fmt(k['installed_beta'])}",
        f"{fmt(k['refit_mu_block'])} / {fmt(k['refit_beta'])}",
        fmt(k["delta_bar_claim"]), fmt(k["delta_bar_family"]),
        fmt(k["installed_bar_claim_in_refit_ci"]),
        "same" if k["fingerprint_matches"] else "DIFFERS",
    ]  # fmt: skip


def _row_wrong(w):
    keys = fmt(w.get("n_keys")) if w.get("n_keys") else "2^32+"
    at_keys = (
        f"{w['above_bar_at_n_keys']} (bar {fmt(w['bar_at_n_keys'])})"
        if w.get("above_bar_at_n_keys") is not None
        else "n/a"
    )
    return [
        w["family"], w["n"], keys, fmt(w["mean"]), fmt(w["sd"]), fmt(w["max"]),
        fmt(w["ks_vs_uniform"], 3),
        fmt(w["ks_crit_05"], 3), fmt(w["in_equality_claim"]), w["above_claim_bar"], at_keys,
    ]  # fmt: skip


def _row_power(r):
    return [
        r["register"], r["L"], r["scorer"], fmt(r["held_out"]),
        f"{fmt(r['planted_mean'])} ({fmt(r['planted_sd'], 3)}, {fmt(r['planted_min'])})",
        fmt(r["claim"]["bar"]), pw(r["claim"]),
        f"{fmt(r['claim_ci_low_bar']['power'], 3)} / {fmt(r['claim_ci_high_bar']['power'], 3)}",
        fmt(r["family"]["power"], 3), f"{r['rank1']['rank1']}/{r['rank1']['n']}", r["target_line"],
    ]  # fmt: skip


def _row_beam_null(n):
    sc = n.get("scale_check")
    return [
        n["scorer"], n["decoder"], n["L"], fmt(n["draws"]), fmt(n["canonical_F"]),
        fmt(n["null"]["mean"]),
        fmt(n["null"]["sd"]), fmt(n["fit"]["mu_block"]), fmt(n["fit"]["beta"]),
        bar_ci(n["bars"]["claim"]), fmt(n["bars"]["family"]["bar"]),
        f"{sc['source']} {fmt(sc['delta_bar_claim'])}" if sc else "none",
    ]  # fmt: skip


def _row_beam_cell(c):
    return [
        c["scorer"], c["decoder"], c["forward_model"], c["L"], f"{c['identified']}/{c['n_plants']}",
        f"{c['rank1']}/{c['n_plants']}", fmt(c["median_recovery"], 3),
        f"{fmt(c['planted_mean'])} ({fmt(c['planted_min'])})", fmt(c["best_decoy_max"]),
        pw(c["claim"]), fmt(c["family"]["power"], 3), fmt(c["runnable_pairing"]),
    ]  # fmt: skip


def _row_wb_null(name, n):
    return [
        name, n["null"]["n"], fmt(n["null"]["mean"]), fmt(n["null"]["sd"]),
        fmt(n["fit"]["mu_block"]),
        fmt(n["fit"]["beta"]), bar_ci(n["bars"]["claim"]), fmt(n["bars"]["family"]["bar"]),
    ]  # fmt: skip


def _row_variant(name, v):
    return [name, fmt(v["planted_mean"]), fmt(v["separation_sd_units"], 2), pw(v["power_claim"])]


def _row_preset(p):
    disc = (
        "; ".join("/".join(fmt(x, 3) for x in r) for r in p["discounts"])
        if p.get("discounts")
        else "n/a"
    )
    return [
        p["preset"], p["model"], p["order"], fmt(p.get("base")), fmt(p.get("dense_levels")),
        ", ".join(_train_name(t, p) for t in p["train"]), fmt(p.get("n_runes")), disc,
        ", ".join(p["discount_source"]) if p.get("discount_source") else "n/a",
        str(p.get("sparse_entries", "n/a")), mb(p.get("table_bytes")),
    ]  # fmt: skip


def _row_cmp(c):
    return [
        c["scorer"], c["order"], fmt(c["null_mean"]), fmt(c["null_sd"]), fmt(c["beta"]),
        fmt(c["bar_claim"]),
        fmt(c["planted_mean"]), fmt(c["separation_sd_units"], 2), fmt(c["power_claim"], 3),
    ]  # fmt: skip


def _row_tp(r):
    return [
        r["scorer"], fmt(r.get("order")), fmt(r.get("dense_levels")), mb(r.get("table_bytes")),
        f"{r['keys_per_s_L240']:,.0f}", f"{r['keys_per_s_L1000']:,.0f}",
    ]  # fmt: skip


def _conf_cell(by: dict, s: str) -> str:
    if s not in by:
        return "n/a"
    v = by[s]
    return f"{fmt(v['planted_mean'], 3)} ({fmt(v['power_claim'], 2)})" + (
        "" if v["held_out"] else " t"
    )


H_NULL = ["scorer", "L", "null mean", "sd", "mu_b", "beta", "blocks", "bar@10^6 [CI]",
          "bar@2^32 [CI]", "max KS (claim)", "max KS (excluded)", "check err"]  # fmt: skip
H_SCALE = ["scorer", "L", "record", "draws", "installed mu_b / beta", "refit mu_b / beta",
           "delta bar@10^6", "delta bar@2^32", "installed bar in refit CI",
           "fingerprint"]  # fmt: skip
H_WRONG = ["family", "n", "keys", "mean", "sd", "max", "KS vs uniform", "KS crit 0.05",
           "in claim", "above bar@10^6", "above bar@keys"]  # fmt: skip
H_POWER = ["register", "L", "scorer", "held out", "planted mean (sd, min)", "bar@10^6",
           "power [Wilson]", "power @ CI bars", "power@2^32", "rank-1", "target"]  # fmt: skip
H_BNULL = ["scorer", "decoder", "L", "draws", "canonical F", "null mean", "sd", "mu_b", "beta",
           "bar@10^6 [CI]", "bar@2^32", "scale check (delta bar@10^6)"]  # fmt: skip
H_BCELL = ["scorer", "decoder", "forward model", "L", "identified", "rank-1", "median recovery",
           "planted mean (min)", "best decoy", "power@10^6 [Wilson]", "power@2^32",
           "runnable"]  # fmt: skip
H_WBNULL = ["null", "n", "mean", "sd", "mu_b", "beta", "bar@10^6 [CI]", "bar@2^32"]
H_VARIANT = ["variant", "planted mean", "separation (null sd units)", "power@10^6 [Wilson]"]
H_PRESET = ["preset", "model", "order", "B", "D", "train", "runes", "discounts D1/D2/D3+ per level",
            "source per level", "sparse entries", "table MB"]  # fmt: skip
H_CMP = ["scorer", "order", "null mean", "null sd", "beta", "bar@10^6", "planted mean",
         "separation (sd units)", "power@10^6"]  # fmt: skip
H_TP = ["scorer", "order", "D", "table MB", "keys/s L=240", "keys/s L=1000"]


def render(data: dict) -> str:
    S = data["sections"]
    cfg = Scale(**data["config"])
    git = data.get("git_sha") or "uncommitted"
    rp = S.get("reproduce")
    cmd = rp["command"] if rp else "python scripts/scorer_power.py"
    L = ["not a solve", ""]
    L += ["# The scorer power harness (`scripts/scorer_power.py`) — instrument report", ""]
    L.append(
        "**Not a solve.** This report measures instruments: how a wrong key scores under each "
        "scorer preset, where the bars sit at N = 10^6 and 2^32, and how often a planted correct "
        "key clears them. No key space of the unsolved pages was searched and nothing here is a "
        "decode of LP2."
    )
    L.append("")
    L.append(
        f'numbering: "{NUMBERING}" · canon SHA-256 `{CANON_SHA256}` (12,956 runes, LP2 pages '
        f"0–55) · git `{git}` · scale **{data['scale']}** · created "
        f"{data['created']} · `{cmd}` → `{data['json_path']}`"
    )
    if data["scale"] != "full":
        L.append("")
        L.append(
            f"This is the **{data['scale']}-scale** report: {cfg.draws:,} null draws per "
            f"(scorer, L) and {cfg.plants} plants per cell. The bars are reduced-scale bars until "
            "`--full` (10^6 draws, Hunter's call) writes the installable records "
            "(TOOLBOX_REQUESTS.md TR-7); the fits under `reports/scorer_power/fits/` are marked "
            "`scale` and are never installed."
        )
    # 0 reusable
    L += ["", "## 0. Reusable parts", ""]
    r = S.get("reusable")
    if r:
        code = ", ".join
        presets_line = f"ngram {code(r['scorers']['ngram'])}; kn {code(r['scorers']['kn'])}"
        rows = [
            ["canon", f"`{r['canon']['sha256']}`, {r['canon']['runes']:,} runes, `{NUMBERING}`"],
            ["scorer presets", f"`{r['scorers']['module']}`: {presets_line}"],
            ["model", code(f"`{m}`" for m in r["model"])],
            ["word-start masks", f"`{r['boundaries']}`"],
            ["nulls and fits", code(f"`{m}`" for m in r["nulls"])],
            ["fit records", r["fits"]],
            ["export", r["export"]],
            ["tests", code(f"`{m}`" for m in r["tests"])],
            ["validators", code(f"`{m}`" for m in r["validators"])],
            ["families (plant/decoy generators)", code(r["families"])],
        ]  # fmt: skip
        L += [table(["part", "where"], rows), "", _cap(data, "sections.reusable", "reusable")]
    # 1 not covered
    L += ["", "## 1. Not covered", ""]
    L += [f"- {item}" for item in S.get("not_covered") or ["(section not run)"]]
    L += ["", _cap(data, "sections.not_covered", "not_covered")]
    # 2 nulls
    L += ["", "## 2. Nulls and bars", ""]
    nulls = S.get("nulls")
    if nulls:
        L.append(
            f"Null (a): {nulls['draws_per_cell']:,} uniform random strings per (scorer, L) "
            "(`calib.measure`); Gumbel fit on block maxima (block 1,000), 200-resample bootstrap "
            "of the block maxima for the intervals. Null (b): "
            f"{nulls['wrong_key_draws_per_family']:,} wrong-key decodes per family on the real "
            "code paths (a finite family enumerates or draws its wrong keys without "
            "replacement), KS statistic against (a) (reported; the families marked `in claim: "
            "no` are outside the equality claim, section 1)."
            + (
                f" Cells at L {nulls['scale_check_lengths']} are scale-check-only (an "
                "installed record exists there; no wrong-key null, no power row)."
                if nulls.get("scale_check_lengths")
                else ""
            )
        )
        L += ["", table(H_NULL, [_row_null(c) for c in nulls["cells"]]), ""]
        L.append(
            _cap(data, "sections.nulls.cells[*] (null, fit, bars, ks_max_in_claim, check)", "nulls")
        )
        sc = [c for c in nulls["cells"] if c.get("scale_check")]
        if sc:
            L += ["", "Scale check: the installed / staged record against this run's refit.", ""]
            L += [table(H_SCALE, [_row_scale(c) for c in sc]), ""]
            L.append(_cap(data, "sections.nulls.cells[*].scale_check", "nulls"))
        L += [
            "",
            "Wrong-key nulls per family (null b), the nb cell with the largest KS in the claim "
            "(the wb cell's KS carries the mask dependence of section 6 and is printed there):",
            "",
        ]
        nb_cells = [c for c in nulls["cells"] if not presets.is_wb(c["scorer"])]
        worst = max(
            nb_cells or nulls["cells"],
            key=lambda c: c["ks_max_in_claim"] if math.isfinite(c["ks_max_in_claim"]) else -1,
        )
        L += [table(H_WRONG, [_row_wrong(w) for w in worst["wrong_key"]]), ""]
        key = f"sections.nulls.cells[scorer={worst['scorer']}, L={worst['L']}].wrong_key"
        L.append(_cap(data, key, "nulls"))
    else:
        L.append("(section not run)")
    # 3 power
    L += ["", "## 3. Power table", ""]
    power = S.get("power")
    if power:
        L.append(
            f"{power['plants_per_cell']} plants per (register, L): random held-out windows, a "
            "random key per family, encrypt, decode with the true key (asserted equal to the "
            "plaintext for every rigid additive family), scored under every scorer. Power = "
            "share of plants above the bar; Wilson 95 % intervals; power at the bootstrap "
            "bars too. The target line is the spec's (>= 0.9 English, >= 0.5 Latin / "
            "vowel-dropped), printed per cell, never as a verdict word. A cell whose plant "
            "text is training text is marked and is not a power. Plants sit at distinct "
            "offsets; where the register holds fewer disjoint windows than plants (the "
            "1,533-rune heldout-solved-sections register at L >= 263, section 1) they overlap and "
            "the Wilson interval is nominal."
        )
        rows = [r for r in power["rows"] if "claim" in r]
        L += ["", table(H_POWER, [_row_power(r) for r in rows]), ""]
        key = "sections.power.rows[*] (claim.power, claim.ci, family.power, rank1)"
        L.append(_cap(data, key, "power", f"{power['plants_per_cell']} plants per cell"))
        if len(rows) < len(power["rows"]):
            L += [
                "",
                "Rows without a bar (the nulls section did not run for that scorer and L) are "
                "in the JSON only.",
            ]
    else:
        L.append("(section not run)")
    # 4 confusion
    L += ["", "## 4. Register confusion matrix", ""]
    conf = S.get("confusion")
    if conf:
        for length, block in conf["lengths"].items():
            scorers = sorted({s for by in block["matrix"].values() for s in by})
            L.append(
                f"L = {length}: planted mean under each scorer (power at the bar@10^6 in "
                "brackets; `t` = trained-on text, not a power)"
            )
            rows = [
                [reg, *[_conf_cell(by, s) for s in scorers]] for reg, by in block["matrix"].items()
            ]
            L += ["", table(["register \\ scorer", *scorers], rows), ""]
            best = ", ".join(f"{k} → {v}" for k, v in block["best_held_out_scorer"].items())
            L += [f"best held-out scorer per register: {best}", ""]
        L.append(_cap(data, "sections.confusion.lengths[L].matrix", "confusion"))
    else:
        L.append("(section not run)")
    # 5 beam
    L += ["", "## 5. Beam cells", ""]
    beam = S.get("beam")
    if beam:
        L.append(
            f"Nulls: {beam['draws']:,} draws per (scorer, decoder, L) for the beam decoders "
            "(`beam_calib` decodes under uniform keys of doublet-free ciphers at the fit's "
            "canonical F count); the rigid rows reuse the nulls section's cell at the same "
            "(scorer, L) where it exists (one rigid bar per (scorer, L) in this report; the "
            "`draws` column says which), and are uniform strings at the beam draw count "
            "otherwise."
        )
        L += ["", table(H_BNULL, [_row_beam_null(n) for n in beam["nulls"]]), ""]
        L.append(_cap(data, "sections.beam.nulls[*]", "beam"))
        L.append("")
        L.append(
            "Plants: held-out solved-section text through `pipeline.encrypt` under the forward "
            "model, decoded with the true seed and the decoys by the preset's decoder "
            "(`pipeline.decrypt`); identified = rank 1 and recovery >= 0.90. A pairing the lane "
            "spec refuses (`decoder_problems`) is still measured and marked."
        )
        L += ["", table(H_BCELL, [_row_beam_cell(c) for c in beam["cells"]]), ""]
        n_pl = beam["cells"][0]["n_plants"] if beam["cells"] else 0
        L.append(
            _cap(
                data,
                "sections.beam.cells[*]",
                "beam",
                f"{n_pl} plants x {cfg.beam_decoys} decoys per cell",
            )
        )
    else:
        L.append("(section not run)")
    # 6 boundaries
    L += ["", "## 6. Boundaries", ""]
    b = S.get("boundaries")
    if b and not b.get("skipped"):
        ps, sm, g, d = b["page_start_masks"], b["sampled_masks"], b["gain"], b["dependence"]
        L.append(
            f"`{b['scorer']}` at L = {b['L']}: null (d) under the {ps['n_masks']} page-start "
            f"masks ({ps['draws_per_mask']:,} strings each) and under masks sampled from the "
            "LP2 word-length histogram (the nulls table's wb row). Boundary log-probs are summed "
            "and divided by L = cipher runes; the `score_boundaries=False` variant is measured "
            "once."
        )
        rows = [_row_wb_null("page-start masks", ps), _row_wb_null("sampled masks", sm)]
        L += ["", table(H_WBNULL, rows), ""]
        L.append(
            f"Mask dependence: per-mask means range {fmt(ps['range_of_means'])}, sd of the mask "
            f"means {fmt(ps['sd_of_means'])} = {fmt(d['sd_of_mask_means_over_pooled_sd'], 3)} "
            f"pooled sd; bar@10^6 page-start minus sampled "
            f"{fmt(d['bar_claim_page_start_minus_sampled'])}."
        )
        rows = [
            _row_variant("boundaries summed (wb)", g["with_boundaries"]),
            _row_variant("score_boundaries=False (wb, measured once)", g["score_boundaries_false"]),
        ]
        if g.get("no_boundary_model"):
            m = g["no_boundary_model"]
            rows.append(_row_variant(f"no boundary model ({m['scorer']})", m))
        L += ["", table(H_VARIANT, rows), ""]
        L.append(
            "Gain of summing the boundaries over the variant: "
            f"{fmt(g['gain_separation_vs_variant'], 2)} "
            f"null-sd units ({g['register']}, L = {g['L']}, {g['n_plants']} plants)."
        )
        key = "sections.boundaries (page_start_masks, sampled_masks, dependence, gain)"
        L += ["", _cap(data, key, "boundaries")]
        wb_cells = [
            c
            for c in (nulls or {}).get("cells", [])
            if presets.is_wb(c["scorer"]) and c["wrong_key"]
        ]
        if wb_cells:
            c = max(wb_cells, key=lambda c: c["ks_max_all"])
            wkey = f"sections.nulls.cells[scorer={c['scorer']}, L={c['L']}].wrong_key"
            L += [
                "",
                f"Wrong-key nulls of the wb scorer (`{c['scorer']}`, L = {c['L']}): the decodes "
                "carry the cipher window's own mask while null (a) averages over sampled masks, "
                "so these KS statistics measure the mask dependence as well and are outside the "
                "'wrong key = uniform string' claim (section 1).",
                "",
                table(H_WRONG, [_row_wrong(w) for w in c["wrong_key"]]),
                "",
                _cap(data, wkey, "nulls"),
            ]
    else:
        L.append(f"({(b or {}).get('skipped') or 'section not run'})")
    # 7 order
    L += ["", "## 7. Order and discounts", ""]
    o = S.get("order")
    if o:
        L += [table(H_PRESET, [_row_preset(p) for p in o["presets"]]), ""]
        reg = o["comparison"][0]["register"] if o["comparison"] else ""
        L += [f"Order comparison at L = {o['reference_L']}, register {reg}:", ""]
        L += [table(H_CMP, [_row_cmp(c) for c in o["comparison"]]), ""]
        L.append(_cap(data, "sections.order.presets[*], sections.order.comparison[*]", "order"))
    else:
        L.append("(section not run)")
    # 8 throughput
    L += ["", "## 8. Throughput", ""]
    t = S.get("throughput")
    if t:
        L += [table(H_TP, [_row_tp(r) for r in t["rows"]]), ""]
        for kind, dd in (t.get("d4_vs_d5") or {}).items():
            what = (
                "kn8-cicada pinned at D = 4 vs the same fit with five dense levels (ad hoc)"
                if kind == "sparse"
                else "the dense kn4-cicada vs kn5-cicada"
            )
            L.append(
                f"- D = 4 vs 5, {kind} ({what}): D = 5 runs at {fmt(dd['ratio_L240'], 2)}x the "
                f"D = 4 keys/s at L = 240 and {fmt(dd['ratio_L1000'], 2)}x at L = 1000, with "
                f"{mb(dd['D5']['table_bytes'])} MB of tables against "
                f"{mb(dd['D4']['table_bytes'])} MB."
            )
        if not t.get("d4_vs_d5"):
            L.append(
                "D = 4 vs 5: not measured at this scale (kn8-cicada or kn4/kn5-cicada needed)."
            )
        extra = (
            f"score_batch, best of two timings, {cfg.throughput_rows[0]:,} / "
            f"{cfg.throughput_rows[1]:,} rows, host {t['host']}"
        )
        L += [
            "",
            _cap(
                data, "sections.throughput.rows[*].keys_per_s_L240, .d4_vs_d5", "throughput", extra
            ),
        ]
    else:
        L.append("(section not run)")
    # 9 conditionals
    L += ["", "## 9. The three conditionals and reopens_if", ""]
    c = S.get("conditionals")
    if c:
        L.append(f"- key space swept: {c['key_space_swept']}")
        L.append(f"- decoder transition model: {c['decoder_transition_model']}")
        L.append(f"- adjudicator register: {c['adjudicator_register']}")
        lp = c.get("latin_power_at_240")
        if lp:
            L.append(
                f"- Latin power at L = 240 under the English-register claim scorer with the "
                f"highest Latin power ({lp['scorer']}; ties go to the first listed): {pw(lp)} "
                "at the bar@10^6 (`sections.conditionals.latin_power_at_240`)"
            )
        L.append(f"- standing conditional: {c['standing_conditional']}")
        L.append("- reopens_if:")
        L += [f"  - {item}" for item in c["reopens_if"]]
        L += ["", _cap(data, "sections.conditionals", "conditionals")]
    else:
        L.append("(section not run)")
    # 10 reproduce
    L += ["", "## 10. Reproduce", ""]
    if rp:
        L.append(
            f"- `{rp['command']}` at git `{rp['git_sha']}`; canon SHA-256 `{rp['canon_sha256']}`, "
            f"numbering `{rp['numbering']}`; Python {rp['python']}, numpy {rp['numpy']}; "
            f"`runeforge/beam.py` SHA-256 `{rp['beam_sha256'][:12]}…`"
        )
        staged = f"; staged records: `{rp['staging_dir']}/`" if rp.get("staging_dir") else ""
        L.append(
            f"- fit records: `{rp['fits_dir']}/` (scale-marked; never installable unless "
            f"full){staged}"
        )
        L.append("- one section: " + ", ".join(f"`{v}`" for v in rp["section_commands"].values()))
        L.append(
            "- render only: `python scripts/scorer_power.py --render-only --out "
            f"{data['json_path']}`"
        )
        L.append(
            "- timings (s): " + ", ".join(f"{k} {fmt(v, 1)}" for k, v in rp["timings_s"].items())
        )
        L.append(
            "- do-not-re-run list: none (this harness writes no ledger row; its numbers are "
            "regenerated, never cited as coverage)"
        )
    else:
        L.append("(section not run)")
    L.append("")
    return "\n".join(L)


# ----------------------------------------------------------------------------- main


def run(
    cfg: Scale,
    sections: list[str],
    workers: int,
    out: Path,
    fits_dir: Path,
    argv,
    carry: list[str] | None = None,
) -> dict:
    data: dict = {}
    if out.exists() and set(sections) != set(SECTIONS):
        try:
            old = json.loads(out.read_text("utf-8"))
        except ValueError:
            old = {}
        if old.get("scale") == cfg.name:
            data = old
            print(f"merging into {_rel(out)} (scale {cfg.name})")
        else:
            print(f"{_rel(out)} is scale {old.get('scale')!r}; starting a fresh {cfg.name} JSON")
    S = data.setdefault("sections", {s: None for s in SECTIONS})
    timings = data.get("timings_s", {})
    data.update(
        {
            "not_a_solve": True,
            "numbering": NUMBERING,
            "canon_sha256": canon.read_pins()["indices:LP2:unsolved"].sha256,
            "git_sha": _git_sha(),
            "scale": cfg.name,
            "N_claim": N_CLAIM,
            "N_family": N_FAMILY,
            "alpha": ALPHA,
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "config": asdict(cfg),
            "json_path": _rel(out),
        }
    )
    if data["canon_sha256"] != CANON_SHA256:
        raise SystemExit(f"canon pin {data['canon_sha256']} != {CANON_SHA256}: state the delta")
    # the derived sections read power/nulls: run them after the measured ones, and recompute
    # them when they already exist, so a fresh run and a merged one say the same thing
    todo = [n for n in COMPUTE_ORDER if n in sections or (n in DERIVED and S.get(n) is not None)]
    for name in todo:
        t0 = time.time()
        print(f"{SECTIONS.index(name)}. {name}", flush=True)
        if name == "reusable":
            S[name] = section_reusable(cfg)
        elif name == "nulls":
            S[name] = section_nulls(cfg, workers, fits_dir)
        elif name == "power":
            S[name] = section_power(cfg, workers, S.get("nulls"))
        elif name == "confusion":
            S[name] = section_confusion(S.get("power"), cfg)
        elif name == "beam":
            S[name] = section_beam(cfg, workers, fits_dir, S.get("nulls"))
        elif name == "boundaries":
            S[name] = section_boundaries(cfg, S.get("nulls"))
        elif name == "order":
            S[name] = section_order(cfg, S.get("nulls"), S.get("power"))
        elif name == "throughput":
            S[name] = section_throughput(cfg)
        elif name == "not_covered":
            S[name] = section_not_covered(cfg, S)
        elif name == "conditionals":
            S[name] = section_conditionals(cfg, S)
        elif name == "reproduce":
            S[name] = section_reproduce(cfg, argv, timings, fits_dir, carry)
        timings[name] = round(time.time() - t0, 1)
        print(f"   {name}: {timings[name]} s", flush=True)
    data["timings_s"] = timings
    if S.get("reproduce"):
        S["reproduce"]["timings_s"] = timings
    return data


def write_outputs(data: dict, out: Path) -> Path:
    """Render and run the banned-word check first, then write the JSON and the markdown.
    On a banned word the JSON (the numbers; hours of draws at --full) is still written and a
    stale markdown beside it is removed, so the pair is never a fresh JSON next to an old
    report; the fix is a wording change and ``--render-only --out <json>``."""
    out.parent.mkdir(parents=True, exist_ok=True)
    md = out.with_suffix(".md")
    text = render(data)
    bad = banned_lines(text)
    out.write_text(json.dumps(data, indent=1, default=_json) + "\n", encoding="utf-8")
    if bad:
        if md.exists():
            md.unlink()
        raise SystemExit(
            f"the rendered report has banned words; {_rel(out)} written, {_rel(md)} not written "
            "(a stale copy was removed); fix the wording and re-render with --render-only:\n  "
            + "\n  ".join(bad)
        )
    md.write_text(text, encoding="utf-8")
    return md


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_true", help="reduced scale (default)")
    g.add_argument("--full", action="store_true", help="10^6 draws; records to calib-staging")
    g.add_argument("--smoke", action="store_true", help="the test scale (under a minute)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--section", action="append", choices=SECTIONS, help="run only these")
    ap.add_argument("--out", type=Path, default=None, help="JSON path (markdown beside it)")
    ap.add_argument("--fits-dir", type=Path, default=None)
    ap.add_argument("--render-only", action="store_true", help="render the markdown from --out")
    a = ap.parse_args(argv)
    cfg = SCALES["full" if a.full else "smoke" if a.smoke else "reduced"]
    carry = []  # the run's own paths / workers, carried into the per-section commands
    if a.out is not None:
        carry += ["--out", str(a.out)]
    if a.fits_dir is not None:
        carry += ["--fits-dir", str(a.fits_dir)]
    if a.workers != 4:
        carry += ["--workers", str(a.workers)]
    if a.out is None:
        a.out = (
            REPORTS / "scorer_power" / "smoke" / "scorer_power.json"
            if a.smoke
            else REPORTS / "scorer_power.json"
        )
    fits_dir = a.fits_dir or (a.out.parent / "fits" if a.smoke else a.out.with_suffix("") / "fits")
    if a.render_only:
        data = json.loads(a.out.read_text("utf-8"))
        md = write_outputs(data, a.out)
        print(f"rendered {_rel(md)}")
        return 0
    sections = a.section or SECTIONS
    t0 = time.time()
    data = run(cfg, sections, a.workers, a.out, fits_dir, argv, carry)
    md = write_outputs(data, a.out)
    print(f"wrote {_rel(a.out)} and {_rel(md)} ({time.time() - t0:.1f} s, scale {cfg.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
