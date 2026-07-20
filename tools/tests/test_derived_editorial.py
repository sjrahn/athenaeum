"""Derived-editorial resolution (spec §4.2.3, ATH-CORPUS 3.2) — the shared
`records.derived_editorial_field` / `derived_editorial` implementation.

Builds custom role-marked mime/origin/form overlays to exercise the full precedence chain
end to end in isolation, independent of any particular corpus's real schemas. See
`test_sidecar.py` for coverage against the PACKAGED schemas' real `role:` marks (the
§12.21 step 2 role-marking sweep) — `text/html`'s artifact-layer title, and a qualified
origin's `ytdlp_title` (plus the origin-qualification gap that surfaces alongside it, now
that the transitional `_legacy_title_fallback` is retired).
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import yaml

from corpus import paths, records, schemas, segments

_MIME = "application/x-test-editorial"

_MIME_SCHEMA = {
    "applies_to": {"content_types": [_MIME]},
    "extended_fields": {
        "subject": {"type": "string", "role": "title"},
        "blurb": {"type": "string", "role": "description"},
        "irrelevant": {"type": "string", "role": "some-unknown-role"},
    },
}

_ORIGIN_SCHEMA = {
    "applies_to": {"schemes": ["testsrc"]},
    "kind": "interpretive",
    "extended_fields": {
        "headline": {"type": "string", "role": "title"},
        "alt_headline": {"type": "string", "role": "title"},
        "blurb2": {"type": "string", "role": "description"},
    },
}

_FORM_SCHEMA = {
    "kind": "form",
    "extended_fields": {
        "subtitle": {"type": "string", "role": "title"},
    },
}


def _write_yaml(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    _write_yaml(
        root / "schema" / "mime" / "application" / "application_x-test-editorial.yaml",
        _MIME_SCHEMA,
    )
    _write_yaml(root / "schema" / "origin" / "testsrc.yaml", _ORIGIN_SCHEMA)
    _write_yaml(root / "schema" / "form" / "testform.yaml", _FORM_SCHEMA)
    schemas.cache_clear()
    return root


def _base_post(rid: str = "a" * 64) -> frontmatter.Post:
    return frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="t@0.1.0")
    )


# ---------- precedence: artifact < origin < form < override ---------- #


def test_artifact_layer_candidate(tmp_path):
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(
        post, mime=_MIME, fields={"subject": "Artifact Subject", "blurb": "Artifact blurb"}
    )
    # A bare (unqualified) origin block matches no overlay — contributes nothing (§7.2).
    records.append_origin_block(post, uri="testsrc://x", snapshot="2026-01-01T00:00:00Z")

    assert records.derived_editorial(post, root) == ("Artifact Subject", "Artifact blurb")
    fields = records.derived_editorial_fields(post, root)
    assert fields["title"].layer == "artifact"
    assert fields["description"].layer == "artifact"


def test_origin_outranks_artifact(tmp_path):
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(
        post, mime=_MIME, fields={"subject": "Artifact Subject", "blurb": "Artifact blurb"}
    )
    records.append_origin_block(
        post,
        uri="testsrc://x",
        snapshot="2026-01-01T00:00:00Z",
        schema_id="testsrc",
        fields={"headline": "Origin Headline"},
    )
    fields = records.derived_editorial_fields(post, root)
    # origin wins the title (its own marked `headline` is non-empty); description falls
    # through to artifact since the origin's description candidate (`blurb2`) is absent.
    assert fields["title"] == records.EditorialField("Origin Headline", "origin")
    assert fields["description"] == records.EditorialField("Artifact blurb", "artifact")


def test_latest_origin_block_wins(tmp_path):
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={})
    records.append_origin_block(
        post,
        uri="testsrc://x",
        snapshot="2026-01-01T00:00:00Z",
        schema_id="testsrc",
        fields={"headline": "First Capture"},
    )
    records.append_origin_block(
        post,
        uri="testsrc://x",
        snapshot="2026-02-01T00:00:00Z",
        schema_id="testsrc",
        fields={"headline": "Re-capture"},
    )
    title = records.derived_editorial_field(post, root, "title")
    assert title.value == "Re-capture" and title.layer == "origin"


def test_within_block_first_non_empty_by_declaration_order(tmp_path):
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={})
    # `headline` is declared before `alt_headline` in the overlay — only `alt_headline`
    # set → it wins (the first declared candidate, `headline`, is absent).
    records.append_origin_block(
        post,
        uri="testsrc://x",
        snapshot="2026-01-01T00:00:00Z",
        schema_id="testsrc",
        fields={"alt_headline": "Alt Wins"},
    )
    assert records.derived_editorial_field(post, root, "title").value == "Alt Wins"
    # Both set → the FIRST declared field (`headline`) wins, not `alt_headline`.
    records.merge_origin_fields(post, {"headline": "Headline Wins"})
    assert records.derived_editorial_field(post, root, "title").value == "Headline Wins"


def test_form_outranks_origin_and_artifact(tmp_path):
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={"subject": "Artifact Subject"})
    records.append_origin_block(
        post,
        uri="testsrc://x",
        snapshot="2026-01-01T00:00:00Z",
        schema_id="testsrc",
        fields={"headline": "Origin Headline"},
    )
    seg = segments.Segment(atom="text", address="turn=1", body="hi")
    post.content = segments.emit(
        [segments.Section(form="testform", segments=[seg], extra={"title": "Whole Record Title"})]
    )
    title = records.derived_editorial_field(post, root, "title")
    assert title.value == "Whole Record Title" and title.layer == "form"


def test_form_implicit_title_beats_explicit_marked_field(tmp_path):
    """The universal `title:` header field is checked before any additional
    schema-declared `role: title` field on the same form (spec §4.2.3)."""
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={})
    seg = segments.Segment(atom="text", address="turn=1", body="hi")
    post.content = segments.emit(
        [
            segments.Section(
                form="testform",
                segments=[seg],
                extra={"title": "Implicit Title", "subtitle": "Explicit Marked Title"},
            )
        ]
    )
    assert records.derived_editorial_field(post, root, "title").value == "Implicit Title"


def test_form_falls_through_to_marked_field_when_implicit_empty(tmp_path):
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={"subject": "Artifact Subject"})
    seg = segments.Segment(atom="text", address="turn=1", body="hi")
    post.content = segments.emit(
        [segments.Section(form="testform", segments=[seg], extra={"subtitle": "Marked Subtitle"})]
    )
    # No implicit `title:` header field → falls to the form's explicitly marked
    # `subtitle` — which still outranks origin/artifact (form is the strongest of the
    # three schema-driven layers).
    assert records.derived_editorial_field(post, root, "title").value == "Marked Subtitle"


def test_span_scope_section_does_not_contribute_at_record_scope(tmp_path):
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={"subject": "Artifact Subject"})
    seg = segments.Segment(atom="text", address="page=1", body="hi")
    post.content = segments.emit(
        [
            segments.Section(
                address="pages=1-1",
                form="testform",
                segments=[seg],
                extra={"title": "Span Title"},
            )
        ]
    )
    # A span-scope section (carries `address`) describes its span, never the record — the
    # record-level title falls through past the form layer to the artifact layer.
    title = records.derived_editorial_field(post, root, "title")
    assert title.value == "Artifact Subject" and title.layer == "artifact"


def test_override_wins_over_every_layer(tmp_path):
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={"subject": "Artifact Subject"})
    records.append_origin_block(
        post,
        uri="testsrc://x",
        snapshot="2026-01-01T00:00:00Z",
        schema_id="testsrc",
        fields={"headline": "Origin Headline"},
    )
    seg = segments.Segment(atom="text", address="turn=1", body="hi")
    post.content = segments.emit(
        [segments.Section(form="testform", segments=[seg], extra={"title": "Form Title"})]
    )
    post.metadata["title"] = "Deliberate Override"

    title = records.derived_editorial_field(post, root, "title")
    assert title.value == "Deliberate Override" and title.layer == "override"
    # `include_override=False` resolves beneath it — what the override is redundant
    # against (the `editorial-override-redundant` lint rule, §12.21 step 1).
    beneath = records.derived_editorial_field(post, root, "title", include_override=False)
    assert beneath.value == "Form Title" and beneath.layer == "form"


def test_empty_or_absent_candidate_falls_through(tmp_path):
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={})
    title = records.derived_editorial_field(post, root, "title")
    assert title.value == "" and title.layer is None


def test_unknown_role_ignored(tmp_path):
    """A declared `role:` value that is neither `title` nor `description` is tolerated —
    parsed without error and never surfaces as a candidate (spec §4.2.3)."""
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={"irrelevant": "Should Never Surface"})
    title = records.derived_editorial_field(post, root, "title")
    desc = records.derived_editorial_field(post, root, "description")
    assert title.value == "" and title.layer is None
    assert desc.value == "" and desc.layer is None


# ---------- emitter: drop empty placeholders, preserve non-empty overrides ---------- #


def test_emitter_drops_empty_override_preserves_non_empty(tmp_path):
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={})
    records.append_origin_block(post, uri="testsrc://x", snapshot="2026-01-01T00:00:00Z")
    post.metadata["title"] = ""
    post.metadata["description"] = "A deliberate override."

    p = paths.record_path(root, post.metadata["id"])
    records.dump(post, p)
    raw = p.read_text("utf-8")
    fm_text = raw.split("---", 2)[1]
    assert "title:" not in fm_text  # empty-string placeholder dropped
    assert "description: A deliberate override." in fm_text  # non-empty preserved verbatim

    reloaded = records.load(p)
    assert "title" not in reloaded.metadata
    assert reloaded.metadata["description"] == "A deliberate override."


def test_birth_frontmatter_has_no_editorial_keys():
    """*(spec §12.3.4)* A freshly-ingested record's frontmatter carries no `title`/
    `description` at all — not even empty placeholders."""
    fm = records.stub_frontmatter(record_id="b" * 64, touch_id="corpus.ingest@0.1.0")
    assert "title" not in fm and "description" not in fm


# ---------- packaged schema: form/conversation.yaml's `participants` mark ---------- #
# (the untitled-604 close — a mechanically-shaped FB/IG/etc. conversation carries no
# authored title, but its own codebook already names who is in it; see corpus.md §4.2.3.)


def test_conversation_form_falls_through_to_participants_when_untitled(tmp_path):
    """The PACKAGED `form/conversation.yaml` marks `participants` `role: title` — the
    mechanical fallback for a shaped-but-not-yet-vouched conversation (no corpus-local
    schema needed; resolves against the installed package like `text/html`'s artifact
    title in test_sidecar.py)."""
    post = _base_post()
    records.set_artifact_block(post, mime="application/json", fields={})
    seg = segments.Segment(atom="text", address="turn=1", body="hi")
    post.content = segments.emit(
        [
            segments.Section(
                form="conversation",
                segments=[seg],
                extra={"participants": ["Rob Hehr", "Steven Rahn", "Marco Preißer"]},
            )
        ]
    )
    title = records.derived_editorial_field(post, tmp_path, "title")
    assert title.value == "Rob Hehr, Steven Rahn, Marco Preißer"
    assert title.layer == "form"


def test_conversation_form_implicit_title_still_beats_participants(tmp_path):
    """An authored whole-record `title:` (the interpretive vouch, once a normalize pass
    writes one) still wins over the mechanical `participants` fallback — same implicit-
    before-explicit rule as any other form (§4.2.3)."""
    post = _base_post()
    records.set_artifact_block(post, mime="application/json", fields={})
    seg = segments.Segment(atom="text", address="turn=1", body="hi")
    post.content = segments.emit(
        [
            segments.Section(
                form="conversation",
                segments=[seg],
                extra={
                    "title": "Facebook Messenger — Meddl loide",
                    "participants": ["Rob Hehr", "Steven Rahn"],
                },
            )
        ]
    )
    title = records.derived_editorial_field(post, tmp_path, "title")
    assert title.value == "Facebook Messenger — Meddl loide"


def test_list_valued_role_field_joins_not_reprs(tmp_path):
    """A `string_or_list` role-marked field (an iMessage group renamed mid-window) derives
    a comma-joined title, never a Python-repr string (spec §4.2.3 via `_first_non_empty`)."""
    root = _make_corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={})
    records.append_origin_block(
        post,
        uri="testsrc://x",
        snapshot="2026-01-01T00:00:00Z",
        schema_id="testsrc",
        fields={"headline": ["Old Name", "New Name"]},
    )
    field = records.derived_editorial_field(post, root, "title")
    assert field.value == "Old Name, New Name"
    assert field.layer == "origin"
