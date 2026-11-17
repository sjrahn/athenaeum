"""A page's `<link rel=canonical>` joins the origin's uri list only when it names the
resource the capture retrieved (spec §7.2: one origin block, one resource's spellings).

open.alberta.ca points a superseded publication's canonical at its SUCCESSOR
(`/publications/9781460125519` → `/publications/9781460141861`), which made the record
claim another publication's URL.
"""

from __future__ import annotations

import frontmatter

from corpus import records
from corpus.derive import apply_drafter_result, canonical_names_retrieved

_PUB = "https://open.alberta.ca/publications/9781460125519"


def test_same_resource_canonical_is_admitted():
    assert canonical_names_retrieved(_PUB + "/", [_PUB]) == _PUB + "/"
    assert canonical_names_retrieved("https://www.example.com/a?x=1",
                                     ["http://example.com/a/?utm_source=t"]) is not None
    assert canonical_names_retrieved("/publications/9781460125519", [_PUB]) == _PUB


def test_a_canonical_naming_another_resource_is_refused():
    assert canonical_names_retrieved(
        "https://open.alberta.ca/publications/9781460141861", [_PUB]) is None
    assert canonical_names_retrieved("https://other.example/x", ["https://example.com/x"]) \
        is None
    assert canonical_names_retrieved("https://example.com/x", []) is None  # uri-less


def _post() -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata.update(records.stub_frontmatter(record_id="e" * 64,
                                                  touch_id="corpus.ingest@0.1.0"))
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri=_PUB, snapshot="2026-11-16T23:57:24Z")
    return post


def _uris(post) -> list[str]:
    uri = post.metadata["_origins"][-1]["fields"]["uri"]
    return uri if isinstance(uri, list) else [uri]


def test_ingest_folds_only_a_same_resource_canonical(tmp_path):
    post = _post()
    apply_drafter_result(post, {"origin_canonical_url":
                                "https://open.alberta.ca/publications/9781460141861"},
                         "text/html", tmp_path)
    assert _uris(post) == [_PUB]
    apply_drafter_result(post, {"origin_canonical_url": "https://www.open.alberta.ca"
                                "/publications/9781460125519"}, "text/html", tmp_path)
    assert _uris(post) == [_PUB, "https://www.open.alberta.ca/publications/9781460125519"]
