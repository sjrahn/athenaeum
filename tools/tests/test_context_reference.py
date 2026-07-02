"""The unified `context` annotations block + the `reference` namespace (spec §4.3.3).

Covers: context block parse/emit round-trip (any namespace, with the `quote`/`occurrence`
locator); the legacy `<!--issue-->` read path upgrading to `<!--context issue/…-->` on write;
the `context()` derived view + its `issues()` projection; and the reference citation ladder +
its lint (`reference-unresolved`, `context-namespace-unknown`).
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import derived_views, lint, paths, records, segments

RID = "a1" * 32
TARGET = "b2" * 32
_ISSUE_FIELDS = {"severity": "warning", "resolution": "open", "detector": "corpus.ingest@0.1.0"}


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _post(rid: str = RID) -> frontmatter.Post:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html")
    records.append_origin_block(post, uri="https://example.com/a", snapshot="2026-06-05T00:00:00Z")
    post.metadata["status"] = "draft"
    return post


def _lint(post, root):
    return lint.lint(post, segments.iter_blocks(post.content or ""), root)


# ---------- parse / emit round-trip ---------- #


def test_context_block_round_trips(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_context_block(
        post,
        namespace="reference",
        id="reference",
        fields={"address": "el=3", "quote": "as Piketty argues", "attribution_text": "Capital"},
    )
    p = paths.record_path(root, RID)
    records.dump(post, p)
    raw = p.read_text("utf-8")
    assert "<!--context reference" in raw  # bare namespace collapse (id == namespace)
    loaded = records.load(p)
    ctx = list(records.iter_context_blocks(loaded))
    assert ctx == [
        {
            "namespace": "reference",
            "id": "reference",
            "subtype": None,
            "fields": {
                "address": "el=3",
                "quote": "as Piketty argues",
                "attribution_text": "Capital",
            },
        }
    ]


def test_legacy_issue_block_reads_and_upgrades(tmp_path):
    # A record still written with `<!--issue X-->` parses as the `issue` namespace and is
    # re-emitted in the canonical `<!--context issue/X-->` form. Build a valid record via the
    # emitter, then downgrade just the opener to the legacy form on disk.
    root = _corpus(tmp_path)
    p = paths.record_path(root, RID)
    seeded = _post()
    records.append_issue_block(
        seeded, id="paywall", severity="warning", resolution="open", detector="corpus.ingest@0.1.0"
    )
    records.dump(seeded, p)
    p.write_text(
        p.read_text("utf-8").replace("<!--context issue/paywall", "<!--issue paywall"),
        encoding="utf-8",
    )

    loaded = records.load(p)
    assert list(records.iter_context_blocks(loaded)) == [
        {
            "namespace": "issue",
            "id": "paywall",
            "subtype": None,
            "fields": _ISSUE_FIELDS,
        }
    ]
    records.dump(loaded, p)
    raw = p.read_text("utf-8")
    assert "<!--context issue/paywall" in raw and "<!--issue" not in raw


# ---------- derived views ---------- #


def test_context_view_and_issues_projection(tmp_path):
    post = _post()
    records.append_issue_block(
        post, id="paywall", severity="warning", resolution="open", detector="corpus.ingest@0.1.0"
    )
    records.append_context_block(
        post, namespace="reference", id="reference", fields={"attribution_text": "Capital"}
    )
    ctx = derived_views.context(post)
    assert {c["namespace"] for c in ctx} == {"issue", "reference"}
    # issues() is exactly the issue-namespace projection.
    assert derived_views.issues(post) == [{"id": "paywall", **_ISSUE_FIELDS}]


# ---------- reference ladder + lint ---------- #


def test_reference_resolved_to_captured_record_lints_clean(tmp_path):
    root = _corpus(tmp_path)
    # The target source record must exist for `source_uri` to resolve.
    target = _post(TARGET)
    records.dump(target, paths.record_path(root, TARGET))

    post = _post()
    records.append_context_block(
        post,
        namespace="reference",
        id="reference",
        fields={
            "address": "el=3",
            "quote": "Capital in the Twenty-First Century",
            "occurrence": 1,
            "attribution_text": "Piketty, Capital",
            "source_url": "https://example.com/piketty",
            "source_uri": f"corpus://{TARGET}",
        },
    )
    findings = _lint(post, root)
    assert not any(f.rule_id == "reference-unresolved" for f in findings)
    assert not any(f.rule_id == "context-namespace-unknown" for f in findings)


def test_reference_dangling_source_uri_warns(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_context_block(
        post,
        namespace="reference",
        id="reference",
        fields={"source_uri": f"corpus://{'cc' * 32}"},  # no such record
    )
    findings = _lint(post, root)
    refs = [f for f in findings if f.rule_id == "reference-unresolved"]
    assert len(refs) == 1 and refs[0].severity == "warning"


def test_unknown_context_namespace_warns(tmp_path):
    root = _corpus(tmp_path)
    post = _post()
    records.append_context_block(post, namespace="bogus", id="bogus", fields={})
    findings = _lint(post, root)
    assert any(f.rule_id == "context-namespace-unknown" for f in findings)
    # The shipped namespaces (issue, reference) resolve via the packaged defaults → no warning.
    post2 = _post()
    records.append_context_block(
        post2, namespace="reference", id="reference", fields={"attribution_text": "x"}
    )
    assert not any(f.rule_id == "context-namespace-unknown" for f in _lint(post2, root))
