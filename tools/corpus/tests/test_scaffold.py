"""Scaffold tests + the 'vendor-nothing' invariant (universal schemas come from package)."""

from __future__ import annotations

from corpus import paths, scaffold, schemas


def test_scaffold_creates_minimal_seam(tmp_path):
    target = tmp_path / "my-corpus"
    out = scaffold.scaffold(target, namespace="document")
    assert out == target.resolve()
    assert (target / "records").is_dir()
    # Per-corpus concerns: origin universal + composite namespace.
    assert (target / "schema" / "origin" / "origin.yaml").is_file()
    # Origin overlays are namespaced by URI scheme family: the example web-host
    # overlay seeds under origin/web/, NOT flat at origin/.
    assert (target / "schema" / "origin" / "web" / "example.com.yaml").is_file()
    assert not (target / "schema" / "origin" / "example.com.yaml").exists()
    assert (target / "schema" / "composite" / "document" / "document.yaml").is_file()
    assert (target / ".gitignore").is_file()
    assert (target / "README.md").is_file()
    # NOT created: mime and atom universals come from the package.
    assert not (target / "schema" / "mime").exists()
    assert not (target / "schema" / "atom").exists()


def test_scaffolded_corpus_is_discoverable_by_find_corpus_root(tmp_path):
    target = tmp_path / "discover-me"
    scaffold.scaffold(target, namespace="document")
    nested = target / "records"  # any dir under the corpus
    nested.mkdir(exist_ok=True)
    assert paths.find_corpus_root(nested) == target.resolve()


def test_vendor_nothing_corpus_can_resolve_pdf_via_packaged_schemas(tmp_path):
    """A corpus that vendors no mime/atom schemas STILL resolves application/pdf —
    proves the package-fallback works end-to-end from a scaffolded corpus."""
    target = tmp_path / "vendor-nothing"
    scaffold.scaffold(target, namespace="document")
    schemas._sources.cache_clear()
    pdf = schemas.load_mime_schema(target, "application/pdf")
    assert pdf is not None
    assert pdf.get("artifact_kind") == "self_contained"
    # The subtype's bare `title` candidate resolves from the packaged schemas:
    extended = pdf.get("extended_fields") or {}
    assert "title" in extended
    # Atomic overlays bundled with the package are also visible:
    overlays = schemas.list_atomic_overlays(target, "text")
    assert "text/data-table" in overlays
    # The corpus's own composite namespace is registered:
    assert schemas.list_classifications(target) == ["document"]


def test_scaffold_refuses_to_overwrite_populated_dirs(tmp_path):
    target = tmp_path / "preexisting"
    (target / "records" / "ab").mkdir(parents=True)
    (target / "records" / "ab" / "x.md").write_text("--- ---", encoding="utf-8")
    import pytest

    with pytest.raises(FileExistsError):
        scaffold.scaffold(target, namespace="document")
