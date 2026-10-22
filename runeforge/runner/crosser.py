"""``runeforge crosser list|replay|escalate|reencipher <kid>``: HIT_PROTOCOL.md steps 2, 3, 6.

A crosser is ``FLAGGED-FOR-ORACLE`` from the moment the sweep writes its
``runs/<lane>/crossers/<kid>.pending``. These commands append to ``<kid>.md`` and never
declare more than PARITY-FAIL / NOISE-CROSSER / INCOMPLETE / NOT-INFORMATIVE or "passes this
step". A crosser adjudicated NOISE-CROSSER or PARITY-FAIL is renamed ``<kid>.noise-crosser``
/ ``<kid>.parity-fail`` (its ``status`` updated inside): ``pending_list`` shows only the open
ones, ``resolved_list`` the others, and the sweep never re-opens a resolved one. Reading the
plaintext is step 7 and is not done here.

* step 2, ``replay``: the CPU-reference keystream, decode and rescore of the scored window;
  PARITY-OK or PARITY-FAIL.
* step 3, ``escalate``: the SAME key continuing, no re-synchronisation, over the escalation
  stream -- the lane's pages, then every later unsolved LP2 page (0-55) not in the lane, in
  canonical order, with the lane's ciphertext view applied to that whole stream. Scored at the
  window, 2x the window, the end of the first full page containing the window's end ("page")
  and the full stream: distinct lengths, ascending, each with z against a size-matched null.
  For the rigid decoder that null is uniform random strings (what any wrong key yields); for a
  beam decoder it is the same beam decoding the same stream prefix under keys from a
  domain-separated SHA-256 stream, with the same key budget as the crosser's own decode at that
  length (the prefix length): a beam lifts noise above uniform strings, so the uniform null
  would overstate z. A z that falls at any step is a NOISE-CROSSER; fewer than two distinct
  lengths is INCOMPLETE, never a pass.
* step 6, ``reencipher``: under the rigid decoder, re-enciphering the rigid decode with the
  same key is the identity, so the step cannot fail: NOT-INFORMATIVE (rigid decoder). For a
  beam decoder the sweep records its path over the lane's whole pages (``decode_record``:
  plain, interrupts, skips, fill); the plaintext is enciphered forward with that record and
  must equal the canonical runes rune for rune, every interrupt must sit on a canonical F and
  every recorded skip must drop a key symbol that really re-enciphers to a canonical repeat.
  The beam builds its paths under exactly these rules, so for its own record this step catches
  a decoder bug or an edited record; it is not independent evidence (step 3 and the oracle
  are). A record with fill positions (the key budget ran out) or no record is INCOMPLETE.

``lane_path`` in a crosser file is repo-relative when the lane lies inside the repository and
is resolved against REPO_ROOT here, so these commands work from any cwd. ``exit_code`` maps a
result to the CLI's exit status.
"""

from __future__ import annotations

import itertools
import json
import os
import time
from pathlib import Path

import numpy as np

from runeforge import canon, generators
from runeforge.lanes import load_lane
from runeforge.paths import REPO_ROOT
from runeforge.runner import pipeline
from runeforge.runner.sweep import CROSSER_SUFFIXES, RUNS_DIR, _atomic_json, keystream_sha256
from runeforge.scoring import presets
from runeforge.scoring.calibration import null_scores

PARITY_TOL = 1e-6
NOT_INFORMATIVE = "NOT-INFORMATIVE (rigid decoder)"
INCOMPLETE = "INCOMPLETE"
RESOLVED = {"NOISE-CROSSER": ".noise-crosser", "PARITY-FAIL": ".parity-fail"}
# verdicts a step may exit 0 with: it passed, or (rigid step 6) it could not have failed
EXIT_0 = ("PARITY-OK", "passes step 3", "passes step 6", NOT_INFORMATIVE)


def exit_code(result: dict) -> int:
    return 0 if result.get("verdict") in EXIT_0 else 1


def _files(base: Path | None, name: str) -> list[Path]:
    """``runs/<id>/crossers/`` first, then the ``previous-*`` archives an older runner moved
    crossers into on ``--no-resume`` (the current runner never moves them)."""
    root = base or RUNS_DIR
    return sorted(root.glob(f"*/crossers/{name}")) + sorted(
        root.glob(f"*/previous-*/crossers/{name}")
    )


def find(kid: str, base: Path | None = None) -> Path:
    """The crosser's file: the open ``.pending`` one, else an adjudicated one."""
    for suffix in CROSSER_SUFFIXES:
        hits = _files(base, f"{kid}{suffix}")
        if hits:
            return hits[0]
    raise FileNotFoundError(f"no crosser {kid!r} under {base or RUNS_DIR}")


def pending_list(base: Path | None = None) -> list[Path]:
    """Open crossers only (``.pending``)."""
    return _files(base, "*.pending")


def resolved_list(base: Path | None = None) -> list[Path]:
    """Crossers the steps adjudicated NOISE-CROSSER or PARITY-FAIL."""
    return sorted(p for suffix in RESOLVED.values() for p in _files(base, f"*{suffix}"))


def lane_file(rec: dict) -> Path:
    p = Path(rec["lane_path"])
    return p if p.is_absolute() else REPO_ROOT / p


def _log(path: Path, lines: list[str]) -> None:
    md = path.with_suffix(".md")
    if not md.exists():
        md.write_text(f'# Crosser {path.stem}\n\nnumbering: "LP2-0-57"\n\n', encoding="utf-8")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(md, "a", encoding="utf-8") as fh:
        fh.write(f"\n## {stamp}\n\n" + "\n".join(lines) + "\n")


def _load(kid: str, base: Path | None):
    path = find(kid, base)
    rec = json.loads(path.read_text(encoding="utf-8"))
    return path, rec, load_lane(lane_file(rec))


def _resolve(path: Path, rec: dict, verdict: str, lines: list[str]) -> Path:
    """Rename an open ``<kid>.pending`` adjudicated NOISE-CROSSER / PARITY-FAIL. An already
    resolved crosser keeps its first adjudication."""
    if verdict not in RESOLVED or path.suffix != ".pending":
        return path
    _atomic_json(path, {**rec, "status": verdict, "resolved_epoch": int(time.time())})
    new = path.with_suffix(RESOLVED[verdict])
    os.replace(path, new)
    lines.append(f"-> filed as `{new.name}` (no longer pending)")
    return new


def replay(kid: str, base: Path | None = None) -> dict:
    """Step 2: regenerate the keystream with the CPU reference, decode, rescore, compare."""
    path, rec, lane = _load(kid, base)
    scorer = presets.get(presets.split_preset(rec["preset"])[0])
    cipher = pipeline.lane_cipher(lane)[: rec["window"]]
    k = pipeline.keys(lane, rec["seed"], cipher.size)
    score = float(scorer.score(pipeline.decrypt(lane, cipher, k)))
    ks_ok = keystream_sha256(lane, rec["seed"]) == rec["keystream_sha256"]
    delta = abs(score - rec["score"])
    verdict = "PARITY-OK" if ks_ok and delta <= PARITY_TOL else "PARITY-FAIL"
    lines = [
        f"step 2 replay (CPU reference): recorded score {rec['score']:.8f}, "
        f"replayed {score:.8f}, |delta| {delta:.2e}; "
        f"keystream sha256 match: {ks_ok} -> {verdict}",
        f"reproduce: `runeforge crosser replay {kid} --cpu`",
    ]
    new = _resolve(path, rec, verdict, lines)
    _log(path, lines)
    return {
        "kid": kid,
        "verdict": verdict,
        "recorded": rec["score"],
        "replayed": score,
        "delta": delta,
        "keystream_match": ks_ok,
        "file": str(new),
    }


def escalation_pages(lane) -> list[int]:
    """The lane's pages, then every later unsolved LP2 page not in the lane (canonical
    order); "later" means after the lane's first page."""
    first = min(lane.pages)
    later = [p for p in canon.UNSOLVED_LP2_PAGES if p > first and p not in lane.pages]
    return [*lane.pages, *later]


def escalation_lengths(window: int, page_sizes: list[int], total: int) -> dict[int, list[str]]:
    """{length: [step names]}: window, 2x window, the end of the first full page that
    contains the window's end, and the full stream; capped at ``total``, deduplicated,
    ascending."""
    ends = np.cumsum(page_sizes) if page_sizes else np.zeros(0, dtype=np.int64)
    page_end = next((int(e) for e in ends if e >= window), total)
    out: dict[int, list[str]] = {}
    for name, n in (
        ("window", window),
        ("2x window", 2 * window),
        ("page", page_end),
        ("full stream", total),
    ):
        n = min(int(n), total)
        if n >= 1:
            out.setdefault(n, []).append(name)
    return dict(sorted(out.items()))


def escalate(kid: str, base: Path | None = None, n_null: int = 2000) -> dict:
    """Step 3: re-score with the same key continuing over the escalation stream; z against a
    size-matched null at each length. A z that falls at any step is a NOISE-CROSSER."""
    path, rec, lane = _load(kid, base)
    scorer = presets.get(presets.split_preset(rec["preset"])[0])
    lp2 = canon.load_lp2()
    pages = escalation_pages(lane)
    stream = pipeline.view(lp2.stream(pages), lane.ciphertext_view)
    k = pipeline.keys(lane, rec["seed"], stream.size)
    rigid = pipeline.beam_model(lane) is None
    plain = pipeline.decrypt(lane, stream, k) if rigid else None
    steps = escalation_lengths(rec["window"], [lp2.page(p).runes.size for p in pages], stream.size)
    rows = []
    for n, names in steps.items():
        if rigid:
            null = null_scores(scorer, n, n=n_null, seed=3301 + n)
            s = float(scorer.score(plain[:n]))
        else:  # the beam's own decode and null at this length, both with a budget of n
            null = beam_null_scores(lane, stream[:n], n_null, domain=f"escalate/{kid}/{n}")
            s = float(scorer.score(pipeline.decrypt(lane, stream[:n], k[:n])))
        rows.append(
            {
                "length": n,
                "step": " = ".join(names),
                "score": s,
                "null_mean": float(null.mean()),
                "null_sd": float(null.std()),
                "z": (s - float(null.mean())) / float(null.std()),
            }
        )
    if len(rows) < 2:
        verdict = INCOMPLETE
    elif any(b["z"] < a["z"] for a, b in itertools.pairwise(rows)):
        verdict = "NOISE-CROSSER"
    else:
        verdict = "passes step 3"
    table = ["| step | length | score | null mean | null sd | z |", "|---|---|---|---|---|---|"]
    table += [
        f"| {r['step']} | {r['length']} | {r['score']:.4f} | {r['null_mean']:.4f} "
        f"| {r['null_sd']:.4f} | {r['z']:.2f} |"
        for r in rows
    ]
    lines = [
        "step 3 escalation (same key continuing, no re-synchronisation) over LP2 pages "
        f"{pages} ({stream.size} runes, view {lane.ciphertext_view}):",
        *table,
        f"-> {verdict}"
        + (" (fewer than two distinct lengths: nothing to escalate)" if len(rows) < 2 else ""),
        f"reproduce: `runeforge crosser escalate {kid}`",
    ]
    new = _resolve(path, rec, verdict, lines)
    _log(path, lines)
    return {"kid": kid, "verdict": verdict, "rows": rows, "pages": pages, "file": str(new)}


NULL_BATCH = 200  # beam null keys per decode call at escalation lengths (memory: L x 200 x w)


def beam_null_scores(lane, cipher, n: int, domain: str) -> np.ndarray:
    """Scores of the lane's beam decoding ``cipher`` under ``n`` keys of a domain-separated
    SHA-256 stream (a source outside every searched family), key budget ``cipher.size``."""
    scorer = presets.get(presets.split_preset(lane.preset)[0])
    gen = generators.get("sha256-ctr", domain=f"runeforge/{domain}")
    out = []
    for a in range(0, n, NULL_BATCH):
        seeds = list(range(a, min(a + NULL_BATCH, n)))
        keys = generators.keystream_batch(gen, seeds, cipher.size)
        out.append(pipeline.score_batch(scorer, pipeline.decrypt(lane, cipher[None, :], keys)))
    return np.concatenate(out)


def record_violations(lane, plain, k, interrupts=(), skips=None) -> list[str]:
    """Steps of a decode record the lane's forward model could not have taken: any interrupt
    when the lane has none (``interrupt_prob`` 0) or any skip when it has no filter, an
    interrupt off a canonical F, or a recorded skip whose dropped key symbol does not
    re-encipher the rune to a canonical repeat of the previous rune (``pipeline.encrypt``: only
    a repeat is dropped, never at position 0). ``k`` must cover the record's key use."""
    p = np.asarray(plain, dtype=np.int64)
    k = np.asarray(k, dtype=np.int64)
    name = lane.ciphertext_view
    inter = {int(i) for i in interrupts}
    skip = {int(i): int(m) for i, m in (skips or {}).items()}
    out = []
    if inter and not lane.interrupt_prob:
        out.append(f"{len(inter)} interrupters, but the lane's interrupt_prob is 0")
    if any(skip.values()) and lane.filter_model != "anti-repeat":
        out.append("key skips, but the lane has no anti-repeat filter")
    j, prev = 0, 0
    for i, x in enumerate(p.tolist()):
        if i in inter:
            if x != pipeline.F:
                out.append(f"position {i}: an interrupter whose plaintext is not F")
            prev = pipeline.F
            continue
        m = skip.get(i, 0)
        if m and i == 0:
            out.append("position 0: a skip (the filter never acts on the first rune)")
        for t in range(m):
            v = pipeline._enc1(lane.combine, x, int(k[j + t]))
            if pipeline._canon1(name, v, prev) != prev:
                out.append(f"position {i}: skipped key symbol {j + t} does not repeat the rune")
        j += m
        prev = pipeline._canon1(name, pipeline._enc1(lane.combine, x, int(k[j])), prev)
        j += 1
    return out


def reencipher_forward(lane, plain, k, interrupts=(), skips=None) -> np.ndarray:
    """Encipher ``plain`` forward in the lane's view, replaying a skip-aware decoder's record
    with ``pipeline.encrypt``'s model: at an interrupt position the canonical rune is an
    unencrypted F (its view symbol follows from the previous canonical rune) and the key does
    not advance; at a position with ``skips[i] = m`` the anti-repeat filter consumed m key
    symbols before the one kept. ``k`` must cover len(plain) + sum(skips)."""
    p = np.asarray(plain, dtype=np.int64)
    k = np.asarray(k, dtype=np.int64)
    name = lane.ciphertext_view
    inter = {int(i) for i in interrupts}
    skip = {int(i): int(m) for i, m in (skips or {}).items()}
    out = np.empty(p.size, dtype=np.int64)
    j, prev = 0, 0  # prev: the previous canonical rune (c_{-1} = 0, as pipeline.view assumes)
    for i, x in enumerate(p.tolist()):
        if i in inter:
            out[i] = pipeline._view1(name, pipeline.F, prev)
            prev = pipeline.F
            continue
        j += skip.get(i, 0)
        out[i] = pipeline._enc1(lane.combine, x, int(k[j]))
        prev = pipeline._canon1(name, int(out[i]), prev)
        j += 1
    return out


def reencipher(kid: str, base: Path | None = None) -> dict:
    """Step 6: encrypt the decoded plaintext forward; it must equal the canonical runes."""
    path, rec, lane = _load(kid, base)
    _scorer, decoder = presets.split_preset(rec["preset"])
    reproduce = f"reproduce: `runeforge crosser reencipher {kid}`"
    if decoder == "rigid":
        _log(
            path,
            [
                f"step 6 re-encipher: {NOT_INFORMATIVE}. The rigid decoder inverts the combine "
                "rune for rune with no skips and no interrupts, so enciphering its plaintext "
                "forward with the same key returns the canonical runes by construction: this "
                "step cannot fail here and is no evidence. It discriminates only for a "
                "skip-aware decoder that records its skip and interrupt positions.",
                reproduce,
            ],
        )
        return {"kid": kid, "verdict": NOT_INFORMATIVE, "mismatches": None, "decoder": decoder}
    record = rec.get("decode_record")
    if not isinstance(record, dict) or "plain" not in record:
        _log(
            path,
            [
                f"step 6 re-encipher: {INCOMPLETE}: decoder {decoder!r} left no decode_record "
                "(plain, interrupts, skips) to encipher forward",
                reproduce,
            ],
        )
        return {"kid": kid, "verdict": INCOMPLETE, "mismatches": None, "decoder": decoder}
    plain = np.asarray(record["plain"], dtype=np.int64)
    skips = record.get("skips") or {}
    fill = record.get("fill") or []
    if fill:
        _log(
            path,
            [
                f"step 6 re-encipher: {INCOMPLETE}: the record has {len(fill)} fill positions "
                "(the decode ran out of key budget there; fill is not a forward-model step)",
                reproduce,
            ],
        )
        return {"kid": kid, "verdict": INCOMPLETE, "mismatches": None, "decoder": decoder}
    interrupts = record.get("interrupts") or ()
    k = pipeline.keys(lane, rec["seed"], plain.size + sum(int(m) for m in skips.values()))
    model = reencipher_forward(lane, plain, k, interrupts, skips)
    violations = record_violations(lane, plain, k, interrupts, skips)
    canonical = canon.load_lp2().stream(lane.pages)
    forward = pipeline.unview(model, lane.ciphertext_view)
    m = min(forward.size, canonical.size)
    mism = int((forward[:m] != canonical[:m]).sum()) + abs(forward.size - canonical.size)
    verdict = "passes step 6" if mism == 0 and not violations else "NOISE-CROSSER"
    lines = [
        f"step 6 re-encipher over pages {lane.pages} with the decoder's record "
        f"({len(interrupts)} interrupts, {len(skips)} skip positions): "
        f"{mism} mismatching runes of {canonical.size}, {len(violations)} steps the forward "
        f"model could not take -> {verdict}",
        *[f"  - {v}" for v in violations[:20]],
        "note: the beam builds its paths under these same rules, so for its own record this "
        "step catches a decoder bug or an edited record; it is not independent evidence "
        "(step 3 and the oracle are).",
        reproduce,
    ]
    new = _resolve(path, rec, verdict, lines)
    _log(path, lines)
    return {
        "kid": kid,
        "verdict": verdict,
        "mismatches": mism,
        "violations": violations,
        "decoder": decoder,
        "file": str(new),
    }
