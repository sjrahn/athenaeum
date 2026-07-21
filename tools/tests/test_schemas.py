"""Schema loader tests — including the four-way corpus-local↔packaged fallback."""

from __future__ import annotations

from pathlib import Path

import frontmatter
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
    # The subtype's bare `title` candidate layers into the merged schema — the artifact
    # opener's MIME names the format, so the candidate isn't namespaced.
    extended = schema.get("extended_fields") or {}
    assert "title" in extended, "subtype's title candidate layers in"


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
    assert "page_count" in extended  # from subtype
    assert "title" in extended  # subtype's bare title candidate
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
    extended = schema.get("extended_fields") or {}
    # The local subtype replaces the packaged one (which carried the bare `title`
    # candidate), and the packaged universal declares no fields — so no `title` survives:
    assert "title" not in extended
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
    # The local universal's field is present (the universal rung merges in, taken whole):
    assert "corpus_tag" in extended
    # The packaged subtype still merges in, carrying its bare `title` candidate (only the
    # universal rung was overridden):
    assert "title" in extended
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
    # The packaged subtype still merges in, carrying its bare `title` candidate:
    assert "title" in extended
    # Axis adds its field:
    assert "axis_tag" in extended
    # Subtype still in (from package):
    assert "page_count" in extended


# ---------- resolve_fingerprint precedence (CLI > origin overlay > mime > off) ---------- #


def _bare_post(origins=None):
    post = frontmatter.Post("")
    post.metadata["_origins"] = list(origins or [])
    return post


def _write_plain_mime(root, fingerprint=None):
    data = {"applies_to": {"content_types": ["text/plain"]}, "mode": "body-draft"}
    if fingerprint is not None:
        data["fingerprint"] = fingerprint
    _write_yaml(root / "schema" / "mime" / "text" / "text_plain.yaml", data)


def test_resolve_fingerprint_cli_override_wins(tmp_path):
    root = _make_corpus(tmp_path)
    _write_plain_mime(root, fingerprint=True)  # schema says ON …
    schemas.cache_clear()
    post = _bare_post()
    # … but the CLI override decides outright, either way.
    assert schemas.resolve_fingerprint(root, "text/plain", post, True) is True
    assert schemas.resolve_fingerprint(root, "text/plain", post, False) is False


def test_resolve_fingerprint_mime_default_and_off(tmp_path):
    root = _make_corpus(tmp_path)
    _write_plain_mime(root, fingerprint="simhash")
    _write_yaml(
        root / "schema" / "mime" / "text" / "text_markdown.yaml",
        {"applies_to": {"content_types": ["text/markdown"]}, "mode": "body-draft"},
    )
    schemas.cache_clear()
    post = _bare_post()
    # mime knob (an algorithm name) flows through; absent knob → off.
    assert schemas.resolve_fingerprint(root, "text/plain", post, None) == "simhash"
    assert schemas.resolve_fingerprint(root, "text/markdown", post, None) is False


def test_resolve_fingerprint_origin_overlay_overrides_mime(tmp_path):
    root = _make_corpus(tmp_path)
    _write_plain_mime(root, fingerprint=True)  # mime defaults ON …
    _write_yaml(
        root / "schema" / "origin" / "web" / "example.com.yaml",
        {
            "applies_to": {"host_pattern": "example.com", "include_subdomains": True},
            "fingerprint": False,
        },
    )
    schemas.cache_clear()
    # … but the record's qualified origin overlay (most-specific) turns it OFF.
    qualified = _bare_post([{"id": "example.com", "subtype": None, "fields": {}}])
    assert schemas.resolve_fingerprint(root, "text/plain", qualified, None) is False
    # An unqualified origin still matches by URI (the drafter path).
    by_uri = _bare_post(
        [{"id": None, "subtype": None, "fields": {"uri": ["https://example.com/x"]}}]
    )
    assert schemas.resolve_fingerprint(root, "text/plain", by_uri, None) is False
    # No origin match → mime wins.
    assert schemas.resolve_fingerprint(root, "text/plain", _bare_post(), None) is True


# ---------- best_origin_overlay_for_uris (origin-block host qualification, spec §7.2) ---------- #


def test_resolve_fingerprint_subtype_overlay_beats_parent(tmp_path):
    """The block's overlay LADDER (spec §4.3.1, §7.2): a subtype-qualified block's
    subtype overlay is more specific than its parent producer overlay — the subtype's
    explicit value wins even when the parent ALSO sets one."""
    root = _make_corpus(tmp_path)
    _write_plain_mime(root, fingerprint=True)  # mime defaults ON
    _write_yaml(root / "schema" / "origin" / "google-takeout.yaml", {"fingerprint": True})
    _write_yaml(
        root / "schema" / "origin" / "google-takeout" / "gmail.yaml", {"fingerprint": False}
    )
    schemas.cache_clear()
    qualified = _bare_post([{"id": "google-takeout", "subtype": "gmail", "fields": {}}])
    assert schemas.resolve_fingerprint(root, "text/plain", qualified, None) is False


def test_resolve_fingerprint_subtype_missing_falls_to_parent(tmp_path):
    """When the subtype overlay doesn't declare `fingerprint` at all (only the parent
    does), the ladder falls through to the parent — the subtype doesn't have to restate
    every knob."""
    root = _make_corpus(tmp_path)
    _write_plain_mime(root)  # no mime-level fingerprint at all
    _write_yaml(root / "schema" / "origin" / "google-takeout.yaml", {"fingerprint": "simhash"})
    _write_yaml(
        root / "schema" / "origin" / "google-takeout" / "gmail.yaml",
        {"description": "no fingerprint knob here"},
    )
    schemas.cache_clear()
    qualified = _bare_post([{"id": "google-takeout", "subtype": "gmail", "fields": {}}])
    assert schemas.resolve_fingerprint(root, "text/plain", qualified, None) == "simhash"


# ---------- origin overlay enumeration (compound producer/subtype ids, §4.3.1) --------- #


def test_load_origin_overlays_lists_compound_id_for_producer_namespace(tmp_path):
    """A nested dir OTHER than a scheme-family dir (`web/`, `otherwise/`) is a producer
    namespace — its files enumerate under the COMPOUND `<producer>/<subtype>` id."""
    root = _make_corpus(tmp_path)
    _write_yaml(root / "schema" / "origin" / "google-takeout.yaml", {"description": "producer"})
    _write_yaml(
        root / "schema" / "origin" / "google-takeout" / "gmail.yaml",
        {"description": "subtype"},
    )
    _write_yaml(root / "schema" / "origin" / "web" / "example.com.yaml", {"description": "host"})
    schemas.cache_clear()
    ids = {id_ for id_, _ in schemas.load_origin_overlays(root)}
    assert "google-takeout" in ids
    assert "google-takeout/gmail" in ids
    assert "example.com" in ids  # scheme-family dir → bare stem, not "web/example.com"


def test_best_origin_overlay_for_uris_match_and_miss(tmp_path):
    root = _make_corpus(tmp_path)
    _write_yaml(
        root / "schema" / "origin" / "web" / "instagram.com.yaml",
        {"applies_to": {"host_pattern": "instagram.com", "include_subdomains": True}},
    )
    schemas.cache_clear()
    assert (
        schemas.best_origin_overlay_for_uris(root, ["https://www.instagram.com/p/x/"])
        == "instagram.com"
    )
    assert schemas.best_origin_overlay_for_uris(root, ["https://example.com"]) is None
    assert schemas.best_origin_overlay_for_uris(root, []) is None


def test_best_origin_overlay_for_uris_include_subdomains(tmp_path):
    root = _make_corpus(tmp_path)
    _write_yaml(
        root / "schema" / "origin" / "web" / "video.example.yaml",
        {"applies_to": {"host_pattern": "video.example", "include_subdomains": True}},
    )
    schemas.cache_clear()
    # A deep subdomain only matches because include_subdomains is set.
    assert (
        schemas.best_origin_overlay_for_uris(root, ["https://cdn.video.example/v/1"])
        == "video.example"
    )
    _write_yaml(
        root / "schema" / "origin" / "web" / "strict.example.yaml",
        {"applies_to": {"host_pattern": "strict.example"}},  # include_subdomains defaults False
    )
    schemas.cache_clear()
    assert schemas.best_origin_overlay_for_uris(root, ["https://cdn.strict.example/x"]) is None


def test_best_origin_overlay_for_uris_specificity_beats_catchall(tmp_path):
    root = _make_corpus(tmp_path)
    _write_yaml(
        root / "schema" / "origin" / "web" / "star.yaml",
        {"applies_to": {"host_pattern": "*"}},
    )
    _write_yaml(
        root / "schema" / "origin" / "web" / "instagram.com.yaml",
        {"applies_to": {"host_pattern": "instagram.com"}},
    )
    schemas.cache_clear()
    # The specific host overlay outranks the catch-all for a matching uri …
    assert (
        schemas.best_origin_overlay_for_uris(root, ["https://instagram.com/x"])
        == "instagram.com"
    )
    # … but the catch-all still wins when nothing more specific matches.
    assert schemas.best_origin_overlay_for_uris(root, ["https://other.com"]) == "star"


def test_best_origin_overlay_for_uris_scheme_cue(tmp_path):
    root = _make_corpus(tmp_path)
    _write_yaml(
        root / "schema" / "origin" / "otherwise" / "imessage-live.yaml",
        {"applies_to": {"scheme": "imessage"}},
    )
    schemas.cache_clear()
    assert (
        schemas.best_origin_overlay_for_uris(root, ["imessage://chat/123"])
        == "imessage-live"
    )
    assert schemas.best_origin_overlay_for_uris(root, ["https://example.com"]) is None
