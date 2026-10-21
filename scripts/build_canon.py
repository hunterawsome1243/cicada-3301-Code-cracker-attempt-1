#!/usr/bin/env python3
"""Build the canonical Liber Primus ciphertext from the vendored transcriptions.

1. Parse rtkd/iddqd's master transcription into ``data/canon/lp2_runes.json`` (and
   ``lp1_runes.json``), structured page -> line -> word -> rune indices.
2. Cross-check rune-for-rune against
     * yo-yo-yo-jbo/cicada_tools  (page-for-page on LP2, section stream on LP1),
     * scream314/cicada3301       (flat stream per LP part),
     * Dukotah/cicada3301         (PROBLEM.json identity + krisyotam_runes.txt segments).
   ANY disagreement that is not recorded, edit for edit, in the curated
   ``data/canon/divergences.json`` is a hard error -- and so is a recorded divergence
   that no longer occurs.
3. Write ``solved_sections.json`` (cipher, method, key, interrupts and the cicada_tools
   reference plaintext for the nine solved sections).
4. Pin the SHA-256s to ``data/canon/lp2_runes.sha256``.

Usage:
    python scripts/build_canon.py           # build, cross-check, write, print the pins
    python scripts/build_canon.py --check   # rebuild in memory; fail if data/canon is stale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runeforge import canon as cn  # noqa: E402
from runeforge import gematria as gm  # noqa: E402
from runeforge import sources as src  # noqa: E402
from runeforge.paths import CANON_DIR, RAW_DIR, REFERENCE_DIR  # noqa: E402

DIVERGENCES = CANON_DIR / "divergences.json"
REFERENCE = REFERENCE_DIR / "cicada_tools_solved.json"

# The nine solved sections: id, title, part, pages (in that part's numbering), cicada_tools dir.
SOLVED = (
    ("a-warning", "A WARNING", "LP1", (1,), "000_a_warning"),
    ("welcome", "WELCOME", "LP1", (3, 4), "001_welcome"),
    ("some-wisdom", "SOME WISDOM", "LP1", (5,), "002_some_wisdom"),
    ("a-koan-1", "A KOAN", "LP1", (6, 7, 8, 9), "003_a_koan"),
    (
        "the-loss-of-divinity",
        "THE LOSS OF DIVINITY",
        "LP1",
        (10, 11, 12, 13),
        "004_the_loss_of_divinity",
    ),
    ("a-koan-2", "A KOAN", "LP1", (14, 15), "005_a_koan"),
    ("an-instruction", "AN INSTRUCTION", "LP1", (16,), "006_an_instruction"),
    ("an-end", "AN END", "LP2", (56,), "016_an_end"),
    ("parable", "PARABLE", "LP2", (57,), "017_parable"),
)


class CrossCheckError(RuntimeError):
    pass


def git_head(path: Path) -> str:
    r = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    if r.returncode != 0:
        raise CrossCheckError(f"cannot read commit of {path}: {r.stderr.strip()}")
    return r.stdout.strip()


def locate(part_pages: list[src.RawPage], offset: int) -> tuple[int, int]:
    """Flat-stream offset -> (page, offset on page)."""
    pos = 0
    for p in part_pages:
        n = len(p.runes)
        if offset < pos + n:
            return p.page, offset - pos
        pos += n
    return part_pages[-1].page, len(part_pages[-1].runes)


# --------------------------------------------------------------------------- cross-checks


def observed_divergences(lp1: list[src.RawPage], lp2: list[src.RawPage]) -> tuple[list[dict], dict]:
    """Run every cross-check; return (edits that differ from canon, per-source summary)."""
    edits: list[dict] = []
    summary: dict[str, dict] = {}
    lp1_stream = "".join(p.rune_string for p in lp1)
    lp2_stream = "".join(p.rune_string for p in lp2)

    def record(source: str, part: str, pages: list[src.RawPage], found: list[src.Edit]) -> None:
        for e in found:
            page, off = locate(pages, e.canon_offset)
            edits.append(
                {"source": source, "part": part, **asdict(e), "page": page, "page_offset": off}
            )

    # cicada_tools: LP2 page for page; LP1 as the concatenated solved sections 000..006.
    ct = src.parse_cicada_tools()
    ct_pages = src.cicada_tools_lp2_pages(ct)
    if sorted(ct_pages) != list(range(src.LP2_PAGES)):
        raise CrossCheckError(f"cicada_tools LP2 page numbers: {sorted(ct_pages)}")
    n_diff = 0
    for p in lp2:
        found = src.diff_runes(p.rune_string, ct_pages[p.page])
        n_diff += len(found)
        record(
            "cicada_tools",
            "LP2",
            lp2,
            [
                src.Edit(
                    e.op,
                    e.canon_offset + sum(len(q.runes) for q in lp2[: p.page]),
                    e.canon,
                    e.source_offset,
                    e.reads,
                )
                for e in found
            ],
        )
    ct_lp1 = "".join(s.rune_string for s in ct if int(s.dirname[:3]) < 7)
    found_lp1 = src.diff_runes(lp1_stream, ct_lp1)
    record("cicada_tools", "LP1", lp1, found_lp1)
    summary["cicada_tools"] = {
        "repo": "yo-yo-yo-jbo/cicada_tools",
        "commit": git_head(RAW_DIR / src.CICADA_TOOLS_DIR),
        "compared": "LP2 page-for-page (58 pages); LP1 solved-section stream",
        "LP2_runes": sum(len(v) for v in ct_pages.values()),
        "edits": {"LP2": n_diff, "LP1": len(found_lp1)},
    }

    # scream314: flat streams.
    sc = src.parse_scream314()
    f1, f2 = src.diff_runes(lp1_stream, sc["LP1"]), src.diff_runes(lp2_stream, sc["LP2"])
    record("scream314", "LP1", lp1, f1)
    record("scream314", "LP2", lp2, f2)
    summary["scream314"] = {
        "repo": "scream314/cicada3301",
        "commit": git_head(RAW_DIR / src.SCREAM_DIR),
        "compared": "flat rune stream per LP part",
        "LP2_runes": len(sc["LP2"]),
        "edits": {"LP2": len(f2), "LP1": len(f1)},
    }

    # Dukotah: the 57 non-empty krisyotam segments are the 57 rune-bearing LP2 pages.
    segs = src.parse_dukotah_segments()
    non_empty = [p for p in lp2 if p.runes]
    if len(segs) != len(non_empty):
        raise CrossCheckError(
            f"Dukotah: {len(segs)} segments vs {len(non_empty)} rune-bearing pages"
        )
    n_diff = 0
    for seg, p in zip(segs, non_empty, strict=True):
        found = src.diff_runes(p.rune_string, seg)
        n_diff += len(found)
        record(
            "dukotah",
            "LP2",
            lp2,
            [
                src.Edit(
                    e.op,
                    e.canon_offset + sum(len(q.runes) for q in lp2[: p.page]),
                    e.canon,
                    e.source_offset,
                    e.reads,
                )
                for e in found
            ],
        )
    problem = src.parse_dukotah_problem()["ciphertext_identity"]
    unsolved = [i for p in lp2[:56] for i in p.runes]
    pages_ne = [len(p.runes) for p in non_empty]
    checks = {
        "n_runes": (problem["n_runes"], len(unsolved)),
        "sha256_of_comma_joined_indices": (
            problem["sha256_of_comma_joined_indices"],
            cn.indices_sha256(unsolved),
        ),
        "first_24_indices": (problem["first_24_indices"], unsolved[:24]),
        "n_segments_total": (problem["n_segments_total"], len(non_empty)),
        "segment_lengths_first_10": (problem["segment_lengths_first_10"], pages_ne[:10]),
    }
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    if bad:
        raise CrossCheckError(f"Dukotah PROBLEM.json identity mismatch: {bad}")
    summary["dukotah"] = {
        "repo": "Dukotah/cicada3301",
        "commit": git_head(RAW_DIR / src.DUKOTAH_DIR),
        "compared": "PROBLEM.json ciphertext_identity (all fields) + krisyotam_runes.txt "
        "segment-for-page",
        "LP2_runes": sum(len(s) for s in segs),
        "edits": {"LP2": n_diff},
    }
    return edits, summary


def check_against_curated(observed: list[dict]) -> list[dict]:
    curated = json.loads(DIVERGENCES.read_text(encoding="utf-8"))["divergences"]
    key = ("source", "part", "op", "canon_offset", "canon", "source_offset", "reads")
    want = {tuple(e[k] for k in key): (d["id"], e) for d in curated for e in d["edits"]}
    got = {tuple(e[k] for k in key): e for e in observed}
    unexpected = [got[k] for k in got if k not in want]
    vanished = [want[k] for k in want if k not in got]
    errors = []
    for e in unexpected:
        errors.append(f"UNDOCUMENTED divergence: {e}")
    for did, e in vanished:
        errors.append(f"documented divergence {did} no longer occurs: {e}")
    for d in curated:
        for e in d["edits"]:
            k = tuple(e[k] for k in key)
            if k in got and (got[k]["page"], got[k]["page_offset"]) != (
                e["page"],
                e["page_offset"],
            ):
                errors.append(
                    f"{d['id']}: page/offset moved to {got[k]['page']}/{got[k]['page_offset']}"
                )
    if errors:
        raise CrossCheckError(
            "cross-check failed -- the canon parser or a source changed:\n  " + "\n  ".join(errors)
        )
    return curated


# --------------------------------------------------------------------------- outputs


def section_of_lp2(ct: list[src.CTSection]) -> dict[int, str]:
    out = {}
    for s in ct:
        if int(s.dirname[:3]) < 7:
            continue
        nums = [p["number"] for p in s.pages]
        name = {"016_an_end": "an-end", "017_parable": "parable"}.get(
            s.dirname, f"p{min(nums)}-{max(nums)}"
        )
        for n in nums:
            out[n] = name
    return out


def page_record(p: src.RawPage, status: str, section: str | None) -> dict:
    return {
        "page": p.page,
        "book_page": p.book_page,
        "status": status,
        "section": section,
        "n_runes": len(p.runes),
        "raw": p.raw,
        "lines": p.lines,
        "line_continues": p.line_continues,
    }


def build_lp_files(lp1, lp2, summary, curated) -> tuple[str, str]:
    ct = src.parse_cicada_tools()
    lp2_sections = section_of_lp2(ct)
    lp1_sections = {pg: sid for sid, _t, part, pages, _d in SOLVED if part == "LP1" for pg in pages}
    rtkd = {
        "repo": "rtkd/iddqd",
        "commit": git_head(RAW_DIR / src.RTKD_DIR),
        "path": src.RTKD_MASTER.split("/", 1)[1],
    }
    cross = [
        {**v, "divergences": [d["id"] for d in curated if d["source"] == k]}
        for k, v in summary.items()
    ]
    common = {
        "$comment": "Generated by scripts/build_canon.py -- do not hand-edit. Rune indices "
        "0-28 in Gematria Primus order; see runeforge/gematria.py.",
        "schema": "runeforge.canon/1",
        "alphabet": gm.RUNES,
        "source": rtkd,
        "cross_checked_against": cross,
        "structure": "pages[].lines[] = words on a physical line; words[] = rune indices. "
        "line_continues[i] is true when line i ends mid-word. 'raw' is the verbatim rtkd "
        "page (delimiters: - word, . clause, & paragraph, $ segment, / line).",
    }
    lp2_pages = []
    for p in lp2:
        status = "solved" if p.page >= 56 else ("runeless" if not p.runes else "unsolved")
        lp2_pages.append(page_record(p, status, lp2_sections.get(p.page)))
    lp2_header = {
        **common,
        "part": "LP2",
        "numbering": cn.LP2_NUMBERING,
        "book_page_offset": src.LP2_BOOK_OFFSET,
        "n_pages": len(lp2),
        "n_runes": sum(len(p.runes) for p in lp2),
        "n_runes_unsolved": sum(len(p.runes) for p in lp2[:56]),
        "unsolved_pages": "0-55 (page 50 carries no runes)",
        "solved_pages": "56 (AN END), 57 (PARABLE)",
    }
    lp1_pages = []
    for p in lp1:
        status = "runeless" if not p.runes else "solved"
        lp1_pages.append(page_record(p, status, lp1_sections.get(p.page)))
    lp1_header = {
        **common,
        "part": "LP1",
        "numbering": cn.LP1_NUMBERING,
        "book_page_offset": 0,
        "n_pages": len(lp1),
        "n_runes": sum(len(p.runes) for p in lp1),
        "note": "Pages 0 and 2 are cleartext title pages (LIBER PRIMUS, INTUS) with no runes.",
    }
    return cn.dumps_canon(lp2_header, lp2_pages), cn.dumps_canon(lp1_header, lp1_pages)


_CT_STEP = {
    "AtbashTransformer",
    "ShiftTransformer",
    "VigenereTransformer",
    "TotientPrimeTransformer",
}


def method_from_cicada_tools(transformers: list[dict]) -> tuple[dict, list[int]]:
    steps, interrupts, labels = [], [], []
    for t in transformers:
        kind = t["type"]
        if kind not in _CT_STEP:
            raise CrossCheckError(f"unknown cicada_tools transformer {kind}")
        if kind == "AtbashTransformer":
            steps.append({"type": "atbash"})
            labels.append("Atbash")
        elif kind == "ShiftTransformer":
            # cicada_tools' decode step ADDS `shift`; our shift(n) encrypts c = p + n.
            steps.append({"type": "shift", "n": -int(t["shift"])})
            labels.append(f"+{t['shift']}")
        elif kind == "VigenereTransformer":
            key = [int(i) for i in gm.runes_to_indices(t["key"])]
            steps.append({"type": "vigenere", "key": key})
            labels.append(f"Vigenere {gm.indices_to_latin(key)}")
        elif kind == "TotientPrimeTransformer":
            if t.get("add", False) or t.get("tot_calls", 1) != 1 or t.get("emirp", False):
                raise CrossCheckError(f"unexpected totient parameters {t}")
            steps.append({"type": "totient_prime_stream"})
            labels.append("subtract phi(p) = p - 1 over primes 2, 3, 5, ...")
        interrupts += [int(i) for i in t.get("interrupt_indices", [])]
    label = " -> ".join(labels) if labels else "plaintext"
    return {"label": label, "steps": steps}, sorted(interrupts)


def build_solved(lp1, lp2, curated) -> str:
    ref = json.loads(REFERENCE.read_text(encoding="utf-8"))
    by_dir = {s["dirname"]: s for s in ref["sections"]}
    pages = {"LP1": {p.page: p for p in lp1}, "LP2": {p.page: p for p in lp2}}
    sections = []
    for sid, title, part, nums, ctdir in SOLVED:
        r = by_dir[ctdir]
        cipher = "".join(pages[part][n].rune_string for n in nums)
        template = "\n".join(pages[part][n].raw for n in nums)
        method, interrupts = method_from_cicada_tools(r["transformers"])
        if cipher == r["cipher"]:
            plain = r["plain"]
            note = []
        elif not method["steps"]:
            # A plaintext section whose transcription differs from cicada_tools': the
            # plaintext IS the canon ciphertext. Every such edit is in divergences.json.
            plain = cipher
            note = [
                d["id"] for d in curated if d["source"] == "cicada_tools" and d["section"] == sid
            ]
            if not note:
                raise CrossCheckError(f"{sid}: undocumented cicada_tools divergence")
        else:
            raise CrossCheckError(f"{sid}: enciphered section differs from cicada_tools")
        sections.append(
            {
                "id": sid,
                "title": title,
                "part": part,
                "numbering": cn.LP1_NUMBERING if part == "LP1" else cn.LP2_NUMBERING,
                "pages": list(nums),
                "book_pages": [n + (src.LP2_BOOK_OFFSET if part == "LP2" else 0) for n in nums],
                "method": method,
                "interrupts": interrupts,
                "n_runes": len(cipher),
                "cipher": cipher,
                "plain": plain,
                "plain_text": cn.render(template, gm.runes_to_indices(plain)),
                "plain_reference": f"cicada_tools {ctdir}",
                "reference_divergences": note,
                "template": template,
            }
        )
    doc = {
        "$comment": "Generated by scripts/build_canon.py -- do not hand-edit. 'cipher' is "
        "the canon; 'plain' is cicada_tools' own decode (data/reference/), never runeforge's. "
        "method.steps are applied in order as DECRYPTION steps; shift(n) encrypts c = p + n.",
        "schema": "runeforge.solved/1",
        "reference": ref["source"],
        "sections": sections,
    }
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if data/canon is stale")
    ap.add_argument("--show-divergences", action="store_true", help="print observed edits")
    args = ap.parse_args()

    if not src.raw_available():
        print(
            "vendored sources missing under data/raw -- run scripts/fetch_raw.sh", file=sys.stderr
        )
        return 2
    lp1, lp2 = src.parse_rtkd_master()
    observed, summary = observed_divergences(lp1, lp2)
    if args.show_divergences:
        for e in observed:
            print(json.dumps(e, ensure_ascii=False))
        return 0
    curated = check_against_curated(observed)

    lp2_text, lp1_text = build_lp_files(lp1, lp2, summary, curated)
    solved_text = build_solved(lp1, lp2, curated)
    outputs = {cn.LP2_FILE: lp2_text, cn.LP1_FILE: lp1_text, cn.SOLVED_FILE: solved_text}

    all2 = [i for p in lp2 for i in p.runes]
    uns = [i for p in lp2[:56] for i in p.runes]
    all1 = [i for p in lp1 for i in p.runes]
    pins = [cn.Pin(hashlib.sha256(t.encode()).hexdigest(), f) for f, t in outputs.items()]
    pins += [
        cn.Pin(cn.indices_sha256(all2), "indices:LP2:all", f"n={len(all2)}"),
        cn.Pin(cn.indices_sha256(uns), "indices:LP2:unsolved", f"n={len(uns)} pages 0-55"),
        cn.Pin(cn.indices_sha256(all1), "indices:LP1:all", f"n={len(all1)}"),
    ]
    outputs[cn.PIN_FILE] = cn.format_pins(pins)

    if args.check:
        stale = [
            f
            for f, t in outputs.items()
            if not (CANON_DIR / f).exists() or (CANON_DIR / f).read_text(encoding="utf-8") != t
        ]
        if stale:
            print(f"STALE canon files: {stale} -- rerun scripts/build_canon.py", file=sys.stderr)
            return 1
        print("OK: cross-checks pass and data/canon is current")
    else:
        CANON_DIR.mkdir(parents=True, exist_ok=True)
        for f, t in outputs.items():
            (CANON_DIR / f).write_text(t, encoding="utf-8")
        print(f"wrote {', '.join(outputs)} to {CANON_DIR}")

    print(f"\ncross-checks: {len(observed)} edits observed, all documented in {DIVERGENCES.name}")
    for name, s in summary.items():
        print(f"  {name:13s} {s['commit'][:12]}  edits {s['edits']}  ({s['compared']})")
    print(f"\nLP2 runes     : {len(all2):,} (unsolved pages 0-55: {len(uns):,})")
    print(f"LP1 runes     : {len(all1):,}")
    for p in pins:
        print(f"  {p.sha256}  {p.name} {p.note}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CrossCheckError, src.SourceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
