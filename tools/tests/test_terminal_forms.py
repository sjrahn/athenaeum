"""Terminal contracts (spec §7.8, ATH-CORPUS 3.3 — the terminal-forms amendment).

Covers the new machinery end to end, in isolation from any particular corpus's real
schemas: the `terminal: true` overlay marker (`schemas.is_terminal_form`), the mime-level
`form:` default and its terminal-only validation (`schemas.resolve_mime_terminal_form`),
per-record disposition resolution (`schemas.resolved_disposition_for_record`), the full
governing-contract precedence (`shape.governing_form`), the fourth `derived_state` value,
the pass gate's terminal no-op (`shape.declared_form_unmet`), and the lint changes
(the inverted `terminal-stored-rendering` rule; the body-empty-family exemption).
*(3.4: the embed-description exemption pair retired alongside
`embed-description-empty-on-normalized` itself, §12.26 — the per-asset `description:`
field it gated on no longer exists.)*

The two packaged terminal contracts (`form/passthrough`, `form/manifest`) are exercised
directly — they ship in `schemas_default/form/`, so a tmp corpus with an empty `schema/`
resolves them via the packaged fallback, exactly like `test_form_coherence.py`."""

from __future__ import annotations

import logging
from pathlib import Path

import frontmatter
import yaml

from corpus import health, lint, paths, queue, records, schemas, segments
from corpus import shape as shape_pkg
from corpus._cli import dispatch


def _write_yaml(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _corpus(tmp_path: Path, name: str = "c") -> Path:
    root = tmp_path / name
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _base_post(rid: str = "a" * 64) -> frontmatter.Post:
    return frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )


# ---------- schemas.is_terminal_form ---------- #


def test_is_terminal_form_true_for_packaged_terminal_contracts(tmp_path):
    root = _corpus(tmp_path)
    assert schemas.is_terminal_form(root, "passthrough") is True
    assert schemas.is_terminal_form(root, "manifest") is True


def test_is_terminal_form_false_for_rendering_contract(tmp_path):
    root = _corpus(tmp_path)
    assert schemas.is_terminal_form(root, "conversation") is False


def test_is_terminal_form_false_for_unknown_id(tmp_path):
    root = _corpus(tmp_path)
    assert schemas.is_terminal_form(root, "not-a-real-form") is False


# ---------- schemas.resolve_mime_terminal_form (§7.1, mime-key validation) ---------- #

_MIME = "application/x-terminal-test"
_MIME_STREAM = "application/x-terminal-stream"


def test_resolve_mime_terminal_form_resolves_terminal_id(tmp_path):
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "mime" / "application" / "application_x-terminal-stream.yaml",
        {"applies_to": {"content_types": [_MIME_STREAM]}, "form": {"id": "passthrough"}},
    )
    schemas.cache_clear()
    assert schemas.resolve_mime_terminal_form(root, _MIME_STREAM) == "passthrough"


def test_resolve_mime_terminal_form_rejects_rendering_contract_id(tmp_path, caplog):
    """A mime schema's `form:` naming a RENDERING contract (not terminal) is a schema-
    authoring mistake: tolerantly rejected (never raised) and logged (§7.1, 3.3)."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "mime" / "application" / "application_x-terminal-test.yaml",
        {"applies_to": {"content_types": [_MIME]}, "form": {"id": "conversation"}},
    )
    schemas.cache_clear()
    with caplog.at_level(logging.WARNING):
        assert schemas.resolve_mime_terminal_form(root, _MIME) is None
    assert any("terminal contract" in rec.message for rec in caplog.records)


def test_resolve_mime_terminal_form_absent_key_is_none(tmp_path):
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "mime" / "application" / "application_x-terminal-test.yaml",
        {"applies_to": {"content_types": [_MIME]}},
    )
    schemas.cache_clear()
    assert schemas.resolve_mime_terminal_form(root, _MIME) is None


def test_resolve_mime_terminal_form_unknown_mime_is_none(tmp_path):
    root = _corpus(tmp_path)
    assert schemas.resolve_mime_terminal_form(root, "application/does-not-exist") is None


# ---------- schemas.resolved_disposition_for_record ---------- #


def test_resolved_disposition_mime_default(tmp_path):
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "mime" / "application" / "application_x-terminal-test.yaml",
        {"applies_to": {"content_types": [_MIME]}, "disposition": "manifest"},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={})
    assert schemas.resolved_disposition_for_record(root, post) == "manifest"


def test_resolved_disposition_origin_override_wins(tmp_path):
    """An origin overlay's `disposition:` override (§7.2) wins over the mime default."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "mime" / "application" / "application_x-terminal-test.yaml",
        {"applies_to": {"content_types": [_MIME]}, "disposition": "manifest"},
    )
    _write_yaml(
        root / "schema" / "origin" / "override-src.yaml",
        {"applies_to": {"schemes": ["ovtest"]}, "kind": "interpretive", "disposition": "work"},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={})
    records.append_origin_block(
        post, uri="ovtest://x", snapshot="2026-01-01T00:00:00Z", schema_id="override-src"
    )
    assert schemas.resolved_disposition_for_record(root, post) == "work"


def test_resolved_disposition_defaults_to_work(tmp_path):
    root = _corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    assert schemas.resolved_disposition_for_record(root, post) == "work"


# ---------- shape.governing_form — the full precedence chain (§7.8, 3.3) ---------- #


def _zip_manifest_mime_schema(root: Path, mime: str = "application/zip") -> None:
    _write_yaml(
        root / "schema" / "mime" / "application" / "application_zip.yaml",
        {"applies_to": {"content_types": [mime]}, "disposition": "manifest"},
    )
    schemas.cache_clear()


def test_governing_form_none_when_genuinely_formless(tmp_path):
    root = _corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    assert shape_pkg.governing_form(post, root) is None


def test_governing_form_a_origin_declares_rendering_contract(tmp_path):
    """Precedence (a): an origin `form:` declaration naming a RENDERING contract — not
    terminal."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "origin" / "conv-src.yaml",
        {"applies_to": {"schemes": ["convtest"]}, "kind": "interpretive",
         "form": {"id": "conversation"}},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(
        post, uri="convtest://x", snapshot="2026-01-01T00:00:00Z", schema_id="conv-src"
    )
    assert shape_pkg.governing_form(post, root) == ("conversation", False)


def test_governing_form_a_origin_declares_terminal_contract(tmp_path):
    """Precedence (a): an origin `form:` declaration naming a TERMINAL contract."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "origin" / "pt-src.yaml",
        {"applies_to": {"schemes": ["pttest"]}, "kind": "interpretive",
         "form": {"id": "passthrough"}},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(
        post, uri="pttest://x", snapshot="2026-01-01T00:00:00Z", schema_id="pt-src"
    )
    assert shape_pkg.governing_form(post, root) == ("passthrough", True)


def test_governing_form_b_mime_default_terminal(tmp_path):
    """Precedence (b): the mime schema's `form:` default, no origin declaration at all."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "mime" / "application" / "application_x-terminal-stream.yaml",
        {"applies_to": {"content_types": [_MIME_STREAM]}, "form": {"id": "passthrough"}},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME_STREAM, fields={})
    assert shape_pkg.governing_form(post, root) == ("passthrough", True)


def test_governing_form_b_mime_default_rejected_falls_through_to_none(tmp_path):
    """A mime `form:` naming a non-terminal id is rejected (§7.1) — with no origin
    declaration and a `work` disposition, the record falls through to formless."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "mime" / "application" / "application_x-terminal-test.yaml",
        {"applies_to": {"content_types": [_MIME]}, "form": {"id": "conversation"}},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime=_MIME, fields={})
    assert shape_pkg.governing_form(post, root) is None


def test_governing_form_c_disposition_manifest_with_embeds(tmp_path):
    """Precedence (c): a resolved `disposition: manifest` record that carries at least one
    attested member embed stands under `form/manifest`, zero overlay edits (§7.8's central
    derivation) — this is the ~290-container private-corpus case."""
    root = _corpus(tmp_path)
    _zip_manifest_mime_schema(root)
    post = _base_post()
    records.set_artifact_block(post, mime="application/zip", fields={})
    records.append_embed_block(
        post, media_type="text/plain", address="path=a.txt", transport="blake3:" + "a" * 64
    )
    assert shape_pkg.governing_form(post, root) == ("manifest", True)


def test_governing_form_c_disposition_manifest_without_embeds_is_none(tmp_path):
    """The fix: a `disposition: manifest` record with NO attested member embeds — a bare
    promoted-member stub (`corpus promote`, §8.1) sharing the format's manifest default
    without ever having run the member-manifest attestation over its OWN bytes — has no
    roster to bind `form/manifest` conformance to, so it stands formless-for-now (`proxy`),
    not swept into `terminal` by a class default it hasn't actually attested. Real
    corpus-private measurement surfaced this: the `text/vcard` mime schema's manifest
    disposition otherwise swept every promoted single-card stub into `terminal`, though
    §12.23's own migration inventory says promoted vcard cards stay `proxy` (spec
    ambiguity — flagged in the report)."""
    root = _corpus(tmp_path)
    _zip_manifest_mime_schema(root)
    post = _base_post()
    records.set_artifact_block(post, mime="application/zip", fields={})
    assert shape_pkg.governing_form(post, root) is None


def test_governing_form_mime_default_yields_to_existing_stored_rendering(tmp_path):
    """*(fix, 3.3)* A mime-level passthrough default must not retroactively condemn a
    record that already carries genuine top-level rendered content with no form-section
    wrapper (the ordinary `rendered` state, §4.1) — the exact `image/jpeg` collision real
    corpus-private data surfaced (OCR segments per image.yaml's own "primarily a document"
    guidance, no wrapping section)."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "mime" / "image" / "image_jpeg.yaml",
        {"applies_to": {"content_types": ["image/jpeg"]}, "form": {"id": "passthrough"}},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime="image/jpeg", fields={})
    seg = segments.Segment(
        atom="text", overlay="text/ocr", address="bbox=0,0,1,1", body="scanned text"
    )
    post.content = segments.emit([seg])
    assert shape_pkg.governing_form(post, root) is None
    assert records.derived_state(post, root) == "rendered"
    assert "terminal-stored-rendering" not in _fired(post, root)


def test_governing_form_disposition_derivation_yields_to_existing_stored_rendering(tmp_path):
    """The same guard applied to the (c)/(d) disposition-derivation path: a manifest
    container that somehow already carries top-level rendered content stays `rendered`,
    not swept into `terminal`."""
    root = _corpus(tmp_path)
    _zip_manifest_mime_schema(root)
    post = _base_post()
    records.set_artifact_block(post, mime="application/zip", fields={})
    records.append_embed_block(
        post, media_type="text/plain", address="path=a.txt", transport="blake3:" + "a" * 64
    )
    seg = segments.Segment(atom="text", address="el=1", body="an unusual describe-pass body")
    post.content = segments.emit([seg])
    assert shape_pkg.governing_form(post, root) is None
    assert records.derived_state(post, root) == "rendered"


def test_governing_form_c_yields_to_explicit_declaration(tmp_path):
    """An overlay MAY still bind a genuine rendering contract over a manifest-disposition
    record — the explicit declaration (a) wins over the (c) derivation (§7.8)."""
    root = _corpus(tmp_path)
    _zip_manifest_mime_schema(root)
    _write_yaml(
        root / "schema" / "origin" / "conv-src.yaml",
        {"applies_to": {"schemes": ["convtest"]}, "kind": "interpretive",
         "form": {"id": "conversation"}},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime="application/zip", fields={})
    records.append_embed_block(
        post, media_type="text/plain", address="path=a.txt", transport="blake3:" + "a" * 64
    )
    records.append_origin_block(
        post, uri="convtest://x", snapshot="2026-01-01T00:00:00Z", schema_id="conv-src"
    )
    assert shape_pkg.governing_form(post, root) == ("conversation", False)


def test_governing_form_b_asserted_whole_record_terminal_section(tmp_path):
    """Precedence (b): no origin declaration, no mime/disposition consulted yet — but the
    content zone already carries an asserted whole-record section whose form id is itself
    terminal (the interpretive-adoption path, §4.4.6)."""
    root = _corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    sec = segments.Section(form="passthrough", segments=[], extra={"title": "A stream"})
    post.content = segments.emit([sec])
    assert shape_pkg.governing_form(post, root) == ("passthrough", True)


def test_governing_form_b_asserted_whole_record_rendering_section_wins_as_non_terminal(tmp_path):
    """*(fix, 3.3)* The same asserted-section path with a RENDERING contract id: the
    record's own asserted section governs directly — `("conversation", False)` — rather
    than falling through to `None` and letting a later class-level default (mime/
    disposition) silently override it. This is the fix real corpus-private data forced: a
    promoted `video/h264` track already carries an asserted `slide-deck` section, and a
    mime-level `form: {id: passthrough}` default on `video/h264` must not out-rank it."""
    root = _corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    seg = segments.Segment(atom="text", overlay="text/message", address="turn=1", body="hi",
                            extra={"participant": 0})
    sec = segments.Section(form="conversation", segments=[seg], extra={"participants": ["A x"]})
    post.content = segments.emit([sec])
    assert shape_pkg.governing_form(post, root) == ("conversation", False)


def test_governing_form_b_asserted_section_outranks_mime_terminal_default(tmp_path):
    """The exact collision the reorder fixes: a mime schema declares a passthrough
    default, but THIS record already carries an asserted, non-terminal whole-record
    section with real content — the asserted section wins, `governing_form` correctly
    reports non-terminal governance, and `terminal-stored-rendering` (below) stays
    silent on it."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "mime" / "video" / "video_h264.yaml",
        {"applies_to": {"content_types": ["video/h264"]}, "form": {"id": "passthrough"}},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime="video/h264", fields={})
    seg = segments.Segment(atom="image", address="frame=00:00:01")
    sec = segments.Section(form="slide-deck", segments=[seg], extra={"title": "Slides"})
    post.content = segments.emit([sec])
    assert shape_pkg.governing_form(post, root) == ("slide-deck", False)
    assert "terminal-stored-rendering" not in _fired(post, root)
    assert records.derived_state(post, root) == "formed"


# ---------- records.derived_state — the fourth value (§4.1, 3.3) ---------- #


def test_derived_state_no_context_degrades_gracefully(tmp_path):
    """Without `corpus_root`, `derived_state` keeps its pre-3.3 three-way read — every
    existing single-arg caller keeps working unchanged."""
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    assert records.derived_state(post) == "proxy"


def test_derived_state_terminal_via_origin_declaration(tmp_path):
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "origin" / "pt-src.yaml",
        {"applies_to": {"schemes": ["pttest"]}, "kind": "interpretive",
         "form": {"id": "passthrough"}},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(
        post, uri="pttest://x", snapshot="2026-01-01T00:00:00Z", schema_id="pt-src"
    )
    assert records.derived_state(post) == "proxy"  # no context: pre-3.3 read
    assert records.derived_state(post, root) == "terminal"  # with context: the real state


def test_derived_state_opener_only_terminal_section_is_terminal_not_formed(tmp_path):
    """The explicit case §7.8/3.3 calls out: an opener-only whole-record terminal section
    is `terminal`, never `formed` — a terminal contract isn't a rendering contract, so it
    can't satisfy `formed`'s row even when stamped."""
    root = _corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    sec = segments.Section(form="manifest", segments=[], extra={"title": "A bundle"})
    post.content = segments.emit([sec])
    assert records.is_formed(post) is True  # the pre-3.3 predicate still sees a form section
    assert records.derived_state(post, root) == "terminal"  # 3.3 corrects the reported state


def test_derived_state_terminal_requires_no_stored_rendering(tmp_path):
    """A terminal-governed record that ALSO carries a stored rendering (a lint violation,
    `terminal-stored-rendering`) does not report `terminal` — the layer-table row requires
    BOTH the terminal contract AND no stored rendering."""
    root = _corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    seg = segments.Segment(atom="text", address="el=1", body="unexpected content")
    sec = segments.Section(form="passthrough", segments=[seg])
    post.content = segments.emit([sec])
    assert records.derived_state(post, root) != "terminal"


def test_derived_state_disposition_derivation_via_context(tmp_path):
    root = _corpus(tmp_path)
    _zip_manifest_mime_schema(root)
    post = _base_post()
    records.set_artifact_block(post, mime="application/zip", fields={})
    records.append_embed_block(
        post, media_type="text/plain", address="path=a.txt", transport="blake3:" + "a" * 64
    )
    assert records.derived_state(post, root) == "terminal"


def test_derived_state_manifest_disposition_no_embeds_stays_proxy(tmp_path):
    """The bug the corpus-private measurement surfaced, exercised through the public
    `derived_state` seam directly."""
    root = _corpus(tmp_path)
    _zip_manifest_mime_schema(root)
    post = _base_post()
    records.set_artifact_block(post, mime="application/zip", fields={})
    assert records.derived_state(post, root) == "proxy"


# ---------- shape.declared_form_unmet — the pass-gate no-op (§8.5, 3.3) ---------- #


def test_declared_form_unmet_terminal_declaration_trivially_met(tmp_path):
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "origin" / "pt-src.yaml",
        {"applies_to": {"schemes": ["pttest"]}, "kind": "interpretive",
         "form": {"id": "passthrough"}},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(
        post, uri="pttest://x", snapshot="2026-01-01T00:00:00Z", schema_id="pt-src"
    )
    # No section stamped at all — the terminal contract's normal, correct state.
    assert shape_pkg.declared_form_unmet(post, root) is None


def test_declared_form_unmet_rendering_declaration_still_gates(tmp_path):
    """Regression: a declared RENDERING contract still refuses when unstamped (pre-3.3
    behavior, unchanged)."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "origin" / "conv-src.yaml",
        {"applies_to": {"schemes": ["convtest"]}, "kind": "interpretive",
         "form": {"id": "conversation"}},
    )
    schemas.cache_clear()
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(
        post, uri="convtest://x", snapshot="2026-01-01T00:00:00Z", schema_id="conv-src"
    )
    assert shape_pkg.declared_form_unmet(post, root) == "conversation"


def test_finalize_terminal_declared_record_is_a_noop(tmp_path):
    """End-to-end pass-gate integration: an enqueued terminal-governed record finalizes
    cleanly with no section ever stamped (spec §8.5's terminal no-op)."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "origin" / "pt-src.yaml",
        {"applies_to": {"schemes": ["pttest"]}, "kind": "interpretive",
         "form": {"id": "passthrough"}},
    )
    schemas.cache_clear()
    rid = "b" * 64
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(
        post, uri="pttest://x", snapshot="2026-01-01T00:00:00Z", schema_id="pt-src"
    )
    records.dump(post, paths.record_path(root, rid))

    queue.enqueue(root, rid)
    queue.drain(root)
    rc = dispatch(["finalize", rid, "--corpus-root", str(root)])
    assert rc == 0
    st = queue.state(root, rid)
    assert st["state"] == "idle" and st["result"]["outcome"] == "completed"


# ---------- lint: terminal-stored-rendering (§7.8, error, 3.3) ---------- #


def _fired(post, root):
    return {f.rule_id for f in lint.lint(post, segments.iter_blocks(post.content or ""), root)}


def _findings(post, root):
    return list(lint.lint(post, segments.iter_blocks(post.content or ""), root))


def test_terminal_stored_rendering_fires_on_content(tmp_path):
    root = _corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    seg = segments.Segment(atom="text", address="el=1", body="this should not be here")
    sec = segments.Section(form="passthrough", segments=[seg])
    post.content = segments.emit([sec])
    findings = [f for f in _findings(post, root) if f.rule_id == "terminal-stored-rendering"]
    assert findings and findings[0].severity == "error"


def test_terminal_stored_rendering_clean_when_opener_only(tmp_path):
    root = _corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    sec = segments.Section(form="passthrough", segments=[], extra={"title": "A stream"})
    post.content = segments.emit([sec])
    assert "terminal-stored-rendering" not in _fired(post, root)


def test_terminal_stored_rendering_silent_for_non_terminal_form(tmp_path):
    root = _corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    seg = segments.Segment(atom="text", overlay="text/message", address="turn=1", body="hi",
                            extra={"participant": 0})
    sec = segments.Section(form="conversation", segments=[seg], extra={"participants": ["A x"]})
    post.content = segments.emit([sec])
    assert "terminal-stored-rendering" not in _fired(post, root)


def test_terminal_stored_rendering_silent_when_genuinely_formless(tmp_path):
    root = _corpus(tmp_path)
    post = _base_post()
    records.set_artifact_block(post, mime="text/plain", fields={})
    assert "terminal-stored-rendering" not in _fired(post, root)


# ---------- lint: body-empty-family exemption for terminal records (§8.5, 3.3) ---------- #


def test_body_empty_normalized_exempt_for_terminal_record(tmp_path):
    """A `form/passthrough`-governed record (mime default) with a frontmatter override, no
    content, no embeds no longer trips `body-empty-normalized` — the empty content zone is
    the contract's prescribed state, not a defect (§12.20's "dissolves with its embeds",
    generalized to the no-embeds passthrough case)."""
    root = _corpus(tmp_path)
    _write_yaml(
        root / "schema" / "mime" / "application" / "application_x-terminal-stream.yaml",
        {"applies_to": {"content_types": [_MIME_STREAM]}, "form": {"id": "passthrough"}},
    )
    schemas.cache_clear()
    post = _base_post()
    post.metadata["title"] = "A stream"
    records.set_artifact_block(post, mime=_MIME_STREAM, fields={})
    assert "body-empty-normalized" not in _fired(post, root)


def test_body_empty_normalized_still_fires_for_non_terminal(tmp_path):
    """Regression: the same shape (override, no content, no embeds) WITHOUT a terminal
    contract still fires (pre-3.3 behavior unchanged)."""
    root = _corpus(tmp_path)
    post = _base_post()
    post.metadata["title"] = "Something"
    records.set_artifact_block(post, mime="text/plain", fields={})
    assert "body-empty-normalized" in _fired(post, root)


# ---------- health: layer_presence + unshaped (§4.1, 3.3) ---------- #


def test_health_layer_presence_reports_terminal(tmp_path):
    root = _corpus(tmp_path)
    _zip_manifest_mime_schema(root)
    # One genuine terminal container.
    p1 = _base_post("c" * 64)
    records.set_artifact_block(p1, mime="application/zip", fields={})
    records.append_embed_block(
        p1, media_type="text/plain", address="path=a.txt", transport="blake3:" + "a" * 64
    )
    records.dump(p1, paths.record_path(root, "c" * 64))
    # One genuine (still-)proxy record — no embeds, no declaration.
    p2 = _base_post("d" * 64)
    records.set_artifact_block(p2, mime="text/plain", fields={})
    records.dump(p2, paths.record_path(root, "d" * 64))

    refs = health.load_all_records(root)
    lp = health.layer_presence(refs, root)
    assert lp["terminal"] == 1
    assert lp["proxy"] == 1


def test_health_unshaped_excludes_terminal(tmp_path):
    root = _corpus(tmp_path)
    _zip_manifest_mime_schema(root)
    p1 = _base_post("c" * 64)
    records.set_artifact_block(p1, mime="application/zip", fields={})
    records.append_embed_block(
        p1, media_type="text/plain", address="path=a.txt", transport="blake3:" + "a" * 64
    )
    records.dump(p1, paths.record_path(root, "c" * 64))

    refs = health.load_all_records(root)
    unshaped = health.unshaped(refs, root)
    assert all(item["id"] != ("c" * 64) for item in unshaped)
