"""Shared pytest configuration.

Tests marked `@pytest.mark.network` need real network access (and usually the
`[capture]` / `[media]` extras). They are skipped by default so the suite runs
offline in CI; pass `--run-network` to include them.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_schema_cache():
    """The schema loaders are `@lru_cache`d (keyed on corpus_root). Each test uses a fresh
    tmp corpus, but clearing before+after keeps a test that writes schema files then loads
    them from seeing a stale entry cached by an earlier load in the same process."""
    from corpus import schemas

    schemas.cache_clear()
    yield
    schemas.cache_clear()


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
