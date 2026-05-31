"""Schema loader tests — including the four-way corpus-local↔packaged fallback."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from corpus import schemas


def _make_corpus(tmp_path: Path) -> Path:
    """Create a minimal corpus tree (records/ + schema/)."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _write_yaml(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


# ---------- mime loader against the packaged universals ---------- #


def test_load_mime_schema_resolves_pdf_from_packaged_defaults(tmp_path):
    """A vendor-nothing corpus resolves application/pdf entirely from the package."""
    root = _make_corpus(tmp_path)
    schemas._sources.cache_clear()
    schema = schemas.load_mime_schema(root, "application/pdf")
    assert schema is not None
    assert "applies_to" in schema
    assert "application/pdf" in schema["applies_to"]["content_types"]
    assert schema.get("artifact_kind") == "self_contained"
    # Reconciliation #7: media_type_id was stripped from bundled mime schemas.
    assert "media_type_id" not in schema
    # Universal mime.yaml's `title` field merged in under the subtype:
    extended = schema.get("extended_fields") or {}
    assert "title" in extended, "universal mime.yaml `title` field must layer in"


def test_mime_schema_id_for_returns_axis_subtype_form(tmp_path):
    root = _make_corpus(tmp_path)
    schemas._sources.cache_clear()
    assert schemas.mime_schema_id_for(root, "application/pdf") == "application/application_pdf"
    assert schemas.mime_schema_id_for(root, "text/html") == "text/text_html"
    assert schemas.mime_schema_id_for(root, "application/x-not-a-real-mime") is None


# ---------- atomic-overlay loader ---------- #


def test_atomic_overlay_resolves_from_packaged_defaults(tmp_path):
    root = _make_corpus(tmp_path)
    schemas._sources.cache_clear()
    # Universal text overlay
    text_universal = schemas.load_atomic_overlay(root, "text")
    assert text_universal is not None
    # A subtype overlay (text/data-table) layered over the universal text
    dt = schemas.load_atomic_overlay(root, "text", "text/data-table")
    assert dt is not None
    # Listing atomic overlays from the bundled set returns slash-form ids
    ids = schemas.list_atomic_overlays(root, "text")
    assert "text/data-table" in ids
    assert "text/transcript" in ids


# ---------- issue loader (reconciliation #4 — universal merges under per-id) ---------- #


def test_load_issue_schema_merges_universal_under_per_id(tmp_path):
    root = _make_corpus(tmp_path)
    schemas._sources.cache_clear()
    fm = schemas.load_issue_schema(root, "format-loss")
    assert fm is not None
    # `format-loss.yaml` carries description only; the universal contributes the
    # severity/resolution/detector field declarations.
    extended = fm.get("extended_fields") or {}
    assert "severity" in extended
    assert "resolution" in extended
    assert "detector" in extended


def test_load_issue_schema_returns_universal_when_id_absent(tmp_path):
    """When no per-id overlay exists, the loader returns the universal alone."""
    root = _make_corpus(tmp_path)
    schemas._sources.cache_clear()
    fm = schemas.load_issue_schema(root, "definitely-not-an-issue-id")
    # Per-id missing but universal present → universal returned.
    assert fm is not None
    assert "severity" in (fm.get("extended_fields") or {})


def test_list_issue_ids_finds_bundled_issues(tmp_path):
    root = _make_corpus(tmp_path)
    schemas._sources.cache_clear()
    ids = schemas.list_issue_ids(root)
    assert "format-loss" in ids
    assert "encoding-corruption" in ids


# ---------- the FOUR-WAY schema-fallback (P1 keystone exit check) ---------- #


def test_fallback_a_all_packaged(tmp_path):
    """(a) No local overrides — every rung resolves from the package."""
    root = _make_corpus(tmp_path)
    schemas._sources.cache_clear()
    schema = schemas.load_mime_schema(root, "application/pdf")
    assert schema is not None
    extended = schema.get("extended_fields") or {}
    assert "title" in extended  # from universal
    assert "page_count" in extended  # from subtype
    assert schema.get("artifact_kind") == "self_contained"


def test_fallback_b_corpus_overrides_subtype_only(tmp_path):
    """(b) Corpus overrides only the subtype; universal+axis still from the package.

    The corpus's local subtype REPLACES the packaged subtype (whole-file wins per
    rung), then is deep-merged on top of the packaged universal.
    """
    root = _make_corpus(tmp_path)
    local_pdf = root / "schema" / "mime" / "application" / "application_pdf.yaml"
    _write_yaml(
        local_pdf,
        {
            "description": "LOCAL OVERRIDE: redefined PDF subtype for testing.",
            "applies_to": {"content_types": ["application/pdf"]},
            "mode": "body-draft",
            "artifact_kind": "decomposable",  # changed from self_contained
            "extended_fields": {
                "local_only_field": {"type": "string", "required": False},
            },
        },
    )
    schemas._sources.cache_clear()
    schema = schemas.load_mime_schema(root, "application/pdf")
    assert schema is not None
    # The local subtype's artifact_kind wins:
    assert schema.get("artifact_kind") == "decomposable"
    # The universal's `title` field is still present (deep-merged from package):
    extended = schema.get("extended_fields") or {}
    assert "title" in extended, "universal title must still merge in"
    # The local field is present:
    assert "local_only_field" in extended
    # The packaged subtype's page_count is GONE — whole-file wins at the subtype rung:
    assert "page_count" not in extended, (
        "local subtype replaces packaged subtype entirely (whole-file at each rung)"
    )


def test_fallback_c_corpus_overrides_universal_only(tmp_path):
    """(c) Corpus overrides only the universal `mime/mime.yaml`."""
    root = _make_corpus(tmp_path)
    local_universal = root / "schema" / "mime" / "mime.yaml"
    _write_yaml(
        local_universal,
        {
            "description": "LOCAL universal — adds a corpus-wide field.",
            "extended_fields": {
                "corpus_tag": {"type": "string", "required": False},
            },
        },
    )
    schemas._sources.cache_clear()
    schema = schemas.load_mime_schema(root, "application/pdf")
    assert schema is not None
    extended = schema.get("extended_fields") or {}
    # The local universal's field is present (universal merges in)
    assert "corpus_tag" in extended
    # The packaged universal's `title` is GONE (whole-file wins at the universal rung)
    assert "title" not in extended, (
        "local universal replaces packaged universal entirely (whole-file at each rung)"
    )
    # The packaged subtype's page_count is still present (subtype came from package):
    assert "page_count" in extended


def test_fallback_d_corpus_overrides_mid_rung_axis(tmp_path):
    """(d) Corpus overrides the axis-common rung (`mime/application/application.yaml`)."""
    root = _make_corpus(tmp_path)
    axis_common = root / "schema" / "mime" / "application" / "application.yaml"
    _write_yaml(
        axis_common,
        {
            "description": "LOCAL axis common for application/*",
            "extended_fields": {
                "axis_tag": {"type": "string", "required": False},
            },
        },
    )
    schemas._sources.cache_clear()
    schema = schemas.load_mime_schema(root, "application/pdf")
    assert schema is not None
    extended = schema.get("extended_fields") or {}
    # Universal still in (from package):
    assert "title" in extended
    # Axis adds its field:
    assert "axis_tag" in extended
    # Subtype still in (from package):
    assert "page_count" in extended


# ---------- the per-corpus seam: composite is corpus-local only ---------- #


def test_composite_namespace_is_corpus_local(tmp_path):
    """A corpus declares its own composite/<ns>/ — not bundled."""
    root = _make_corpus(tmp_path)
    schemas._sources.cache_clear()
    # No composite namespaces by default in a vendor-nothing corpus.
    assert schemas.list_classifications(root) == []

    # Add a local composite namespace.
    ns_dir = root / "schema" / "composite" / "document"
    _write_yaml(
        ns_dir / "document.yaml",
        {
            "kind": "interpretive",
            "description": "Generic document classification.",
            "applies_at": ["record"],
            "extended_fields": {},
        },
    )
    schemas._sources.cache_clear()
    assert schemas.list_classifications(root) == ["document"]
    loaded = schemas.load_classification_schema(root, "document")
    assert loaded is not None
    assert loaded["kind"] == "interpretive"


# ---------- origin overlays: universal packaged, per-host local ---------- #


def test_origin_overlays_are_corpus_local(tmp_path):
    """Origin is a per-corpus concern (sources of retrieval are corpus-specific).
    Neither the universal `origin/origin.yaml` nor per-host overlays ship in the
    package; both live corpus-local. The scaffold writes the universal at
    `corpus init` time (see test_scaffold)."""
    root = _make_corpus(tmp_path)
    # Vendor a universal origin overlay (what `corpus init` writes for real corpora).
    _write_yaml(
        root / "schema" / "origin" / "origin.yaml",
        {
            "description": "Universal origin fields.",
            "extended_fields": {
                "uri": {"type": "string_or_list", "required": True, "semantic_type": "uri"},
                "snapshot": {"type": "string", "required": True, "semantic_type": "timestamp"},
            },
        },
    )
    # Define a per-host overlay locally.
    _write_yaml(
        root / "schema" / "origin" / "example.com.yaml",
        {
            "kind": "interpretive",
            "description": "Example.com origin.",
            "applies_to": {"host_pattern": "example.com", "include_subdomains": True},
            "extended_fields": {
                "publisher_section": {"type": "string", "required": False},
            },
        },
    )
    schemas._sources.cache_clear()
    overlay = schemas.load_origin_overlay_by_id(root, "example.com")
    assert overlay is not None
    extended = overlay.get("extended_fields") or {}
    # Local per-host fields present:
    assert "publisher_section" in extended
    # Local universal uri/snapshot fields layer in:
    assert "uri" in extended
    assert "snapshot" in extended
    # Matching by URI uses the host pattern:
    matched = schemas.origin_overlays_for_uris(root, ["https://www.example.com/page"])
    assert any(id_ == "example.com" for id_, _ in matched)


def test_origin_universal_does_not_ship_in_package(tmp_path):
    """Sanity: the packaged source has no origin/origin.yaml — only corpora supply it."""
    root = _make_corpus(tmp_path)
    schemas._sources.cache_clear()
    sources = schemas._sources(root)
    packaged = sources[1]  # corpus-local, package
    assert not packaged.exists("origin/origin.yaml"), (
        "package must not ship origin/origin.yaml — origin is a per-corpus concern"
    )
