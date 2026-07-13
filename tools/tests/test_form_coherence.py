"""3.0 form-coherence + byte-mark + two-status lint (spec §4.3.2.1, §4.3.2.3, §7.8, §4.1).

The form overlays (`conversation`, `statement`, `receipt`) ship in the package, so a
tmp corpus with an empty `schema/` resolves them via the packaged fallback."""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import lint, schemas, segments


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _post(status: str = "stub") -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": "a" * 64, "title": "", "description": "d", "status": status,
         "touch": "corpus.ingest@0.1.0"}
    )
    return post


def _fired(post, root):
    return {f.rule_id for f in lint.lint(post, segments.iter_blocks(post.content or ""), root)}


# ---------- two-status lifecycle (§4.1) ---------- #


def test_draft_status_tolerated():
    post = _post("draft")
    assert not any(
        f.rule_id == "status-invalid"
        for f in lint.lint(post, [], Path("/nonexistent"))
    )


def test_unknown_status_flagged():
    post = _post("bogus")
    fired = {f.rule_id for f in lint.lint(post, [], Path("/nonexistent"))}
    assert "status-invalid" in fired


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
