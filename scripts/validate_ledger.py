#!/usr/bin/env python3
"""Validate the append-only lane ledger (``ledger/ledger.jsonl``): the gate every session runs.

A port of Dukotah's ``liber-primus/analysis/handoff/validate_ledger.py`` to this JSONL ledger.
Standard library only, because it runs from the Stop hook, possibly outside the venv. It
re-checks ``runeforge.ledger.LedgerRow``'s rules independently, so a row written by hand or by
an older version of that model is still caught. Checks, in order of how much they matter:

  1. UNSOUND NEGATIVES: ``status: negative`` without ``positive_control: passed``. A null from
     an instrument never shown to recover a planted key is an unknown wearing a negative's
     clothes (Rule 2). A failed control is only ever ``inconclusive``; a verified hit needs a
     passing control too.
  2. THRESHOLDS: a negative needs a threshold fixed in advance, and once a lane has fixed one,
     no later row of that lane may change it (never edit a threshold after seeing a result).
  3. EVIDENCE: every ``evidence`` path exists, relative to the repo root (``#anchor`` suffixes
     and globs allowed). ERROR on a concluded row (negative, inconclusive, hit-*), else WARN.
  4. DANGLING LINKS: ``supersedes`` / ``superseded_by`` name lanes that appear in the ledger,
     and a ``superseded`` row names its successor.
  5. SCHEMA: required keys, the controlled vocabularies, field types, no unknown fields,
     ``numbering: LP2-0-57``, the three conditionals on every negative. A malformed line is
     reported by its line number.
  6. APPEND-ONLY: the ledger committed at HEAD is a byte prefix of the working file. This is
     the analogue of Dukotah's count-drift check: there a stale ``counts`` block misstated the
     rows under it; here a rewritten or deleted row would silently rewrite the record.

Every rule runs on EVERY row, not only on the latest row per lane: ``Ledger.rows()`` validates
each row through the pydantic model, so one bad historical row makes the whole ledger
unreadable to ``runeforge status``. A clean run here is a ledger runeforge can read. The status
recount in the header, and the NOTES, use the latest row per lane, which is each lane's state.

Exit code 1 on any ERROR (``--strict``: on any WARN too), else 0. A missing or empty ledger is
valid. The last line of the text output is always ``Unsound negatives = <n>``;
SESSION_PROMPT.md §A step 4 requires it to read 0.

    python scripts/validate_ledger.py [--ledger PATH] [--root DIR] [--strict] [--no-git] [--json]
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import itertools
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Same default and override as runeforge.paths.LEDGER_PATH, so the gate checks the file the
# CLI writes.
LEDGER = Path(os.environ.get("RUNEFORGE_LEDGER", ROOT / "ledger" / "ledger.jsonl"))

# Mirrors of runeforge/ledger.py. tests/test_validate_ledger.py pins every one of them to the
# pydantic model, so the two cannot drift apart without a red test.
STATUSES = (
    "never-run",
    "running",
    "parked",
    "inconclusive",
    "negative",
    "hit-unverified",
    "hit-verified",
    "superseded",
)
VERDICTS = (
    "NULL",
    "CANDIDATE",
    "INCONCLUSIVE (power)",
    "EXCLUDED (gate)",
    "FOUND-ERROR",
    "NO-ERROR-FOUND",
)
POSITIVE_CONTROLS = ("none", "passed", "failed")
CATEGORIES = ("instrument", "bounded", "redteam", "closeout")
CONDITIONALS = ("key_space", "decoder", "register")
NUMBERING = "LP2-0-57"
REQUIRED = ("lane_id", "hypothesis", "family", "status")
OPEN = ("never-run", "running", "parked")
CONCLUDED = ("negative", "inconclusive", "hit-unverified", "hit-verified")
RESULT_SEEN = ("negative", "hit-unverified", "hit-verified")  # a bar here was used on a result

NUM = (int, float)
NONE = type(None)
JSON_NAMES = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dict: "object",
    list: "array",
    NONE: "null",
}
# LedgerRow's fields and the JSON types each may hold. Every list field is a list of strings.
FIELDS: dict[str, tuple[type, ...]] = {
    "lane_id": (str,),
    "hypothesis": (str,),
    "family": (str,),
    "category": (str, NONE),
    "round": (str, int, NONE),  # LedgerRow coerces an integer round to str
    "numbering": (str,),
    "status": (str,),
    "verdict": (str, NONE),
    "prereg": (str, NONE),
    "threshold": (*NUM, str, NONE),
    "threshold_fixed_in_advance": (bool,),
    "claim_bar": (*NUM, NONE),
    "family_wise_bar": (*NUM, NONE),
    "n_trials": (int,),
    "params": (dict,),
    "control_spec": (dict,),
    "positive_control": (str,),
    "control_detail": (dict, str, NONE),
    "null": (dict, NONE),
    "result": (dict, NONE),
    "best_score": (*NUM, NONE),
    "best_candidate_ref": (str, NONE),
    "coverage": (str, NONE),
    "not_covered": (str, NONE),
    "conditionals": (dict, NONE),
    "reopens_if": (str, NONE),
    "external_ids": (list,),
    "evidence": (list,),
    "reproduce": (str, NONE),
    "supersedes": (list,),
    "superseded_by": (list,),
    "parked_state": (dict, str, NONE),
    "started": (str, NONE),
    "finished": (str, NONE),
    "host": (str,),
    "git_sha": (str, NONE),
    "data_sha256": (str,),
    "notes": (str, NONE),
    "recorded": (str,),
}
VOCAB: dict[str, tuple[str | None, ...]] = {
    "status": STATUSES,
    "verdict": (*VERDICTS, None),
    "positive_control": POSITIVE_CONTROLS,
    "category": (*CATEGORIES, None),
    "numbering": (NUMBERING,),
}


@dataclass
class Report:
    ledger: str
    present: bool = False
    rows: int = 0
    lanes: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unsound_negatives: int = 0

    def exit_code(self, strict: bool = False) -> int:
        return 1 if self.errors or (strict and self.warnings) else 0


def _kind(value: object) -> str:
    return JSON_NAMES.get(type(value), type(value).__name__)


def _typed(value: object, kinds: tuple[type, ...]) -> bool:
    if isinstance(value, bool) and bool not in kinds:  # bool is an int to isinstance()
        return False
    if not isinstance(value, kinds):
        return False
    return not isinstance(value, list) or all(isinstance(x, str) for x in value)


def _as_list(value: object) -> list[str]:
    """A link or evidence field as a list of strings. A bare string (Dukotah's ledger has a few)
    is one path, not a sequence of characters; other wrong types were reported by the schema."""
    if isinstance(value, str):
        return [value]
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def _no_constant(name: str) -> object:
    raise ValueError(f"{name} is not JSON")


def evidence_exists(path: str, root: Path) -> bool:
    """A trailing ``#anchor`` points into a document and is not part of the filename."""
    p = path.split("#", 1)[0].strip()
    if not p:
        return False
    if any(c in p for c in "*?["):
        return bool(glob.glob(p, root_dir=root, recursive=True))
    return (root / p).exists()


def _git_ignored(path: str, root: Path) -> bool:
    p = path.split("#", 1)[0].strip()
    if not p or os.path.isabs(p):
        return False
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", "--no-index", "--", p],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return r.returncode == 0


def repaired_lanes(rows: list[tuple[int, dict]]) -> dict[str, str]:
    """Lanes whose latest row is ``superseded`` and whose successor's rows link back with
    ``supersedes``: {lane: successor(s)}. Mirrors ``runeforge.ledger.repaired_lanes``."""
    latest: dict[str, dict] = {}
    links: dict[str, set[str]] = {}
    for _, row in rows:
        lane = row.get("lane_id")
        if not isinstance(lane, str):
            continue
        latest[lane] = row
        for ref in _as_list(row.get("supersedes")):
            links.setdefault(ref, set()).add(lane)
    out = {}
    for lane, row in latest.items():
        succ = [x for x in _as_list(row.get("superseded_by")) if x in links.get(lane, set())]
        if row.get("status") == "superseded" and succ:
            out[lane] = ", ".join(succ)
    return out


def _parse(raw: bytes, rep: Report) -> list[tuple[int, dict]]:
    rows = []
    for n, line in enumerate(raw.split(b"\n"), 1):
        if not line.strip():
            continue
        rep.rows += 1
        try:
            text = line.decode("utf-8")
            row = json.loads(text, parse_constant=_no_constant)
        except ValueError as exc:  # UnicodeDecodeError and JSONDecodeError are ValueErrors
            rep.errors.append(f"line {n}: malformed row ({exc})")
            continue
        if not isinstance(row, dict):
            rep.errors.append(f"line {n}: a row is a JSON object, not {_kind(row)}")
            continue
        if len(text.splitlines()) > 1:
            rep.errors.append(
                f"[{row.get('lane_id')}] line {n}: a raw line break (CR, U+0085, U+2028 ...) "
                "inside the row; Ledger.rows() splits lines with str.splitlines() and cannot "
                "read it. Escape it."
            )
        try:
            json.dumps(row, ensure_ascii=False).encode("utf-8")
        except UnicodeEncodeError:
            rep.errors.append(
                f"[{row.get('lane_id')}] line {n}: a lone surrogate escape (\\ud800 ...); "
                "LedgerRow cannot read it"
            )
        rows.append((n, row))
    return rows


def _check_row(
    n: int, row: dict, lane_ids: set[str], root: Path, rep: Report, repaired_by: str = ""
) -> None:
    """``repaired_by``: this is a historical row of a lane that has since been superseded with
    a ``supersedes`` link (SESSION_PROMPT.md section A step 4). Its findings stay visible as
    WARNs and are not counted: rows are append-only, so the repair can never remove them."""
    lane = row.get("lane_id") if isinstance(row.get("lane_id"), str) else None
    at = f"[{lane or '<no lane_id>'}] line {n}:"
    warn = rep.warnings.append
    if repaired_by:

        def err(msg: str) -> None:
            warn(f"{msg} [historical row; repaired: superseded by {repaired_by}]")

    else:
        err = rep.errors.append
    status = row.get("status")
    pc = row.get("positive_control", "none")

    # 5. schema
    for k in REQUIRED:
        if not str(row.get(k) or "").strip():
            err(f"{at} missing required field `{k}`")
    unknown = sorted(set(row) - set(FIELDS))
    if unknown:
        err(
            f"{at} unknown field(s) {unknown}: LedgerRow forbids extra fields, so runeforge "
            "cannot read this row"
        )
    for k, allowed in VOCAB.items():
        if k in row and row[k] not in allowed:
            err(f"{at} {k} {row[k]!r} is not in the controlled vocabulary")
    if "numbering" not in row:
        err(f"{at} no `numbering`; every row states {NUMBERING!r}")
    for k, kinds in FIELDS.items():
        if k in VOCAB or k not in row or (k in REQUIRED and row[k] in (None, "")):
            continue
        if not _typed(row[k], kinds):
            want = " | ".join(sorted({JSON_NAMES[t] for t in kinds}))
            what = "array with a non-string item" if isinstance(row[k], list) else _kind(row[k])
            err(f"{at} `{k}` is {what}, expected {want}")
    cond = row.get("conditionals")
    if isinstance(cond, dict) and not all(isinstance(v, str) for v in cond.values()):
        err(f"{at} `conditionals` values are strings")

    # 1. unsound negatives (and the other control rules of the model)
    if status == "negative" and pc != "passed":
        rep.unsound_negatives += 0 if repaired_by else 1
        err(
            f"{at} UNSOUND NEGATIVE: status=negative but positive_control={pc!r}. A null from "
            "an instrument never shown to recover a planted key is not a negative; record the "
            "passing control, or the lane is `inconclusive`."
        )
    if status == "hit-verified" and pc != "passed":
        err(
            f"{at} hit-verified but positive_control={pc!r}; a verified hit needs a passing control"
        )
    if pc == "passed":
        _check_control_evidence(at, row.get("control_detail"), root, err)
    if row.get("verdict") == "CANDIDATE" and status not in ("hit-unverified", "hit-verified"):
        err(f"{at} verdict CANDIDATE goes with hit-unverified or hit-verified, not {status!r}")
    if status == "running" and row.get("started") in (None, ""):
        err(f"{at} running without `started`")
    if pc == "failed" and status in ("negative", "hit-verified"):
        err(f"{at} positive_control failed but status {status!r}; a failed control is inconclusive")
    if row.get("threshold_fixed_in_advance") is True and row.get("threshold") in (None, ""):
        err(
            f"{at} threshold_fixed_in_advance is true but no threshold is recorded; a bar filled "
            "in later is a post-hoc bar"
        )

    # 2. thresholds and the conditionals every negative (and verified hit) carries
    if status in ("negative", "hit-verified"):
        thr, fixed = row.get("threshold"), row.get("threshold_fixed_in_advance")
        if thr in (None, "") or fixed is not True:
            err(
                f"{at} {status} without a threshold fixed in advance (threshold={thr!r}, "
                f"threshold_fixed_in_advance={fixed!r}); a post-hoc bar is not a test"
            )
        have = cond if isinstance(cond, dict) else {}
        missing = [k for k in CONDITIONALS if not have.get(k)]
        if missing:
            err(
                f"{at} {status} without its conditionals {missing}; every negative and verified "
                "hit states key space, decoder and register"
            )

    # 3. evidence
    evidence = _as_list(row.get("evidence"))
    for p in evidence:
        if not evidence_exists(p, root):
            if _git_ignored(p, root):
                warn(
                    f"{at} evidence {p!r} is under a gitignored path, so no clone has it; cite "
                    "a committed file (RESULTS.md, a report, result JSON) instead"
                )
            else:
                (err if status in CONCLUDED else warn)(f"{at} evidence path does not exist: {p!r}")
        elif os.path.isabs(p) or os.path.normpath(p).split(os.sep)[0] == "..":
            warn(f"{at} evidence path is outside the repository: {p!r}")
    if status in CONCLUDED and not evidence:
        warn(f"{at} {status} row lists no evidence")

    # 4. dangling links
    for fld in ("supersedes", "superseded_by"):
        for ref in _as_list(row.get(fld)):
            if ref == lane:
                err(f"{at} {fld} points at its own lane")
            elif ref not in lane_ids:
                err(f"{at} {fld} points at unknown lane {ref!r}")
    if status == "superseded" and not row.get("superseded_by"):
        err(f"{at} superseded without `superseded_by` naming its successor")


def _check_control_evidence(at: str, detail: object, root: Path, err) -> None:
    """Rule 2's evidence: positive_control 'passed' cites the committed control report
    (``lanes/<id>/control-<sha12>.json``) by path and SHA-256, and that report passed."""
    if not isinstance(detail, dict) or not detail.get("path") or not detail.get("sha256"):
        err(
            f"{at} positive_control 'passed' without control_detail {{path, sha256}}: a passing "
            "control is the report `runeforge control` wrote, not a word in the ledger"
        )
        return
    path = root / str(detail["path"])
    try:
        data = path.read_bytes()
    except OSError:
        err(
            f"{at} control report {detail['path']!r} does not exist (commit it with the lane)"
        )
        return
    if hashlib.sha256(data).hexdigest() != detail["sha256"]:
        err(f"{at} control report {detail['path']!r} does not match the recorded sha256")
        return
    try:
        status = json.loads(data).get("status")
    except (ValueError, AttributeError):
        status = None
    if status != "passed":
        err(f"{at} the cited control report says status={status!r}, not 'passed'")


def _check_lanes(rows: list[tuple[int, dict]], rep: Report, repaired: dict[str, str]) -> None:
    hist: dict[str, list[tuple[int, dict]]] = {}
    for n, row in rows:
        if isinstance(row.get("lane_id"), str) and row["lane_id"]:
            hist.setdefault(row["lane_id"], []).append((n, row))
    rep.lanes = len(hist)
    for lane, lane_rows in hist.items():
        # 2. the first row that fixes a threshold in advance freezes it for every later row
        frozen: tuple[int, object] | None = None
        unfixed_warned = False
        fixed_before: list[object] = []  # thresholds fixed in advance by earlier rows
        for n, row in lane_rows:
            thr, fixed = row.get("threshold"), row.get("threshold_fixed_in_advance") is True
            if row.get("status") in RESULT_SEEN and fixed and thr not in fixed_before:
                msg = (
                    f"[{lane}] line {n}: {row.get('status')} with threshold {thr!r} 'fixed in "
                    "advance', but no earlier row of the lane records it; pre-register the bar "
                    "before the run"
                )
                if lane in repaired and n != lane_rows[-1][0]:
                    rep.warnings.append(
                        f"{msg} [historical row; repaired: superseded by {repaired[lane]}]"
                    )
                else:
                    rep.errors.append(msg)
            if fixed:
                fixed_before.append(thr)
            if frozen is not None:
                if thr != frozen[1]:
                    msg = (
                        f"[{lane}] line {n}: threshold changed from {frozen[1]!r} (fixed in "
                        f"advance at line {frozen[0]}) to {thr!r}; never edit a threshold after "
                        "seeing a result -- append a dated addendum in `notes` instead"
                    )
                    if lane in repaired and n != lane_rows[-1][0]:
                        rep.warnings.append(
                            f"{msg} [historical row; repaired: superseded by {repaired[lane]}]"
                        )
                    else:
                        rep.errors.append(msg)
                if not fixed and not unfixed_warned:
                    unfixed_warned = True
                    rep.warnings.append(
                        f"[{lane}] line {n}: threshold_fixed_in_advance went back to false after "
                        f"line {frozen[0]} fixed the threshold"
                    )
            elif fixed:  # an empty threshold here is itself an error (_check_row)
                frozen = (n, thr)

        _, latest = lane_rows[-1]
        status = str(latest.get("status"))
        rep.by_status[status] = rep.by_status.get(status, 0) + 1
        if status in OPEN and not latest.get("reopens_if"):
            rep.notes.append(
                f"[{lane}] open lane ({status}) with no `reopens_if`; a future reader cannot tell "
                "what would settle it"
            )
        for ref in _as_list(latest.get("supersedes")):
            if ref in hist and ref != lane and hist[ref][-1][1].get("status") != "superseded":
                rep.notes.append(
                    f"[{lane}] supersedes {ref!r}, but {ref!r} is still "
                    f"{hist[ref][-1][1].get('status')!r}; append a `superseded` row for it with "
                    f"superseded_by [{lane!r}]"
                )


def _rows_in(blob: bytes) -> int:
    return sum(1 for x in blob.split(b"\n") if x.strip())


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    except OSError:  # no git on PATH, or no such directory
        return None


def _first_change(old: bytes, new: bytes) -> int:
    """1-based line of ``old`` where ``new`` stops extending it."""
    i = next((i for i, (a, b) in enumerate(zip(old, new, strict=False)) if a != b), len(new))
    return old[:i].count(b"\n") + 1


def _check_append_only(path: Path, raw: bytes, rep: Report, root: Path = ROOT) -> None:
    """6. Every committed version of the ledger extends the one before it, and the working file
    extends HEAD's. Checking only HEAD would let a rewrite pass once it is committed, and both
    automated gates (the Stop hook, overnight.sh) run after the commit. A rewrite Hunter
    approved is listed by commit SHA in ``ledger/REWRITES`` (one per line). Skipped when the
    ledger is not in a git repository; a shallow clone checks the history it has."""
    top = _git(root, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0:
        if top is not None and b"dubious ownership" in top.stderr:
            rep.notes.append(
                "append-only check skipped: git refuses this repository (safe.directory)"
            )
        return
    toplevel = Path(top.stdout.decode().strip())
    try:
        rel = path.resolve().relative_to(toplevel.resolve()).as_posix()
    except ValueError:
        return  # the ledger is outside this repository
    log = _git(toplevel, "log", "--format=%H", "--", rel)
    commits = log.stdout.decode().split() if log is not None and log.returncode == 0 else []
    allowed_file = toplevel / "ledger" / "REWRITES"
    allowed = set()
    if allowed_file.exists():
        allowed = {
            ln.split("#", 1)[0].strip()
            for ln in allowed_file.read_text(encoding="utf-8").splitlines()
            if ln.split("#", 1)[0].strip()
        }
    versions: list[tuple[str, bytes]] = []  # oldest first; b"" where the file was deleted
    for sha in reversed(commits):
        blob = _git(toplevel, "cat-file", "blob", f"{sha}:{rel}")
        data = blob.stdout if blob is not None and blob.returncode == 0 else b""
        versions.append((sha, data.replace(b"\r\n", b"\n")))
    versions.append(("working file", raw.replace(b"\r\n", b"\n")))
    for (_, old), (sha, new) in itertools.pairwise(versions):
        if new.startswith(old) or any(sha.startswith(a) for a in allowed if len(a) >= 7):
            continue
        what = f"commit {sha[:12]}" if sha != "working file" else "the working file"
        if old.startswith(new):
            rep.errors.append(
                f"APPEND-ONLY: {what} has {_rows_in(new)} rows where the version before it had "
                f"{_rows_in(old)}; rows were deleted. Rows are never deleted -- restore them and "
                "append a correcting row linked with `supersedes` (a rewrite Hunter approved "
                "goes in ledger/REWRITES)."
            )
        else:
            rep.errors.append(
                f"APPEND-ONLY: {what} rewrites line {_first_change(old, new)} of the version "
                "before it. Rows are never edited -- restore it and append a correcting row "
                "linked with `supersedes` (a rewrite Hunter approved goes in ledger/REWRITES)."
            )


def _display(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def validate(path: Path | str = LEDGER, root: Path | str = ROOT, use_git: bool = True) -> Report:
    path, root = Path(path).absolute(), Path(root)
    rep = Report(ledger=_display(path, root), present=path.exists())
    raw = b""
    if rep.present:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            rep.errors.append(f"cannot read the ledger: {exc}")
    if raw.strip() and not raw.endswith(b"\n"):
        rep.warnings.append(
            "the ledger does not end with a newline; the next Ledger.append() would join two "
            "rows on one line"
        )
    rows = _parse(raw, rep)
    lane_ids = {r["lane_id"] for _, r in rows if isinstance(r.get("lane_id"), str)}
    last_line = {r["lane_id"]: n for n, r in rows if isinstance(r.get("lane_id"), str)}
    repaired = repaired_lanes(rows)
    for n, row in rows:
        lane = row.get("lane_id")
        historical = isinstance(lane, str) and lane in repaired and last_line[lane] != n
        _check_row(n, row, lane_ids, root, rep, repaired[lane] if historical else "")
    _check_lanes(rows, rep, repaired)
    if use_git:
        _check_append_only(path, raw, rep, root)
    return rep


def render(rep: Report) -> str:
    head = f"{rep.ledger}  numbering {NUMBERING}  {rep.rows} rows, {rep.lanes} lanes"
    out = [head + ("  (status of the latest row per lane)" if rep.present else "  (no file yet)")]
    out += [
        f"   {st:18s} {k}" for st, k in sorted(rep.by_status.items(), key=lambda x: (-x[1], x[0]))
    ]
    out.append("")
    for label, items, cap in (
        ("ERRORS", rep.errors, None),
        ("WARNINGS", rep.warnings, 25),
        ("NOTES", rep.notes, 10),
    ):
        shown = items if cap is None else items[:cap]
        out += [f"{label}: {len(items)}", *(f"   {m}" for m in shown)]
        if len(items) > len(shown):
            out.append(f"   ... and {len(items) - len(shown)} more (--json lists all)")
        out.append("")
    out.append(f"Unsound negatives = {rep.unsound_negatives}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ledger", type=Path, default=LEDGER, help="default: ledger/ledger.jsonl")
    ap.add_argument(
        "--root", type=Path, default=ROOT, help="directory evidence paths resolve against"
    )
    ap.add_argument("--strict", action="store_true", help="fail on WARN as well as ERROR")
    ap.add_argument("--no-git", action="store_true", help="skip the append-only check")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args(argv)

    rep = validate(args.ledger, args.root, use_git=not args.no_git)
    code = rep.exit_code(args.strict)
    if args.json:
        print(json.dumps({**asdict(rep), "numbering": NUMBERING, "exit_code": code}, indent=2))
    else:
        print(render(rep))
    return code


if __name__ == "__main__":
    sys.exit(main())
