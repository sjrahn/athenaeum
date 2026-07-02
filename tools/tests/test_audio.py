"""Audio mime schema + drafter (#12) and the resolver's schema-declared working_kind (#13)."""

from __future__ import annotations

from pathlib import Path

from corpus import draft, resolver, schemas


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def test_audio_mime_schema_resolves(tmp_path):
    """audio/mpeg now has a bundled mime schema, so ingest no longer hard-exits."""
    root = _make_corpus(tmp_path)
    schema = schemas.load_mime_schema(root, "audio/mpeg")
    assert schema is not None
    assert schema.get("artifact_kind") == "self_contained"  # required by ingest
    assert schema.get("working_kind") == "audio"
    assert schemas.mime_schema_id_for(root, "audio/mpeg") == "audio/audio_mpeg"
    # WAV too (pairs with the RIFF/WAVE mime-detect fix).
    assert schemas.mime_schema_id_for(root, "audio/x-wav") == "audio/audio_x-wav"


def test_audio_drafters_registered():
    assert "audio/audio_mpeg" in draft.REGISTRY
    assert "audio/audio_x-wav" in draft.REGISTRY


def test_resolver_working_kind_schema_first(tmp_path):
    """Bundled mime schemas declare working_kind; the resolver reads it schema-first."""
    root = _make_corpus(tmp_path)
    assert resolver._working_kind_for(root, "audio/mpeg") == "audio"
    assert resolver._working_kind_for(root, "application/pdf") == "pdf"
    assert resolver._working_kind_for(root, "text/html") == "html"
    assert resolver._working_kind_for(root, "image/png") == "image"
    assert resolver._working_kind_for(root, "video/mp4") == "video"
    # A media type with neither a schema nor a table entry → None (caller raises).
    assert resolver._working_kind_for(root, "application/x-nope") is None


def test_resolver_working_kind_generalizes_to_new_media_type(tmp_path):
    """A corpus-supplied mime schema with working_kind makes a NEW media type resolvable
    without editing the resolver's built-in table (#13 — the altitude fix)."""
    root = _make_corpus(tmp_path)
    custom_dir = root / "schema" / "mime" / "application"
    custom_dir.mkdir(parents=True)
    (custom_dir / "application_x-custom.yaml").write_text(
        "applies_to:\n  content_types:\n  - application/x-custom\nworking_kind: image\n",
        encoding="utf-8",
    )
    schemas._sources.cache_clear()
    # Not in _INITIAL_KIND_FOR_MIME, but the schema declares working_kind → resolvable.
    assert "application/x-custom" not in resolver._INITIAL_KIND_FOR_MIME
    assert resolver._working_kind_for(root, "application/x-custom") == "image"
