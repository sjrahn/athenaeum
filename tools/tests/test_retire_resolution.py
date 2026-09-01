"""`corpus retire-resolution` — the v42 lifecycle sweep (spec §4.3.3.2, CHANGELOG v42).

The contract worth pinning: `open`/`wontfix` blocks stand minus the field, `fixed`/
`superseded` blocks drop outright, an unknown corpus-local value strips conservatively
(block kept, value reported), non-issue namespaces and clean records are untouched, and
the sweep is idempotent.
"""

from __future__ import annotations

import frontmatter

from corpus import records
from corpus._cli.retire_resolution import sweep_post

RID = "e5" * 32


def _post() -> frontmatter.Post:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=RID, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html")
    return post


def _legacy_issue(post, id_: str, resolution: str | None) -> None:
    fields = {"severity": "warning", "detector": "corpus.ingest@0.1.0"}
    if resolution is not None:
        fields["resolution"] = resolution
    records.append_context_block(post, namespace="issue", id=id_, fields=fields)


def _issue_ids(post) -> list[str]:
    return [i["id"] for i in records.iter_issue_blocks(post)]


def test_open_and_wontfix_stand_minus_the_field():
    post = _post()
    _legacy_issue(post, "paywall", "open")
    _legacy_issue(post, "format-loss", "wontfix")
    counts = sweep_post(post)
    assert counts == {"stripped": 2}
    assert _issue_ids(post) == ["paywall", "format-loss"]
    assert all("resolution" not in i["fields"] for i in records.iter_issue_blocks(post))


def test_fixed_and_superseded_drop_outright():
    post = _post()
    _legacy_issue(post, "encoding-artifact", "fixed")
    _legacy_issue(post, "partial-content", "superseded")
    _legacy_issue(post, "paywall", "open")
    counts = sweep_post(post)
    assert counts["dropped"] == 2 and counts["stripped"] == 1
    assert _issue_ids(post) == ["paywall"]


def test_an_unknown_value_strips_conservatively_and_is_reported():
    """The sweep never deletes on a value it does not understand."""
    post = _post()
    _legacy_issue(post, "format-loss", "needs-human-review")
    counts = sweep_post(post)
    assert counts["stripped"] == 1
    assert counts["kept-unknown:needs-human-review"] == 1
    assert _issue_ids(post) == ["format-loss"]


def test_a_clean_record_is_untouched_and_the_sweep_is_idempotent():
    post = _post()
    _legacy_issue(post, "paywall", None)  # already lifecycle-free
    records.append_context_block(
        post, namespace="sweep", id="extraction",
        fields={"kind": "text/ocr", "detector": "corpus.ingest@0.1.0"},
    )
    assert not sweep_post(post)  # empty counter ⇒ nothing to write

    _legacy_issue(post, "format-loss", "open")
    assert sweep_post(post) == {"stripped": 1}
    assert not sweep_post(post)  # second pass: nothing left to do
    # the non-issue namespace rode through untouched
    assert [c["namespace"] for c in post.metadata["_contexts"]] == ["issue", "sweep", "issue"]
