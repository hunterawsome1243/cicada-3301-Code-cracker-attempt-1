"""Filesystem locations. Override the data root with ``RUNEFORGE_DATA``."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("RUNEFORGE_DATA", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
CANON_DIR = DATA_DIR / "canon"
REFERENCE_DIR = DATA_DIR / "reference"
CORPORA_DIR = DATA_DIR / "corpora"
LANES_DIR = Path(os.environ.get("RUNEFORGE_LANES", REPO_ROOT / "lanes"))
REPORTS_DIR = REPO_ROOT / "reports"
LEDGER_PATH = Path(os.environ.get("RUNEFORGE_LEDGER", REPO_ROOT / "ledger" / "ledger.jsonl"))
