#!/usr/bin/env python3
"""Mechanical gate for lanes/<id>/RESULTS.md (SESSION_PROMPT.md §C4): FAIL = lane not finished.

    python scripts/check_results.py lanes/<id>/RESULTS.md

Prints PASS (exit 0), or FAIL and one ``  - <problem>`` line per problem (exit 1).

It checks that the write-up states what a reader needs to judge the verdict -- the eight template
sections, control, null, bar, coverage with its three conditionals, reopens_if, a reproduce
command -- that a NULL follows from its own verdict arithmetic, and that no overclaiming word
slipped in. It cannot tell whether the numbers are right; the verify-lane subagent re-derives
those. HTML comments are template guidance and never count.

Standard library only: the Stop hook runs it without the venv. Extends murphy's
jobs/attack-lane/tools/check_results.py to the template in .claude/rules/lanes.md.
"""

from __future__ import annotations

import math
import re
import sys

SECTIONS = [  # number, heading keyword(s), name used in the problem line
    ("0", "headline", "Headline numbers"),
    ("1", "why", "Why this lane"),
    ("2", "instrument", "Instrument audited before the sweep"),
    ("3", "result", "Result vs null vs bar"),
    ("4", "survivor", "Survivors reported, not dropped"),
    ("5", "coverage", "Coverage"),
    ("6", "change|reopen", "What would change this verdict"),
    ("7", "artifact|reproduce", "Artifacts and reproduce"),
]
SEARCHED = ("NULL", "CANDIDATE", "INCONCLUSIVE (power)")  # lanes that ran a control and a null
GATED = ("EXCLUDED (gate)",)
REDTEAM = ("FOUND-ERROR", "NO-ERROR-FOUND")
ANY = (*SEARCHED, *GATED, *REDTEAM, None)
VERDICT_RE = re.compile(
    r"(NULL|CANDIDATE|INCONCLUSIVE\s*\(power\)|EXCLUDED\s*\(gate\)|FOUND-ERROR|NO-ERROR-FOUND)"
    r"(?![\w-])"
)
NUM = r"[+\-−]?\d+(?:,\d{3})*(?:\.\d+)?"  # scores are written with U+2212 as often as with '-'
DEC = r"[+\-−]?\d+\.\d+"  # a score, not a trial count: '--n 184320' is no bar value
VAL = r"(?![a-z])[\s*`_:=]*" + NUM  # 'mean −6.41', 'null_sd = 0.08', '**max:** −6.18'
PARA = r"(?:(?!\n[ \t]*\n).)"  # any character short of a blank line: markdown soft-wraps
_ONE = r"(?:(?!\n[ \t]*\n|best real).)"  # PARA that does not run into the next statement
FLOOR_RE = re.compile(
    rf"(?is)best real\W*?({NUM}){_ONE}{{0,80}}?\bvs\.?\s+(?:the\s+)?floor\W*?({NUM})"
    rf"{_ONE}{{0,80}}?\bvs\.?\s+(?:the\s+)?ceiling\W*?({NUM})"
)
BANNED = re.compile(
    r"(?i)\b(exhausted|closed|unsolvable|confirmed|cracked|solved|the frontier is complete)\b"
)
SOLVED_OK = re.compile(r"(?i)\bsolved[\s-]+(?:pages?|sections?)\b|\bnine\s+solved\b")
AUDIT_COLUMNS = ("claim", "actual evidence", "overreach", "live lane", "settling test")
RUNNABLE = re.compile(r"(?:^|&&|;)\s*(?:\$\s*)?(?:python3?|runeforge)\s+\S")
GATES_ONLY = re.compile(r"scripts/(?:check_results|validate_ledger)\.py")  # regenerate nothing
# a path or file name is a citation, not a claim: murphy's research/EXHAUSTED.md is required reading
PATHLIKE = re.compile(r"[\w.-]*/[\w./-]+|\b[\w-]+\.(?:md|py|json|jsonl|yaml|yml|txt|log)\b")
MIN_GAP_NATS = 0.25  # runeforge.runner.control.MIN_GAP_NATS; scores are mean log2 per rune


def value(s: str) -> float:
    return float(s.replace("−", "-").replace(",", ""))


def plain(s: str) -> str:
    """'**Verdict:** `NULL`' reads like 'Verdict: NULL'."""
    return re.sub(r"[*`]", "", s)


def sections(text: str) -> dict[str, str]:
    """Body of each template section, keyed by its number; matched by number plus keyword."""
    heads = list(re.finditer(r"(?m)^##[ \t]+(.*)$", text))
    out: dict[str, str] = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        for num, kw, _ in SECTIONS:
            if num not in out and re.match(rf"§?{num}\b\.?.*(?:{kw})", h[1], re.I):
                out[num] = text[h.end() : end]
    return out


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def audit_rows(lines: list[str]) -> list[int] | None:
    """Line indices of the claim-audit table's rows, or None when there is no such table."""
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|") and all(c in line.lower() for c in AUDIT_COLUMNS):
            rows = []
            for j in range(i + 2, len(lines)):  # i + 1 is the |---| separator
                if not lines[j].lstrip().startswith("|"):
                    break
                rows.append(j)
            return rows
    return None


def commands(body: str) -> list[str]:
    """Inline code spans and the lines of fenced code blocks."""
    fence = r"(?ms)^[ \t]*```[^\n]*\n(.*?)^[ \t]*```"
    spans = re.findall(r"`([^`\n]+)`", re.sub(fence, "", body))
    return spans + [ln for block in re.findall(fence, body) for ln in block.splitlines()]


def near(text: str, a: str, b: str, unless: str = "(?!)") -> bool:
    """`a`, then `b` in the same paragraph (within 300 characters), with no `unless` between."""
    return bool(re.search(rf"(?s){a}(?:(?!\n[ \t]*\n|{unless}).){{0,300}}?{b}", text))


def control_count(body: str, verdict: str) -> list[str]:
    """'recovered k/n'; NULL and CANDIDATE need the pre-registered pass bar (SESSION_PROMPT §C2)."""
    m = re.search(r"(?i)recovered\s+(\d+)\s*/\s*(\d+)", body)
    if not m:
        return ["§2 control: no 'recovered k/n' count"]
    k, n = int(m[1]), int(m[2])
    if k > n:
        return [f"§2 control: recovered {k}/{n} has k > n"]
    if verdict != "INCONCLUSIVE (power)" and (n < 20 or 10 * k < 9 * n):
        return [f"§2 control: recovered {k}/{n} is below the pass bar (>= 90 % of >= 20 plants)"]
    return []


def items(body: str) -> list[str]:
    """Bullet items and paragraphs, soft-wrapped lines joined."""
    out, cur = [], []
    for line in body.splitlines():
        if not line.strip() or re.match(r"\s*(?:[-*+]|\d+\.)\s", line):
            if cur:
                out.append(" ".join(cur))
            cur = [line.strip()] if line.strip() else []
        else:
            cur.append(line.strip())
    if cur:
        out.append(" ".join(cur))
    return out


def null_size(body: str, _verdict: str) -> list[str]:
    """Each null is stated with its own size: one undersized null must not hide behind another
    null's n, an escalation length or a trial count."""
    p, sized = [], 0
    for it in items(body):
        if not re.match(r"(?i)[-*+\s]*(?:\d+\.\s*)?(?:null|shuffle)", plain(it)):
            continue
        ns = re.findall(r"\bn\s*=\s*(\d+(?:,\d{3})*)", it)
        ns += re.findall(r"(?i)\b(\d+(?:,\d{3})*)\s+(?:shuffles|shuffled|null runs|nulls)\b", it)
        if not ns:
            p.append(f"§3 null: size not stated in '{it[:60]}'")
            continue
        sized += 1
        p += [f"§3 null: n = {value(n):.0f} < 20 in '{it[:60]}'" for n in ns if value(n) < 20]
    if not sized and not p:
        p.append("§3 null: size not stated (a '- Null ...: n = <count>' line)")
    return p


def null_arithmetic(text: str, secs: dict[str, str]) -> list[str]:
    """NULL is 'best real X vs floor Y vs ceiling Z' and must follow from it (SESSION_PROMPT §C2).

    Every such statement is checked and they must agree. The gap is in nats, as
    ``runeforge control`` computes it: scores are mean log2-probability per rune, so
    (Y - Z) * ln 2 >= 0.25. Best real >= floor is a crosser; it may stand in a NULL only once a
    row of the §4 survivors table records it as NOISE-CROSSER."""
    found = list(FLOOR_RE.finditer(plain(text)))
    if not found:
        return ["NULL: no 'best real X vs floor Y vs ceiling Z' (verdict arithmetic)"]
    p = []
    if len({tuple(map(value, m.groups())) for m in found}) > 1:
        p.append(
            "NULL: the 'best real vs floor vs ceiling' statements disagree: "
            + "; ".join(f"{m[1]} / {m[2]} / {m[3]}" for m in found)
        )
    adjudicated = any(
        ln.lstrip().startswith("|") and "NOISE-CROSSER" in ln
        for ln in secs.get("4", "").splitlines()
    )
    for m in found:
        x, y, z = map(value, m.groups())
        if x >= y and not adjudicated:
            p.append(
                f"NULL: best real {m[1]} >= floor {m[2]} and no §4 survivor row adjudicated "
                "NOISE-CROSSER"
            )
        gap = (y - z) * math.log(2)
        if gap < MIN_GAP_NATS:
            p.append(
                f"NULL: floor - ceiling = {y - z:.3f} (log2 per rune) = {gap:.3f} nats < "
                f"{MIN_GAP_NATS}; that is INCONCLUSIVE (power)"
            )
    return list(dict.fromkeys(p))


def gate_line(text: str) -> list[str]:
    """EXCLUDED (gate): which fingerprint constraints failed, for most of >= 12 simulated keys."""
    g = re.search(rf"(?s)GATE FAIL{PARA}{{0,400}}", text)
    if g is None:
        return ["EXCLUDED (gate): no 'GATE FAIL' line"]
    line = g[0]
    p = []
    if not re.search(
        r"(?i)\b(?:C[1-6][a-c]?|IoC|doublet|repeated words?|lag-?\d|cross-word|mod-?\d|entropy)",
        line,
    ):
        p.append("EXCLUDED (gate): GATE FAIL line names no failed constraint (IoC, doublet, ...)")
    m = re.search(r"(\d+)\s*/\s*(\d+)\s+(?:\w+\s+)?keys", line)
    if not m:
        p.append("EXCLUDED (gate): GATE FAIL line does not say how many keys failed ('k/n keys')")
    elif int(m[2]) < 12 or 2 * int(m[1]) <= int(m[2]):
        p.append(f"EXCLUDED (gate): {m[1]}/{m[2]} keys failed; needs most of >= 12 keys")
    return p


RULES = [  # (verdicts, section, check, problem): check(body, verdict), or a pattern that must occur
    (SEARCHED, "2", control_count, None),
    (
        SEARCHED,
        "2",
        r"\brank[\s-]*(?:1|one)\b(?![,.]?\d)",  # not 'within rank 1,000'
        "§2 control: rank 1 recovery not stated",
    ),
    (
        SEARCHED,
        "2",
        r"GATE (?:PASS|FAIL)",
        "§2: no fingerprint gate result (GATE PASS / GATE FAIL)",
    ),
    (SEARCHED, "3", null_size, None),
    (SEARCHED, "3", rf"(?<![a-z])mean{VAL}", "§3 null: mean not given with a value"),
    (SEARCHED, "3", rf"(?<![a-z])(?:sd|std|σ){VAL}", "§3 null: sd not given with a value"),
    (SEARCHED, "3", rf"(?<![a-z])max{VAL}", "§3 null: max not given with a value"),
    (
        SEARCHED,
        "3",
        rf"(?<![a-z])z(?:-score)?(?:\s+of)?\s*[=:≈]?\s*{NUM}",
        "§3: no z-score (z = ...)",
    ),
    (SEARCHED, "3", rf"(?:threshold|\bbar\b)[^\n]{{0,80}}?{DEC}", "§3: no threshold/bar value"),
    (GATED, "5", "typical key", "§5: does not say the gate excludes only the typical key"),
    (ANY, "5", r"not[_ ]covered", "§5: no not_covered"),
    (ANY, "5", r"key[\s-]?space", "§5: conditional 'key space' not stated"),
    (ANY, "5", "decoder", "§5: conditional 'decoder' not stated"),
    (ANY, "5", "register", "§5: conditional 'register' not stated"),
    (ANY, "6", r"reopens[_ ]if", "§6: no reopens_if"),
]


def check(text: str) -> list[str]:
    text = re.sub(r"(?s)<!--.*?-->", lambda m: "\n" * m[0].count("\n"), text)
    lines = text.splitlines()
    secs = sections(text)
    p = [f"missing section '## {n}. {name}'" for n, _, name in SECTIONS if n not in secs]

    s1 = re.search(r"(?m)^##[ \t]+§?1\b", text)
    m = re.search(r"(?im)\bverdict\s*:\s*(.*)$", plain(text[: s1.start()] if s1 else text[:4000]))
    v = VERDICT_RE.match(m[1]) if m else None
    verdict = re.sub(r"\s*\(", " (", v[1]) if v else None
    if not m:
        p.append("no 'Verdict:' line before '## 1.'")
    elif not v:
        p.append("Verdict: first word must be one of " + ", ".join(ANY[:-1]))
    if not re.search(r"(?i)numbering\W{0,6}LP2-0-57\b", plain(text)):
        p.append('numbering not stated (numbering: "LP2-0-57")')

    for vs, sec, rule, problem in RULES:
        if verdict not in vs or sec not in secs:
            continue
        if callable(rule):
            p += rule(secs[sec], verdict)
        elif not re.search(rule, secs[sec], re.I):
            p.append(problem)
    if "7" in secs and not any(
        RUNNABLE.search(c.strip()) and not GATES_ONLY.search(c) for c in commands(secs["7"])
    ):
        p.append("§7: no reproduce command in backticks (`python ...` or `runeforge ...`)")

    if verdict == "NULL":
        p += null_arithmetic(text, secs)
    kill = r"(?i:kill[\s-]*condition)"
    if verdict in ("NULL", "CANDIDATE") and (
        not near(text, kill, r"(?i:\b(?:did not fire|not fired|fired)\b)")
        or near(text, kill, r"(?i:not checked)")
    ):
        p.append("no Q5 kill-condition check saying whether it fired (SESSION_PROMPT §C3)")
    if verdict == "CANDIDATE" and not near(  # the trust anchor's self-test does not count
        text,
        r"(?i:oracle)",
        r"(?:→|->|:|=)\s*\**(?:PASS|FAIL)\b",
        unless=r"(?i:self-?test|not run)",
    ):
        p.append("CANDIDATE without an oracle PASS/FAIL line")
    if verdict in GATED:
        p += gate_line(text)
    rows = audit_rows(lines) if verdict in REDTEAM else None
    if verdict in REDTEAM and not rows:
        p.append(f"{verdict}: no claim-audit table with rows (columns: {', '.join(AUDIT_COLUMNS)})")
    for j in rows or []:
        if not re.search(r"[\w/-]+\.\w+:\d+", cells(lines[j])[0]):
            p.append(f"line {j + 1}: claim-audit row cites no file:line in its Claim cell")

    quoted = set(rows or [])  # a Claim cell quotes the audited text verbatim

    def blank(m: re.Match) -> str:
        return " " * len(m[0])

    for i, line in enumerate(lines):
        scan = "|".join(cells(line)[1:]) if i in quoted else line
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        tail = "" if nxt.lstrip().startswith("|") else " ".join(nxt.split()[:3])
        window = SOLVED_OK.sub(blank, PATHLIKE.sub(blank, f"{scan} {tail}"))
        for m in BANNED.finditer(window):
            if m.start() < len(scan):  # reported on the line where the word starts
                p.append(f"line {i + 1}: banned word '{m[1].lower()}' (say coverage / not_covered)")
    return p


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python scripts/check_results.py lanes/<id>/RESULTS.md", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        with open(argv[0], encoding="utf-8") as f:
            problems = check(f.read())
    except (OSError, UnicodeDecodeError) as exc:
        problems = [f"cannot read {argv[0]}: {exc}"]
    print("FAIL" if problems else "PASS")
    for x in problems:
        print("  - " + x)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
