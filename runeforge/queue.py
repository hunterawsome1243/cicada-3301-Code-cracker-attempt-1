"""``queue.json``: the round plan Hunter approves. The loop never invents a lane.

Format: a JSON array of entries (overnight.sh counts them with
``jq '[.[] | select(.approved==true)] | length'``, so the top level must be an array of
objects -- a top-level object with a list in it would make that jq expression fail)::

    [{"id": "P3-MT19937-PY27-EXACT", "category": "bounded", "approved": true,
      "gpu_hours_cap": 2, "prereg_ready": true, "note": "optional"}]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StrictFloat, StrictInt

from runeforge.paths import REPO_ROOT

QUEUE_PATH = REPO_ROOT / "queue.json"


class QueueEntry(BaseModel):
    """Strict types: overnight.sh approves only a literal JSON ``true`` (``.approved==true``),
    so ``"yes"`` or ``1`` must be refused here rather than read as approved."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: Literal["instrument", "bounded", "redteam", "closeout"]
    approved: StrictBool = False
    gpu_hours_cap: StrictInt | StrictFloat = 0.0
    prereg_ready: StrictBool = False
    note: str | None = None


def load_queue(path: Path | str = QUEUE_PATH) -> list[QueueEntry]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("queue.json must be a JSON array of entries (see runeforge/queue.py)")
    entries = [QueueEntry.model_validate(e) for e in data]
    ids = [e.id for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate lane ids in queue.json")
    return entries
