"""Parsers for the vendored transcriptions under ``data/raw/`` (read-only).

Four lineages are read:

* ``rtkd/iddqd`` master transcription -- the primary source the canon is built from.
  Delimiters: ``-`` word, ``.`` clause, ``&`` paragraph, ``$`` segment, ``§`` chapter,
  ``/`` line, ``%`` page.
* ``scream314/cicada3301`` ``liber_primus.md`` -- Unicode runes grouped by image ranges
  (not always one page per heading), so it is compared as a flat stream per LP part.
* ``yo-yo-yo-jbo/cicada_tools`` ``liber_primus/*/section.json`` -- per-page runes with
  LP2 page numbers, plus the reference transformer chain for each solved section.
* ``Dukotah/cicada3301`` ``liber-primus/PROBLEM.json`` (SHA-256-pinned unsolved stream)
  and ``liber-primus/data/krisyotam_runes.txt`` (the file their pipeline loads).
"""

from __future__ import annotations

import difflib
import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path

from runeforge import gematria as gm
from runeforge.paths import RAW_DIR

RTKD_DIR = "rtkd"
SCREAM_DIR = "scream314"
CICADA_TOOLS_DIR = "cicada_tools"
DUKOTAH_DIR = "dukotah"
JENS_DIR = "jens-wedin"

RTKD_MASTER = (
    f"{RTKD_DIR}/liber-primus__transcription--master/liber-primus__transcription--master.txt"
)
SCREAM_LP = f"{SCREAM_DIR}/liber_primus.md"
CICADA_TOOLS_SECTIONS = f"{CICADA_TOOLS_DIR}/liber_primus"
CICADA_TOOLS_CORE = f"{CICADA_TOOLS_DIR}/core.py"
DUKOTAH_PROBLEM = f"{DUKOTAH_DIR}/liber-primus/PROBLEM.json"
DUKOTAH_KRIS = f"{DUKOTAH_DIR}/liber-primus/data/krisyotam_runes.txt"

# Every file the canon build reads; scripts/fetch_raw.sh sparse-checks-out these paths.
REQUIRED_FILES = (RTKD_MASTER, SCREAM_LP, CICADA_TOOLS_CORE, DUKOTAH_PROBLEM, DUKOTAH_KRIS)

LP1_PAGES = 17  # LP1 = book pages 0-16
LP2_PAGES = 58  # LP2 = 0.jpg-57.jpg = book pages 17-74
LP2_BOOK_OFFSET = 17  # LP2 page n is book ("complete set") page n + 17
LP1_RUNELESS_PAGES = (0, 2)  # cleartext title pages "LIBER PRIMUS" and "INTUS"

_WORD_DELIMS = "-."
_BLOCK_MARKS = "&$§"


class SourceError(RuntimeError):
    """A vendored source is missing or does not have the structure we expect."""


def raw_path(rel: str, raw_dir: Path | None = None) -> Path:
    p = (raw_dir or RAW_DIR) / rel
    if not p.exists():
        raise SourceError(f"missing vendored source {p} -- run scripts/fetch_raw.sh")
    return p


def raw_available(raw_dir: Path | None = None) -> bool:
    return all(((raw_dir or RAW_DIR) / f).exists() for f in REQUIRED_FILES)


# --------------------------------------------------------------------------- rtkd


@dataclass
class RawPage:
    """One page of the master transcription.

    ``lines`` holds the rune words of each physical line. A word broken across a line
    break appears as a fragment at the end of one line and the start of the next;
    ``line_continues[i]`` is True when line ``i`` ends mid-word. Non-rune tokens
    (numbers, hex) are kept only in ``raw``.
    """

    part: str
    page: int
    book_page: int
    raw: str
    lines: list[list[list[int]]] = field(default_factory=list)
    line_continues: list[bool] = field(default_factory=list)

    @property
    def runes(self) -> list[int]:
        return [i for line in self.lines for w in line for i in w]

    @property
    def rune_string(self) -> str:
        return gm.indices_to_runes(self.runes)


def _line_texts(raw: str) -> list[str]:
    """Physical rune-bearing lines of a page, with block marks stripped."""
    out = []
    for piece in raw.split("/"):
        text = "".join(c for c in piece if c not in _BLOCK_MARKS).strip()
        if text and any(gm.is_rune(c) for c in text):
            out.append(text)  # lines of numbers / hex only are dropped
    return out


def _parse_page_text(raw: str) -> list[list[list[int]]]:
    lines: list[list[list[int]]] = []
    for text in _line_texts(raw):
        words: list[list[int]] = []
        cur: list[int] = []
        for ch in text:
            if gm.is_rune(ch):
                cur.append(gm.rune_to_idx(ch))
            elif ch in _WORD_DELIMS:
                if cur:
                    words.append(cur)
                cur = []
            elif ch in "\n\r\t ":
                continue
            elif ch.isalnum():
                if cur:
                    raise SourceError(f"alphanumeric glued to a rune word in line {text!r}")
            else:
                raise SourceError(f"unexpected character {ch!r} in line {text!r}")
        if cur:
            words.append(cur)
        lines.append(words)
    return lines


def _mark_continuations(pages: list[RawPage]) -> None:
    """A line continues when it ends on a rune and the next line (possibly on the next
    page) starts with one -- i.e. a word is split by the line break."""
    texts = [(p, _line_texts(p.raw)) for p in pages]
    flat = [(p, i, t) for p, ts in texts for i, t in enumerate(ts)]
    for p, _ in texts:
        p.line_continues = [False] * len(p.lines)
    for (p, i, t), (_, _, nxt) in itertools.pairwise(flat):
        p.line_continues[i] = gm.is_rune(t[-1]) and gm.is_rune(nxt[0])
    if flat:
        p, i, t = flat[-1]
        p.line_continues[i] = False


def parse_rtkd_master(path: Path | None = None) -> tuple[list[RawPage], list[RawPage]]:
    """Return (lp1_pages, lp2_pages) from rtkd's master transcription.

    The file holds the 73 rune-bearing book pages; LP1 pages 0 and 2 are cleartext
    title pages and are absent. LP2 page 50 is a runeless 13x8 grid of two-character
    tokens and is present with zero runes.
    """
    text = gm.normalize_glyphs((path or raw_path(RTKD_MASTER)).read_text(encoding="utf-8"))
    for c in text:
        if 0x16A0 <= ord(c) <= 0x16FF and not gm.is_rune(c):
            raise SourceError(f"non-canonical runic codepoint U+{ord(c):04X} in rtkd master")
    head, sep, body = text.partition("\n\n")
    if not sep or "Delimiters" not in head:
        raise SourceError("rtkd master: delimiter header not found")
    chunks = body.split("%")
    if len(chunks) != 74 or chunks[-1].strip() != "§":
        raise SourceError(
            f"rtkd master: expected 73 pages + trailing chapter mark, got {len(chunks)}"
        )
    chunks = chunks[:-1]

    lp1_book_pages = [1, *range(3, LP1_PAGES)]  # 15 rune-bearing LP1 pages
    lp1: list[RawPage] = []
    for book_page, chunk in zip(lp1_book_pages, chunks[:15], strict=True):
        raw = chunk.strip("\n")
        lp1.append(RawPage("LP1", book_page, book_page, raw, _parse_page_text(raw)))
    in_file_order = list(lp1)
    for missing in LP1_RUNELESS_PAGES:
        lp1.append(RawPage("LP1", missing, missing, ""))
    lp1.sort(key=lambda p: p.page)

    lp2: list[RawPage] = []
    for n, chunk in enumerate(chunks[15:]):
        raw = chunk.strip("\n")
        lp2.append(RawPage("LP2", n, n + LP2_BOOK_OFFSET, raw, _parse_page_text(raw)))
    _mark_continuations(in_file_order + lp2)
    if len(lp2) != LP2_PAGES:
        raise SourceError(f"rtkd master: expected {LP2_PAGES} LP2 pages, got {len(lp2)}")

    # Structural anchors: if these move, the page mapping above is wrong.
    if not lp1[1].rune_string.startswith("ᚱᛝᚱᚪᛗᚹ"):
        raise SourceError("rtkd master: LP1 page 1 is not A WARNING")
    if not lp2[0].rune_string.startswith("ᛋᚻᛖᚩᚷᛗᛡᚠ"):
        raise SourceError("rtkd master: LP2 page 0 does not start the unsolved stream")
    if not lp2[57].rune_string.startswith("ᛈᚪᚱᚪᛒᛚᛖ"):
        raise SourceError("rtkd master: LP2 page 57 is not PARABLE")
    if lp2[50].runes:
        raise SourceError("rtkd master: LP2 page 50 should be runeless")
    return lp1, lp2


# --------------------------------------------------------------------------- scream314

_SCREAM_ALLOWED = set("•'\"-.:0123456789 \t")


def parse_scream314(path: Path | None = None) -> dict[str, str]:
    """Flat rune strings {'LP1': ..., 'LP2': ...} from scream314's liber_primus.md.

    Only indented code lines made of runes and punctuation are read, so runes quoted in
    prose (e.g. the note "every clear text F is an ᚠ") are not mistaken for ciphertext.
    """
    text = gm.normalize_glyphs((path or raw_path(SCREAM_LP)).read_text(encoding="utf-8"))
    i2, i3 = text.find("\n# LP2"), text.find("\n# Magic Squares")
    if i2 < 0 or i3 < 0:
        raise SourceError("scream314: '# LP2' / '# Magic Squares' headings not found")

    def runes_of(block: str) -> str:
        out = []
        for line in block.split("\n"):
            if not line.startswith("    ") or not any(gm.is_rune(c) for c in line):
                continue
            bad = {c for c in line.strip() if not gm.is_rune(c) and c not in _SCREAM_ALLOWED}
            if bad:
                raise SourceError(f"scream314: unexpected characters {bad} in {line[:60]!r}")
            out.append("".join(c for c in line if gm.is_rune(c)))
        return "".join(out)

    return {"LP1": runes_of(text[:i2]), "LP2": runes_of(text[i2:i3])}


# --------------------------------------------------------------------------- cicada_tools


@dataclass
class CTSection:
    dirname: str
    title: str
    transformers: list[dict]
    pages: list[dict]  # {"number": int|None, "filename": str, "text": str}

    @property
    def rune_string(self) -> str:
        return "".join(
            c for p in self.pages for c in gm.normalize_glyphs(p["text"]) if gm.is_rune(c)
        )

    @property
    def solved(self) -> bool:
        return not any(t["type"] == "UnsolvedTransformer" for t in self.transformers)


def parse_cicada_tools(sections_dir: Path | None = None) -> list[CTSection]:
    root = sections_dir or raw_path(CICADA_TOOLS_SECTIONS)
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        data = json.loads((d / "section.json").read_text(encoding="utf-8"))
        out.append(CTSection(d.name, data["title"], data["transformers"], data["pages"]))
    if len(out) != 18:
        raise SourceError(f"cicada_tools: expected 18 sections, got {len(out)}")
    return out


def cicada_tools_lp2_pages(sections: list[CTSection]) -> dict[int, str]:
    """LP2 page number -> rune string, from sections 007..017 (which use LP2 numbering)."""
    pages: dict[int, str] = {}
    for s in sections:
        if int(s.dirname[:3]) < 7:
            continue
        for p in s.pages:
            runes = "".join(c for c in gm.normalize_glyphs(p["text"]) if gm.is_rune(c))
            pages[p["number"]] = pages.get(p["number"], "") + runes
    return pages


def cicada_tools_alphabet(core_path: Path | None = None) -> dict[str, list]:
    """RuneUtils._RUNES / _LATIN / _GP_PRIMES from cicada_tools/core.py, read without import."""
    import ast

    tree = ast.parse((core_path or raw_path(CICADA_TOOLS_CORE)).read_text(encoding="utf-8"))
    found: dict[str, list] = {}
    rune_utils = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RuneUtils"]
    if not rune_utils:
        raise SourceError("cicada_tools core.py: class RuneUtils not found")
    for node in rune_utils[0].body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name) and t.id in ("_RUNES", "_LATIN", "_GP_PRIMES"):
                found[t.id] = ast.literal_eval(node.value)
    if set(found) != {"_RUNES", "_LATIN", "_GP_PRIMES"}:
        raise SourceError("cicada_tools core.py: alphabet tables not found")
    return found


# --------------------------------------------------------------------------- Dukotah


def parse_dukotah_problem(path: Path | None = None) -> dict:
    return json.loads((path or raw_path(DUKOTAH_PROBLEM)).read_text(encoding="utf-8"))


def parse_dukotah_segments(path: Path | None = None) -> list[str]:
    """The non-empty '%'-separated segments of krisyotam_runes.txt (57 = 55 unsolved + 2)."""
    text = gm.normalize_glyphs((path or raw_path(DUKOTAH_KRIS)).read_text(encoding="utf-8"))
    segs = ["".join(c for c in s if gm.is_rune(c)) for s in text.split("%")]
    return [s for s in segs if s]


# --------------------------------------------------------------------------- diffing


@dataclass(frozen=True)
class Edit:
    """One edit turning the canon stream into a source stream."""

    op: str  # replace | delete | insert
    canon_offset: int
    canon: str  # canon runes at canon_offset (empty for an insert)
    source_offset: int
    reads: str  # what the source has instead (empty for a delete)


def diff_runes(canon: str, other: str) -> list[Edit]:
    if canon == other:
        return []
    sm = difflib.SequenceMatcher(None, canon, other, autojunk=False)
    return [
        Edit(op, i1, canon[i1:i2], j1, other[j1:j2])
        for op, i1, i2, j1, j2 in sm.get_opcodes()
        if op != "equal"
    ]
