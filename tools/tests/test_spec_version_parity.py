"""`ath._version.SPEC_VERSION` must equal the `version:` frontmatter of all
four spec parts. The spec is not shipped in the wheel, so this is a
repo-layout gate (skipped outside the distribution checkout) rather than a
runtime derivation — the stamp reaches the OpenAPI document and export
certificates, so a lag here pins consumers to the wrong number."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ath._version import SPEC_VERSION

SPEC_DIR = Path(__file__).resolve().parents[2] / "spec"
PARTS = ("athenaeum.md", "corpus.md", "ledger.md", "custody.md")


def _frontmatter_version(path: Path) -> int:
    head = path.read_text(encoding="utf-8").split("\n---", 2)[0]
    m = re.search(r"^version:\s*(\d+)\s*$", head, re.MULTILINE)
    assert m, f"{path.name}: no `version:` in frontmatter"
    return int(m.group(1))


@pytest.mark.skipif(not SPEC_DIR.is_dir(), reason="spec/ not present (installed wheel)")
def test_spec_version_matches_all_four_parts() -> None:
    versions = {p: _frontmatter_version(SPEC_DIR / p) for p in PARTS}
    assert set(versions.values()) == {SPEC_VERSION}, (
        f"ath._version.SPEC_VERSION={SPEC_VERSION} but spec frontmatter says {versions}"
    )
