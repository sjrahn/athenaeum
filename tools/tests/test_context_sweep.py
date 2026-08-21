"""The `sweep` namespace of the unified `context` block (spec §4.3.3.6, v31).

Covers: the packaged `context/sweep/sweep.yaml` overlay resolving both the bare
`sweep` namespace lookup (`context-namespace-unknown`'s check) and the full
`sweep/extraction` class-id; the `iter_sweep_blocks`/`append_sweep_block` accessors;
the `sweeps()` / `swept_bands()` derived views; and the four new lint rules —
`sweep-shape` (`sweep-kind-invalid` + `sweep-detector-format`), `sweep-address-invalid`,
and `sweep-band-overlap`.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import derived_views, lint, records, schemas, segments

RID = "a1" * 32


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _post(mime: str = "audio/mpeg") -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata.update({"id": RID, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime=mime, fields={"title": "T"})
    records.append_origin_block(
        post, uri="https://example.com/a", snapshot="2026-06-05T00:00:00Z"
    )
    return post


def _lint(post, root, blocks=()):
    return lint.lint(post, list(blocks), root)


DETECTOR = "corpus.draft.mime/audio@0.1.0"


# ---------- schema resolution ---------- #


def test_sweep_namespace_schema_resolves(tmp_path):
    root = _corpus(tmp_path)
    # The bare-namespace lookup `_rule_context_shape` makes (context-namespace-unknown).
    assert schemas.load_context_schema(root, "sweep") is not None
    # The full class-id a lookup by opener id would use.
    assert schemas.load_context_schema(root, "sweep/extraction") is not None


# ---------- parse / emit round-trip + accessors ---------- #


def test_sweep_block_round_trips(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-3600"
    )
    p = root / "records" / f"{RID}.md"
    records.dump(post, p)
    raw = p.read_text("utf-8")
    assert "<!--context sweep/extraction" in raw

    loaded = records.load(p)
    assert list(records.iter_sweep_blocks(loaded)) == [
        {
            "id": "extraction",
            "subtype": None,
            "fields": {
                "kind": "text/ocr",
                "detector": DETECTOR,
                "address": "time_range=0-3600",
            },
        }
    ]


def test_sweep_block_whole_transport_omits_address(tmp_path):
    post = _post()
    records.append_sweep_block(post, kind="structural", detector=DETECTOR)
    fields = next(iter(records.iter_sweep_blocks(post)))["fields"]
    assert "address" not in fields


# ---------- derived views ---------- #


def test_context_view_includes_sweep_namespace(tmp_path):
    post = _post()
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-3600"
    )
    ctx = derived_views.context(post)
    assert ctx == [
        {
            "namespace": "sweep",
            "id": "extraction",
            "kind": "text/ocr",
            "detector": DETECTOR,
            "address": "time_range=0-3600",
        }
    ]


def test_sweeps_view_projection(tmp_path):
    post = _post()
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-3600"
    )
    assert derived_views.sweeps(post) == [
        {
            "id": "extraction",
            "kind": "text/ocr",
            "detector": DETECTOR,
            "address": "time_range=0-3600",
        }
    ]


def test_swept_bands_groups_by_kind(tmp_path):
    post = _post()
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-10"
    )
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=20-30"
    )
    records.append_sweep_block(post, kind="structural", detector=DETECTOR)
    assert derived_views.swept_bands(post) == {
        "text/ocr": ["time_range=0-10", "time_range=20-30"],
        "structural": [None],
    }


# ---------- lint: sweep-shape ---------- #


def test_sweep_missing_kind_and_detector(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_context_block(post, namespace="sweep", id="extraction", fields={})
    findings = _lint(post, root)
    rule_ids = {f.rule_id for f in findings}
    assert "sweep-kind-invalid" in rule_ids
    assert "sweep-detector-format" in rule_ids


def test_sweep_kind_structural_and_bare_atom_resolve(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(post, kind="structural", detector=DETECTOR)
    records.append_sweep_block(post, kind="text", detector=DETECTOR, address="time_range=0-10")
    findings = _lint(post, root)
    assert not any(f.rule_id == "sweep-kind-invalid" for f in findings)


def test_sweep_kind_declared_atom_overlay_resolves(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-10"
    )
    findings = _lint(post, root)
    assert not any(f.rule_id == "sweep-kind-invalid" for f in findings)


def test_sweep_kind_unresolvable_flagged(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(post, kind="text/nonexistent", detector=DETECTOR)
    findings = _lint(post, root)
    assert any(f.rule_id == "sweep-kind-invalid" for f in findings)


def test_sweep_detector_bad_format(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(post, kind="structural", detector="not a touch id")
    findings = _lint(post, root)
    assert any(f.rule_id == "sweep-detector-format" for f in findings)


# ---------- lint: sweep-address-invalid ---------- #


def test_sweep_address_undeclared_axis(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(
        post, kind="structural", detector=DETECTOR, address="bogus_axis=1-2"
    )
    findings = _lint(post, root)
    assert any(f.rule_id == "sweep-address-invalid" for f in findings)


def test_sweep_address_declared_axis_clean(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(
        post, kind="structural", detector=DETECTOR, address="time_range=0-3600"
    )
    findings = _lint(post, root)
    assert not any(f.rule_id == "sweep-address-invalid" for f in findings)


def test_sweep_address_region_grammar_reused(tmp_path):
    """A region-shaped value in a sweep address (`bbox=` in pixels, not fractions) fails
    the same region grammar `address-region-invalid` checks on segment addresses."""
    root = _corpus(tmp_path)
    post = _post(mime="application/pdf")
    records.append_sweep_block(
        post, kind="structural", detector=DETECTOR, address="page=1&bbox=0,0,2700,1920"
    )
    findings = _lint(post, root)
    assert any(f.rule_id == "sweep-address-invalid" for f in findings)


# ---------- lint: sweep-band-overlap ---------- #


def test_sweep_band_overlap_same_kind_overlapping_ranges(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-3600"
    )
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=1800-4000"
    )
    findings = _lint(post, root)
    assert any(f.rule_id == "sweep-band-overlap" for f in findings)


def test_sweep_band_no_overlap_disjoint_ranges_clean(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-10"
    )
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=20-30"
    )
    findings = _lint(post, root)
    assert not any(f.rule_id == "sweep-band-overlap" for f in findings)


def test_sweep_band_different_kind_never_overlaps(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-3600"
    )
    records.append_sweep_block(
        post, kind="structural", detector=DETECTOR, address="time_range=0-3600"
    )
    findings = _lint(post, root)
    assert not any(f.rule_id == "sweep-band-overlap" for f in findings)


def test_sweep_band_missing_address_is_whole_transport(tmp_path):
    """A sweep with no `address:` covers the whole transport — it overlaps every other
    band of its kind, even a narrow one (spec §4.3.3.6)."""
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(post, kind="text/ocr", detector=DETECTOR)  # whole transport
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-10"
    )
    findings = _lint(post, root)
    assert any(f.rule_id == "sweep-band-overlap" for f in findings)


def test_sweep_band_two_whole_transport_sweeps_overlap(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_sweep_block(post, kind="text/ocr", detector=DETECTOR)
    records.append_sweep_block(post, kind="text/ocr", detector=DETECTOR)
    findings = _lint(post, root)
    assert any(f.rule_id == "sweep-band-overlap" for f in findings)


def test_sweep_band_non_range_axis_mismatch_no_overlap(tmp_path):
    """Two sweeps over the SAME time range but different `stream_id=` axes address
    different sub-populations — the non-range axis disproves overlap even though the
    range axis alone would look identical."""
    root = _corpus(tmp_path)
    post = _post(mime="video/mp4")
    records.append_sweep_block(
        post,
        kind="text/ocr",
        detector=DETECTOR,
        address="stream_id=a0&time_range=0-10",
    )
    records.append_sweep_block(
        post,
        kind="text/ocr",
        detector=DETECTOR,
        address="stream_id=a1&time_range=0-10",
    )
    findings = _lint(post, root)
    assert not any(f.rule_id == "sweep-band-overlap" for f in findings)


def test_sweep_band_conservative_when_ranges_not_comparable(tmp_path):
    """Two same-kind sweeps whose addresses share no param axis at all can't be disproven
    — the rule flags rather than silently passing (spec §4.3.3.6: fail-closed). (A shared
    NON-range axis with differing values, like `page=1` vs `page=2`, DOES disprove overlap
    — that's `test_sweep_band_non_range_axis_mismatch_no_overlap`'s case, generalized.)"""
    root = _corpus(tmp_path)
    post = _post(mime="application/pdf")
    records.append_sweep_block(post, kind="structural", detector=DETECTOR, address="page=1")
    records.append_sweep_block(
        post, kind="structural", detector=DETECTOR, address="bbox=0.1,0.1,0.2,0.2"
    )
    findings = _lint(post, root)
    assert any(f.rule_id == "sweep-band-overlap" for f in findings)


# ---------- integration: sweep + segments together ---------- #


def test_integration_two_ocr_segments_with_exhaustive_sweep_lints_clean(tmp_path):
    root = _corpus(tmp_path)
    post = _post(mime="video/h264")
    seg1 = segments.Segment(
        atom="text", overlay="text/ocr", address="time_range=0-5", body="hello"
    )
    seg2 = segments.Segment(
        atom="text", overlay="text/ocr", address="time_range=10-15", body="world"
    )
    blocks = [seg1, seg2]
    post.content = segments.emit(blocks)
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-3600"
    )
    findings = _lint(post, root, blocks)
    assert findings == []


def test_integration_overlapping_second_sweep_fails(tmp_path):
    root = _corpus(tmp_path)
    post = _post(mime="video/h264")
    seg1 = segments.Segment(
        atom="text", overlay="text/ocr", address="time_range=0-5", body="hello"
    )
    seg2 = segments.Segment(
        atom="text", overlay="text/ocr", address="time_range=10-15", body="world"
    )
    blocks = [seg1, seg2]
    post.content = segments.emit(blocks)
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=0-3600"
    )
    records.append_sweep_block(
        post, kind="text/ocr", detector=DETECTOR, address="time_range=1800-4000"
    )
    findings = _lint(post, root, blocks)
    assert any(f.rule_id == "sweep-band-overlap" for f in findings)


def test_integration_sweep_with_nonexistent_kind_fails(tmp_path):
    root = _corpus(tmp_path)
    post = _post(mime="video/h264")
    seg1 = segments.Segment(
        atom="text", overlay="text/ocr", address="time_range=0-5", body="hello"
    )
    blocks = [seg1]
    post.content = segments.emit(blocks)
    records.append_sweep_block(post, kind="text/nonexistent", detector=DETECTOR)
    findings = _lint(post, root, blocks)
    assert any(f.rule_id == "sweep-kind-invalid" for f in findings)
