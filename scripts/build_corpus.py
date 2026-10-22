#!/usr/bin/env python3
"""Build the rune corpora in data/corpora/ offline from SHA-256-pinned vendored texts.

    python scripts/build_corpus.py                      # every corpus in SOURCES
    python scripts/build_corpus.py latin lp-solved      # only these (index.json is merged)
    python scripts/build_corpus.py --out DIR --raw DIR  # elsewhere (the tests build into tmp)
    python scripts/build_corpus.py --list               # print the table, build nothing

Gutenberg is not reachable from the build machine, but the vendored Dukotah repo carries the
texts, so every corpus is rebuilt from a file under data/raw whose SHA-256 is pinned below (a
mismatch is a hard error: a silently different text would change every gate and scorer that
trains on it). Each text is cut to its body by literal markers, normalised to A-Z, split into
words and transliterated with runeforge.gematria.DEFAULT_RULES. Output per corpus:
``<name>.npz`` (runes int8, word_ids int32, meta JSON) and one entry in ``index.json``.
Outputs are deterministic and gitignored; this script and its table are the record.

To add a corpus: append a Spec to SOURCES (and its file to the dukotah) sparse path list in
scripts/fetch_raw.sh so CI's sparse checkout has it).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runeforge import canon  # noqa: E402
from runeforge import gematria as gm  # noqa: E402
from runeforge.corpus import INDEX_FILE  # noqa: E402
from runeforge.paths import CORPORA_DIR, RAW_DIR  # noqa: E402

DUK = "dukotah/liber-primus"


@dataclass(frozen=True)
class Text:
    """One vendored file and the rule that cuts it to its body.

    ``start`` (inclusive, must occur exactly once) and ``end`` (exclusive, first occurrence
    after ``start``) are literal strings in the raw file; None means file start / end.
    ``drop`` removes each (from, to) span (from inclusive, to exclusive; from must occur once).
    ``drop_lines`` is a regex; lines of the *normalised* body that match it are removed.
    """

    path: str  # relative to data/raw
    sha256: str
    start: str | None = None
    end: str | None = None
    drop: tuple[tuple[str, str], ...] = ()
    drop_lines: str | None = None


@dataclass(frozen=True)
class Spec:
    name: str
    register: str
    language: str  # ISO 639 code
    texts: tuple[Text, ...] = ()  # concatenated in order
    derive: str | None = None  # "canon:solved" | "vowel-dropped:<base corpus>"
    note: str = ""


SELF_RELIANCE = Text(
    f"{DUK}/data/keys/self_reliance.txt",
    "b2f3dbd3866e0bec5ae41ac29df09b537c2ef18fa1b88678966587b824ca92f0",
)
EMERSON_ESSAYS_1 = Text(
    f"{DUK}/data/keys/armada18/emerson_essays_first_series.txt",
    "0559e94b304079ebbc5d4d8500eb62b3cf88f4981a98f0151f3abd0ec6e1d7b8",
    start="I.\nHISTORY\n",
    end="Next Volume",
    # Self-Reliance already comes from self_reliance.txt; do not train on it twice.
    drop=(("II.\nSELF-RELIANCE\n", "III.\nCOMPENSATION\n"),),
    drop_lines=r"^\s*[IVXLC]+\.\s*$",  # essay-number lines
)
MOBY_DICK = Text(
    f"{DUK}/data/keys/armada18/melville_moby_dick.txt",
    "9a6844ac0703853720010787c7b6c70b0020f1ab1862dcd74452fa46474d1215",
    start="CHAPTER 1. Loomings.\n\nCall me Ishmael.",  # after contents, etymology, extracts
    end="*** END OF THE PROJECT GUTENBERG EBOOK",
)
CAESAR_BG = Text(
    f"{DUK}/analysis/latin/latin_218.txt",
    "84ac8411841a4d8f5f4a49b6a2cd1f466917c6a5af72916d5e0b2b1ecb2f659c",
    start="C. IULI CAESARIS DE BELLO GALLICO COMMENTARIUS PRIMUS",
    end="End of Project Gutenberg's",
)
BEOWULF = Text(
    f"{DUK}/analysis/round10b/B6-non-english-plaintext/corpora/oe_beowulf.txt",
    "5190b80b0829da81b1b375a5494909dc751aa365de6a88a816b576c048c54839",
    start="BĒOWULF.\n\nI. THE PASSING OF SCYLD.",
    end="LIST OF NAMES; NOTES; AND GLOSSARY.",
    drop_lines=r"^[^a-z]*$",  # the editors' modern-English fitt headings carry no lowercase
)

SOURCES: tuple[Spec, ...] = (
    Spec(
        "cicada-english",
        "cicada-english",
        "en",
        (SELF_RELIANCE, EMERSON_ESSAYS_1),
        note="Emerson: Self-Reliance first, then Essays First Series without its Self-Reliance",
    ),
    Spec("english-general", "english-general", "en", (MOBY_DICK,), note="Melville, Moby-Dick"),
    Spec(
        "lp-solved",
        "lp-solved",
        "en",
        derive="canon:solved",
        note="the nine solved sections' plaintext (Cicada-English spellings)",
    ),
    Spec(
        "latin",
        "latin",
        "la",
        (CAESAR_BG,),
        note=(
            "Caesar, De Bello Gallico I-IV. Not latin_28233 (Newton's Principia): about 10% of "
            "its tokens are geometric point labels (AB, FG, ...). Roman numerals kept as words."
        ),
    ),
    Spec(
        "old-english",
        "old-english",
        "ang",
        (BEOWULF,),
        note="Beowulf + the Finnsburh fragment (Harrison & Sharp text, line numbers dropped)",
    ),
    Spec(
        "vowel-dropped-english",
        "vowel-dropped-english",
        "en",
        derive="vowel-dropped:english-general",
        note="english-general with every vowel rune after a word's first rune removed",
    ),
)
SPECS = {s.name: s for s in SOURCES}

# Text normalisation before word splitting: NFKD with combining marks dropped (macrons and
# accents: ē -> e, ǣ -> æ), then these letters spelled out. Any other non-A-Z character,
# including apostrophes, hyphens and Greek, separates words (as murphy's english_stream).
LETTERS = {"Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe", "Þ": "TH", "þ": "th", "Ð": "TH", "ð": "th"}
LETTERS |= {"ß": "ss", "ſ": "s", "Ƿ": "W", "ƿ": "w"}
_LETTER_TABLE = str.maketrans(LETTERS)

# vowel-dropped: the vowel runes U O I E A Y and the vowel digraph runes EO OE AE IA EA.
# Removed everywhere except at a word's first rune, so no word vanishes ("A", "I", "OF" stay
# as A, I, O) and word ids are unchanged. U is also V (V -> U), so a V is dropped too.
VOWELS = ("U", "O", "I", "E", "A", "Y", "EO", "OE", "AE", "IA", "EA")
VOWEL_RUNES = tuple(sorted(gm.LATIN.index(v) for v in VOWELS))


class BuildError(RuntimeError):
    """A source is missing, does not match its pin, or does not have its markers."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def indices_sha256(runes: np.ndarray) -> str:
    """Comma-joined decimal indices, the canon pin convention (runeforge.canon.indices_sha256)."""
    return hashlib.sha256(",".join(map(str, runes.tolist())).encode()).hexdigest()


def rules_record(rules: gm.TransliterationRules = gm.DEFAULT_RULES) -> dict:
    return {
        "transliteration": "runeforge.gematria.DEFAULT_RULES",
        "substitutions": " ".join(f"{a}->{b}" for a, b in rules.substitutions),
        "graphemes": " ".join(f"{g}={i}" for g, i in rules.ordered_graphemes()),
        "normalize": "NFKD, combining marks dropped, then "
        + ", ".join(f"{k}->{v}" for k, v in LETTERS.items()),
        "words": "maximal runs of A-Z after upper-casing; every other character separates words",
    }


# --------------------------------------------------------------------------- text -> runes


def read_source(t: Text, raw_dir: Path) -> str:
    path = raw_dir / t.path
    if not path.exists():
        raise BuildError(f"{path} missing; run scripts/fetch_raw.sh")
    got = sha256_file(path)
    if got != t.sha256:
        raise BuildError(f"{t.path}: sha256 {got} != pinned {t.sha256}; refusing to build")
    return path.read_text(encoding="utf-8")


def extract_body(text: str, t: Text) -> str:
    if t.start is not None:
        if text.count(t.start) != 1:
            raise BuildError(f"{t.path}: start marker {t.start!r} occurs {text.count(t.start)}x")
        text = text[text.index(t.start) :]
    if t.end is not None:
        i = text.find(t.end)
        if i < 0:
            raise BuildError(f"{t.path}: end marker {t.end!r} not found after start")
        text = text[:i]
    for a, b in t.drop:
        i = text.find(a)
        j = text.find(b, i + len(a)) if i >= 0 else -1
        if text.count(a) != 1 or j < 0:
            raise BuildError(f"{t.path}: drop span {a!r} .. {b!r} not found exactly once")
        text = text[:i] + text[j:]
    return text


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.translate(_LETTER_TABLE)


def transliterate(text: str, rules: gm.TransliterationRules = gm.DEFAULT_RULES) -> list[list[int]]:
    """Same output as ``gematria.transliterate_words(text, rules)``, memoised per distinct word."""
    cache: dict[str, list[int]] = {}
    out = []
    for w in re.findall(r"[A-Z]+", text.upper()):
        r = cache.get(w)
        if r is None:
            r = cache[w] = gm.transliterate_word(w, rules)
        out.append(r)
    return out


def text_words(t: Text, raw_dir: Path) -> tuple[list[list[int]], dict]:
    body = normalize(extract_body(read_source(t, raw_dir), t))
    if t.drop_lines is not None:
        pat = re.compile(t.drop_lines)
        body = "\n".join(line for line in body.split("\n") if not pat.match(line))
    stray = sum(1 for c in body if c.isalpha() and not c.isascii())
    rec = {k: v for k, v in asdict(t).items() if v not in (None, ())}
    rec["non_latin_letters_dropped"] = stray  # e.g. Greek quotations: word separators
    return transliterate(body), rec


def solved_words(canon_dir: Path | None = None) -> tuple[list[list[int]], dict]:
    """The solved sections' plaintext, word boundaries from each plain_text.

    Tokens containing a digit (AN END's hash, SOME WISDOM's numbers) are not runes and are
    skipped; the result must equal each section's plain rune stream exactly.
    """
    words: list[list[int]] = []
    for s in canon.load_solved_sections(canon_dir):
        sec: list[list[int]] = []
        for tok in s.plain_text.split():
            if not any(c.isdigit() for c in tok):
                sec += gm.transliterate_words(tok)
        if [i for w in sec for i in w] != s.plain.tolist():
            raise BuildError(f"solved section {s.id}: plain_text does not re-derive its runes")
        words += sec
    pins = canon.read_pins((canon_dir or canon.CANON_DIR) / canon.PIN_FILE)
    rec = {
        "path": f"data/canon/{canon.SOLVED_FILE}",
        "sha256": pins[canon.SOLVED_FILE].sha256,
        "sections": [s.id for s in canon.load_solved_sections(canon_dir)],
        "rule": "plain_text tokens with a digit skipped; checked rune-for-rune against plain",
    }
    return words, rec


def to_arrays(words: list[list[int]]) -> tuple[np.ndarray, np.ndarray]:
    words = [w for w in words if w]
    lens = np.array([len(w) for w in words], dtype=np.int64)
    runes = np.array([i for w in words for i in w], dtype=np.int64)
    return runes, np.repeat(np.arange(lens.size, dtype=np.int64), lens)


def drop_vowels(runes: np.ndarray, word_ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    first = np.ones(runes.size, dtype=bool)
    first[1:] = word_ids[1:] != word_ids[:-1]
    keep = first | ~np.isin(runes, VOWEL_RUNES)
    return runes[keep], word_ids[keep]


# --------------------------------------------------------------------------- build


def build_one(
    spec: Spec, raw_dir: Path, canon_dir: Path | None, done: dict
) -> tuple[np.ndarray, np.ndarray, dict]:
    if spec.name in done:
        return done[spec.name]
    meta: dict = {"name": spec.name, "register": spec.register, "language": spec.language}
    if spec.derive == "canon:solved":
        words, rec = solved_words(canon_dir)
        runes, word_ids = to_arrays(words)
        meta |= {"sources": [rec], "numbering": canon.LP2_NUMBERING}
    elif spec.derive and spec.derive.startswith("vowel-dropped:"):
        base = SPECS[spec.derive.split(":", 1)[1]]
        b_runes, b_words, b_meta = build_one(base, raw_dir, canon_dir, done)
        runes, word_ids = drop_vowels(b_runes, b_words)
        meta |= {
            "derived_from": base.name,
            "derived_from_indices_sha256": b_meta["indices_sha256"],
            "sources": b_meta["sources"],
            "rule": f"drop vowel runes {list(VOWEL_RUNES)} except at a word's first rune",
        }
    elif spec.texts:
        words, recs = [], []
        for t in spec.texts:
            w, rec = text_words(t, raw_dir)
            words += w
            recs.append(rec | {"n_words": len(w)})
        runes, word_ids = to_arrays(words)
        meta["sources"] = recs
    else:
        raise BuildError(f"{spec.name}: no texts and no derive rule")
    meta |= {
        "n_runes": int(runes.size),
        "n_words": int(word_ids[-1] + 1) if word_ids.size else 0,
        "indices_sha256": indices_sha256(runes),
        "rules": rules_record(),
        "note": spec.note,
    }
    done[spec.name] = (runes, word_ids, meta)
    return done[spec.name]


def write(out_dir: Path, runes: np.ndarray, word_ids: np.ndarray, meta: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{meta['name']}.npz"
    np.savez_compressed(
        path,
        runes=runes.astype(np.int8),
        word_ids=word_ids.astype(np.int32),
        meta=np.array(json.dumps(meta, ensure_ascii=False, sort_keys=True)),
    )
    return path


def build(
    names: list[str] | None = None,
    out_dir: Path | None = None,
    raw_dir: Path | None = None,
    canon_dir: Path | None = None,
) -> dict:
    """Build the named corpora (default: all) and merge them into ``out_dir/index.json``."""
    out_dir = Path(out_dir or CORPORA_DIR)
    raw_dir = Path(raw_dir or RAW_DIR)
    unknown = [n for n in names or () if n not in SPECS]
    if unknown:
        raise BuildError(f"unknown corpus {unknown}; known: {', '.join(SPECS)}")
    index_path = out_dir / INDEX_FILE
    index = {"corpora": {}}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    done: dict = {}
    for name in names or list(SPECS):
        runes, word_ids, meta = build_one(SPECS[name], raw_dir, canon_dir, done)
        write(out_dir, runes, word_ids, meta)
        index["corpora"][name] = meta
    index = {
        "$comment": "Generated by scripts/build_corpus.py -- do not hand-edit.",
        "numbering": canon.LP2_NUMBERING,
        "corpora": {
            k: index["corpora"][k]
            for k in sorted(index["corpora"])
            if (out_dir / f"{k}.npz").exists()
        },
    }
    index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", "utf-8")
    return index


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("names", nargs="*", help=f"corpora to build (default all: {', '.join(SPECS)})")
    ap.add_argument("--out", type=Path, default=None, help="output dir (default data/corpora)")
    ap.add_argument("--raw", type=Path, default=None, help="vendored sources (default data/raw)")
    ap.add_argument("--list", action="store_true", help="print the SOURCES table and exit")
    args = ap.parse_args(argv)
    if args.list:
        for s in SOURCES:
            src = ", ".join(t.path for t in s.texts) or s.derive
            print(f"{s.name:24} {s.register:24} {s.language:4} {src}")
        return 0
    try:
        index = build(args.names or None, args.out, args.raw)
    except BuildError as e:
        print(f"build_corpus: {e}", file=sys.stderr)
        return 1
    for name in args.names or list(SPECS):
        m = index["corpora"][name]
        print(f"{name:24} {m['n_runes']:>9,} runes {m['n_words']:>8,} words  {m['language']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
