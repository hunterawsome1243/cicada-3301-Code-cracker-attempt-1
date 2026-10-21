from __future__ import annotations

import os

import pytest

from runeforge.sources import raw_available


def pytest_collection_modifyitems(config, items):
    """Tests marked ``raw`` need the vendored sources. Locally they skip when the sources
    are absent; with RUNEFORGE_REQUIRE_RAW=1 (CI) a missing source is an error."""
    if raw_available():
        return
    if os.environ.get("RUNEFORGE_REQUIRE_RAW") == "1":
        raise pytest.UsageError("RUNEFORGE_REQUIRE_RAW=1 but data/raw is missing")
    for item in items:
        if "raw" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="data/raw missing: run scripts/fetch_raw.sh"))
