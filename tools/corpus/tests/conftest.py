"""Shared pytest configuration.

Tests marked `@pytest.mark.network` need real network access (and usually the
`[capture]` / `[media]` extras). They are skipped by default so the suite runs
offline in CI; pass `--run-network` to include them.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="run tests marked @pytest.mark.network (real network access)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network"):
        return
    skip_network = pytest.mark.skip(reason="needs --run-network (network access)")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
