"""scripts/hooks/python_only.sh: the verify-lane subagent's Bash runs only `python ...`
(SESSION_PROMPT.md section C4: "Read + Bash(python *)")."""

from __future__ import annotations

import json
import subprocess

import pytest

from runeforge.paths import REPO_ROOT

HOOK = REPO_ROOT / "scripts" / "hooks" / "python_only.sh"


def _run(command: str) -> int:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        ["bash", str(HOOK)], input=payload, text=True, capture_output=True
    ).returncode


@pytest.mark.parametrize(
    "command",
    [
        "python /tmp/verify/check.py",
        'python3 -c \'import json; print(json.load(open("runs/x/status.json"))["cursor"])\'',
        "python -m runeforge.cli control lanes/x.yaml --seed 7 --out /tmp/verify-x",
        "python -m runeforge.cli score lanes/x.yaml 681",
    ],
)
def test_python_commands_pass(command):
    assert _run(command) == 0


@pytest.mark.parametrize(
    "command",
    [
        "runeforge control lanes/x.yaml",
        "cat runs/x/sweep.jsonl",
        "python x.py && rm -rf lanes",
        "python -c 'x'; rm y",
        "python -c 'import os' > /tmp/a",
        'python -c "$(rm -rf x)"',
        "python x.py | tee lanes/x/RESULTS.md",
        "python -c 'unterminated",
    ],
)
def test_everything_else_is_blocked(command):
    assert _run(command) == 2


def test_the_agent_registers_the_hook():
    text = (REPO_ROOT / ".claude/agents/verify-lane.md").read_text(encoding="utf-8")
    front = text.split("---")[1]
    assert "tools: Read, Bash" in front and "scripts/hooks/python_only.sh" in front
