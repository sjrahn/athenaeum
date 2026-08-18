"""Reference-dataset adapter derivation (spec/corpus.md §7.1, spec/ledger.md
§6.5, custody amendment v21): `refdata.resolve_adapter_name` derives a
dataset's format adapter from its latest snapshot's mirror record's mime
overlay `ref_adapter` when the manifest declares none, an explicit
`reference.adapter` remaining the override. No optional adapter dependency
needed here — this exercises only mime-schema + record lookup, never opens
an archive.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from ath.manifest import Reference, Snapshot
from corpus import paths, records
from refdata import resolve_adapter_name
from refdata.errors import AdapterUnavailable

_MIME = "application/x-testmirror"
_ARTIFACT = "e" * 64


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _write_mime_schema(root: Path, *, ref_adapter: str | None) -> None:
    """A minimal mime subtype schema under a throwaway 'testfmt' axis,
    claiming `_MIME` — matches `_iter_mime_subtype_paths`' shape
    (`mime/<axis>/<axis>_<subtype>.yaml`, distinct from the axis-common
    `mime/<axis>/<axis>.yaml`)."""
    d = root / "schema" / "mime" / "testfmt"
    d.mkdir(parents=True)
    body = f"applies_to:\n  content_types: [{_MIME}]\n"
    if ref_adapter is not None:
        body += f"ref_adapter: {ref_adapter}\n"
    (d / "testfmt_mirror.yaml").write_text(body, encoding="utf-8")


def _write_record(root: Path, *, mime: str | None) -> None:
    post = frontmatter.Post(
        content="",
        **records.stub_frontmatter(record_id=_ARTIFACT, touch_id="corpus.ingest@0.1.0"),
    )
    if mime is not None:
        records.set_artifact_block(post, mime=mime, fields={})
    records.dump(post, paths.record_path(root, _ARTIFACT))


def _ref(*, adapter: str | None = None, latest: str = "t") -> Reference:
    return Reference(
        dataset="testds", description="test", adapter=adapter, latest=latest,
        snapshots={"t": Snapshot(artifact=_ARTIFACT)},
    )


def test_explicit_adapter_wins_no_corpus_needed() -> None:
    assert resolve_adapter_name(_ref(adapter="zim"), corpora_roots=()) == "zim"


def test_derives_from_mirror_records_mime_overlay(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    _write_mime_schema(root, ref_adapter="osm-pbf")
    _write_record(root, mime=_MIME)
    assert resolve_adapter_name(_ref(), corpora_roots=(root,)) == "osm-pbf"


def test_explicit_adapter_wins_even_with_a_derivable_overlay(tmp_path: Path) -> None:
    """An explicit manifest `adapter:` is the override — proven here by a
    corpus that COULD derive `osm-pbf` but the reference asks for `zim`
    instead, and `zim` is what comes back."""
    root = _corpus(tmp_path)
    _write_mime_schema(root, ref_adapter="osm-pbf")
    _write_record(root, mime=_MIME)
    assert resolve_adapter_name(_ref(adapter="zim"), corpora_roots=(root,)) == "zim"


def test_no_record_found_raises_named_and_notes_override() -> None:
    with pytest.raises(AdapterUnavailable, match="no mirror record"):
        resolve_adapter_name(_ref(), corpora_roots=())


def test_record_with_no_mime_raises_named(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    _write_record(root, mime=None)
    with pytest.raises(AdapterUnavailable, match="no artifact mime"):
        resolve_adapter_name(_ref(), corpora_roots=(root,))


def test_mime_matching_no_schema_raises_named(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    _write_record(root, mime="application/x-unregistered-anywhere")
    with pytest.raises(AdapterUnavailable, match="matches no mime schema"):
        resolve_adapter_name(_ref(), corpora_roots=(root,))


def test_schema_without_ref_adapter_raises_named(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    _write_mime_schema(root, ref_adapter=None)
    _write_record(root, mime=_MIME)
    with pytest.raises(AdapterUnavailable, match="declares no ref_adapter"):
        resolve_adapter_name(_ref(), corpora_roots=(root,))


def test_unregistered_latest_tag_raises_named() -> None:
    ref = Reference(
        dataset="testds", description="test", adapter=None, latest="nope",
        snapshots={"t": Snapshot(artifact=_ARTIFACT)},
    )
    with pytest.raises(AdapterUnavailable, match="names no registered snapshot"):
        resolve_adapter_name(ref, corpora_roots=())


@pytest.mark.parametrize(
    "setup",
    ["no-record", "no-mime", "no-schema", "no-ref-adapter"],
)
def test_every_failure_mode_names_the_explicit_override(
    tmp_path: Path, setup: str
) -> None:
    root = _corpus(tmp_path)
    corpora_roots: tuple[Path, ...] = ()
    if setup == "no-record":
        corpora_roots = ()
    elif setup == "no-mime":
        _write_record(root, mime=None)
        corpora_roots = (root,)
    elif setup == "no-schema":
        _write_record(root, mime="application/x-unregistered-anywhere")
        corpora_roots = (root,)
    elif setup == "no-ref-adapter":
        _write_mime_schema(root, ref_adapter=None)
        _write_record(root, mime=_MIME)
        corpora_roots = (root,)
    with pytest.raises(AdapterUnavailable, match="explicit manifest adapter"):
        resolve_adapter_name(_ref(), corpora_roots=corpora_roots)


def test_derivation_keys_to_latest_snapshot_not_requested_tag(tmp_path: Path) -> None:
    """Derivation is per-dataset, off `reference.latest` — a caller
    resolving a PINNED older tag still gets the adapter derived from the
    LATEST snapshot's record, never the pinned one's."""
    root = _corpus(tmp_path)
    _write_mime_schema(root, ref_adapter="osm-pbf")
    _write_record(root, mime=_MIME)
    ref = Reference(
        dataset="testds", description="test", adapter=None, latest="t",
        snapshots={
            "t": Snapshot(artifact=_ARTIFACT),
            "older": Snapshot(artifact="f" * 64),  # no record for this one at all
        },
    )
    assert resolve_adapter_name(ref, corpora_roots=(root,)) == "osm-pbf"
