"""Lint rule tests — including the three P1 reconciliations.

Reconciliation #1 — embed rules read embeds from the metadata zone.
Reconciliation #5 — touch regex keeps the `corpus.` prefix (no-op).
Reconciliation #6 — `perceptual:` presence on a segment is NOT an error;
                    only its shape is validated.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import lint, paths, records, segments


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _clean_post() -> frontmatter.Post:
    """A bare proxy record (spec §4.1) — no `title`/`description` keys at all (spec
    §4.2.1, §12.3.4: both retired 3.5, and birth frontmatter never carried them), no
    `status:` key. Lints fully clean: an override-less record's empty content zone is
    expected, not flagged (`body-empty-normalized` gates on `has_editorial_override`)."""
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


def test_3_12_reconciliation_retires_the_pre_3_5_rules(tmp_path):
    """ATH-CORPUS 3.12 reconciliation (#153): these rule ids enforced law 3.5/3.7 retired —
    `entry:` labels, segment/section `description:`, the frontmatter `title`/`description`
    override pair, and `canonical:`. Pinned here, same style as `section-address-span` above,
    so their absence reads as intended."""
    registered = {rid for rid, _fn in lint._REGISTRY}
    retired = {
        "entry-missing",
        "segment-description-required",
        "section-description-redundant",
        "editorial-override-placeholder",
        "editorial-override-redundant",
        "canonical-format",
    }
    assert not (registered & retired)
    assert retired.isdisjoint(lint.DIAGNOSE_QUICK_RULES)


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


def test_transport_and_perceptual_format_rules_are_retired(tmp_path):
    """*(v20)* `_rule_transport_format`/`_rule_perceptual_format` (record scope) retire:
    grammar duty moves to `hash-tag-grammar`, legacy-detection to
    `hash-legacy-transport` (§4.2.1). Segment-scope `segment-perceptual-format` is
    untouched (§7.7/§4.3.2.2) and stays registered."""
    registered = {rid for rid, _fn in lint._REGISTRY}
    assert "transport-format" not in registered
    assert "perceptual-format" not in registered
    assert "segment-perceptual-format" in registered
    assert "transport-format" not in lint.DIAGNOSE_QUICK_RULES
    assert "hash-tag-grammar" in lint.DIAGNOSE_QUICK_RULES


def test_hash_tag_grammar_valid_values_pass(tmp_path):
    """A bare-algorithm tag, a procedure-versioned tag, and a list of both are all
    well-formed `<tag>:<hex>` (spec §7.6) and lint clean."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["hash"] = "sha256:" + "a" * 64
    assert not any(f.rule_id == "hash-tag-grammar" for f in _lint(post, root))

    post.metadata["hash"] = ["sha256:" + "a" * 64, "html-stampfree@1:" + "b" * 64]
    assert not any(f.rule_id == "hash-tag-grammar" for f in _lint(post, root))


def test_hash_tag_grammar_bad_hex_fails(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["hash"] = "sha256:not-hex"
    assert any(f.rule_id == "hash-tag-grammar" for f in _lint(post, root))


def test_hash_tag_grammar_malformed_tag_fails(tmp_path):
    """No `:` separator, or an empty procedure/version half of an `@`-tag, is a
    grammar violation (spec §7.6)."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    for bad in ["sha256-no-colon", "@1:" + "a" * 32, "html-stampfree@:" + "a" * 32]:
        post.metadata["hash"] = bad
        assert any(f.rule_id == "hash-tag-grammar" for f in _lint(post, root)), bad


def test_hash_tag_grammar_blake3_tag_is_inadmissible(tmp_path):
    """`blake3` as a `hash:` tag duplicates the primary identity on `id` — inadmissible
    even though it is grammatically a well-formed bare algorithm tag (spec §4.2.1)."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["hash"] = "blake3:" + "a" * 64
    findings = [f for f in _lint(post, root) if f.rule_id == "hash-tag-grammar"]
    assert findings and findings[0].severity == "error"


def test_hash_tag_grammar_unknown_tag_is_allowed(tmp_path):
    """A well-formed tag this process's registry has never heard of is NOT a finding —
    the recipe registry is open to extension (spec §7.9); an unrecognized-but-valid tag
    must not lint red just because it's unfamiliar."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["hash"] = "some-future-algo:" + "a" * 40
    assert not any(f.rule_id == "hash-tag-grammar" for f in _lint(post, root))


def test_hash_tag_grammar_similarity_recipe_is_inadmissible(tmp_path):
    """A tag whose registered recipe is similarity-class is never admissible in
    `hash:` — that field's contract is "equality means same content", which a
    similarity value cannot support (spec §4.2.1, §7.9)."""
    from corpus import hashing

    hashing.register_recipe(
        hashing.Recipe(
            id="test-simhash@1", residency="procedure-versioned", comparison="similarity"
        )
    )
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["hash"] = "test-simhash@1:" + "a" * 32
    findings = [f for f in _lint(post, root) if f.rule_id == "hash-tag-grammar"]
    assert findings and findings[0].severity == "error"


def test_hash_legacy_transport_flags_each_legacy_key(tmp_path):
    """`transport`/`canonical`/`perceptual` frontmatter keys are each pre-v20 fields
    (spec §4.2.1) — present, they fire the advisory, one finding per key."""
    root = _make_corpus(tmp_path)
    for key in ("transport", "canonical", "perceptual"):
        post = _clean_post()
        post.metadata[key] = "sha256:" + "a" * 64
        hits = [f for f in _lint(post, root) if f.rule_id == "hash-legacy-transport"]
        assert hits and hits[0].severity == "info" and hits[0].subtype == key


def test_hash_legacy_transport_not_flagged_when_absent(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    assert not any(f.rule_id == "hash-legacy-transport" for f in _lint(post, root))


def test_legacy_transport_well_formed_folds_into_hash_without_grammar_error(tmp_path):
    """`records.loads()`'s tolerant fold (spec §4.2.1) leaves BOTH `hash:` (the folded
    value, what every other rule reads) and the raw `transport:` key (what
    `hash-legacy-transport` reads) in `post.metadata`. A well-formed folded value trips
    only the advisory, never `hash-tag-grammar` — reproduced here directly, mirroring
    what `records.loads()` does to a record whose only hash key is `transport:`,
    without depending on this module's raw record-text grammar."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    hashval = "sha256:" + "b" * 64
    post.metadata["transport"] = hashval
    post.metadata["hash"] = hashval  # what `records.loads()`'s fold would have produced
    findings = _lint(post, root)
    assert any(f.rule_id == "hash-legacy-transport" and f.subtype == "transport" for f in findings)
    assert not any(f.rule_id == "hash-tag-grammar" for f in findings)


def test_hash_superseded_recipe_version_fires_against_newer_registered_version(tmp_path):
    """A stored `<procedure>@<old-version>` whose procedure is registered at a
    DIFFERENT version is flagged for deliberate re-flush — never rewritten, never an
    error (spec §7.9)."""
    from corpus import hashing

    hashing.register_recipe(
        hashing.Recipe(id="test-proc@2", residency="procedure-versioned", comparison="identity")
    )
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["hash"] = "test-proc@1:" + "a" * 32
    findings = [
        f for f in _lint(post, root) if f.rule_id == "hash-superseded-recipe-version"
    ]
    assert findings
    assert findings[0].severity == "warning"
    assert findings[0].fields["procedure"] == "test-proc"
    assert findings[0].fields["stored_version"] == "1"
    assert "2" in findings[0].fields["current_versions"]


def test_hash_superseded_recipe_version_current_version_not_flagged(tmp_path):
    """The exact currently-registered version is not superseded."""
    from corpus import hashing

    hashing.register_recipe(
        hashing.Recipe(id="test-proc-b@1", residency="procedure-versioned", comparison="identity")
    )
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["hash"] = "test-proc-b@1:" + "a" * 32
    assert not any(
        f.rule_id == "hash-superseded-recipe-version" for f in _lint(post, root)
    )


def test_hash_superseded_recipe_version_unknown_procedure_not_flagged(tmp_path):
    """A procedure-versioned tag this process's registry has never heard of at all is
    not this rule's business — same open-registry discipline as `hash-tag-grammar`."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["hash"] = "wholly-unregistered-proc@1:" + "a" * 32
    assert not any(
        f.rule_id == "hash-superseded-recipe-version" for f in _lint(post, root)
    )


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


def _member_row(**fields):
    return {
        "media_type": "image/png",
        "address": "el=1",
        "transport": "blake3:" + "a" * 64,
        "fields": fields,
    }


def test_member_row_clean_shape_lints_clean(tmp_path):
    """The closed four-key shape — `bytes` present and an int — is exactly conformant
    (spec §4.3.1.4); nothing here to flag."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["_embeds"] = [_member_row(bytes=1024)]
    assert not any(f.rule_id == "member-row-unknown-key" for f in _lint(post, root))


def test_member_row_unknown_key_flagged(tmp_path):
    """A stray descriptive key on a members-block row (spec §4.3.1.4: the row is closed to
    address/media_type/transport/bytes) — the exact defect class that let the retired
    per-asset block accumulate authored prose beside its byte-facts."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["_embeds"] = [_member_row(bytes=1024, width=640, alt="a logo")]
    findings = [f for f in _lint(post, root) if f.rule_id == "member-row-unknown-key"]
    assert findings and findings[0].severity == "error"
    assert findings[0].fields["unknown_keys"] == ["alt", "width"]


def test_member_row_missing_bytes_flagged(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["_embeds"] = [_member_row()]  # no `bytes` at all
    findings = [f for f in _lint(post, root) if f.rule_id == "member-row-unknown-key"]
    assert findings and "missing required `bytes`" in findings[0].message


def test_member_row_non_int_bytes_flagged(tmp_path):
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["_embeds"] = [_member_row(bytes="1024")]  # string, not int
    findings = [f for f in _lint(post, root) if f.rule_id == "member-row-unknown-key"]
    assert findings and "not an int" in findings[0].message


def test_member_row_legacy_embed_form_is_exempt(tmp_path):
    """Pre-3.4 per-asset `<!--embed-->` rows are read-only and carry whatever the retired
    block stored — not this check's business (spec §12.26). `_members_block: False` marks
    a record read from the legacy form."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.metadata["_members_block"] = False
    post.metadata["_embeds"] = [_member_row(width=640, alt="a logo")]  # no `bytes` either
    assert not any(f.rule_id == "member-row-unknown-key" for f in _lint(post, root))


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


def test_segment_lossless_contract(tmp_path):
    """A `text` segment whose overlay opts out of lossless (`enables_lossless: false`) must
    stay a body-empty marker (spec §4.3.2.3). A marker carrying a body is
    `segment-body-requires-lossless`; a body-empty marker is silent — 3.5 retired the
    segment `description` field the old rule demanded in its place (§4.2.3, §12.27): the
    honest residue for content that matters is a typed `issue` block, authored separately,
    not a lint-mandated field."""
    root = _make_corpus(tmp_path)
    # text/data-table-dynamic is bundled non-lossless (enables_lossless: false).
    with_body = segments.Segment(
        atom="text", address="el=2", overlay="text/data-table-dynamic", body="x"
    )
    marker_empty = segments.Segment(
        atom="text", address="el=3", overlay="text/data-table-dynamic"
    )
    post = _clean_post()
    fired = {f.rule_id for f in lint.lint(post, [with_body, marker_empty], root)}
    assert "segment-body-requires-lossless" in fired  # body on a non-lossless overlay
    assert "segment-description-required" not in fired  # retired 3.5 — no such rule exists


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


def _unrelated_segment() -> segments.Segment:
    """A content-zone segment that keeps the record out of the manifest (no-segments)
    exemption, without referencing the member under test."""
    return segments.Segment(atom="text", address="el=999", body="unrelated content")


def test_embed_unreferenced_silent_when_the_member_is_already_promoted(tmp_path):
    """A member that already has its own promoted record (§8.1, §12.9's member index) is not
    dangling, even though nothing on this record references it: a placement is only owed to a
    member that was actually SEATED with a rendering (§12.30's reseat never fabricates one for
    a member that received none), so a stub-promoted, unrendered member legitimately has no
    reference here yet — that is normalization pressure (§8.5), not an orphan."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    hexval = "a" * 64
    _embed(post, "stream_id=0")
    post.metadata["_embeds"][0]["transport"] = f"blake3:{hexval}"
    leaf = paths.record_path(root, hexval)
    leaf.parent.mkdir(parents=True, exist_ok=True)
    leaf.write_text("---\nid: " + hexval + "\n---\n", encoding="utf-8")
    findings = [
        f for f in lint.lint(post, [_unrelated_segment()], root)
        if f.rule_id == "embed-unreferenced"
    ]
    assert findings == []


def test_embed_unreferenced_still_fires_for_a_genuinely_unpromoted_member(tmp_path):
    """The rule's whole point, unweakened: a member with no reference AND no promoted record
    of its own is still an orphan nobody has done anything with."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    hexval = "b" * 64
    _embed(post, "stream_id=0")
    post.metadata["_embeds"][0]["transport"] = f"blake3:{hexval}"
    assert not paths.record_path(root, hexval).is_file()
    findings = [
        f for f in lint.lint(post, [_unrelated_segment()], root)
        if f.rule_id == "embed-unreferenced"
    ]
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_embed_unreferenced_promoted_member_check_degrades_without_root(tmp_path):
    """Without a corpus root the member-index lookup has nothing to check against — the rule
    falls back to its original unconditional warning rather than silently clearing (this rule
    ran root-free before the check existed; a missing root should never narrow it to nothing).
    Calls the rule function directly rather than through `lint.lint` — other registered rules
    are not root-tolerant and are not what this test is about."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    hexval = "c" * 64
    _embed(post, "stream_id=0")
    post.metadata["_embeds"][0]["transport"] = f"blake3:{hexval}"
    leaf = paths.record_path(root, hexval)
    leaf.parent.mkdir(parents=True, exist_ok=True)
    leaf.write_text("---\nid: " + hexval + "\n---\n", encoding="utf-8")
    findings = list(lint._rule_embed_unreferenced(post, [_unrelated_segment()], None))
    assert len(findings) == 1


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


def test_section_empty_skips_terminal_forms(tmp_path):
    """The §7.8 inversion: a terminal contract's section is bare BY DESIGN — an
    empty `<!--section passthrough-->` is conformance, never a `section-empty`
    warning; a bare (formless) empty section still warns."""
    root = _make_corpus(tmp_path)
    post = _clean_post()
    post.content = "<!--section passthrough-->"
    assert not any(f.rule_id == "section-empty" for f in _lint(post, root))
    post.content = "<!--section-->"
    assert any(f.rule_id == "section-empty" for f in _lint(post, root))
