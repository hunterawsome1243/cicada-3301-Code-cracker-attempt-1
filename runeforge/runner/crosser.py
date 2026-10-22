"""``runeforge crosser replay|escalate|reencipher <kid>``: HIT_PROTOCOL.md steps 2, 3 and 6.

A crosser is ``FLAGGED-FOR-ORACLE`` from the moment the sweep writes its ``.pending`` file;
these commands only ever append to ``runs/<lane>/crossers/<kid>.md`` and never declare more
than PARITY-FAIL / NOISE-CROSSER or "passes this step". Reading the plaintext is step 7 and
is not done here.
"""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

import numpy as np

from runeforge import canon
from runeforge.lanes import load_lane
from runeforge.runner import pipeline
from runeforge.runner.sweep import RUNS_DIR, keystream_sha256
from runeforge.scoring import presets
from runeforge.scoring.calibration import null_scores

PARITY_TOL = 1e-6


def find(kid: str, base: Path | None = None) -> Path:
    hits = sorted((base or RUNS_DIR).glob(f"*/crossers/{kid}.pending"))
    if not hits:
        raise FileNotFoundError(f"no pending crosser {kid!r} under {base or RUNS_DIR}")
    return hits[0]


def _log(pending: Path, lines: list[str]) -> None:
    md = pending.with_suffix(".md")
    if not md.exists():
        md.write_text(f'# Crosser {pending.stem}\n\nnumbering: "LP2-0-57"\n\n', encoding="utf-8")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(md, "a", encoding="utf-8") as fh:
        fh.write(f"\n## {stamp}\n\n" + "\n".join(lines) + "\n")


def _load(kid: str, base: Path | None):
    pending = find(kid, base)
    rec = json.loads(pending.read_text(encoding="utf-8"))
    lane = load_lane(rec["lane_path"])
    return pending, rec, lane


def replay(kid: str, base: Path | None = None) -> dict:
    """Step 2: regenerate the keystream with the CPU reference, decode, rescore, compare."""
    pending, rec, lane = _load(kid, base)
    scorer = presets.get(presets.split_preset(rec["preset"])[0])
    cipher = pipeline.lane_cipher(lane)[: rec["window"]]
    k = pipeline.keys(lane, rec["seed"], cipher.size)
    score = float(scorer.score(pipeline.decrypt(lane, cipher, k)))
    ks_ok = keystream_sha256(lane, rec["seed"]) == rec["keystream_sha256"]
    delta = abs(score - rec["score"])
    verdict = "PARITY-OK" if ks_ok and delta <= PARITY_TOL else "PARITY-FAIL"
    _log(
        pending,
        [
            f"step 2 replay (CPU reference): recorded score {rec['score']:.8f}, "
            f"replayed {score:.8f}, |delta| {delta:.2e}; "
            f"keystream sha256 match: {ks_ok} -> {verdict}",
            f"reproduce: `runeforge crosser replay {kid} --cpu`",
        ],
    )
    return {
        "kid": kid,
        "verdict": verdict,
        "recorded": rec["score"],
        "replayed": score,
        "delta": delta,
        "keystream_match": ks_ok,
    }


def escalate(kid: str, base: Path | None = None, n_null: int = 2000) -> dict:
    """Step 3: re-score at 2x the window, the full first page set and the full stream with
    the same key; z against a size-matched null at each length. A z that falls at any step
    is a NOISE-CROSSER."""
    pending, rec, lane = _load(kid, base)
    scorer = presets.get(presets.split_preset(rec["preset"])[0])
    full = pipeline.lane_cipher(lane)
    k = pipeline.keys(lane, rec["seed"], full.size)
    plain = pipeline.decrypt(lane, full, k)
    lengths = []
    for n in (rec["window"], 2 * rec["window"], full.size):
        n = min(n, full.size)
        if n not in lengths:
            lengths.append(n)
    rows = []
    for n in lengths:
        null = null_scores(scorer, n, n=n_null, seed=3301 + n)
        s = float(scorer.score(plain[:n]))
        z = (s - float(null.mean())) / float(null.std())
        rows.append(
            {
                "length": n,
                "score": s,
                "null_mean": float(null.mean()),
                "null_sd": float(null.std()),
                "z": z,
            }
        )
    falls = any(b["z"] < a["z"] for a, b in itertools.pairwise(rows))
    verdict = "NOISE-CROSSER" if falls else "passes step 3"
    table = ["| length | score | null mean | null sd | z |", "|---|---|---|---|---|"]
    table += [
        f"| {r['length']} | {r['score']:.4f} | {r['null_mean']:.4f} | {r['null_sd']:.4f} "
        f"| {r['z']:.2f} |"
        for r in rows
    ]
    _log(
        pending,
        [
            "step 3 escalation (same key, no re-synchronisation):",
            *table,
            f"-> {verdict}",
            f"reproduce: `runeforge crosser escalate {kid}`",
        ],
    )
    return {"kid": kid, "verdict": verdict, "rows": rows}


def reencipher(kid: str, base: Path | None = None) -> dict:
    """Step 6: encrypt the decoded plaintext forward; it must equal the canonical runes."""
    pending, rec, lane = _load(kid, base)
    full_view = pipeline.lane_cipher(lane)
    k = pipeline.keys(lane, rec["seed"], full_view.size)
    plain = pipeline.decrypt(lane, full_view, k)
    no_filter = lane.model_copy(update={"filter_model": "off", "interrupt_prob": 0.0})
    model_cipher, _ = pipeline.encrypt(no_filter, plain, k, np.random.default_rng(0))
    canonical = canon.load_lp2().stream(lane.pages)
    forward = pipeline.unview(model_cipher, lane.ciphertext_view)
    ok = bool(np.array_equal(forward, canonical))
    verdict = "passes step 6" if ok else "NOISE-CROSSER"
    mism = int((forward != canonical).sum())
    _log(
        pending,
        [
            f"step 6 re-encipher over pages {lane.pages}: {mism} mismatching runes "
            f"of {canonical.size} -> {verdict}",
            f"reproduce: `runeforge crosser reencipher {kid}`",
        ],
    )
    return {"kid": kid, "verdict": verdict, "mismatches": mism}


def pending_list(base: Path | None = None) -> list[Path]:
    return sorted((base or RUNS_DIR).glob("*/crossers/*.pending"))
