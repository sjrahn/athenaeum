"""3.0 form-coherence + byte-mark + two-status lint (spec §4.3.2.1, §4.3.2.3, §7.8, §4.1).

The form overlays (`conversation`, `statement`, `receipt`) ship in the package, so a
tmp corpus with an empty `schema/` resolves them via the packaged fallback."""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import lint, records, schemas, segments


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _post(legacy_status: str | None = None) -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": "a" * 64, "title": "", "description": "d",
         "touch": "corpus.ingest@0.1.0"}
    )
    if legacy_status is not None:
        post.metadata["status"] = legacy_status
    return post


def _fired(post, root):
    return {f.rule_id for f in lint.lint(post, segments.iter_blocks(post.content or ""), root)}


# ---------- derived-state lifecycle (§4.1) ---------- #


def test_no_legacy_status_key_not_flagged():
    post = _post()
    assert "status" not in post.metadata
    assert not any(
        f.rule_id == "frontmatter-legacy-status"
        for f in lint.lint(post, [], Path("/nonexistent"))
    )


def test_legacy_status_key_flagged_regardless_of_value():
    """Any stray `status:` value — even one that was never a valid 3.0 status — is flagged
    the same way: the field itself is retired (spec §4.1), not its value."""
    post = _post("bogus")
    fired = {f.rule_id for f in lint.lint(post, [], Path("/nonexistent"))}
    assert "frontmatter-legacy-status" in fired


# ---------- byte-mark (§4.3.2.3) ---------- #


def test_structural_negative_level_flagged(tmp_path):
    root = _root(tmp_path)
    post = _post()
    mark = segments.Segment(atom="structural", address="el=1", level=0)
    post.content = segments.emit([mark])
    assert "structural-level-invalid" in _fired(post, root)


def test_structural_valid_level_clean(tmp_path):
    root = _root(tmp_path)
    post = _post()
    mark = segments.Segment(atom="structural", address="el=1", level=1, entry="H")
    post.content = segments.emit([mark])
    assert "structural-level-invalid" not in _fired(post, root)


# ---------- form-coherence (§4.3.2.1, §7.8) ---------- #


def _conversation(participants, messages):
    """messages: list of (participant_index, turn_n, text)."""
    segs = [
        segments.Segment(
            atom="text", overlay="text/message", address=f"turn={n}", body=text,
            extra={"participant": p},
        )
        for (p, n, text) in messages
    ]
    return segments.Section(form="conversation", segments=segs,
                            extra={"participants": participants})


def test_conforming_conversation_is_clean(tmp_path):
    root = _root(tmp_path)
    post = _post()
    sec = _conversation(["Andy <a@x>", "Steven <s@y>"],
                        [(0, 1, "hi"), (1, 2, "yo"), (0, 3, "hey")])
    post.content = segments.emit([sec])
    fired = _fired(post, root)
    assert not any(f.startswith("form-") for f in fired)


def test_missing_envelope_field_errors(tmp_path):
    root = _root(tmp_path)
    post = _post()
    sec = segments.Section(
        form="conversation",
        segments=[segments.Segment(atom="text", overlay="text/message",
                                   address="turn=1", body="hi", extra={"participant": 0})],
    )  # no participants codebook
    post.content = segments.emit([sec])
    findings = lint.lint(post, segments.iter_blocks(post.content), root)
    envelope = [f for f in findings if f.rule_id == "form-envelope-missing"]
    assert envelope and envelope[0].severity == "error"


def test_codebook_index_out_of_range_errors(tmp_path):
    root = _root(tmp_path)
    post = _post()
    sec = _conversation(["Andy <a@x>"], [(3, 1, "hi")])  # index 3 into a 1-element codebook
    post.content = segments.emit([sec])
    findings = lint.lint(post, segments.iter_blocks(post.content), root)
    oor = [f for f in findings if f.rule_id == "form-codebook-index-out-of-range"]
    assert oor and oor[0].severity == "error"


def test_nonmonotonic_turns_warn(tmp_path):
    root = _root(tmp_path)
    post = _post()
    sec = _conversation(["A <a>", "B <b>"], [(0, 5, "a"), (1, 2, "b")])  # 2 follows 5
    post.content = segments.emit([sec])
    assert "form-address-nonmonotonic" in _fired(post, root)


def test_unknown_form_warns(tmp_path):
    root = _root(tmp_path)
    post = _post()
    sec = segments.Section(
        form="not-a-real-form",
        segments=[segments.Segment(atom="text", address="turn=1", body="x")],
    )
    post.content = segments.emit([sec])
    assert "form-overlay-unknown" in _fired(post, root)


def test_form_overlays_bundled(tmp_path):
    root = _root(tmp_path)
    for fid in ("conversation", "statement", "receipt"):
        ov = schemas.load_form_overlay(root, fid)
        assert ov and ov.get("kind") == "form"
        assert "checks" in ov
    assert set(schemas.list_form_overlays(root)) >= {"conversation", "statement", "receipt"}


# ---------- mixed-artifact top level: formless segments before a section (§4.3.2.1) ---------- #


def _mixed_statement() -> str:
    """The spec's worked example (§4.3.2.1): a page-1 cover letter as a bare formless `image`
    segment, then a `statement` section over pages 2-6."""
    cover = segments.Segment(
        atom="image", address="page=1",
        description="Cover letter accompanying the March statement.",
    )
    sec = segments.Section(
        form="statement", address="pages=2-6",
        extra={"account": "…7841", "period": "2026-03"},
        segments=[
            segments.Segment(atom="text", overlay="text/ocr", address="page=2", body="opening"),
            segments.Segment(atom="text", overlay="text/ocr", address="page=6", body="closing"),
        ],
    )
    return segments.emit([cover, sec])


def test_formless_segments_before_section_parse():
    """The worked example parses: a formless top-level segment, then the section + children.
    (Before the fix this raised 'sections and segments cannot mix'.)"""
    blocks = segments.iter_blocks(_mixed_statement())
    assert isinstance(blocks[0], segments.Segment) and blocks[0].address == "page=1"
    assert isinstance(blocks[1], segments.Section) and blocks[1].form == "statement"
    assert blocks[1].address == "pages=2-6"
    assert [s.address for s in blocks[1].segments] == ["page=2", "page=6"]
    assert len(blocks) == 2  # the cover segment is NOT absorbed into the section


def test_mixed_statement_lints_clean(tmp_path):
    root = _root(tmp_path)
    post = _post()
    # A full record so only form/mixing rules can speak: PDF artifact (page=1 is a renderable
    # self-slice, not a missing embed) + an origin.
    records.set_artifact_block(post, mime="application/pdf", fields={})
    records.append_origin_block(post, uri="file:///march.pdf", snapshot="2026-03-31T00:00:00Z")
    post.content = _mixed_statement()
    findings = lint.lint(post, segments.iter_blocks(post.content), root)
    assert not [f for f in findings if f.severity == "error"], [f.rule_id for f in findings]


def test_two_sections_with_leading_formless_segment_parse():
    cover = segments.Segment(atom="image", address="page=1")
    sec_a = segments.Section(
        form="statement", address="pages=2-3", extra={"account": "a", "period": "2026-01"},
        segments=[segments.Segment(atom="text", overlay="text/ocr", address="page=2", body="a")],
    )
    sec_b = segments.Section(
        form="statement", address="pages=4-5", extra={"account": "a", "period": "2026-02"},
        segments=[segments.Segment(atom="text", overlay="text/ocr", address="page=4", body="b")],
    )
    blocks = segments.iter_blocks(segments.emit([cover, sec_a, sec_b]))
    assert [type(b).__name__ for b in blocks] == ["Segment", "Section", "Section"]
    assert blocks[0].address == "page=1"
    assert (blocks[1].address, blocks[2].address) == ("pages=2-3", "pages=4-5")


def test_whole_record_section_rejects_formless_sibling():
    import pytest

    cover = segments.Segment(atom="image", address="page=1")
    sec = segments.Section(  # whole-record: address omitted → spans the entire zone
        form="conversation", extra={"participants": ["A x"]},
        segments=[segments.Segment(atom="text", overlay="text/message", address="turn=1",
                                   body="hi", extra={"participant": 0})],
    )
    with pytest.raises(ValueError, match="whole-record section"):
        segments.iter_blocks(segments.emit([cover, sec]))


def test_sectionless_flat_record_still_parses():
    """The default case is untouched: a bare flat run of formless segments."""
    body = segments.emit([
        segments.Segment(atom="text", address="el=1", body="one"),
        segments.Segment(atom="text", address="el=2", body="two"),
    ])
    blocks = segments.iter_blocks(body)
    assert [b.address for b in blocks] == ["el=1", "el=2"]
    assert all(isinstance(b, segments.Segment) for b in blocks)


# ---------- codefence balance vs verbatim chat text (§12.18 step 4) ---------- #


def test_codefence_unbalanced_skips_verbatim_transcript_bodies(tmp_path):
    root = _root(tmp_path)
    # A chat user genuinely typed a bare ``` — verbatim content in a text/message body, not a
    # truncation artifact. The balance rule must not fire on it.
    sec = segments.Section(
        form="conversation", extra={"participants": ["A x"]},
        segments=[segments.Segment(atom="text", overlay="text/message", address="turn=1",
                                   body="here's code:\n```\nprint(1)", extra={"participant": 0})],
    )
    post = _post()
    post.content = segments.emit([sec])
    assert "body-codefence-unbalanced" not in _fired(post, root)


def test_codefence_unbalanced_still_flags_extracted_document_bodies(tmp_path):
    root = _root(tmp_path)
    # The same unpaired fence in a NON-transcript (extracted document) body still surfaces.
    post = _post()
    post.content = segments.emit([segments.Segment(atom="text", address="el=1", body="```\nx")])
    assert "body-codefence-unbalanced" in _fired(post, root)


# ---------- form/document + the `sheet` axis (spreadsheets, §7.8) ---------- #


def _sheet_section(name: str, addrs: list[str]) -> segments.Section:
    """One `document`-form section over a single spreadsheet worksheet — `addrs` are the
    child segments' own (possibly `&bbox=`-narrowed) addresses, all sharing `name`."""
    segs = [
        segments.Segment(
            atom="text", overlay="text/data-table", address=a,
            body="| a | b |\n| --- | --- |\n| 1 | 2 |",
        )
        for a in addrs
    ]
    return segments.Section(form="document", address=f"sheet={name}", entry=name, segments=segs)


def test_document_form_admits_sheet_axis_clean(tmp_path):
    """A multi-sheet, formed document record — one section per worksheet, some children
    narrowed with `&bbox=`, one tab name carrying a percent-encoded `&` (SPEC's xlsx/xls
    address scheme) — lints with NO form-coherence findings now that `document` declares
    `sheet` among its checked address axes."""
    root = _root(tmp_path)
    post = _post()
    sec_inputs = _sheet_section("INPUTS", ["sheet=INPUTS&bbox=A1:B2", "sheet=INPUTS&bbox=A6:E11"])
    sec_overview = _sheet_section("Overview %26 Results", ["sheet=Overview %26 Results"])
    post.content = segments.emit([sec_inputs, sec_overview])
    fired = _fired(post, root)
    assert not any(f.startswith("form-") for f in fired), fired


def test_document_form_still_flags_an_axis_outside_the_declared_set(tmp_path):
    """The axis-set check stays strict: a child address on a param `document` does not
    declare (e.g. a non-worksheet OOXML container part, `xpath=`) still warns."""
    root = _root(tmp_path)
    post = _post()
    sec = segments.Section(
        form="document", address="sheet=Charts", entry="Charts",
        segments=[segments.Segment(atom="image", address="xpath=/xl/media/image1.png")],
    )
    post.content = segments.emit([sec])
    assert "form-address-axis" in _fired(post, root)


def test_statement_pages_axis_nonmonotonic_still_flagged(tmp_path):
    """Regression: adding `sheet` to `document`'s axes (a string-valued, unordered axis)
    must not weaken monotonic enforcement elsewhere — `statement`'s numeric `pages` axis
    (per-section child addresses, §4.3.2.1) still catches a genuinely out-of-order run."""
    root = _root(tmp_path)
    post = _post()
    sec = segments.Section(
        form="statement", address="pages=1-4", extra={"account": "a", "period": "2026-03"},
        segments=[
            segments.Segment(atom="text", overlay="text/ocr", address="page=3", body="x"),
            segments.Segment(atom="text", overlay="text/ocr", address="page=1", body="y"),
        ],
    )
    post.content = segments.emit([sec])
    assert "form-address-nonmonotonic" in _fired(post, root)


# ---------- co-addressed segment pairings (§7.8 `checks.paired_segments`) ---------- #


def _schematic_sheet(*, with_table: bool) -> segments.Section:
    """A `form/schematic` sheet: the figure marker, optionally its from-to sibling."""
    segs = [segments.Segment(atom="image", overlay="image/figure", address="el=3")]
    if with_table:
        segs.append(
            segments.Segment(
                atom="text",
                overlay="text/data-table",
                address="el=3&bbox=0,0,2700,1920",
                body="| From component | To component |\n|---|---|\n| B+ | Fuse F5 |\n",
            )
        )
    return segments.Section(form="schematic", segments=segs)


def test_schematic_figure_with_from_to_sibling_is_clean(tmp_path):
    root = _root(tmp_path)
    post = _post()
    post.content = segments.emit([_schematic_sheet(with_table=True)])
    assert not any(f.startswith("form-") for f in _fired(post, root))


def test_schematic_figure_without_from_to_sibling_errors(tmp_path):
    """The pair IS the contract: a sheet whose relation was never transcribed is a gate
    failure, not a record that merely looks finished."""
    root = _root(tmp_path)
    post = _post()
    post.content = segments.emit([_schematic_sheet(with_table=False)])
    findings = lint.lint(post, segments.iter_blocks(post.content), root)
    pair = [f for f in findings if f.rule_id == "form-segment-pair-missing"]
    assert len(pair) == 1
    assert pair[0].severity == "error"
    assert "el=3" in (pair[0].address or "")


def test_schematic_pair_must_share_the_address(tmp_path):
    """A from-to table addressing a DIFFERENT region does not satisfy the figure's
    obligation — the pairing is co-addressed (§4.3.2.2 same-region stacking)."""
    root = _root(tmp_path)
    post = _post()
    sec = segments.Section(
        form="schematic",
        segments=[
            segments.Segment(atom="image", overlay="image/figure", address="el=3"),
            segments.Segment(atom="text", overlay="text/data-table",
                             address="el=9&bbox=0,0,10,10", body="| a |\n|---|\n| b |\n"),
        ],
    )
    post.content = segments.emit([sec])
    assert "form-segment-pair-missing" in _fired(post, root)


def test_document_figure_needs_no_pairing(tmp_path):
    """The obligation is `schematic`'s alone — a `document` page's figures (a component
    photo, a location illustration) stand alone exactly as before."""
    root = _root(tmp_path)
    post = _post()
    sec = segments.Section(
        form="document",
        segments=[segments.Segment(atom="image", overlay="image/figure", address="el=3")],
    )
    post.content = segments.emit([sec])
    assert "form-segment-pair-missing" not in _fired(post, root)
