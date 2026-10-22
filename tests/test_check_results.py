"""scripts/check_results.py, the mechanical half of the RESULTS.md gate (SESSION_PROMPT.md §C4).

The script runs from the Stop hook without the venv, so every check here invokes it the same way:
a subprocess under ``python -S`` (no site-packages at all). The good fixtures are worked examples
of the template in .claude/rules/lanes.md, one per verdict class; the bad ones pin the exact FAIL
output a lane author sees. The template itself, filled in, must pass.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_results.py"
FIXTURES = ROOT / "tests" / "fixtures" / "results"
RULES_DIR = ROOT / ".claude" / "rules"
VOCAB = "NULL, CANDIDATE, INCONCLUSIVE (power), EXCLUDED (gate), FOUND-ERROR, NO-ERROR-FOUND"
AUDIT_COLUMNS = "claim, actual evidence, overreach, live lane, settling test"


def run(path: Path) -> tuple[int, list[str]]:
    r = subprocess.run(
        [sys.executable, "-S", str(SCRIPT), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    return r.returncode, r.stdout.splitlines()


def run_text(tmp_path: Path, text: str) -> tuple[int, list[str]]:
    f = tmp_path / "RESULTS.md"
    f.write_text(text, encoding="utf-8")
    return run(f)


def fail(*problems: str) -> tuple[int, list[str]]:
    return 1, ["FAIL", *(f"  - {p}" for p in problems)]


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.md").read_text(encoding="utf-8")


def line_of(text: str, needle: str) -> int:
    return next(i for i, ln in enumerate(text.splitlines(), 1) if needle in ln)


# --------------------------------------------------------------------------- fixtures


@pytest.mark.parametrize(
    "name",
    ["good_null", "good_candidate", "good_inconclusive", "good_excluded", "good_found_error"],
)
def test_good_fixture_passes(name):
    assert run(FIXTURES / f"{name}.md") == (0, ["PASS"])


BAD = {
    "bad_sections": [
        "missing section '## 0. Headline numbers'",
        "missing section '## 1. Why this lane'",
        "missing section '## 2. Instrument audited before the sweep'",
        "missing section '## 3. Result vs null vs bar'",
        "missing section '## 4. Survivors reported, not dropped'",
        "missing section '## 5. Coverage'",
        "missing section '## 6. What would change this verdict'",
        "missing section '## 7. Artifacts and reproduce'",
        'numbering not stated (numbering: "LP2-0-57")',
        "NULL: no 'best real X vs floor Y vs ceiling Z' (verdict arithmetic)",
        "no Q5 kill-condition check saying whether it fired (SESSION_PROMPT §C3)",
    ],
    "bad_control_null": [
        "§2 control: no 'recovered k/n' count",
        "§2 control: rank 1 recovery not stated",
        "§3 null: n = 5 < 20 in '- Null: 5 shuffles, mean −6.412.'",
        "§3 null: sd not given with a value",
        "§3 null: max not given with a value",
        "§3: no z-score (z = ...)",
        "§3: no threshold/bar value",
    ],
    "bad_banned": [  # 'nine solved sections', 'solved-page' and the HTML comment are not flagged
        "line 11: banned word 'closed' (say coverage / not_covered)",
        "line 11: banned word 'the frontier is complete' (say coverage / not_covered)",
        "line 16: banned word 'solved' (say coverage / not_covered)",
        "line 16: banned word 'cracked' (say coverage / not_covered)",
        "line 31: banned word 'confirmed' (say coverage / not_covered)",  # +1: the gate line
        "line 31: banned word 'exhausted' (say coverage / not_covered)",
        "line 36: banned word 'unsolvable' (say coverage / not_covered)",
    ],
    "bad_candidate_no_oracle": ["CANDIDATE without an oracle PASS/FAIL line"],
    "bad_null_no_floor": ["NULL: no 'best real X vs floor Y vs ceiling Z' (verdict arithmetic)"],
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_bad_fixture_fails_with_exact_problems(name):
    assert run(FIXTURES / f"{name}.md") == fail(*BAD[name])


# --------------------------------------------------------------------------- one change at a time

MUTATIONS = [  # (fixture, old, new, expected problems; [] means PASS)
    (
        "good_null",
        "recovered 20/20",
        "recovered 12/20",
        ["§2 control: recovered 12/20 is below the pass bar (>= 90 % of >= 20 plants)"],
    ),
    (  # every statement of the arithmetic changes together
        "good_null",
        "best real −6.371 vs floor",
        "best real −5.100 vs floor",
        ["NULL: best real −5.100 >= floor −5.214 and no §4 survivor row adjudicated NOISE-CROSSER"],
    ),
    (  # only one of the three statements changed: they disagree
        "good_null",
        "**Verdict: NULL — best real −6.371",
        "**Verdict: NULL — best real −6.500",
        [
            "NULL: the 'best real vs floor vs ceiling' statements disagree: "
            "−6.500 / −5.214 / −6.198; −6.371 / −5.214 / −6.198; −6.371 / −5.214 / −6.198"
        ],
    ),
    (  # 0.186 in log2 units is 0.129 nats
        "good_null",
        "vs ceiling −6.198",
        "vs ceiling −5.400",
        [
            "NULL: floor - ceiling = 0.186 (log2 per rune) = 0.129 nats < 0.25; "
            "that is INCONCLUSIVE (power)"
        ],
    ),
    (  # 0.300 log2 clears 0.25 in the wrong units but is 0.208 nats
        "good_null",
        "vs ceiling −6.198",
        "vs ceiling −5.514",
        [
            "NULL: floor - ceiling = 0.300 (log2 per rune) = 0.208 nats < 0.25; "
            "that is INCONCLUSIVE (power)"
        ],
    ),
    (  # a second, undersized null cannot hide behind the first null's n
        "good_null",
        "- Null 2, domain-separated SHA-256 stream: n = 200",
        "- Null 2, domain-separated SHA-256 stream: n = 8",
        ["§3 null: n = 8 < 20 in '- Null 2, domain-separated SHA-256 stream: n = 8, mean −6.40'"],
    ),
    (
        "good_null",
        "recovered 20/20 plants at rank 1 |",
        "recovered 20/20 plants within rank 1,000 |",
        [],  # §2 still states rank 1; the §0 table is not where the rule looks
    ),
    (
        "good_null",
        "- Gate (`runeforge gate",
        "- Fingerprint (`runeforge gate",
        [],  # still a GATE PASS line
    ),
    (
        "good_null",
        "did not fire (20/20)",
        "not checked",
        ["no Q5 kill-condition check saying whether it fired (SESSION_PROMPT §C3)"],
    ),
    (
        "good_null",
        "**Verdict: NULL",
        "**Verdict: INCONCLUSIVE",
        [f"Verdict: first word must be one of {VOCAB}"],
    ),
    ("good_null", "**Verdict: NULL", "**Result: NULL", ["no 'Verdict:' line before '## 1.'"]),
    ("good_null", 'numbering: "LP2-0-57" · ', "", ['numbering not stated (numbering: "LP2-0-57")']),
    (
        "good_null",
        "did not fire (20/20)",
        "nothing happened (20/20)",
        ["no Q5 kill-condition check saying whether it fired (SESSION_PROMPT §C3)"],
    ),
    (
        "good_null",
        "```bash\nruneforge control lanes/B04-CICADA-REGISTER.yaml\n"
        "runeforge sweep lanes/B04-CICADA-REGISTER.yaml --detach\n"
        "python scripts/check_results.py lanes/B04-CICADA-REGISTER/RESULTS.md\n```",
        "Re-run the control and the sweep from the lane spec.",
        ["§7: no reproduce command in backticks (`python ...` or `runeforge ...`)"],
    ),
    ("good_null", "- not_covered:", "- out of scope:", ["§5: no not_covered"]),
    (  # the trial count on the threshold_for.py command line is not a bar value
        "good_null",
        "→ bar −5.702; expected",
        "→ printed; expected",
        ["§3: no threshold/bar value"],
    ),
    ("good_null", "z = +0.49 against", "a z-score of +0.49 against", []),
    ("good_null", "- reopens_if:", "- reopens when:", ["§6: no reopens_if"]),
    (  # headings are matched by number plus keyword, so rewording keeps passing
        "good_null",
        "## 5. Coverage — read this, not the verdict",
        "## 5 — Coverage (read this before the verdict)",
        [],
    ),
    ("good_null", "## 7. Artifacts and reproduce", "## 7. How to reproduce", []),
    (
        "good_null",
        "## 4. Survivors reported, not dropped",
        "## 4. Escalation",
        ["missing section '## 4. Survivors reported, not dropped'"],
    ),
    ("good_inconclusive", "recovered 9/20", "recovered 0/20", []),  # a failed control is allowed
    (
        "good_inconclusive",
        "recovered 9/20",
        "recovered 21/20",
        ["§2 control: recovered 21/20 has k > n"],
    ),
    (
        "good_excluded",
        "for 12/12 keys",
        "for 5/12 keys",
        ["EXCLUDED (gate): 5/12 keys failed; needs most of >= 12 keys"],
    ),
    (
        "good_excluded",
        "typical key",
        "key",
        ["§5: does not say the gate excludes only the typical key"],
    ),
    ("good_found_error", "**Verdict: FOUND-ERROR", "**Verdict: NO-ERROR-FOUND", []),
    (
        "good_found_error",
        "| Actual evidence | Overreach |",  # all five columns are required
        "| Evidence | Notes |",
        [  # ... and the quoted claim in what was the Claim column loses its exemption
            f"FOUND-ERROR: no claim-audit table with rows (columns: {AUDIT_COLUMNS})",
            "line 49: banned word 'closed' (say coverage / not_covered)",
        ],
    ),
]


@pytest.mark.parametrize(("name", "old", "new", "expected"), MUTATIONS)
def test_single_change(tmp_path, name, old, new, expected):
    text = fixture(name)
    assert old in text, f"{name}.md no longer contains {old!r}"
    got = run_text(tmp_path, text.replace(old, new))
    assert got == (fail(*expected) if expected else (0, ["PASS"]))


def test_overclaim_only_allowed_inside_a_claim_cell(tmp_path):
    """The Claim column quotes the audited text; the lane's own columns may not overclaim."""
    text = fixture("good_found_error")
    assert "family closed under" in text  # a quoted claim, which passes
    old = "an English-register negative recorded without its register conditional"
    text = text.replace(old, "a negative closed without its register conditional")
    n = line_of(text, "a negative closed without")
    assert run_text(tmp_path, text) == fail(
        f"line {n}: banned word 'closed' (say coverage / not_covered)"
    )


def test_claim_cell_must_cite_file_and_line(tmp_path):
    text = fixture("good_found_error").replace("`ledger/ledger.jsonl:14` ", "the ledger row ")
    n = line_of(text, "| the ledger row ")
    assert run_text(tmp_path, text) == fail(
        f"line {n}: claim-audit row cites no file:line in its Claim cell"
    )


def test_candidate_needs_its_own_oracle_line(tmp_path):
    """Without the oracle bullet and the verdict line's 'oracle PASS', only the trust anchor's
    self-test mentions the oracle, and that does not count."""
    text = fixture("good_candidate")
    text = text.replace(text[text.index("- Oracle:") : text.index("- Pending:")], "")
    text = text.replace("our oracle PASS on LP2 pages 0 and 1; ", "")
    assert "oracle --selftest  -> selftest PASS" in text
    assert run_text(tmp_path, text) == fail("CANDIDATE without an oracle PASS/FAIL line")


# --------------------------------------------------------------------------- the script itself


def test_standard_library_only():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = {
        a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    imported |= {
        n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
    }
    assert imported - {"__future__"} <= set(sys.stdlib_module_names)


def test_usage_and_unreadable_file(tmp_path):
    r = subprocess.run([sys.executable, "-S", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 2 and "usage" in r.stderr
    code, out = run(tmp_path / "missing.md")
    assert code == 1 and out[0] == "FAIL" and "cannot read" in out[1]


# --------------------------------------------------------------------------- .claude/rules


def template(name: str) -> str:
    """The template between its markers in lanes.md, without the outer ```` fence."""
    text = (RULES_DIR / "lanes.md").read_text(encoding="utf-8")
    body = text.split(f"<!-- {name}-TEMPLATE-BEGIN -->")[1]
    body = body.split(f"<!-- {name}-TEMPLATE-END -->")[0]
    return "\n".join(ln for ln in body.strip().splitlines() if not ln.startswith("````")) + "\n"


FILL = {  # a NULL, with good_null.md's numbers
    "lane_id": "B04-CICADA-REGISTER",
    "family": "SHA-256/512 keystreams from Cicada vocabulary",
    "verdict": "NULL",
    "verdict_summary": "best real −6.371 vs floor −5.214 vs ceiling −6.198 over 184,320 keys",
    "prereg_commit": "3f1c2a9",
    "n_trials": "184,320",
    "k": "20",
    "n": "20",
    "null_n": "200",
    "null_mean": "−6.412",
    "null_sd": "0.083",
    "null_max": "−6.177",
    "bar": "−5.702",
    "best_real": "−6.371",
    "z": "+0.49",
    "floor": "−5.214",
    "ceiling": "−6.198",
    "n_crossers": "0",
    "category": "bounded",
    "round_split": "34/31/22/13 %",
    "q2_fact": "every upstream B-04 negative is English-register only",
    "q2_path": "data/raw/dukotah/liber-primus/analysis/round18/L7-redteam/RESULTS.md",
    "why_new": "The register is new; the dictionary is B-04's.",
    "pytest_line": "212 passed, 9 deselected in 41.07s",
    "canon_line": "023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585 OK",
    "oracle_selftest_line": "selftest PASS",
    "gate_line": "GATE PASS — 12/12 keys inside the LP2 band",
    "median_recovery": "1.000",
    "min_recovery": "0.958",
    "planted_score": "−4.830",
    "wrong_key_score": "−7.460",
    "null2_n": "200",
    "null2_mean": "−6.405",
    "null2_sd": "0.080",
    "null2_max": "−6.198",
    "preset": "cicada-ngram3:rigid",
    "window": "120",
    "expected_fp": "0.004",
    "separation": "1.016",
    "kill_condition": "control replay < 18/20 at 10 % of budget",
    "kill_check_point": "18,432 keys",
    "kill_outcome": "did not fire",
    "top_k": "1",
    "kid": "sha512-ctr/w=0412/atbash/+3",
    "s_head": "−6.371",
    "z_head": "+0.49",
    "s_2x": "−6.902",
    "z_2x": "−0.21",
    "s_page": "−6.987",
    "z_page": "−0.44",
    "s_stream": "−7.381",
    "z_stream": "−1.07",
    "outcome": "z falls; noise",
    "oracle_result": "not run (no crosser)",
    "coverage": "184,320 keys",
    "coverage_fraction": "100 %",
    "not_covered": "PBKDF2/scrypt stretching; offsets ≥ 8",
    "cond_key_space": "2,880 strings × 64 configurations",
    "cond_decoder": "rigid screen, beam on the top 1,000",
    "cond_register": "Cicada-register English",
    "reopens_if": "a key that starts after page 0",
    "sweep_sha256": "9c41e0d27b5a",
    "git_sha": "7d02e4b",
}


def test_results_template_filled_in_passes(tmp_path):
    raw = re.sub(r"(?s)<!--.*?-->", "", template("RESULTS"))  # guidance, never filled in
    missing = sorted(set(re.findall(r"<([a-z][a-z0-9_]*)>", raw)) - set(FILL))
    assert not missing, f"placeholders without a test value: {missing}"
    filled = re.sub(r"<([a-z][a-z0-9_]*)>", lambda m: FILL[m[1]], raw)
    assert run_text(tmp_path, filled) == (0, ["PASS"])


def test_results_template_unfilled_fails(tmp_path):
    code, out = run_text(tmp_path, template("RESULTS"))
    assert code == 1 and f"  - Verdict: first word must be one of {VOCAB}" in out


PREREG_ELEMENTS = [  # SESSION_PROMPT.md §C2, in order
    "written before any measurement in this lane",
    "no decode, plant, null or sweep of this lane's own has been executed",
    "what was read",
    'numbering: "LP2-0-57"',
    "aiming test",
    "q1",
    "q2",
    "q3",
    "q4",
    "q5 kill condition at 10 % of budget",
    "hypothesis",
    "key space",
    "ciphertext view",
    "decoder",
    "beam",
    "register",
    "positive control",
    "pass bar",
    "≥ 0.90",
    "≥ 20 plants",
    "shuffle of the real runes",
    "≥ 200",
    "domain-separated sha-256 stream",
    "scripts/threshold_for.py",
    "expected false positives",
    "< 1",
    "hit function",
    "flagged-for-oracle",
    "floor",
    "ceiling",
    "0.25",
    "budget",
    "gpu-hours",
    "not_covered",
    "conditionals",
    "reopens_if",
    "external_ids",
]


def test_prereg_template_has_every_element():
    text = " ".join(template("PREREG").lower().split())
    assert [e for e in PREREG_ELEMENTS if e.lower() not in text] == []


@pytest.mark.parametrize(
    ("name", "glob"),
    [("lanes.md", "lanes/**"), ("reports.md", "reports/**"), ("gpu.md", "runeforge/gpu/**")],
)
def test_rules_are_path_scoped(name, glob):
    text = (RULES_DIR / name).read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---")[1])
    assert glob in front["paths"]


def _two(text: str, *pairs: tuple[str, str]) -> str:
    for old, new in pairs:
        assert old in text, old
        text = text.replace(old, new)
    return text


def test_a_crosser_stands_in_a_null_only_when_a_survivor_row_adjudicates_it(tmp_path):
    above = ("best real −6.371 vs floor", "best real −5.100 vs floor")
    row = ("| −7.381 | −1.07 | z falls; noise |", "| −7.381 | −1.07 | NOISE-CROSSER |")
    assert run_text(tmp_path, _two(fixture("good_null"), above, row)) == (0, ["PASS"])
    # the word elsewhere (a hypothetical in reopens_if) is no adjudication
    elsewhere = ("- reopens_if:", "- reopens_if: a crosser not adjudicated NOISE-CROSSER;")
    code, out = run_text(tmp_path, _two(fixture("good_null"), above, elsewhere))
    assert code == 1 and any("no §4 survivor row adjudicated" in x for x in out)


def test_rank_one_thousand_is_not_rank_one(tmp_path):
    text = fixture("good_null")
    sec2 = text[text.index("## 2.") : text.index("## 3.")]
    assert "rank 1" in sec2
    mutated = text.replace(sec2, sec2.replace("at rank 1", "within rank 1,000"))
    code, out = run_text(tmp_path, mutated)
    assert code == 1 and "  - §2 control: rank 1 recovery not stated" in out


def test_a_write_up_without_the_gate_result_fails(tmp_path):
    text = "\n".join(ln for ln in fixture("good_null").splitlines() if "GATE PASS" not in ln)
    code, out = run_text(tmp_path, text)
    assert code == 1 and "  - §2: no fingerprint gate result (GATE PASS / GATE FAIL)" in out


def test_gate_fail_named_by_constraint_id(tmp_path):
    text = fixture("good_excluded")
    g = text.index("GATE FAIL —")
    end = text.index("\n\n", g)
    mutated = text[:g] + "GATE FAIL: C3 repeated words >= 3 for 12/12 keys." + text[end:]
    assert run_text(tmp_path, mutated) == (0, ["PASS"])


def test_cited_paths_are_not_claims_and_soft_wraps_are_read_whole(tmp_path):
    text = fixture("good_null")
    cite = "- reopens_if:"
    ok = text.replace(
        cite,
        "- Not re-run: murphy `research/EXHAUSTED.md` and\n"
        "  data/raw/dukotah/liber-primus/analysis/armada/recon-community-exhausted.md.\n"
        "- The nine solved\n  sections train the scorer.\n" + cite,
    )
    assert run_text(tmp_path, ok) == (0, ["PASS"])
    bad = text.replace(cite, "- The register is new, and the frontier is\n  complete.\n" + cite)
    code, out = run_text(tmp_path, bad)
    assert code == 1 and any("the frontier is complete" in x for x in out)


def test_oracle_must_have_run_and_reproduce_must_regenerate(tmp_path):
    text = fixture("good_candidate")
    o = text.index("- Oracle: `python -m runeforge.oracle")
    end = text.index("\n- Pending", o)
    not_run = text[:o] + "- Oracle: not run yet; it will print PASS or FAIL." + text[end:]
    code, out = run_text(tmp_path, not_run)
    assert code == 1 and "  - CANDIDATE without an oracle PASS/FAIL line" in out
    null = fixture("good_null")
    f = null.index("```bash", null.index("## 7."))
    fend = null.index("```", f + 3) + 3
    only_gate = (
        null[:f] + "```bash\npython scripts/check_results.py lanes/X/RESULTS.md\n```" + null[fend:]
    )
    code, out = run_text(tmp_path, only_gate)
    assert code == 1 and any(x.startswith("  - §7: no reproduce command") for x in out)
