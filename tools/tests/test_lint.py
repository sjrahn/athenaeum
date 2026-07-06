"""Lint rule tests — including the three P1 reconciliations.

Reconciliation #1 — embed rules read embeds from the metadata zone.
Reconciliation #5 — touch regex keeps the `corpus.` prefix (no-op).
Reconciliation #6 — `perceptual:` presence on a segment is NOT an error;
                    only its shape is validated.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import lint, records, segments


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _clean_post() -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": "a" * 64,
            "description": "ok",
            "status": "draft",
            "touch": "corpus.ingest@0.1.0",
        }
    )
    records.set_artifact_block(post, mime="application/pdf", fields={"title": "T"})
    records.append_origin_block(
        post,
        uri="https://example.com/p",
        snapshot="2026-05-31T00:00:00Z",
    )
    return post


def _lint(post, root):
    blocks = segments.iter_blocks(post.content or "")
    return lint.lint(post, blocks, root)


def test_clean_record_lints_clean(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    assert _lint(post, root) == []


def _seg(addr: str) -> segments.Segment:
    return segments.Segment(atom="text", address=addr, body="x")


def test_section_address_derives_envelope():
    # Discrete-index schemes envelope to their children's span; single point collapses.
    assert segments.section_address([_seg("page=4"), _seg("page=5"), _seg("page=6")]) == "pages=4-6"
    assert segments.section_address([_seg("page=7")]) == "pages=7"
    spine_segs = [_seg("spine=2"), _seg("spine=3")]
    assert segments.section_address(spine_segs) == "spines=2-3"
    assert segments.section_address([_seg("block=3-9")]) == "block=3-9"  # already-ranged child
    assert segments.section_address([_seg("sheet=Sales")]) == "sheet=Sales"
    # The factory derives the same address it builds with.
    built = segments.Section.spanning([_seg("page=4"), _seg("page=5")], entry="Ch")
    assert built.address == "pages=4-5"
    # Temporal / heterogeneous / empty → None (not span-checkable).
    assert segments.section_address([_seg("time_range=00:00:00-00:01:00")]) is None
    assert segments.section_address([_seg("page=1"), _seg("frame=00:00:05")]) is None
    assert segments.section_address([]) is None


def test_section_address_span_lint_flags_mismatch(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    good = segments.Section.spanning([_seg("page=1"), _seg("page=2")], entry="A")
    # Claims pages=1-9 but its segments only span 4-5 (built directly, bypassing spanning).
    bad = segments.Section(
        address="pages=1-9", entry="B", segments=[_seg("page=4"), _seg("page=5")]
    )
    post.content = segments.emit([good, bad])
    spans = [f for f in _lint(post, root) if f.rule_id == "section-address-span"]
    assert len(spans) == 1
    assert spans[0].severity == "warning"
    assert "pages=1-9" in spans[0].message and "pages=4-5" in spans[0].message


def test_missing_id_caught(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    del post.metadata["id"]
    findings = _lint(post, root)
    assert any(f.rule_id == "id-missing" for f in findings)


def test_status_invalid_caught(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["status"] = "frobnicated"
    findings = _lint(post, root)
    assert any(f.rule_id == "status-invalid" for f in findings)


def test_touch_grammar(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    # Valid grammar:
    for v in [
        "corpus.ingest@0.1.0",
        "corpus.draft.mime/application/pdf@0.1.0_2",
        "claude-opus-4-8[1m]",
        "corpus.compile@0.1.0+claude-opus-4-8[1m]",
        # §4.2.2: the model modifier is optional — bare model ids are valid, standalone
        # and in the combined form (this is what `compile --model gpt-4o` produces).
        "gpt-4o",
        "claude-opus-4-8",
        "corpus.compile@0.1.0+gpt-4o",
    ]:
        post.metadata["touch"] = v
        assert not any(f.rule_id.startswith("touch") for f in _lint(post, root)), v
    # Invalid — structurally malformed (whitespace / empty / no valid leading token):
    for bad in ["has space", "", "  ", "@noversion"]:
        post.metadata["touch"] = bad
        assert any(f.rule_id == "touch-format" for f in _lint(post, root)), repr(bad)


def test_origin_missing_or_uri_missing(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["_origins"] = []
    assert any(f.rule_id == "origins-empty" for f in _lint(post, root))


def test_origin_uri_less_local_file_lints_clean(tmp_path):
    """A uri-less origin carrying local-file metadata (filename/source_modified) is valid —
    a dropped-in file has no retrieval uri (spec §7.2)."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["_origins"] = []
    records.append_origin_block(
        post,
        uri=None,
        snapshot="2026-06-29T00:00:00Z",
        fields={"filename": "scan.pdf", "source_modified": "2025-11-03T14:22:09Z"},
    )
    findings = _lint(post, root)
    assert not any(f.rule_id == "origin-without-source" for f in findings)
    assert not any(f.rule_id == "origin-snapshot-missing" for f in findings)


def test_origin_without_uri_or_local_metadata_is_malformed(tmp_path):
    """An origin with neither a uri nor local-file metadata has no source identity → error."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["_origins"] = []
    records.append_origin_block(post, uri=None, snapshot="2026-06-29T00:00:00Z")
    assert any(f.rule_id == "origin-without-source" for f in _lint(post, root))


def test_embed_rules_read_metadata_zone(tmp_path):
    """Reconciliation #1 — embed format checks run on metadata-zone embeds."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    records.append_embed_block(
        post,
        media_type="image/png",
        address="page=1",
        transport="not-a-hash",  # wrong shape
    )
    findings = _lint(post, root)
    assert any(f.rule_id == "embed-transport-format" for f in findings)


def test_embed_in_content_body_is_invisible_to_embed_rules(tmp_path):
    """If a record erroneously stuffs <!--embed--> into the content zone (no
    metadata-zone embed), the embed-format rules find nothing — embed rules look
    only at the metadata zone."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    # Misplaced: put an embed-shaped block in the content body.
    post.content = (
        "<!--embed image/png\naddress: page=1\ntransport: not-a-hash\n-->\n"
    )
    # No embed_format errors fire because metadata-zone embeds is empty:
    findings = _lint(post, root)
    assert not any(f.rule_id == "embed-transport-format" for f in findings)


def test_perceptual_present_is_NOT_an_error(tmp_path):
    """Reconciliation #6 — perceptual presence on a segment is not flagged; only
    a bad shape is."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(
        atom="text",
        address="page=1",
        body="t",
        perceptual="simhash:a" * 1 + "0" * 31,  # 32-char hex
    )
    post.content = segments.emit([seg])
    findings = _lint(post, root)
    assert not any(f.rule_id == "segment-perceptual-format" for f in findings), (
        "valid-shape perceptual should not trigger the rule"
    )


def test_perceptual_malformed_is_an_error(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(
        atom="text",
        address="page=1",
        body="t",
        perceptual="not-a-hash",
    )
    post.content = segments.emit([seg])
    findings = _lint(post, root)
    assert any(f.rule_id == "segment-perceptual-format" for f in findings)


def test_perceptual_list_is_accepted(tmp_path):
    """§7.6 — a multi-region segment may carry a list of perceptual hashes."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(
        atom="text",
        address="page=1",
        body="t",
        perceptual=["simhash:" + "a" * 16, "phash:" + "b" * 16],
    )
    post.content = segments.emit([seg])
    findings = _lint(post, root)
    assert not any(f.rule_id == "segment-perceptual-format" for f in findings)


def test_perceptual_list_with_bad_entry_is_an_error(tmp_path):
    """A list-valued perceptual is validated per-element (not bypassed)."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(
        atom="text",
        address="page=1",
        body="t",
        perceptual=["simhash:" + "a" * 16, "not-a-hash"],
    )
    post.content = segments.emit([seg])
    findings = _lint(post, root)
    assert any(f.rule_id == "segment-perceptual-format" for f in findings)


def test_issue_vocab_is_schema_extensible(tmp_path):
    """§4.3.3.1 — issue severity/resolution vocab is schema-declared, not hardcoded; a
    corpus may extend it in its local `context/issue/issue.yaml`."""
    root = _make_corpus(tmp_path)
    issue_dir = root / "schema" / "context" / "issue"
    issue_dir.mkdir(parents=True)
    (issue_dir / "issue.yaml").write_text(
        "extended_fields:\n"
        "  severity:\n"
        "    type: string\n"
        "    enum: [blocking, warning, info, critical]\n",
        encoding="utf-8",
    )
    post = _clean_post()
    records.append_issue_block(
        post,
        id="format-loss",
        severity="critical",  # corpus-extended value, not in the universal default
        resolution="open",
        detector="corpus.ingest@0.1.0",
    )
    findings = _lint(post, root)
    assert not any(f.rule_id == "issue-severity-invalid" for f in findings)


def test_image_segment_with_body_caught(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(atom="image", address="page=1", body="should not be here")
    post.content = segments.emit([seg])
    findings = _lint(post, root)
    assert any(f.rule_id == "segment-non-text-with-body" for f in findings)


def test_issue_shape_validation(tmp_path):
    """Reconciliation #2: issues must use our spec's vocabulary."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    # CarbonAi-shape issue (bad).
    records.append_issue_block(
        post,
        id="format-loss",
        severity="major",  # not in the schema enum
        resolution="needs-human-review",  # not in the schema enum
        detector="not a touch id",  # whitespace → not a valid touch identifier
    )
    findings = _lint(post, root)
    rule_ids = {f.rule_id for f in findings}
    assert "issue-severity-invalid" in rule_ids
    assert "issue-resolution-invalid" in rule_ids
    assert "issue-detector-format" in rule_ids


def test_issue_spec_shape_passes(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    records.append_issue_block(
        post,
        id="format-loss",
        severity="warning",
        resolution="open",
        detector="corpus.draft.mime/application/pdf@0.1.0",
    )
    findings = _lint(post, root)
    assert not any(f.rule_id.startswith("issue-") for f in findings)


def test_normalized_record_must_have_description(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["status"] = "normalized"
    post.metadata["description"] = ""
    findings = _lint(post, root)
    assert any(f.rule_id == "description-empty" for f in findings)


def test_segment_address_duplicate_caught(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg1 = segments.Segment(atom="text", address="page=1", body="a")
    seg2 = segments.Segment(atom="text", address="page=1", body="b")
    post.content = segments.emit([seg1, seg2])
    findings = _lint(post, root)
    assert any(f.rule_id == "segment-address-duplicate" for f in findings)


def test_segment_same_address_different_opener_id_is_ok(tmp_path):
    """spec §4.3.2.2: same-region stacking is OK when opener-id differs."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg_a = segments.Segment(atom="text", address="page=1", body="raw text", overlay=None)
    seg_b = segments.Segment(
        atom="text", address="page=1", body="| col |\n| --- |\n| v |", overlay="text/data-table"
    )
    post.content = segments.emit([seg_a, seg_b])
    findings = _lint(post, root)
    assert not any(f.rule_id == "segment-address-duplicate" for f in findings)


# ---------- retired 1.0 grammar (classify blocks / section composites) ---------- #


def _add_classify(post, fields):
    post.metadata.setdefault("_classifies", []).append(
        {"namespace": "source", "id": "majority-report", "subtype": None, "fields": fields}
    )


def test_classify_block_flags_retired(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    _add_classify(post, {"provenance": "auto"})
    fired = [f for f in _lint(post, root) if f.rule_id == "classify-block-retired"]
    assert len(fired) == 1 and fired[0].severity == "warning"


def test_section_composite_flags_retired(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    sec = segments.Section(
        address="block=1", entry="x", classification="recipe/dinner", segments=[]
    )
    fired = [
        f
        for f in lint.lint(post, [sec], root)
        if f.rule_id == "section-composite-retired"
    ]
    assert len(fired) == 1 and fired[0].severity == "warning"


def test_clean_record_has_no_retired_findings(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    assert not any(
        f.rule_id in ("classify-block-retired", "section-composite-retired")
        for f in _lint(post, root)
    )


# ---------- normalizer-support parity rules ---------- #


def _fired(post, root, blocks=None):
    return {f.rule_id for f in lint.lint(post, blocks if blocks is not None else [], root)}


def test_description_too_long(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["description"] = "word " * 801
    assert "description-too-long" in _fired(post, root)


def test_segment_lossless_contract(tmp_path):
    root = _make_corpus(tmp_path)
    # text/data-table-dynamic is bundled non-lossless (enables_lossless: false).
    with_body = segments.Segment(
        atom="text", address="el=2", overlay="text/data-table-dynamic", body="x"
    )
    marker_no_desc = segments.Segment(
        atom="text", address="el=3", overlay="text/data-table-dynamic"
    )
    post = _clean_post()
    fired = {f.rule_id for f in lint.lint(post, [with_body, marker_no_desc], root)}
    assert "segment-body-requires-lossless" in fired  # body on a non-lossless overlay
    assert "segment-description-required" in fired  # body-empty marker, no description


def test_entry_missing(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(atom="text", address="el=1", body="hi")  # no entry
    seg2 = segments.Segment(atom="text", address="el=2", body="ho")  # no entry
    assert "entry-missing" in {f.rule_id for f in lint.lint(post, [seg, seg2], root)}
    # A single top-level block is exempt — the record is its own TOC line.
    assert "entry-missing" not in {f.rule_id for f in lint.lint(post, [seg], root)}


def test_body_sanity_rules(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.content = "hi <script>x</script>\n```\n<!--TODO-->\nsee ![[broken"
    fired = _fired(post, root)
    assert {
        "body-html-residue",
        "body-codefence-unbalanced",
        "body-unknown-comment",
        "body-wikilink-malformed",
    } <= fired
    # empty body on a normalized record
    norm = _clean_post()
    norm.metadata["status"] = "normalized"
    norm.content = ""
    assert "body-empty-normalized" in _fired(norm, root)


def test_embed_description_empty_on_normalized(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["status"] = "normalized"
    records.append_embed_block(
        post, media_type="image/png", address="el=4", transport="blake3:" + "0" * 64
    )
    assert "embed-description-empty-on-normalized" in _fired(post, root)


def test_issue_on_draft(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()  # status draft
    records.append_issue_block(
        post, id="incomplete", severity="warning", resolution="open", detector="claude-opus-4-8[1m]"
    )
    assert "issue-on-draft" in _fired(post, root)
    # a mechanical drafter issue (detector corpus.*) is legitimate on a draft
    post2 = _clean_post()
    records.append_issue_block(
        post2,
        id="paywall",
        severity="warning",
        resolution="open",
        detector="corpus.draft.html@0.1.0",
    )
    assert "issue-on-draft" not in _fired(post2, root)
