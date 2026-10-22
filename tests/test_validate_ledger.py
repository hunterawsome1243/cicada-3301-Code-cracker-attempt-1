"""scripts/validate_ledger.py: Dukotah's six ledger rules, ported to the JSONL ledger.

Ledgers are written by hand (rows as dicts) so every rule is exercised the way a hand-edited or
older-version row would hit it, and once through ``runeforge.ledger.Ledger`` for the contract:
whatever runeforge writes, the validator accepts.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import typing
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_ledger.py"
_spec = importlib.util.spec_from_file_location("validate_ledger", SCRIPT)
vl = importlib.util.module_from_spec(_spec)
sys.modules["validate_ledger"] = vl
_spec.loader.exec_module(vl)

CONDITIONALS = {
    "key_space": "seeds 0..2^32, all",
    "decoder": "rigid screen, keyskip1 beam adjudication",
    "register": "cicada-english n-gram",
}
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def row(lane_id: str = "L-1", status: str = "never-run", **kw) -> dict:
    base = {
        "lane_id": lane_id,
        "hypothesis": "toy hypothesis",
        "family": "prng",
        "status": status,
        "numbering": "LP2-0-57",
        "reopens_if": "a decoder that models skip_by_two",
    }
    if status == "running":
        base["started"] = "2026-10-22T00:00:00+00:00"
    return {**base, **kw}


def negative(lane_id: str = "L-1", **kw) -> dict:
    sound = {
        "positive_control": "passed",
        "threshold": -5.5,
        "threshold_fixed_in_advance": True,
        "conditionals": CONDITIONALS,
        "evidence": ["lanes/L-1/RESULTS.md"],
        "verdict": "NULL",
    }
    return row(lane_id, "negative", **{**sound, **kw})


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo root holding the evidence the sound rows point at."""
    (tmp_path / "lanes" / "L-1").mkdir(parents=True)
    (tmp_path / "lanes" / "L-1" / "RESULTS.md").write_text("Verdict: NULL\n")
    (tmp_path / "runs" / "L-1").mkdir(parents=True)
    (tmp_path / "runs" / "L-1" / "sweep.jsonl").write_text("{}\n")
    return tmp_path


def write(root: Path, *rows: dict) -> Path:
    path = root / "ledger" / "ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def check(root: Path, *rows: dict, **kw):
    return vl.validate(write(root, *rows), root=root, use_git=False, **kw)


def has(messages: list[str], *needles: str) -> bool:
    return any(all(n in m for n in needles) for m in messages)


# --- output contract -------------------------------------------------------------------------


def test_missing_ledger_is_valid(tmp_path, capsys):
    path = tmp_path / "ledger" / "ledger.jsonl"
    assert vl.main(["--ledger", str(path), "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == "Unsound negatives = 0"
    assert "0 rows, 0 lanes" in out[0] and "ERRORS: 0" in out


def test_empty_ledger_is_valid(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("\n\n")
    rep = vl.validate(path, root=tmp_path)
    assert (rep.rows, rep.lanes, rep.errors, rep.warnings) == (0, 0, [], [])
    assert rep.exit_code(strict=True) == 0
    assert vl.render(rep).splitlines()[-1] == "Unsound negatives = 0"


def test_clean_ledger_recounts_the_latest_row_per_lane(repo):
    rep = check(
        repo,
        row("L-1", "running", threshold=-5.5, threshold_fixed_in_advance=True),
        negative("L-1"),
        row("L-2"),
        row("L-3", "parked", parked_state={"cursor": 12}),
    )
    assert rep.errors == [] and rep.warnings == [] and rep.notes == []
    assert (rep.rows, rep.lanes) == (4, 3)
    assert rep.by_status == {"negative": 1, "never-run": 1, "parked": 1}
    text = vl.render(rep)
    assert text.splitlines()[0].startswith("ledger/ledger.jsonl  numbering LP2-0-57  4 rows, 3")
    assert text.splitlines()[-1] == "Unsound negatives = 0"


# --- 1. unsound negatives --------------------------------------------------------------------


def test_unsound_negatives_are_errors_and_counted(repo):
    no_control = negative("L-1", positive_control="none")
    failed = negative("L-2", positive_control="failed")
    defaulted = negative("L-3")
    del defaulted["positive_control"]  # the model's default is "none"
    rep = check(repo, no_control, failed, defaulted)
    assert rep.unsound_negatives == 3 and rep.exit_code() == 1
    assert has(rep.errors, "[L-2] line 2", "UNSOUND NEGATIVE", "'failed'", "inconclusive")
    assert vl.render(rep).splitlines()[-1] == "Unsound negatives = 3"


def test_failed_or_missing_control_cannot_carry_a_verified_hit(repo):
    hit = row("L-1", "hit-verified", evidence=["lanes/L-1/RESULTS.md"], verdict="CANDIDATE")
    rep = check(repo, {**hit, "positive_control": "failed"})
    assert has(rep.errors, "hit-verified", "'failed'") and rep.unsound_negatives == 0
    assert check(repo, {**hit, "positive_control": "passed"}).errors == []


def test_a_failed_control_is_inconclusive(repo):
    rep = check(repo, row("L-1", "inconclusive", positive_control="failed", evidence=["runs/L-1"]))
    assert rep.errors == [] and rep.warnings == []


# --- 2. thresholds ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"threshold": None},
        {"threshold": ""},
        {"threshold_fixed_in_advance": False},
        {"threshold_fixed_in_advance": "true"},  # a string is not a fixed-in-advance flag
    ],
)
def test_a_negative_needs_a_threshold_fixed_in_advance(repo, change):
    rep = check(repo, negative(**change))
    assert has(rep.errors, "threshold fixed in advance") and rep.exit_code() == 1


def test_absent_threshold_and_zero_threshold(repo):
    bad = negative()
    del bad["threshold"]
    assert has(check(repo, bad).errors, "threshold=None")
    assert check(repo, negative(threshold=0)).errors == []  # zero is a bar, not a missing one


def test_threshold_is_frozen_once_fixed_in_advance(repo):
    rep = check(
        repo,
        row("L-1", "running", threshold=-5.5, threshold_fixed_in_advance=True),
        row(
            "L-1",
            "running",
            threshold=-5.5,
            threshold_fixed_in_advance=True,
            notes="2026-10-22 addendum: bar unchanged",
        ),
        negative("L-1", threshold=-6.0),
        # before a threshold is fixed it may still move
        row("L-2", threshold=-4.0),
        row("L-2", "running", threshold=-4.5, threshold_fixed_in_advance=True),
        row("L-2", "running", threshold=-4.5, threshold_fixed_in_advance=True),
    )
    assert len(rep.errors) == 1
    assert has(rep.errors, "[L-1] line 3", "threshold changed from -5.5", "line 1", "-6.0")


def test_dropping_or_unfixing_a_frozen_threshold(repo):
    fixed = row("L-1", "running", threshold=-5.5, threshold_fixed_in_advance=True)
    dropped = {**fixed}
    del dropped["threshold"]
    assert has(check(repo, fixed, dropped).errors, "line 2", "to None")
    rep = check(repo, fixed, {**fixed, "threshold_fixed_in_advance": False}, fixed)
    assert rep.errors == [] and len(rep.warnings) == 1
    assert has(rep.warnings, "line 2", "went back to false")


# --- 3. evidence -----------------------------------------------------------------------------


def test_missing_evidence_on_a_concluded_row_is_an_error(repo):
    for status in ("negative", "inconclusive", "hit-unverified"):
        extra = {"verdict": "CANDIDATE"} if status.startswith("hit") else {}
        bad = {**negative(), "status": status, "evidence": ["lanes/L-1/MISSING.md"], **extra}
        rep = check(repo, bad)
        assert has(rep.errors, "evidence path does not exist", "MISSING.md"), status


def test_missing_evidence_on_an_open_row_is_a_warning(repo):
    rep = check(repo, row("L-1", "running", evidence=["lanes/L-1/PREREG.md"]))
    assert rep.errors == [] and has(rep.warnings, "PREREG.md")
    assert rep.exit_code() == 0 and rep.exit_code(strict=True) == 1


def test_evidence_anchors_and_globs_resolve(repo):
    ev = ["lanes/L-1/RESULTS.md#section-5", "lanes/*/RESULTS.md", "runs/**/sweep.jsonl"]
    assert check(repo, negative(evidence=ev)).errors == []
    assert has(check(repo, negative(evidence=["lanes/*/NOPE.md"])).errors, "NOPE.md")


def test_evidence_shape_and_location(repo):
    # a bare string is a type error, but its path is still checked rather than walked per char
    rep = check(repo, negative(evidence="lanes/L-1/MISSING.md"))
    assert has(rep.errors, "`evidence` is string")
    assert has(rep.errors, "does not exist: 'lanes/L-1/MISSING.md'")
    outside = str(repo / "lanes" / "L-1" / "RESULTS.md")
    assert has(check(repo, negative(evidence=[outside])).warnings, "outside the repository")
    assert has(check(repo, negative(evidence=[])).warnings, "lists no evidence")


# --- 4. dangling links -----------------------------------------------------------------------


def test_links_point_at_lanes_that_exist(repo):
    rep = check(repo, row("L-1", supersedes=["L-404"]), row("L-2", superseded_by=["L-405"]))
    assert has(rep.errors, "[L-1]", "supersedes points at unknown lane 'L-404'")
    assert has(rep.errors, "[L-2]", "superseded_by points at unknown lane 'L-405'")
    assert has(check(repo, row("L-1", supersedes=["L-1"])).errors, "its own lane")


def test_superseded_rows_name_their_successor(repo):
    assert has(check(repo, row("L-1", "superseded")).errors, "without `superseded_by`")
    fix = row("L-2", "inconclusive", supersedes=["L-1"], evidence=["runs/L-1"])
    fix["verdict"] = "FOUND-ERROR"
    marked = {**negative("L-1"), "status": "superseded", "superseded_by": ["L-2"]}
    rep = check(repo, negative("L-1"), fix, marked)
    assert rep.errors == [] and rep.notes == []
    # until the old lane is marked, the link is one-sided: a note, not an error
    rep = check(repo, negative("L-1"), fix)
    assert rep.errors == [] and has(rep.notes, "[L-2] supersedes 'L-1'", "still 'negative'")


# --- 5. schema -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad, message",
    [
        ({**row(), "hypothesis": ""}, "missing required field `hypothesis`"),
        ({k: v for k, v in row().items() if k != "family"}, "missing required field `family`"),
        (row(status="untested"), "status 'untested' is not in the controlled vocabulary"),
        (row(verdict="NEGATIVE"), "verdict 'NEGATIVE' is not in the controlled vocabulary"),
        (row(positive_control="not-run"), "positive_control 'not-run' is not in the"),
        (row(category="vibes"), "category 'vibes' is not in the"),
        (row(numbering="LP1-0-16"), "numbering 'LP1-0-16' is not in the"),
        ({k: v for k, v in row().items() if k != "numbering"}, "no `numbering`"),
        (row(control_result="passed"), "unknown field(s) ['control_result']"),
        (row(n_trials=True), "`n_trials` is boolean, expected integer"),
        (row(n_trials=2.5), "`n_trials` is number, expected integer"),
        (row(supersedes=[1]), "`supersedes` is array with a non-string item"),
        (row(threshold_fixed_in_advance=None), "`threshold_fixed_in_advance` is null"),
        (row(conditionals={"key_space": 1}), "`conditionals` values are strings"),
        (negative(conditionals=None), "conditionals ['key_space', 'decoder', 'register']"),
        (negative(conditionals={**CONDITIONALS, "register": ""}), "conditionals ['register']"),
        ({**row("L-1", "running"), "started": None}, "running without `started`"),
        (row(status="inconclusive", verdict="CANDIDATE"), "verdict CANDIDATE goes with"),
    ],
)
def test_schema(repo, bad, message):
    rep = check(repo, bad)
    assert has(rep.errors, message), rep.errors
    assert rep.exit_code() == 1


def test_malformed_lines_are_reported_by_line_number(repo):
    path = write(repo, row("L-1"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
        fh.write("[1, 2]\n")
        fh.write(json.dumps(row("L-2"))[:-1] + ', "best_score": NaN}\n')
        fh.write(json.dumps(row("L-3", hypothesis="a\u2028b"), ensure_ascii=False) + "\n")
        fh.write(json.dumps(row("L-4")))  # no trailing newline
    rep = vl.validate(path, root=repo, use_git=False)
    assert rep.rows == 6 and rep.lanes == 3  # L-1, L-3, L-4 parsed
    assert has(rep.errors, "line 2: malformed row")
    assert has(rep.errors, "line 3: a row is a JSON object, not array")
    assert has(rep.errors, "line 4: malformed row", "NaN is not JSON")
    assert has(rep.errors, "[L-3] line 5: a raw line break")
    assert has(rep.warnings, "does not end with a newline")


# --- notes -----------------------------------------------------------------------------------


def test_open_lanes_without_reopens_if_are_notes(repo):
    rep = check(repo, row("L-1", reopens_if=None), row("L-2", "parked", reopens_if=""))
    assert rep.errors == [] and rep.warnings == [] and rep.exit_code(strict=True) == 0
    assert has(rep.notes, "[L-1] open lane (never-run)") and has(rep.notes, "[L-2]", "parked")
    # only the lane's latest row counts: a lane that moved on is not open any more
    assert check(repo, row("L-1", reopens_if=None), negative("L-1")).notes == []


# --- 6. append-only --------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    ident = [
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run(["git", *ident, *args], cwd=cwd, check=True, capture_output=True)


@needs_git
def test_append_only_against_the_committed_ledger(repo):
    _git(repo, "init", "-q")
    first, second = row("L-1"), row("L-2")
    path = write(repo, first, second)
    _git(repo, "add", "ledger/ledger.jsonl")
    _git(repo, "commit", "-q", "-m", "ledger")
    assert vl.validate(path, root=repo).errors == []

    write(repo, first, second, row("L-3"))  # appended: fine
    assert vl.validate(path, root=repo).errors == []

    write(repo, first, {**second, "hypothesis": "edited after the fact"}, row("L-3"))
    rep = vl.validate(path, root=repo)
    assert has(rep.errors, "APPEND-ONLY: the working file rewrites line 2") and rep.exit_code() == 1
    assert vl.validate(path, root=repo, use_git=False).errors == []  # --no-git

    write(repo, first)
    assert has(vl.validate(path, root=repo).errors, "has 1 rows where the version before it had 2")
    path.unlink()
    assert has(vl.validate(path, root=repo).errors, "has 0 rows where the version before it had 2")
    shutil.rmtree(repo / "ledger")  # the whole directory gone: still caught
    assert has(vl.validate(path, root=repo).errors, "has 0 rows where the version before it had 2")


@needs_git
def test_append_only_checks_every_committed_version(repo):
    """Both automated gates run after the commit, so a rewrite must not pass once committed."""
    _git(repo, "init", "-q")
    first, second = row("L-1"), row("L-2")
    path = write(repo, first, second)
    _git(repo, "add", "ledger/ledger.jsonl")
    _git(repo, "commit", "-q", "-m", "ledger")
    write(repo, first, {**second, "hypothesis": "edited after the fact"})
    _git(repo, "commit", "-q", "-am", "lane(L-2): NULL")
    rep = vl.validate(path, root=repo)
    assert has(rep.errors, "APPEND-ONLY: commit", "rewrites line 2")
    write(repo, first)
    _git(repo, "commit", "-q", "-am", "drop a row")
    assert has(vl.validate(path, root=repo).errors, "rows were deleted")
    # a rewrite Hunter approved is listed by SHA and passes
    shas = subprocess.run(
        ["git", "log", "--format=%H"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.split()
    (repo / "ledger" / "REWRITES").write_text("".join(f"{x}  # approved\n" for x in shas[:2]))
    assert vl.validate(path, root=repo).errors == []


def test_a_threshold_fixed_in_advance_must_be_recorded(repo):
    rep = check(repo, row("L-1", threshold_fixed_in_advance=True))
    assert has(rep.errors, "threshold_fixed_in_advance is true but no threshold")
    # and the freeze starts at that row, so filling it in later is a change
    rep = check(repo, row("L-1", threshold_fixed_in_advance=True), negative("L-1", threshold=-6.0))
    assert has(rep.errors, "threshold changed from None")


def test_historical_findings_are_repaired_by_superseding_the_lane(repo):
    """SESSION_PROMPT.md section A step 4: the repair is a FOUND-ERROR lane plus `supersedes`
    links. Rows are append-only, so the bad row stays; it becomes a visible WARN."""
    bad = negative("L-1", positive_control="none")
    rep = check(repo, bad)
    assert rep.unsound_negatives == 1 and rep.exit_code() == 1
    fix = row("R-1", "inconclusive", verdict="FOUND-ERROR", supersedes=["L-1"], evidence=["x.md"])
    (repo / "x.md").write_text("audit\n")
    carried = {"threshold": -5.5, "threshold_fixed_in_advance": True}  # as Ledger.update does
    retire = row("L-1", "superseded", superseded_by=["R-1"], **carried)
    rep = check(repo, bad, fix, retire)
    assert rep.errors == [] and rep.unsound_negatives == 0 and rep.exit_code() == 0
    assert has(rep.warnings, "UNSOUND NEGATIVE", "repaired: superseded by R-1")
    # superseded without the successor's link back is not a repair
    rep = check(repo, bad, row("R-1"), retire)
    assert rep.unsound_negatives == 1 and rep.exit_code() == 1


@needs_git
def test_evidence_under_a_gitignored_path_is_a_warning_not_a_permanent_error(repo):
    _git(repo, "init", "-q")
    (repo / ".gitignore").write_text("runs/\n")
    shutil.rmtree(repo / "runs")  # a fresh clone has no runs/
    rep = check(repo, negative("L-1", evidence=["runs/L-1/sweep.jsonl"]))
    assert rep.errors == [] and has(rep.warnings, "gitignored path")


def test_integer_round_and_surrogates(repo):
    assert check(repo, row("L-1", round=3)).errors == []
    path = write(repo, row("L-1"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row("L-2"))[:-1] + ', "notes": "\\ud800"}\n')
        fh.write(json.dumps(row("L-3"))[:-1] + ', "notes": "a"}\r' + "\n")
    rep = vl.validate(path, root=repo, use_git=False)
    assert has(rep.errors, "[L-2] line 2: a lone surrogate")
    assert not has(rep.errors, "[L-3]")  # CRLF is one line


@needs_git
def test_append_only_skips_an_untracked_ledger(repo):
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("x\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "readme")
    path = write(repo, row("L-1"))
    assert vl.validate(path, root=repo).errors == []


# --- CLI, and the contract with runeforge.ledger ---------------------------------------------


def test_cli_runs_on_the_standard_library_alone(repo):
    """-I -S: no site-packages, so neither runeforge nor pydantic is importable."""
    path = write(repo, negative("L-1", positive_control="none"), row("L-2", evidence=["x.md"]))
    cli = [sys.executable, "-I", "-S", str(SCRIPT), "--ledger", str(path), "--root", str(repo)]

    r = subprocess.run([*cli, "--no-git"], capture_output=True, text=True)
    assert r.returncode == 1, r.stderr
    assert r.stdout.splitlines()[-1] == "Unsound negatives = 1"

    r = subprocess.run([*cli, "--no-git", "--json"], capture_output=True, text=True)
    doc = json.loads(r.stdout)
    assert doc["unsound_negatives"] == 1 and doc["exit_code"] == 1 == r.returncode
    assert doc["numbering"] == "LP2-0-57" and doc["by_status"] == {"negative": 1, "never-run": 1}
    assert len(doc["warnings"]) == 1

    write(repo, row("L-2", evidence=["x.md"]))  # a WARN only; git: not a repository, skipped
    assert subprocess.run(cli, capture_output=True).returncode == 0
    assert subprocess.run([*cli, "--strict"], capture_output=True).returncode == 1


def test_mirrors_match_the_model():
    from runeforge import ledger as rl

    assert vl.STATUSES == rl.STATUSES
    assert vl.VERDICTS == rl.VERDICTS
    assert vl.CATEGORIES == rl.CATEGORIES
    assert vl.CONDITIONALS == rl.CONDITIONALS
    assert vl.NUMBERING == rl.NUMBERING
    assert typing.get_args(rl.PositiveControl) == vl.POSITIVE_CONTROLS
    fields = rl.LedgerRow.model_fields
    assert set(vl.FIELDS) == set(fields)
    assert set(vl.REQUIRED) == {k for k, f in fields.items() if f.is_required()}


def test_rows_written_by_runeforge_ledger_validate_cleanly(repo):
    from runeforge import ledger as rl

    led = rl.Ledger(repo / "ledger" / "ledger.jsonl")
    led.new("L-0", "parked idea", "prng", reopens_if="a measured prior")
    led.preregister(
        "L-1",
        "toy hypothesis",
        "prng",
        category="bounded",
        threshold=-5.5,
        threshold_fixed_in_advance=True,
        reopens_if="a decoder that models skip_by_two",
        evidence=["lanes/L-1/RESULTS.md"],
    )
    led.record_result(
        "L-1",
        "negative",
        verdict="NULL",
        positive_control="passed",
        control_detail={"recovered": "20/20"},
        conditionals=CONDITIONALS,
        n_trials=2**32,
        best_score=-7.1,
        null={"mean": -9.0, "sd": 0.4, "max": -7.6},
        coverage="seeds 0..2^32",
        not_covered="string seeds",
        external_ids=["dukotah:R12-D3"],
    )
    led.new(
        "R-1",
        "re-derive L-1's headline number",
        "redteam",
        status="inconclusive",
        verdict="FOUND-ERROR",
        positive_control="failed",
        supersedes=["L-1"],
        evidence=["runs/L-1/sweep.jsonl"],
    )
    led.update("L-1", status="superseded", superseded_by=["R-1"])
    led.new("L-2", "running lane", "prng", status="running", reopens_if="never")

    rep = vl.validate(led.path, root=repo, use_git=False)
    assert (rep.errors, rep.warnings, rep.notes) == ([], [], [])
    assert rep.by_status == {"never-run": 1, "superseded": 1, "inconclusive": 1, "running": 1}
    assert vl.render(rep).splitlines()[-1] == "Unsound negatives = 0"


def test_validator_rejects_what_ledger_rows_cannot_read(tmp_path):
    """Ledger.rows() splits on str.splitlines(); a raw U+2028 in a field breaks its row there."""
    from runeforge import ledger as rl

    led = rl.Ledger(tmp_path / "ledger.jsonl")
    led.new("L-9", "a\u2028b", "prng", reopens_if="x")
    try:
        led.rows()
        readable = True
    except ValueError:
        readable = False
    rep = vl.validate(led.path, root=tmp_path, use_git=False)
    assert bool(rep.errors) is (not readable)
