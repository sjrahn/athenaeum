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
    """A bare proxy record (spec §4.1) — no `title`/`description` keys at all (spec
    §12.3.4: birth frontmatter carries no editorial fields), no `status:` key. Lints
    fully clean: no stored placeholder to flag (`editorial-override-placeholder`), and an
    override-less record's empty content zone is expected, not flagged
    (`body-empty-normalized` gates on `has_editorial_override`)."""
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": "a" * 64,
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


def test_section_address_span_rule_is_retired(tmp_path):
    """*(3.7, §12.29)* The rule re-derived a section's envelope and compared it to the stored
    one. Nothing is stored, so the comparison has no second operand and the rule is gone —
    pinned here so its absence from a lint diff reads as intended, not as a hole."""
    assert "section-address-span" not in {rid for rid, _fn in lint._REGISTRY}


def test_missing_id_caught(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    del post.metadata["id"]
    findings = _lint(post, root)
    assert any(f.rule_id == "id-missing" for f in findings)


def test_legacy_status_flagged(tmp_path):
    """A record still carrying a frontmatter `status:` key is flagged (info) — a transitional
    3.0 field, never re-emitted on write (spec §4.1, §12.19)."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["status"] = "stub"
    findings = _lint(post, root)
    hit = next(f for f in findings if f.rule_id == "frontmatter-legacy-status")
    assert hit.severity == "info"


def test_no_legacy_status_key_not_flagged(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    assert "status" not in post.metadata
    findings = _lint(post, root)
    assert not any(f.rule_id == "frontmatter-legacy-status" for f in findings)


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


def test_lone_override_is_legal(tmp_path):
    """*(3.2)* A record carrying a title override but no description (or vice versa) is a
    legal, deliberate lone editorial assertion — the retired `is_authored` strict-AND (and
    its `vouch-half-authored` lint rule) is gone; nothing flags this."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["title"] = "Half-vouched"
    findings = _lint(post, root)
    assert not any(f.rule_id.startswith("editorial-override-") for f in findings)


def test_empty_string_placeholder_flagged(tmp_path):
    """A stored empty-string `description: ''` is 3.1-era placeholder residue (spec
    §12.21) — info, not a defect; `dumps()` drops it on the next write."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["description"] = ""
    findings = _lint(post, root)
    hit = next(f for f in findings if f.rule_id == "editorial-override-placeholder")
    assert hit.severity == "info"


def test_full_override_not_flagged_as_placeholder(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["title"] = "Fully vouched"
    post.metadata["description"] = "ok"
    findings = _lint(post, root)
    assert not any(f.rule_id == "editorial-override-placeholder" for f in findings)


def test_editorial_override_redundant_flagged(tmp_path):
    """*(3.2, §12.21 step 1)* A frontmatter override equal to the record's derived value
    beneath it (here, via the transitional legacy artifact-bare-`title` fallback — no
    packaged schema is role-marked yet) is noise, not an assertion."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["title"] = "T"  # equals the artifact block's bare `title` field
    findings = _lint(post, root)
    hit = next(f for f in findings if f.rule_id == "editorial-override-redundant")
    assert hit.severity == "warning"


def test_editorial_override_not_redundant_when_it_diverges(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["title"] = "A Deliberately Different Title"
    findings = _lint(post, root)
    assert not any(f.rule_id == "editorial-override-redundant" for f in findings)


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


def test_qualified_section_is_form_not_retired(tmp_path):
    """3.0: a qualified section opener binds the FORM axis (§4.4.1) — a valid
    structural-shape judgment, not a returning composite. It is never flagged
    `section-composite-retired` (the rule is gone), and it contributes `form/<id>`
    to the derived classifications view (§9.1)."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(
        atom="text", overlay="text/message", address="turn=1", body="hi",
        extra={"participant": 0},
    )
    sec = segments.Section(
        address="turn=1", form="conversation", segments=[seg],
        extra={"participants": ["Andy <a@x>"]},
    )
    fired = {f.rule_id for f in lint.lint(post, [sec], root)}
    assert "section-composite-retired" not in fired
    assert not any(f.severity == "error" for f in lint.lint(post, [sec], root))
    post.content = segments.emit([sec])
    assert "form/conversation" in records.derived_classifications(post)


def test_clean_record_has_no_retired_findings(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    assert not any(f.rule_id == "classify-block-retired" for f in _lint(post, root))


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
    bare = segments.Segment(atom="text", address="el=1", body="hi")  # no entry
    bare2 = segments.Segment(atom="text", address="el=2", body="ho")  # no entry
    labeled = segments.Segment(atom="text", address="el=3", body="yo", entry="Appendix")
    # A uniformly bare flat zone is the §4.3.2.1 default, well-formed state — silent.
    assert "entry-missing" not in {f.rule_id for f in lint.lint(post, [bare, bare2], root)}
    # PARTIAL labeling — a half-built authored TOC — fires, as a warning.
    partial = [f for f in lint.lint(post, [bare, labeled], root) if f.rule_id == "entry-missing"]
    assert partial and partial[0].severity == "warning"
    # Fully labeled and single-block records are silent.
    labeled2 = segments.Segment(atom="text", address="el=4", body="hey", entry="Notes")
    assert "entry-missing" not in {f.rule_id for f in lint.lint(post, [labeled, labeled2], root)}
    assert "entry-missing" not in {f.rule_id for f in lint.lint(post, [bare], root)}
    # Structural byte-marks never count: their entry is the source's, optional (§4.3.2.3).
    mark = segments.Segment(atom="structural", address="el=1", level=1, entry="Ch. 1")
    assert "entry-missing" not in {f.rule_id for f in lint.lint(post, [mark, bare, bare2], root)}


def test_body_sanity_rules(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.content = "hi <script>x</script>\n```\n<!--TODO-->\n"
    fired = _fired(post, root)
    assert {
        "body-html-residue",
        "body-codefence-unbalanced",
        "body-unknown-comment",
    } <= fired
    # empty body on a record carrying an editorial override (title + description both set
    # → has_editorial_override)
    norm = _clean_post()
    norm.metadata["title"] = "T"
    norm.metadata["description"] = "d"
    norm.content = ""
    assert "body-empty-normalized" in _fired(norm, root)


def test_body_corpus_link_forbidden_flags_corpus_uri(tmp_path):
    """A segment body carrying a `corpus://` reference is a spec violation (§4.3.2.2, 3.4)
    — the retired body-link grammar's replacement rule."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(atom="text", address="el=1", body="see corpus://" + "a" * 64)
    findings = [
        f for f in lint.lint(post, [seg], root) if f.rule_id == "body-corpus-link-forbidden"
    ]
    assert findings and findings[0].severity == "error"


def test_body_corpus_link_forbidden_flags_raw_blake3_wikilink(tmp_path):
    """A raw-blake3 `[[<hash>]]` wikilink in a segment body is equally forbidden,
    `corpus://`-scheme or not — both stored forms retired together (§12.26)."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(atom="text", address="el=1", body="see [[" + "c" * 64 + "]]")
    assert "body-corpus-link-forbidden" in {
        f.rule_id for f in lint.lint(post, [seg], root)
    }


def test_body_corpus_link_forbidden_flags_embed_wikilink(tmp_path):
    """The `![[corpus://...]]` embed form is forbidden too."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(
        atom="text", address="el=1", body="![[corpus://" + "d" * 64 + "?el=1]]"
    )
    assert "body-corpus-link-forbidden" in {
        f.rule_id for f in lint.lint(post, [seg], root)
    }


def test_body_corpus_link_forbidden_silent_on_clean_body(tmp_path):
    """A bare `[[` with no corpus-reference grammar behind it is innocent — e.g. faithfully
    transcribed source carrying Swift's `[[Foo]]` nested-array type syntax, caught live as a
    false positive during 3.4 verification. Only `[[`/`![[` opening directly onto
    `corpus://` or a raw 64-hex hash counts."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(
        atom="text", address="el=1", body="plain prose, no links, and `[[Foo]]` is a type"
    )
    assert "body-corpus-link-forbidden" not in {
        f.rule_id for f in lint.lint(post, [seg], root)
    }


def test_body_corpus_link_forbidden_ignores_origin_lineage_uri(tmp_path):
    """The origin block's lineage `uri: corpus://...` (capture history, §8.1/§12.15) lives
    in the metadata zone, not a segment body — the rule must never see it, no matter how
    many origins a promoted record carries."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    records.append_origin_block(
        post, uri="corpus://" + "b" * 64 + "?el=1", snapshot="2026-05-31T00:00:00Z"
    )
    seg = segments.Segment(atom="text", address="el=1", body="clean")
    assert "body-corpus-link-forbidden" not in {
        f.rule_id for f in lint.lint(post, [seg], root)
    }


def test_issue_on_draft_rule_dropped(tmp_path):
    """3.0: the `issue-on-draft` draft-status rule is dropped (§12.18 step 1 — lint drops
    draft-status rules). A record with no stored rendering is the artifact's proxy (§4.1);
    an interpretive issue on it yields no `issue-on-draft` finding."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    records.append_issue_block(
        post, id="incomplete", severity="warning", resolution="open", detector="claude-opus-4-8[1m]"
    )
    assert "issue-on-draft" not in _fired(post, root)


def test_section_description_redundant_no_longer_spares_any_section(tmp_path):
    """*(3.2)* `section-description-redundant` fires on an all-lossless section whose header
    carries a `description:`. *(3.7)* And now on EVERY such section: the whole-record
    exemption existed because that header was the editorial vouch's home, and 3.5 retired
    both the vouch and the field while 3.7 retired the spelling the exemption keyed on
    (§12.29). Any surviving section `description:` is unswept residue, wherever it sits."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    seg = segments.Segment(
        atom="text", overlay="text/message", address="turn=1", body="hi",
        extra={"participant": 0},
    )

    span = segments.Section(
        address="turn=1", form="conversation", segments=[seg],
        description="A synopsis restating lossless content.",
        extra={"participants": ["Andy <a@x>"]},
    )
    assert "section-description-redundant" in _fired(post, root, [span])

    whole = segments.Section(
        address=None, form="conversation", segments=[seg],
        description="Unswept residue — 3.5 retired this field (§4.3.2.1).",
        extra={"participants": ["Andy <a@x>"]},
    )
    assert "section-description-redundant" in _fired(post, root, [whole])


def test_address_region_grammar(tmp_path):
    """`bbox=` is x,y,WIDTH,HEIGHT as FRACTIONS in [0,1] — the grammar 1,778 authored
    addresses broke by writing pixels into it, unnoticed because nothing validated a
    STORED address (only the render path did, and only when someone resolved it)."""
    root = _make_corpus(tmp_path)
    post = _clean_post()

    pixels = segments.Segment(
        atom="text", overlay="text/data-table", address="el=3&bbox=0,0,2700,1920", body="| a |"
    )
    fired = [f for f in _lint_blocks(post, root, [pixels]) if f.rule_id == "address-region-invalid"]
    assert fired and fired[0].severity == "error"
    assert "fractions of the image" in fired[0].message

    # Corners instead of position+size — the other way the grammar gets misread.
    corners = segments.Segment(
        atom="text", overlay="text/data-table", address="bbox=0.5,0.5,0.8,0.2", body="| a |"
    )
    assert "address-region-invalid" in {
        f.rule_id for f in _lint_blocks(post, root, [corners])
    }

    # A correct fractional crop, and a multi-region `cover=` chain, stay silent.
    good = segments.Segment(
        atom="text", overlay="text/data-table",
        address="el=5&cover=0.955,0,0.045,0.32;0.24,0.8,0.045,0.2&bbox=0.24,0,0.76,1",
        body="| a |",
    )
    assert "address-region-invalid" not in {
        f.rule_id for f in _lint_blocks(post, root, [good])
    }

    # `bbox=` on a spreadsheet is an A1 RANGE — a different grammar under the same key,
    # which the rule declines to judge rather than guessing.
    a1 = segments.Segment(
        atom="text", overlay="text/data-table", address="sheet=Data&bbox=A1:D20", body="| a |"
    )
    assert "address-region-invalid" not in {
        f.rule_id for f in _lint_blocks(post, root, [a1])
    }


def test_address_region_grammar_covers_embeds_and_sections(tmp_path):
    """Every surface that STORES an address is checked — not just segments."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    records.append_embed_block(
        post,
        media_type="image/png",
        address="el=2&bbox=0,0,1200,800",
        transport=f"blake3:{'b' * 64}",
        fields={"description": "a figure"},
    )
    seg = segments.Segment(atom="text", address="el=1", body="hi")
    fired = [
        f for f in _lint_blocks(post, root, [seg]) if f.rule_id == "address-region-invalid"
    ]
    assert fired and "embed 1" in fired[0].message


def _lint_blocks(post, root, blocks):
    return lint.lint(post, blocks, root)


# ---------- embed-unreferenced / embed-missing-target (pinned pre-refactor) ---------- #


def _embed(post, address, media_type="image/png"):
    records.append_embed_block(
        post, media_type=media_type, address=address, transport="blake3:" + "0" * 64
    )


def test_embed_unreferenced_exact_segment_match(tmp_path):
    """A segment at exactly the embed's address is a reference — the baseline case."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    _embed(post, "el=3")
    seg = segments.Segment(atom="text", address="el=3", body="x")
    findings = [f for f in lint.lint(post, [seg], root) if f.rule_id == "embed-unreferenced"]
    assert findings == []


def test_embed_unreferenced_chain_counts_as_reference(tmp_path):
    """A segment address that CHAINS INTO the embed (`el=3&bbox=...`) counts as a reference —
    the base address split off before `&` is folded into the referenced set (lint.py:987-992);
    a lossless transcription cites the bytes it read this way, and treating only exact matches
    as references would call such an embed an orphan."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    _embed(post, "el=3")
    seg = segments.Segment(atom="text", address="el=3&bbox=0,0,1,1", body="x")
    findings = [f for f in lint.lint(post, [seg], root) if f.rule_id == "embed-unreferenced"]
    assert findings == []


def test_embed_unreferenced_section_address_does_not_count(tmp_path):
    """A section's own span address is NOT counted as an embed reference (lint.py:978-980) —
    only child SEGMENT addresses are; a 3.0 section is a form span, not an embed-referencing
    grouping, and the 2.x leniency that counted it masked latent orphans. This is the
    non-obvious decision the rule pins."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    _embed(post, "el=3")
    child = segments.Segment(atom="text", address="el=1", body="x")
    sec = segments.Section(address="el=3", entry="A", segments=[child])
    findings = [f for f in lint.lint(post, [sec], root) if f.rule_id == "embed-unreferenced"]
    assert findings and findings[0].severity == "warning"


def test_embed_unreferenced_list_address_any_match_suffices(tmp_path):
    """An embed's `address` may be a list; a segment matching ANY one member of that list is
    enough to count as a reference — the finding only fires when NONE match."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    _embed(post, ["el=3", "el=6"])
    seg = segments.Segment(atom="text", address="el=6", body="x")
    findings = [f for f in lint.lint(post, [seg], root) if f.rule_id == "embed-unreferenced"]
    assert findings == []


def test_embed_unreferenced_skipped_for_rfc822(tmp_path):
    """`message/rfc822` records skip the rule entirely — its `part=<N>` embeds are the
    email's MIME members declared for promotion, not body-flow assets a mechanical draft can
    position (lint.py:964-967)."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    records.set_artifact_block(post, mime="message/rfc822", fields={})
    _embed(post, "part=2")
    seg = segments.Segment(atom="text", address="part=1", body="x")
    findings = [f for f in lint.lint(post, [seg], root) if f.rule_id == "embed-unreferenced"]
    assert findings == []


def test_embed_unreferenced_skipped_for_manifest_no_segments(tmp_path):
    """A record with embeds and NO content-zone segments at all (the manifest shape) is
    skipped outright — the embeds ARE the content, not flow-assets positioned within it, so
    "unreferenced" is not a defect."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    _embed(post, "el=3")
    findings = [f for f in lint.lint(post, [], root) if f.rule_id == "embed-unreferenced"]
    assert findings == []


def test_embed_unreferenced_fires_with_ordinal_and_media_type(tmp_path):
    """An orphaned embed fires as a `warning`, and the message names its 1-based ordinal and
    media type (the second embed here is unreferenced; the first is not)."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    _embed(post, "el=1", media_type="image/jpeg")
    _embed(post, "el=9", media_type="image/png")
    seg = segments.Segment(atom="text", address="el=1", body="x")
    findings = [f for f in lint.lint(post, [seg], root) if f.rule_id == "embed-unreferenced"]
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "embed 2" in findings[0].message
    assert "image/png" in findings[0].message


def test_embed_missing_target_image_segment_without_embed_errors(tmp_path):
    """An `image/*` segment at an address no embed carries is an `error` — nothing in the
    record can resolve it."""
    root = _make_corpus(tmp_path)
    post = _clean_post()  # application/pdf artifact
    seg = segments.Segment(atom="image", address="el=7", body="")
    findings = [f for f in lint.lint(post, [seg], root) if f.rule_id == "embed-missing-target"]
    assert findings and findings[0].severity == "error"


def test_embed_missing_target_matched_by_embed_is_silent(tmp_path):
    """A segment whose address DOES appear on an embed in the record is not flagged."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    _embed(post, "el=7")
    seg = segments.Segment(atom="image", address="el=7", body="")
    findings = [f for f in lint.lint(post, [seg], root) if f.rule_id == "embed-missing-target"]
    assert findings == []


def test_embed_missing_target_self_slice_exemptions(tmp_path):
    """Self-slice addresses need no embed — the resolver materializes them on demand
    (`_self_slice`, lint.py:1020-1031). Covers every branch of that predicate: an
    `att=`-chained lineage reference (exempt regardless of artifact mime), `frame=`/`time=`/
    `time_range=` on a `video/*` record, `page=` on an `application/pdf` record, and `bbox=`
    on an `image/*` record."""
    root = _make_corpus(tmp_path)

    # att= is exempt on ANY artifact mime — it's resolver-materializable through
    # containment lineage, not tied to a particular artifact type.
    post = _clean_post()  # application/pdf
    seg = segments.Segment(atom="image", address="turn=1&att=2", body="")
    assert "embed-missing-target" not in {f.rule_id for f in lint.lint(post, [seg], root)}

    video_post = _clean_post()
    records.set_artifact_block(video_post, mime="video/mp4", fields={})
    for addr in ["frame=00:00:05", "time=00:00:05", "time_range=00:00:00-00:00:05"]:
        seg = segments.Segment(atom="image", address=addr, body="")
        fired = {f.rule_id for f in lint.lint(video_post, [seg], root)}
        assert "embed-missing-target" not in fired, addr

    pdf_post = _clean_post()  # application/pdf
    seg = segments.Segment(atom="image", address="page=3", body="")
    assert "embed-missing-target" not in {f.rule_id for f in lint.lint(pdf_post, [seg], root)}

    image_post = _clean_post()
    records.set_artifact_block(image_post, mime="image/jpeg", fields={})
    seg = segments.Segment(atom="image", address="bbox=0.1,0.1,0.5,0.5", body="")
    assert "embed-missing-target" not in {f.rule_id for f in lint.lint(image_post, [seg], root)}

    # The exemptions are artifact-mime-specific: a `page=` address is NOT self-slicing on a
    # video record, so it still requires an embed.
    seg = segments.Segment(atom="image", address="page=3", body="")
    assert "embed-missing-target" in {f.rule_id for f in lint.lint(video_post, [seg], root)}
