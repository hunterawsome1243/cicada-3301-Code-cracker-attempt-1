"""The two Claude Code hooks behind the frozen toolbox and the stop gate (OVERNIGHT_LOOP.md Part 1
§6), driven the way Claude Code drives them: one JSON payload on stdin; exit 0 allows, exit 2
blocks and stderr is the reason Claude sees. Every test points the hook at a throwaway project
root through CLAUDE_PROJECT_DIR, so nothing here reads or writes the real FROZEN.txt or ledger,
and the stop-gate tests bring their own stub gate scripts (or a copy of the real
scripts/check_results.py) so they do not depend on the repository's state.

The Bash tables run against two frozen lists: the split list (individual test files, as the real
FROZEN.txt will have them) and the CLAUDE.md list (``tests/*`` and friends).
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / "scripts" / "hooks"
DENY = HOOKS / "deny_frozen.sh"
STOP = HOOKS / "stop_gate.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="the hooks are bash scripts")

FROZEN = """\
# frozen toolbox (test copy)
data/canon/*
data/raw/*   # vendored upstreams: an inline comment is not part of the pattern
runeforge/oracle.py
runeforge/stats/**

tests/test_solved_pages.py
scripts/check_results.py
FROZEN.txt
"""
CLAUDE_FROZEN = """\
data/canon/*
data/raw/*
runeforge/oracle.py
runeforge/controls.py
runeforge/ledger.py
runeforge/stats/*
runeforge/scoring/calib/*
tests/*
scripts/check_results.py
scripts/validate_ledger.py
scripts/threshold_for.py
FROZEN.txt
"""
FILES = (
    "data/canon/lp2_runes.json",
    "data/canon/sub/dir/y",
    "data/raw/dukotah/README.md",
    "runeforge/oracle.py",
    "runeforge/cli.py",
    "runeforge/stats/core.py",
    "runeforge/scoring/calib/quad.json",
    "tests/test_solved_pages.py",
    "scripts/check_results.py",
)


def _env(root: Path | None, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.pop("CLAUDE_PROJECT_DIR", None)
    if root is not None:
        env["CLAUDE_PROJECT_DIR"] = str(root)
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
    env.update(extra)
    return env


def _project(r: Path, frozen: str) -> Path:
    for rel in FILES:
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text("x\n")
    (r / "runs").mkdir()
    (r / "FROZEN.txt").write_text(frozen)
    return r


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return _project(tmp_path / "proj", FROZEN)


@pytest.fixture(params=["split", "claude"])
def any_root(request, tmp_path: Path) -> Path:
    return _project(tmp_path / "proj", FROZEN if request.param == "split" else CLAUDE_FROZEN)


@pytest.fixture
def claude_root(tmp_path: Path) -> Path:
    return _project(tmp_path / "proj", CLAUDE_FROZEN)


def deny(root: Path, payload, cwd: Path | None = None, script: Path = DENY, env=None):
    if isinstance(payload, dict):
        payload = json.dumps(
            {"hook_event_name": "PreToolUse", "cwd": str(cwd or root), "session_id": "t", **payload}
        )
    return subprocess.run(
        [str(script)],
        input=payload,
        capture_output=True,
        text=True,
        env=env or _env(root),
        timeout=30,
    )


def bash(root: Path, command: str, cwd: Path | None = None):
    return deny(root, {"tool_name": "Bash", "tool_input": {"command": command}}, cwd)


def write(root: Path, path, tool: str = "Write", cwd: Path | None = None, key="file_path"):
    return deny(root, {"tool_name": tool, "tool_input": {key: str(path), "content": "y"}}, cwd)


# --- Edit / Write ---------------------------------------------------------------------------------
def test_write_to_canon_is_blocked_with_the_reason(root):
    r = write(root, root / "data/canon/lp2_runes.json")
    assert r.returncode == 2
    assert "frozen: data/canon/lp2_runes.json is listed in FROZEN.txt" in r.stderr
    assert "TOOLBOX_REQUESTS.md" in r.stderr and "(CLAUDE.md, Frozen toolbox)" in r.stderr


@pytest.mark.parametrize(
    ("tool", "rel", "key", "blocked"),
    [
        ("Write", "runeforge/cli.py", "file_path", False),
        ("Write", "runeforge/new_module.py", "file_path", False),
        ("Edit", "runeforge/oracle.py", "file_path", True),
        ("MultiEdit", "FROZEN.txt", "file_path", True),
        ("Write", "data/canon/new.json", "file_path", True),
        ("Write", "data/canon/sub/dir/deeper/z", "file_path", True),
        ("Write", "data/raw/dukotah/README.md", "file_path", True),
        ("Edit", "runeforge/stats/core.py", "file_path", True),
        ("Write", "tests/test_solved_pages.py", "file_path", True),
        ("Write", "tests/test_new.py", "file_path", False),
        ("NotebookEdit", "data/canon/x.ipynb", "notebook_path", True),
        ("Edit", "runeforge/../data/canon/lp2_runes.json", "file_path", True),
        ("Read", "runeforge/oracle.py", "file_path", False),
    ],
)
def test_file_tools_absolute_paths(root, tool, rel, key, blocked):
    r = write(root, root / rel, tool=tool, key=key)
    assert r.returncode == (2 if blocked else 0), r.stderr


def test_edit_outside_the_root_is_allowed(root, tmp_path):
    outside = tmp_path / "elsewhere" / "data" / "canon" / "lp2_runes.json"
    assert write(root, outside, tool="Edit").returncode == 0


def test_relative_path_resolves_against_the_payload_cwd(root):
    assert write(root, "lp2_runes.json", cwd=root / "data/canon").returncode == 2
    assert write(root, "runeforge/oracle.py", cwd=root).returncode == 2
    assert write(root, "oracle.py", cwd=root).returncode == 0


def test_write_through_a_symlink_into_a_frozen_path_is_blocked(root, tmp_path):
    link = tmp_path / "outside_link.py"
    link.symlink_to(root / "runeforge/oracle.py")
    assert write(root, link).returncode == 2


# --- Bash -----------------------------------------------------------------------------------------
UNRESOLVED_BLOCKED = [  # write targets from xargs / $(...) / loops, traced to their producer
    "grep -rl old_name runeforge | xargs sed -i 's/old_name/new_name/g'",
    "grep -rl old_name . | xargs sed -i 's/a/b/'",
    "find runeforge -name '*.py' | xargs sed -i 's/a/b/'",
    "git ls-files '*.py' | xargs sed -i 's/a/b/'",
    "git grep -l old_name | xargs perl -pi -e 's/a/b/'",
    "sed -i 's/old/new/g' $(grep -rl old runeforge)",
    "for f in $(grep -rl old runeforge); do sed -i 's/old/new/' \"$f\"; done",
    "black $(git ls-files '*.py')",
    "grep -rl x runeforge | while read -r f; do sed -i 's/a/b/' \"$f\"; done",
    "while IFS= read -r f; do sed -i 's/a/b/' \"$f\"; done < <(git ls-files '*.py')",
    "mapfile -t fs < <(git ls-files '*.py'); black \"${fs[@]}\"",
    "for f in runeforge/*.py; do echo $f; done | xargs sed -i s/a/b/",
    "(cd runeforge && ls) | xargs rm",
    "ls | xargs rm",
    "rg -l old | xargs sed -i s/a/b/",
    "git diff --name-only | xargs black",
    "git ls-files -z | xargs -0 rm",
    "echo FROZEN.txt | xargs rm",
    "git grep -l x | xargs -I{} sh -c 'sed -i s/a/b/ \"{}\"'",
    "git grep -l x | xargs sh -c 'sed -i s/a/b/ \"$@\"' _",
    "find runeforge -name '*.py' -exec sh -c 'sed -i s/a/b/ \"$1\"' _ {} \\;",
    'rm -rf "$(git rev-parse --show-toplevel)/data/canon"',
    'rm "$ROOT_UNSET_IN_TEST/FROZEN.txt"',
    "F=$(ls data/canon); rm $F",
]

BLOCKED = [
    "sed -i s/a/b/ runeforge/oracle.py",
    "sed -i.bak -e s/a/b/ runeforge/oracle.py",
    "sed --in-place=.orig 's/a/b/' runeforge/oracle.py",
    "perl -pi -e 's/a/b/' runeforge/oracle.py",
    "echo hi > data/canon/x.json",
    "echo hi>data/canon/x.json",
    "echo hi >> data/canon/sub/dir/y",
    "echo hi &> FROZEN.txt",
    "make 2> data/canon/err.log",
    "echo hi >| FROZEN.txt",
    "cp /tmp/b data/canon/a",
    "cp /tmp/b data/canon/a 2>/dev/null",
    "cp -t data/canon /tmp/b",
    "cp /tmp/b /tmp/c data/canon",
    "cp -r /tmp/canon data/",
    "mv data/canon/a /tmp/a",
    "mv /tmp/a runeforge/oracle.py",
    "mv runeforge somewhere_else",
    "install -m 644 /tmp/x scripts/check_results.py",
    "ln -sf /tmp/evil runeforge/oracle.py",
    "rm data/canon/lp2_runes.json",
    "rm -rf data",
    "rm -rf .",
    "rm runeforge/*.py",
    "rm data/canon/{a,b}.json",
    "rmdir data/canon/sub/dir",
    "chmod -R u+w runeforge",
    "chmod 000 FROZEN.txt",
    "touch runeforge/stats/new.py",
    "truncate -s 0 FROZEN.txt",
    "mkdir -p data/canon/new",
    "dd if=/dev/zero of=data/canon/x bs=1 count=1",
    "tee -a FROZEN.txt",
    "ls 2>&1 | tee runeforge/oracle.py",
    "echo x | tee /tmp/a runeforge/oracle.py",
    "git checkout -- tests/test_solved_pages.py",
    "git checkout HEAD~1 runeforge/oracle.py",
    "git checkout .",
    "git restore runeforge/oracle.py",
    "git restore --source=HEAD~2 -- data/canon",
    "git restore --staged --worktree FROZEN.txt",
    "git rm --cached FROZEN.txt",
    "git mv runeforge/oracle.py runeforge/oracle_old.py",
    "git -C data checkout -- canon/lp2_runes.json",
    "cd data/canon && rm lp2_runes.json",
    "cd data && cd canon; rm lp2_runes.json",
    "cd runeforge\nrm oracle.py",
    "pushd runeforge >/dev/null && rm oracle.py",
    "(cd /tmp && true); rm data/canon/lp2_runes.json",
    "cd /tmp | true; rm FROZEN.txt",
    'F=data/canon/lp2_runes.json; rm "$F"',
    'rm "$CLAUDE_PROJECT_DIR/FROZEN.txt"',
    "rm $(ls data/canon)",
    "ls data/canon | xargs rm",
    "for f in data/canon/*; do rm $f; done",
    "find data/canon -name '*.json' -delete",
    "find runeforge -name '*.py' -exec sed -i s/a/b/ {} +",
    "find runeforge -name '*.py' -exec sed -i 's/a/b/' {} +",
    "find /tmp -name x -exec cp {} data/canon/ \\;",
    "bash -c 'echo x > runeforge/oracle.py'",
    'sh -ec "rm -f FROZEN.txt"',
    "eval 'rm FROZEN.txt'",
    'echo "$(rm data/canon/lp2_runes.json)"',
    "echo `rm data/canon/lp2_runes.json`",
    "sudo -u hunter rm FROZEN.txt",
    "timeout 10 rm FROZEN.txt",
    "env A=1 rm FROZEN.txt",
    "if true; then rm FROZEN.txt; fi",
    "python3 -c \"open('runeforge/oracle.py', 'w').write('')\"",
    'python -c \'import pathlib; pathlib.Path("data/canon/x").write_text("")\'',
    'perl -e \'open(my $f, ">", "FROZEN.txt")\'',
    "python3 - <<'EOF'\nfrom pathlib import Path\nPath('data/canon/x').write_text('')\nEOF",
    "bash <<EOF\nrm data/canon/lp2_runes.json\nEOF",
    "cat > data/canon/x <<'EOF'\nhello\nEOF",
    "echo a#b > data/canon/x",
    "black runeforge",
    "isort tests/test_solved_pages.py",
    "ruff check --fix .",
    "ruff format scripts/check_results.py",
    'echo "unterminated > data/canon/x',
    # -t DIR inside a short-option cluster
    "cp -vt data/canon /tmp/x",
    "cp -rt data/canon /tmp/x",
    "cp -at runeforge/stats /tmp/x",
    "install -Dt runeforge/stats /tmp/x",
    "install -vt data/canon /tmp/x",
    "ln -sft data/canon /tmp/x",
    "cp -fvt tests /tmp/test_solved_pages.py",
    "cp --target-directory=data/canon /tmp/x",
    "mv -vt /tmp data/canon/lp2_runes.json",
    # function bodies, interpreter options, python -m, shell option ends, env -C, archives, git
    "function f { rm FROZEN.txt; }; f",
    "f() { rm FROZEN.txt; }; f",
    "python3 -W ignore -c \"open('runeforge/oracle.py','w')\"",
    "python3 -X utf8 -c \"open('runeforge/oracle.py','w')\"",
    "python3 -Bc \"open('runeforge/oracle.py','w')\"",
    "python -m black runeforge/oracle.py",
    "python -m ruff format tests",
    "python -m isort tests",
    "python3 -m zipfile -e /tmp/x.zip data/canon",
    "bash -c -- 'rm FROZEN.txt'",
    "env -C data/canon rm lp2_runes.json",
    "env --chdir=data/canon rm lp2_runes.json",
    "env -S 'rm FROZEN.txt'",
    "tar -xf /tmp/x.tar -C data/canon",
    "tar xzf /tmp/x.tgz -C data/canon",
    "tar -x -f /tmp/x.tar --directory=data/raw",
    "unzip -o /tmp/x.zip -d data/canon",
    "unzip /tmp/x.zip 'data/canon/*'",
    "git clean -fdx tests",
    "git clean -fdx",
    "git submodule deinit -f data/raw/dukotah",
    "git submodule deinit --all -f",
    "trap 'rm -f FROZEN.txt' EXIT; echo hi",
    "trap -- 'rm FROZEN.txt' EXIT",
    "(( x = 1 << 2 ))\nrm FROZEN.txt\n",
    "x=1; (( x <<= 2 )); rm FROZEN.txt",
    "for ((i=0; i<3; i++)); do rm FROZEN.txt; done",
    "sudo -D data/canon rm lp2_runes.json",
    "python3 -c \"open(ROOT + '/FROZEN.txt', 'w')\"",
    "for f in tests/test_*.py; do black $f; done",
    "echo x > $(echo data/canon/x)",
    "cd data && grep -rl x . | xargs rm",
    "git -C runeforge ls-files | xargs rm",
    "xargs rm < FROZEN.txt",
    "xargs -a FROZEN.txt rm",
    *UNRESOLVED_BLOCKED,
]
CLAUDE_LIST_BLOCKED = [  # need tests/* (the CLAUDE.md list) rather than individual test files
    "cp -fvt tests /tmp/test_new.py",
    'cp "$SRC" tests/',
    "printf '%s\\n' tests/* | xargs sed -i s/a/b/",
]

ALLOWED = [
    "python -m pytest -q",
    "pytest -q > /tmp/log 2>&1",
    "cat data/canon/x.json > /tmp/out",
    "cp data/canon/a /tmp/b",
    "cp -r data/canon /tmp/canon_copy",
    "ln -s runeforge/oracle.py /tmp/link",
    "cat FROZEN.txt",
    "grep -n def runeforge/oracle.py | head -5",
    "sed -n 1,20p runeforge/oracle.py",
    "perl -ne 'print if /x/' runeforge/oracle.py",
    "echo hi > runeforge/notes.txt",
    "touch runeforge/new_module.py",
    "rm -rf runs/old && mkdir -p runs/new",
    "mv runeforge/cli.py runeforge/cli2.py",
    "chmod +x scripts/hooks/deny_frozen.sh",
    "git status --porcelain && git diff -- runeforge/oracle.py",
    "git log --oneline -5 -- data/canon",
    "git add FROZEN.txt && git commit -m 'freeze runeforge/oracle.py'",
    "git checkout -b lane/x",
    "git restore --staged FROZEN.txt runeforge/oracle.py",
    "git commit -m \"$(cat <<'EOF'\nlane(x): don't touch runeforge/oracle.py (frozen)\nEOF\n)\"",
    "echo '>' runeforge/oracle.py",
    "echo 'a; rm FROZEN.txt'",
    "ls # don't > data/canon/x",
    "cat <<'EOF' > notes.md\nrm data/canon/lp2_runes.json\nit's fine > FROZEN.txt\nEOF",
    "python3 -c \"print(open('data/canon/lp2_runes.json').read())\"",
    "find data/canon -name '*.json' -exec cat {} +",
    "find runs -name '*.tmp' -delete",
    "cd /tmp && rm oracle.py",
    "echo hi > /tmp/x; cat runeforge/oracle.py",
    "diff <(sort data/canon/a) <(sort /tmp/b)",
    "echo $(cat data/canon/lp2_runes.json) > /tmp/x",
    "for f in data/canon/*; do wc -c $f; done",
    "ls data/canon | xargs wc -c",
    "python3 - <<'EOF'\nimport json\nd = json.load(open('data/canon/lp2_runes.json'))\n"
    "open('runs/x.json', 'w').write(json.dumps(d))\nEOF",
    "runeforge oracle --selftest",
    "ruff check runeforge scripts tests && black --check runeforge scripts tests",
    "black runeforge/cli.py && ruff check --fix runeforge/cli.py && ruff format --check .",
    "runeforge sweep lanes/x.yaml --detach && python scripts/check_results.py lanes/x/RESULTS.md",
    'echo "$(date) iteration done" >> runs/overnight/log',
    "cat > lanes/x/PREREG.md <<'EOF'\nreads data/canon/* only; bar > 3.2; FROZEN.txt as is\nEOF",
    "",
    # everyday commands
    "pytest -q tests",
    "git status",
    "git diff",
    "git log --oneline -5",
    "runeforge status",
    "runeforge status --short",
    "grep -rn oracle runeforge tests",
    "sed -n 1,20p FROZEN.txt",
    "python scripts/validate_ledger.py",
    "ls runs | xargs rm",
    "black --check runeforge scripts tests",
    "ruff check .",
    "python -m black --check runeforge",
    "python3 -W error -m pytest -q",
    "python3 -X importtime -c 'import runeforge'",
    "tail -n 50 runs/x/sweep.log | grep -i error",
    "kill $(cat runs/x/sweep.pid)",
    # unresolved targets whose producers name no frozen path
    'rm -rf "$TMP_DIR" && pytest -q tests',
    'mv "$OUT" runs/final.json && cat tests/test_x.py',
    "python -c \"import os; os.makedirs('runs/tests', exist_ok=True)\"",
    'cat tests/test_x.py > "$OUT"',
    'cp tests/test_x.py "$DEST"',
    'D=$(mktemp -d); rm -rf "$D"',
    "find runs -name '*.json' | xargs rm",
    "find runs -name '*.py' -delete",
    "grep -rl old runs | xargs sed -i s/a/b/",
    "cd runs && grep -rl x . | xargs rm",
    "git ls-files runs | xargs rm",
    "git diff --name-only | xargs ruff check",
    "git diff --name-only | xargs black --check",
    "git ls-files '*.py' | xargs wc -l",
    "ls runeforge | xargs -I{} cp runeforge/{} /tmp/",
    "for f in $(ls data/canon); do cp data/canon/$f runs/$f; done",
    "cat runs/list | xargs rm",
    'while read -r f; do echo "$f"; done < runs/list',
    "rm -f runs/$(date +%s).log",
    "trap 'rm -rf \"$TMP\"' EXIT; python scripts/x.py",
    "for f in tests/*.py; do python -m py_compile $f; done",
    "echo $(( 1 << 2 )) > runs/x",
    # archives, clean, env -C elsewhere
    "tar -czf runs/x.tgz data/canon",
    "tar -tf /tmp/x.tar",
    "tar -xf /tmp/x.tar -C runs",
    "unzip -l /tmp/x.zip",
    "unzip -o /tmp/x.zip -d runs/x",
    "git clean -n",
    "git clean -fd runs",
    "env -C runs rm x.json",
    "cp -vt runs data/canon/lp2_runes.json",
    "cat FROZEN.txt | xargs -I{} cp {} /tmp/backup/",
    "head -n1 runs/list | xargs -I{} rm -rf runs/{}",
    "for lane in lanes/*; do python scripts/check_results.py $lane/RESULTS.md; done",
    "setsid nohup runeforge sweep lanes/x.yaml > runs/x/sweep.log 2>&1 &",
    'echo "export PATH=$PWD/.venv/bin:$PATH" >> "$CLAUDE_ENV_FILE"',
    "git -C runs ls-files | xargs rm",
    "python3 -c \"import json; json.dump({}, open('runs/tests.json', 'w'))\"",
    "python3 -c \"open('/tmp/x/runeforge/oracle.py', 'w')\"",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_bash_writes_to_frozen_paths_are_blocked(any_root, command):
    r = bash(any_root, command)
    assert r.returncode == 2, f"not blocked: {command!r}\n{r.stderr}"
    assert "is listed in FROZEN.txt" in r.stderr


@pytest.mark.parametrize("command", CLAUDE_LIST_BLOCKED)
def test_bash_writes_under_a_frozen_tests_dir_are_blocked(claude_root, command):
    r = bash(claude_root, command)
    assert r.returncode == 2, f"not blocked: {command!r}\n{r.stderr}"
    assert "is listed in FROZEN.txt" in r.stderr


@pytest.mark.parametrize("command", ALLOWED)
def test_bash_reads_and_unfrozen_writes_are_allowed(any_root, command):
    r = bash(any_root, command)
    assert r.returncode == 0, f"blocked: {command!r}\n{r.stderr}"


def test_bash_relative_paths_follow_the_payload_cwd(root):
    assert bash(root, "rm lp2_runes.json", cwd=root / "data/canon").returncode == 2
    assert bash(root, "cd .. && rm canon/lp2_runes.json", cwd=root / "data/canon").returncode == 2
    assert bash(root, "rm lp2_runes.json", cwd=root / "runs").returncode == 0
    assert bash(root, "git ls-files | xargs rm", cwd=root / "runs").returncode == 0
    assert bash(root, "git ls-files | xargs rm", cwd=root / "data").returncode == 2


# --- why a heuristic blocked ----------------------------------------------------------------------
@pytest.mark.parametrize("command", UNRESOLVED_BLOCKED)
def test_unresolved_write_targets_say_why(root, command):
    r = bash(root, command)
    assert r.returncode == 2, r.stderr
    assert "why: unresolved write target" in r.stderr
    assert "name the path literally or split the command" in r.stderr


def test_unresolved_message_names_the_target_and_its_producer(root):
    r = bash(root, "grep -rl old_name runeforge | xargs sed -i 's/old_name/new_name/g'")
    assert "unresolved write target `<xargs input>` could be anything under `runeforge`" in r.stderr
    assert "(listed by `grep -rl old_name runeforge`)" in r.stderr
    r = bash(root, "for f in $(grep -rl old runeforge); do sed -i 's/old/new/' \"$f\"; done")
    assert "unresolved write target `$f`" in r.stderr
    r = bash(root, 'rm -rf "$ROOT_UNSET_IN_TEST/data/canon"')
    assert "unresolved write target `$ROOT_UNSET_IN_TEST/data/canon`" in r.stderr
    assert "a frozen path if `$ROOT_UNSET_IN_TEST` is the project root" in r.stderr


def test_code_and_parse_heuristics_say_why(root):
    r = bash(root, "python3 -c \"import os; os.remove('runeforge/oracle.py')\"")
    assert r.returncode == 2
    assert "why: interpreter code `os.remove('runeforge/oracle.py')`" in r.stderr
    r = bash(root, 'echo "unterminated > data/canon/x')
    assert r.returncode == 2
    assert "why: the command could not be parsed" in r.stderr


def test_literal_targets_need_no_why(root):
    r = bash(root, "rm data/canon/lp2_runes.json")
    assert r.returncode == 2
    assert "why:" not in r.stderr


# --- FROZEN.txt parsing ---------------------------------------------------------------------------
def test_inline_comments_are_stripped(root):
    (root / "FROZEN.txt").write_text("data/canon/*   # canonical transcription\n")
    assert bash(root, "rm data/canon/lp2_runes.json").returncode == 2
    assert write(root, root / "data/canon/lp2_runes.json").returncode == 2


def test_frozen_txt_with_a_bom_is_read(root):
    (root / "FROZEN.txt").write_bytes(b"\xef\xbb\xbfFROZEN.txt\nrunes/x\n")
    assert bash(root, "rm FROZEN.txt").returncode == 2


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le"])
def test_undecodable_frozen_txt_blocks_writes_and_allows_reads(root, encoding):
    (root / "FROZEN.txt").write_bytes("data/canon/*\nFROZEN.txt\n".encode(encoding))
    for r in (bash(root, "echo hi > runs/x"), write(root, root / "runs/x.json")):
        assert r.returncode == 2, r.stderr
        assert "FROZEN.txt unreadable:" in r.stderr
    assert write(root, root / "runeforge/oracle.py", tool="Read").returncode == 0


# --- robustness -----------------------------------------------------------------------------------
@pytest.mark.parametrize("payload", ["not json at all {", "[1, 2]", ""])
def test_garbage_payload_warns_and_allows(root, payload):
    r = deny(root, payload)
    assert r.returncode == 0
    assert "warning" in r.stderr


def test_missing_frozen_txt_allows_everything(root):
    (root / "FROZEN.txt").unlink()
    assert write(root, root / "data/canon/lp2_runes.json").returncode == 0
    assert bash(root, "rm -rf data").returncode == 0


def test_comment_only_frozen_txt_allows_everything(root):
    (root / "FROZEN.txt").write_text("# nothing frozen yet\n\n")
    assert bash(root, "echo hi > data/canon/lp2_runes.json").returncode == 0


def test_root_defaults_to_two_levels_above_the_script(root):
    hooks = root / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    for name in ("deny_frozen.sh", "frozen_guard.py"):
        shutil.copy2(HOOKS / name, hooks / name)
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(root / "FROZEN.txt")}}
    r = deny(root, payload, script=hooks / "deny_frozen.sh", env=_env(None))
    assert r.returncode == 2, r.stderr


def test_guard_is_standard_library_only():
    tree = ast.parse((HOOKS / "frozen_guard.py").read_text())
    mods = {
        a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    mods |= {
        n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
    }
    assert mods - {"__future__"} <= set(sys.stdlib_module_names)
    assert "subprocess" not in mods


def test_guard_is_fast(root):
    command = "cd data && git status && " + " && ".join(f"cat canon/f{i}" for i in range(200))
    t0 = time.monotonic()
    assert bash(root, command).returncode == 0
    command = " && ".join(f"ls runs | xargs rm; rm -rf $X{i}" for i in range(200))
    assert bash(root, command).returncode == 0
    assert time.monotonic() - t0 < 5


# --- stop gate ------------------------------------------------------------------------------------
VALIDATOR = """\
import pathlib, sys
bad = pathlib.Path("ledger/BAD").exists()
print("ERRORS: 1\\n  - ledger row broken" if bad else "ERRORS: 0")
sys.exit(1 if bad else 0)
"""
CHECKER = """\
import pathlib, sys
with open("checked.log", "a") as fh:
    fh.write(sys.argv[1] + "\\n")
ok = "BAD" not in pathlib.Path(sys.argv[1]).read_text()
print("PASS" if ok else "FAIL\\n  - section 5 (Coverage) missing")
sys.exit(0 if ok else 1)
"""
OLD = "2001-01-01T12:00:00 +0000"  # a commit date far outside the 24-hour window


def _git(root: Path, *args: str, date: str | None = None) -> None:
    extra = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        check=True,
        capture_output=True,
        env=_env(None, **extra),
    )


def _commit(root: Path, message: str, date: str | None = None) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message, date=date)


@pytest.fixture
def gate_root(tmp_path: Path) -> Path:
    r = tmp_path / "gate"
    (r / "scripts").mkdir(parents=True)
    (r / "ledger").mkdir()
    (r / "lanes" / "L1").mkdir(parents=True)
    (r / "scripts" / "validate_ledger.py").write_text(VALIDATOR)
    (r / "scripts" / "check_results.py").write_text(CHECKER)
    (r / "lanes" / "L1" / "RESULTS.md").write_text("ok\n")
    (r / ".gitignore").write_text("checked.log\n")
    return r


def stop(root: Path, payload=None, **env: str):
    data = json.dumps(payload if payload is not None else {"hook_event_name": "Stop"})
    return subprocess.run(
        [str(STOP)],
        input=data,
        capture_output=True,
        text=True,
        env=_env(root, **{"RUNEFORGE_PYTHON": sys.executable, **env}),
        timeout=60,
    )


def _checked(root: Path) -> list[str]:
    log = root / "checked.log"
    return log.read_text().split() if log.exists() else []


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def test_stop_hook_active_exits_at_once(gate_root):
    (gate_root / "ledger" / "BAD").touch()
    r = stop(gate_root, {"hook_event_name": "Stop", "stop_hook_active": True})
    assert r.returncode == 0
    assert _checked(gate_root) == []


@needs_git
def test_failing_ledger_blocks_the_stop(gate_root):
    _git(gate_root, "init", "-q")
    (gate_root / "ledger" / "BAD").touch()
    r = stop(gate_root, {"hook_event_name": "Stop", "stop_hook_active": False})
    assert r.returncode == 2
    assert "ledger row broken" in r.stderr and "validate_ledger.py" in r.stderr
    assert "commit, then stop" not in r.stderr
    assert "Committing alone does not pass this gate" in r.stderr


@needs_git
def test_untracked_failing_results_blocks_and_passing_one_allows(gate_root):
    _git(gate_root, "init", "-q")
    (gate_root / "lanes" / "L1" / "RESULTS.md").write_text("BAD\n")
    r = stop(gate_root)
    assert r.returncode == 2
    assert "section 5 (Coverage) missing" in r.stderr
    assert _checked(gate_root) == ["lanes/L1/RESULTS.md"]
    (gate_root / "lanes" / "L1" / "RESULTS.md").write_text("ok\n")
    assert stop(gate_root).returncode == 0


@needs_git
def test_only_changed_results_are_checked(gate_root):
    (gate_root / "lanes" / "L1" / "RESULTS.md").write_text("BAD but committed long ago\n")
    (gate_root / "lanes" / "L2").mkdir()
    (gate_root / "lanes" / "L2" / "RESULTS.md").write_text("ok\n")
    (gate_root / "lanes" / "L2" / "notes.md").write_text("BAD, but not a RESULTS.md\n")
    (gate_root / "lanes" / "L2" / "deep").mkdir()
    (gate_root / "lanes" / "L2" / "deep" / "RESULTS.md").write_text("BAD, but two levels down\n")
    _git(gate_root, "init", "-q")
    _commit(gate_root, "init", date=OLD)
    assert stop(gate_root).returncode == 0
    assert _checked(gate_root) == []
    (gate_root / "lanes" / "L2" / "RESULTS.md").write_text("ok, edited\n")
    assert stop(gate_root).returncode == 0
    assert _checked(gate_root) == ["lanes/L2/RESULTS.md"]
    (gate_root / "lanes" / "L1" / "RESULTS.md").write_text("BAD, edited\n")
    assert stop(gate_root).returncode == 2


@needs_git
def test_committed_results_from_the_last_day_are_checked_once(gate_root):
    _git(gate_root, "init", "-q")
    _commit(gate_root, "init", date=OLD)
    (gate_root / "lanes" / "L1" / "RESULTS.md").write_text("BAD, committed just now\n")
    _commit(gate_root, "lane(L1): NULL")
    (gate_root / "lanes" / "L1" / "RESULTS.md").write_text("BAD, edited again\n")
    r = stop(gate_root)
    assert r.returncode == 2
    assert _checked(gate_root) == ["lanes/L1/RESULTS.md"]  # listed twice, checked once


@needs_git
def test_unpushed_commits_are_checked_and_pushed_ones_are_not(gate_root):
    _git(gate_root, "init", "-q")
    _commit(gate_root, "init", date=OLD)
    _git(gate_root, "branch", "upstream")
    _git(gate_root, "branch", "-q", "--set-upstream-to=upstream")
    (gate_root / "lanes" / "L2").mkdir()
    (gate_root / "lanes" / "L2" / "RESULTS.md").write_text("BAD, unpushed for days\n")
    _commit(gate_root, "lane(L2): NULL", date=OLD)
    r = stop(gate_root)
    assert r.returncode == 2
    assert _checked(gate_root) == ["lanes/L2/RESULTS.md"]
    _git(gate_root, "branch", "-f", "upstream", "HEAD")  # as if pushed
    assert stop(gate_root).returncode == 0


@needs_git
@pytest.mark.parametrize(
    ("fixture", "code"), [("bad_null_no_floor.md", 2), ("bad_sections.md", 2), ("good_null.md", 0)]
)
def test_committed_results_meet_the_real_checker(gate_root, fixture, code):
    shutil.copy2(REPO / "scripts" / "check_results.py", gate_root / "scripts" / "check_results.py")
    (gate_root / "scripts" / "validate_ledger.py").unlink()
    _git(gate_root, "init", "-q")
    _commit(gate_root, "init", date=OLD)
    fixtures = REPO / "tests" / "fixtures" / "results"
    shutil.copy2(fixtures / fixture, gate_root / "lanes" / "L1" / "RESULTS.md")
    _commit(gate_root, "lane(L1): close")
    r = stop(gate_root)
    assert r.returncode == code, r.stderr
    if code:
        assert "--- scripts/check_results.py lanes/L1/RESULTS.md (exit 1)" in r.stderr
        assert "FAIL" in r.stderr


def test_no_scripts_no_ledger_no_lanes_no_git_allows(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = stop(empty)
    assert r.returncode == 0
    assert "not found" in r.stderr


@needs_git
def test_bad_runeforge_python_falls_back_to_python3(gate_root):
    _git(gate_root, "init", "-q")
    (gate_root / "ledger" / "BAD").touch()
    r = stop(gate_root, RUNEFORGE_PYTHON="/nonexistent/python")
    assert r.returncode == 2
    assert "ledger row broken" in r.stderr


def test_garbage_stop_payload_still_runs_the_gate(gate_root):
    (gate_root / "ledger" / "BAD").touch()
    r = subprocess.run(
        [str(STOP)],
        input="garbage",
        capture_output=True,
        text=True,
        env=_env(gate_root, RUNEFORGE_PYTHON=sys.executable),
        timeout=60,
    )
    assert r.returncode == 2
