"""Integration check against the REAL BFO-2020 / CommonCoreOntologies
release archives (spec/ledger.md §15.2) — the same files the synthetic
`test_refdata_bfo.py`/`test_refdata_cco.py`/`test_refdata_spine.py` fixtures
mimic the shape of. These are large, gitignored research artifacts, not
tracked by the repo — skip cleanly (never fail) when they aren't present,
e.g. in CI or a fresh checkout without the `research/` directory populated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ath.manifest import Reference, Snapshot
from refdata.spine import resolve_term

_RESEARCH = Path(__file__).resolve().parents[2] / "research"
_BFO_ZIP = _RESEARCH / "BFO-2020-master.zip"
_CCO_ZIP = _RESEARCH / "CommonCoreOntologies-v2.2.zip"

pytestmark = pytest.mark.skipif(
    not (_BFO_ZIP.is_file() and _CCO_ZIP.is_file()),
    reason="real spine release archives not present under research/ (gitignored, dev-machine-only)",
)


def _real_ref(dataset: str, adapter: str, zip_path: Path) -> Reference:
    return Reference(
        dataset=dataset, description="real release archive", adapter=adapter, spine=True,
        latest="t", snapshots={"t": Snapshot(artifact="a" * 64, path=str(zip_path))},
    )


def test_cco_resolves_ont00001017_to_agent_with_zero_ambiguity() -> None:
    ref = _real_ref("cco", "cco-release", _CCO_ZIP)
    term = resolve_term("cco:ont00001017", [ref])
    assert term.native_id == "ont00001017"
    assert term.label == "Agent"
    assert term.deprecated is False


def test_cco_resolves_agent_by_label_too() -> None:
    ref = _real_ref("cco", "cco-release", _CCO_ZIP)
    term = resolve_term("cco:Agent", [ref])
    assert term.native_id == "ont00001017"


def test_bfo_resolves_a_known_label() -> None:
    ref = _real_ref("bfo", "bfo-2020", _BFO_ZIP)
    term = resolve_term("bfo:site", [ref])
    assert term.native_id == "BFO_0000029"
    assert term.deprecated is False


def test_bfo_resolves_the_same_term_by_native_id() -> None:
    ref = _real_ref("bfo", "bfo-2020", _BFO_ZIP)
    term = resolve_term("bfo:BFO_0000029", [ref])
    assert term.label == "site"
