"""The canonical ciphertext, its pinned hashes, and the solved-section table.

Every load verifies the pinned SHA-256s in ``data/canon/lp2_runes.sha256``; a mismatch
raises :class:`CanonIntegrityError`. Nothing downstream may read the transcription any
other way.

Numbering: LP2 pages are ``0..57`` (``numbering: "LP2-0-57"``); book ("complete set")
page = LP2 page + 17. LP1 pages are ``0..16`` (``"LP1-0-16"``), equal to book pages.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from runeforge import gematria as gm
from runeforge.paths import CANON_DIR

LP2_FILE = "lp2_runes.json"
LP1_FILE = "lp1_runes.json"
SOLVED_FILE = "solved_sections.json"
PIN_FILE = "lp2_runes.sha256"

LP2_NUMBERING = "LP2-0-57"
LP1_NUMBERING = "LP1-0-16"
UNSOLVED_LP2_PAGES = tuple(range(56))  # 0-55; page 50 carries no runes


class CanonIntegrityError(RuntimeError):
    """The canon on disk does not match its pinned hashes."""


def indices_sha256(indices) -> str:
    """SHA-256 of the comma-joined decimal indices (Dukotah PROBLEM.json convention)."""
    return hashlib.sha256(",".join(str(int(i)) for i in indices).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- serialisation


def dumps_canon(header: dict, pages: list[dict]) -> str:
    """Deterministic JSON: header pretty-printed, one page per line (diff-friendly)."""
    head = json.dumps(header, ensure_ascii=False, indent=1)
    assert head.endswith("\n}")
    rows = ",\n".join(
        "  " + json.dumps(p, ensure_ascii=False, separators=(",", ":")) for p in pages
    )
    return head[:-2] + ',\n "pages": [\n' + rows + "\n ]\n}\n"


@dataclass(frozen=True)
class Pin:
    sha256: str
    name: str
    note: str = ""


def read_pins(path: Path | None = None) -> dict[str, Pin]:
    pins = {}
    for line in (path or CANON_DIR / PIN_FILE).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        pins[parts[1]] = Pin(parts[0], parts[1], parts[2] if len(parts) > 2 else "")
    return pins


def format_pins(pins: list[Pin]) -> str:
    lines = [
        "# runeforge canon pins (SHA-256). Every load of the canon asserts these.",
        "# Regenerate only with scripts/build_canon.py; 'indices:*' hash the comma-joined",
        "# rune indices, so they are independent of JSON formatting and comparable upstream",
        "# (indices:LP2:unsolved == Dukotah/cicada3301 PROBLEM.json ciphertext_identity).",
    ]
    lines += [f"{p.sha256}  {p.name}" + (f"  {p.note}" if p.note else "") for p in pins]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- model


@dataclass(frozen=True)
class Page:
    part: str
    page: int
    book_page: int
    status: str  # unsolved | solved | runeless
    section: str | None
    raw: str
    lines: tuple[tuple[tuple[int, ...], ...], ...]
    line_continues: tuple[bool, ...]

    @property
    def runes(self) -> np.ndarray:
        return np.array([i for line in self.lines for w in line for i in w], dtype=np.int64)

    @property
    def n_runes(self) -> int:
        return sum(len(w) for line in self.lines for w in line)

    def words(self) -> list[list[int]]:
        """Words on this page, re-joining fragments split by a line break."""
        out: list[list[int]] = []
        join = False
        for line, cont in zip(self.lines, self.line_continues, strict=True):
            for k, w in enumerate(line):
                if k == 0 and join and out:
                    out[-1] = out[-1] + list(w)
                else:
                    out.append(list(w))
            join = cont
        return out


@dataclass(frozen=True)
class Canon:
    part: str
    numbering: str
    header: dict
    pages: tuple[Page, ...]

    def page(self, n: int) -> Page:
        p = self.pages[n]
        assert p.page == n
        return p

    def stream(self, pages=None) -> np.ndarray:
        sel = self.pages if pages is None else [self.page(n) for n in pages]
        parts = [p.runes for p in sel]
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)

    def sections(self) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for p in self.pages:
            if p.section is not None:
                out.setdefault(p.section, []).append(p.page)
        return out


def _parse(text: str) -> Canon:
    data = json.loads(text)
    pages = tuple(
        Page(
            part=data["part"],
            page=p["page"],
            book_page=p["book_page"],
            status=p["status"],
            section=p.get("section"),
            raw=p["raw"],
            lines=tuple(tuple(tuple(w) for w in line) for line in p["lines"]),
            line_continues=tuple(p["line_continues"]),
        )
        for p in data["pages"]
    )
    header = {k: v for k, v in data.items() if k != "pages"}
    return Canon(data["part"], data["numbering"], header, pages)


def _verify(canon: Canon, path: Path, pins: dict[str, Pin]) -> None:
    fname = path.name
    if fname not in pins:
        raise CanonIntegrityError(f"no pin for {fname}")
    got = file_sha256(path)
    if got != pins[fname].sha256:
        raise CanonIntegrityError(f"{fname}: sha256 {got} != pinned {pins[fname].sha256}")
    key = f"indices:{canon.part}:all"
    got = indices_sha256(canon.stream())
    if got != pins[key].sha256:
        raise CanonIntegrityError(f"{key}: sha256 {got} != pinned {pins[key].sha256}")
    if canon.part == "LP2":
        got = indices_sha256(canon.stream(UNSOLVED_LP2_PAGES))
        if got != pins["indices:LP2:unsolved"].sha256:
            raise CanonIntegrityError("indices:LP2:unsolved does not match its pin")


@lru_cache(maxsize=4)
def _load(fname: str, canon_dir: str) -> Canon:
    d = Path(canon_dir)
    path = d / fname
    canon = _parse(path.read_text(encoding="utf-8"))
    _verify(canon, path, read_pins(d / PIN_FILE))
    return canon


def load_lp2(canon_dir: Path | None = None) -> Canon:
    return _load(LP2_FILE, str(canon_dir or CANON_DIR))


def load_lp1(canon_dir: Path | None = None) -> Canon:
    return _load(LP1_FILE, str(canon_dir or CANON_DIR))


def unsolved_stream(canon_dir: Path | None = None) -> np.ndarray:
    """The 12,956-rune unsolved LP2 stream (pages 0-55, flattened)."""
    return load_lp2(canon_dir).stream(UNSOLVED_LP2_PAGES)


def unsolved_sections(canon_dir: Path | None = None) -> dict[str, np.ndarray]:
    """The nine unsolved sections (book order) as flat rune streams."""
    lp2 = load_lp2(canon_dir)
    return {
        name: lp2.stream(pages)
        for name, pages in lp2.sections().items()
        if all(lp2.page(n).status in ("unsolved", "runeless") for n in pages)
    }


# --------------------------------------------------------------------------- solved sections


@dataclass(frozen=True)
class SolvedSection:
    id: str
    title: str
    part: str
    numbering: str
    pages: tuple[int, ...]
    method: dict
    interrupts: tuple[int, ...]
    cipher: np.ndarray
    plain: np.ndarray
    plain_text: str
    template: str


@lru_cache(maxsize=2)
def _load_solved(canon_dir: str) -> tuple[SolvedSection, ...]:
    d = Path(canon_dir)
    path = d / SOLVED_FILE
    pins = read_pins(d / PIN_FILE)
    got = file_sha256(path)
    if got != pins[SOLVED_FILE].sha256:
        raise CanonIntegrityError(f"{SOLVED_FILE}: sha256 {got} != pinned")
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        SolvedSection(
            id=s["id"],
            title=s["title"],
            part=s["part"],
            numbering=s["numbering"],
            pages=tuple(s["pages"]),
            method=s["method"],
            interrupts=tuple(s["interrupts"]),
            cipher=gm.runes_to_indices(s["cipher"]),
            plain=gm.runes_to_indices(s["plain"]),
            plain_text=s["plain_text"],
            template=s["template"],
        )
        for s in data["sections"]
    )


def load_solved_sections(canon_dir: Path | None = None) -> tuple[SolvedSection, ...]:
    return _load_solved(str(canon_dir or CANON_DIR))


def solved_section(section_id: str, canon_dir: Path | None = None) -> SolvedSection:
    for s in load_solved_sections(canon_dir):
        if s.id == section_id:
            return s
    raise KeyError(section_id)


# --------------------------------------------------------------------------- rendering


def render(template: str, indices) -> str:
    """Render rune indices into a raw rtkd template (rune positions are replaced in order).

    ``-`` becomes a space, ``.`` a full stop and space, ``&`` a paragraph break; a line
    break ``/`` joins a word split across lines and is a space otherwise.
    """
    values = [int(i) for i in indices]
    chars = [c for c in template if c != "\n"]
    n_slots = sum(1 for c in chars if gm.is_rune(c))
    if n_slots != len(values):
        raise ValueError(f"template has {n_slots} rune positions, got {len(values)} indices")
    it = iter(values)
    out: list[str] = []
    for k, c in enumerate(chars):
        if gm.is_rune(c):
            out.append(gm.LATIN[next(it)])
        elif c == "-":
            out.append(" ")
        elif c == ".":
            out.append(". ")
        elif c == "&":
            out.append("\n")
        elif c in "$§":
            continue
        elif c == "/":
            prev = chars[k - 1] if k else ""
            nxt = next((x for x in chars[k + 1 :] if x not in "&$§"), "")
            out.append("" if gm.is_rune(prev) and gm.is_rune(nxt) else " ")
        else:
            out.append(c)
    text = "".join(out)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)
