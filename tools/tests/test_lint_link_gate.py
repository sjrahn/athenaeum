"""`subject-link-flattened` — the #52/#118 link gate registered in `corpus.lint`'s default
rule set. Config-driven (a host with no `regions:` declaration is never judged, §7.2) and
parse-tolerant (a missing artifact silently does not fire)."""

from __future__ import annotations

import frontmatter

from corpus import hashing, lint, paths, records, schemas, segments
from corpus.store import LocalArtifactStore

HOST = "linkgate.example.com"

_OVERLAY_WITH_SUBJECT = """\
regions:
  - role: article
    selector: div.article
    renders: subject
"""

_OVERLAY_NO_SUBJECT = """\
regions:
  - role: rail
    selector: div.rail
    renders: framing
"""


def _make_corpus(tmp_path, overlay_yaml: str | None):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    overlay_dir = root / "schema" / "origin" / "web"
    overlay_dir.mkdir(parents=True)
    if overlay_yaml is not None:
        (overlay_dir / f"{HOST}.yaml").write_text(overlay_yaml, encoding="utf-8")
    schemas.cache_clear()
    return root


def _record_from_blocks(
    tmp_path,
    html: str,
    blocks: list,
    *,
    overlay_yaml: str | None = _OVERLAY_WITH_SUBJECT,
    with_artifact: bool = True,
    with_origin: bool = True,
):
    """Build a synthetic record whose content zone is the properly marked-up serialization
    of `blocks` — `iter_blocks` (which the rule under test reparses) recognizes only real
    `<!--segment ...-->` / `<!--section ...-->` openers, never bare prose."""
    root = _make_corpus(tmp_path, overlay_yaml)
    src = root / "page.html"
    src.write_text(html, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    if with_artifact:
        LocalArtifactStore(root).put(rid, "html", src)

    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime="text/html", fields={})
    if with_origin:
        records.append_origin_block(
            post,
            uri=f"https://{HOST}/p",
            snapshot="2026-01-01T00:00:00Z",
            schema_id=HOST,
        )
    post.content = segments.emit(blocks)
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return post, root


def _record(tmp_path, html: str, text: str, **kwargs):
    """A record whose whole content zone is one top-level text segment carrying `text`."""
    return _record_from_blocks(
        tmp_path, html, [segments.Segment(atom="text", body=text)], **kwargs
    )


def _findings(post, root):
    blocks = segments.iter_blocks(post.content or "")
    return [f for f in lint.lint(post, blocks, root) if f.rule_id == "subject-link-flattened"]


_HTML = '<div class="article"><a href="/torque">Torque Spec</a></div>'


def test_fires_with_the_right_count_and_sample(tmp_path):
    post, root = _record(tmp_path, _HTML, "See the Torque Spec for details.")
    findings = _findings(post, root)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "error"
    assert finding.fields["flattened"] == 1
    assert finding.fields["subject_anchors"] == 1
    assert finding.fields["sample"] == ["Torque Spec"]
    assert "1 of 1 subject-region anchor(s) render flattened" in finding.message
    assert "Torque Spec" in finding.message
    assert "#118" in finding.message


def test_does_not_fire_without_a_subject_regions_declaration(tmp_path):
    post, root = _record(
        tmp_path,
        _HTML,
        "See the Torque Spec for details.",
        overlay_yaml=_OVERLAY_NO_SUBJECT,
    )
    assert _findings(post, root) == []


def test_does_not_fire_with_no_overlay_at_all(tmp_path):
    post, root = _record(
        tmp_path,
        _HTML,
        "See the Torque Spec for details.",
        overlay_yaml=None,
    )
    assert _findings(post, root) == []


def test_does_not_fire_when_the_artifact_is_missing(tmp_path):
    post, root = _record(
        tmp_path,
        _HTML,
        "See the Torque Spec for details.",
        with_artifact=False,
    )
    assert _findings(post, root) == []


def test_does_not_fire_when_all_anchors_are_linked(tmp_path):
    post, root = _record(tmp_path, _HTML, "See the [Torque Spec](/torque) for details.")
    assert _findings(post, root) == []


def test_does_not_fire_without_an_origin_declaring_the_host(tmp_path):
    post, root = _record(
        tmp_path,
        _HTML,
        "See the Torque Spec for details.",
        with_origin=False,
    )
    assert _findings(post, root) == []


def test_does_not_fire_when_flattened_text_only_appears_in_a_nav_span(tmp_path):
    """#89's restoration renders the page's own breadcrumb as plain text inside a trailing
    `form/nav` span, and a crumb label routinely repeats a subject anchor's own text. That
    must not be scored as a flattening — the anchor's text was never placed in the body's
    own content, only in the nav span's unrelated rendering."""
    blocks = [
        segments.Segment(atom="text", body="Unrelated prose about a different repair."),
        segments.Section(
            form="nav",
            segments=[segments.Segment(atom="text", body="Vehicle > Torque Spec")],
        ),
    ]
    post, root = _record_from_blocks(tmp_path, _HTML, blocks)
    assert _findings(post, root) == []
