from __future__ import annotations

from runeforge.cli import main


def test_canon_verify(capsys):
    assert main(["canon", "--verify"]) == 0
    out = capsys.readouterr().out
    assert "023312066df471005264b9cbe7997cb77d2a9a6a2dc9b3316d22674023af1585" in out
    assert "13,136" in out and "12,956" in out


def test_solved_and_oracle():
    assert main(["solved"]) == 0
    assert main(["oracle"]) == 0


def test_status_on_empty_ledger(tmp_path, capsys):
    assert main(["status", "--ledger", str(tmp_path / "none.jsonl")]) == 0
    assert "empty" in capsys.readouterr().out
