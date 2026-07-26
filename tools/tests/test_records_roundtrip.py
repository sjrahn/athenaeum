"""Records round-trip + roster-in-metadata-zone (reconciliation #1) tests."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import yaml

from corpus import records, schemas, segments


def _make_golden(tmp_path):
    """Hand-author a small spec-conformant record with one of every block family."""
    p = tmp_path / "ab" / ("a" * 64 + ".md")
    p.parent.mkdir(parents=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": "a" * 64,
            "description": "Test golden record exercising every block family.",
            "status": "draft",
            "transport": "sha256:" + "b" * 64,
            "touch": ["corpus.ingest@0.1.0", "corpus.draft.mime/application/pdf@0.1.0"],
        }
    )
    records.set_artifact_block(
        post,
        mime="application/pdf",
        fields={"title": "Golden", "pdf_page_count": 2},
    )
    records.append_origin_block(
        post,
        uri="https://example.com/golden.pdf",
        snapshot="2026-05-31T00:00:00Z",
        schema_id="example.com",
    )
    # Legacy 1.0 classify block — retired grammar, must still round-trip losslessly.
    post.metadata.setdefault("_classifies", []).append(
        {"namespace": "document", "id": "document", "subtype": None, "fields": {}}
    )
    # Reconciliation #1: the members roster lives in the METADATA zone.
    records.append_member(
        post,
        media_type="image/png",
        address="page=1&bbox=0.1,0.1,0.5,0.5",
        transport="blake3:" + "c" * 64,
        fields={"bytes": 4118, "alt": "Cover figure"},
    )
    # Content zone — one sectionless segment.
    seg = segments.Segment(atom="text", address="page=1", body="First page text.")
    post.content = segments.emit([seg])
    # Annotation — one record-scope issue, in OUR spec's shape.
    records.append_issue_block(
        post,
        id="encoding-artifact",
        severity="warning",
        resolution="open",
        detector="corpus.draft.mime/application/pdf@0.1.0",
    )
    return post, p


def test_dump_then_load_roundtrips_every_block(tmp_path):
    post, p = _make_golden(tmp_path)
    records.dump(post, p)
    raw = p.read_text("utf-8")

    # Sanity: the members block appears BEFORE any section/segment line (metadata zone).
    members_pos = raw.index("<!--members")
    segment_pos = raw.index("<!--segment")
    assert members_pos < segment_pos, "roster must precede content zone (reconciliation #1)"
    # And the issue (now an `issue`-namespace context block) is in the annotation zone.
    issue_pos = raw.index("<!--context issue/")
    assert segment_pos < issue_pos

    loaded = records.load(p)
    # Core frontmatter preserved. `status` is NOT among these — dumps() never emits it
    # (spec §4.1, §12.19), so a round-tripped record carries no status line to read back.
    for k in ("id", "description", "transport"):
        assert loaded.metadata[k] == post.metadata[k]
    assert loaded.metadata["touch"] == post.metadata["touch"]
    assert "status" not in loaded.metadata

    # Metadata-zone blocks preserved.
    assert records.media_type_for(loaded) == "application/pdf"
    assert records.title_for(loaded, tmp_path) == "Golden"

    origins = list(records.iter_origin_blocks(loaded))
    assert len(origins) == 1
    assert origins[0]["id"] == "example.com"
    assert origins[0]["fields"]["uri"] == "https://example.com/golden.pdf"

    classifies = list(records.iter_classify_blocks(loaded))
    assert len(classifies) == 1
    assert classifies[0]["namespace"] == "document"
    assert classifies[0]["id"] == "document"

    # The roster is parsed FROM the metadata zone.
    members = list(records.iter_members(loaded))
    assert len(members) == 1
    m = members[0]
    assert m["media_type"] == "image/png"
    assert m["address"] == "page=1&bbox=0.1,0.1,0.5,0.5"
    assert m["transport"].startswith("blake3:")
    # *(3.4)* The row is closed to four keys: `bytes` survives, the `alt` the caller passed does
    # not. Dropping at the append/emit seams is what keeps the shape closed without every
    # producer having to know about it (spec §4.3.1.4).
    assert m["fields"] == {"bytes": 4118}

    # Content zone is segments only — no roster block leaked into it.
    assert "<!--members" not in (loaded.content or "")
    content_blocks = segments.iter_blocks(loaded.content or "")
    assert len(content_blocks) == 1
    assert isinstance(content_blocks[0], segments.Segment)
    assert content_blocks[0].body == "First page text."

    # Annotation zone preserved.
    issues = list(records.iter_issue_blocks(loaded))
    assert len(issues) == 1
    assert issues[0]["id"] == "encoding-artifact"
    assert issues[0]["fields"]["severity"] == "warning"
    assert issues[0]["fields"]["resolution"] == "open"
    assert issues[0]["fields"]["detector"].startswith("corpus.")


def test_derived_classifications_view(tmp_path):
    post, p = _make_golden(tmp_path)
    records.dump(post, p)
    loaded = records.load(p)
    derived = records.derived_classifications(loaded)
    # Per spec §9.1 (2.0): mime + origin contribute; legacy classify blocks,
    # the members roster, and issues do not.
    assert derived == [
        "mime/application/pdf",
        "origin/example.com",
    ]


def test_append_origin_block_uri_optional_for_local_file():
    """A dropped-in local file records a uri-LESS origin carrying `filename`/`source_modified`
    instead of a `file://` staging path (spec §7.2). A later folded-in retrieval uri (the
    iMessage `imessage://` injection) lands on the same block beside the file metadata."""
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64})
    records.append_origin_block(
        post,
        uri=None,
        snapshot="2026-06-29T00:00:00Z",
        fields={"filename": "chat.html", "source_modified": "2025-12-31T10:00:00Z"},
    )
    fields = post.metadata["_origins"][-1]["fields"]
    assert "uri" not in fields  # uri omitted entirely, not empty-string
    assert fields["filename"] == "chat.html"
    assert fields["source_modified"] == "2025-12-31T10:00:00Z"

    # The drafter folds a synthetic retrieval origin onto the same (uri-less) block.
    records.add_origin_uri_alias(post, "imessage://chat/+1403,+1587/2025-12")
    fields = post.metadata["_origins"][-1]["fields"]
    assert fields["uri"] == "imessage://chat/+1403,+1587/2025-12"
    assert fields["filename"] == "chat.html"  # file metadata survives the fold


def test_derive_capture_origin_local_file_is_uri_less(tmp_path):
    """A dropped file with no capture sidecar yields a uri-less origin carrying the basename
    and the file mtime — not a `file://` staging path dead on arrival. A sidecar `source_url`
    yields a retrieval origin (uri, no local fields)."""
    from corpus._cli.ingest import _derive_capture_origin

    src = tmp_path / "scan0001.pdf"
    src.write_bytes(b"%PDF-1.4\n")

    uri, snapshot, fields, schema_id = _derive_capture_origin(src, {})
    assert uri is None
    assert schema_id is None
    assert fields["filename"] == "scan0001.pdf"
    assert fields["source_modified"].endswith("Z")  # ISO-8601 UTC mtime
    assert snapshot  # ingest observation time

    uri2, _snap2, fields2, schema2 = _derive_capture_origin(
        src, {"source_url": "https://example.com/x", "fetched_at": "2026-06-29T00:00:00Z"}
    )
    assert uri2 == "https://example.com/x"
    assert fields2 == {}
    assert schema2 is None


def test_derive_capture_origin_producer_declared_overlay(tmp_path):
    """A capture sidecar's `origin_schema:` + `origin_fields:` declare an overlay on a uri-less
    local origin (spec §7.2) — the schema id is returned to stamp the block, the declared fields
    merge beside the universal filename/source_modified."""
    from corpus._cli.ingest import _derive_capture_origin

    src = tmp_path / "chat.html"
    src.write_bytes(b"<html></html>")
    sidecar = {
        "origin_schema": "imessage-export",
        "origin_fields": {"chat_name": "Family group", "phone_number": ["+14035551234"]},
    }
    uri, _snap, fields, schema_id = _derive_capture_origin(src, sidecar)
    assert uri is None
    assert schema_id == "imessage-export"
    assert fields["filename"] == "chat.html"  # universal local-file metadata kept
    assert fields["chat_name"] == "Family group"  # producer-declared fields merged in
    assert fields["phone_number"] == ["+14035551234"]


def test_set_origin_schema_id_stamps_most_recent_block():
    """`set_origin_schema_id` promotes the most-recent origin block's opener to
    `<!--origin <id>-->` — the draft-time half of producer-declared binding (spec §7.2)."""
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64})
    records.append_origin_block(
        post, uri=None, snapshot="2026-06-29T00:00:00Z", fields={"filename": "chat.html"}
    )
    assert records.set_origin_schema_id(post, "imessage-export") is True
    assert post.metadata["_origins"][-1]["id"] == "imessage-export"
    assert records.derived_classifications(post) == ["origin/imessage-export"]
    assert records.set_origin_schema_id(post, "  ") is False  # empty/whitespace is a no-op


def test_set_origin_schema_id_compound_splits_id_and_subtype_and_roundtrips(tmp_path):
    """A compound `schema_id` (`<id>/<subtype>`) splits on the FIRST `/` (spec §4.3.1) —
    `gmail` is a SUBTYPE of the `google-takeout` producer, not a distinct overlay id. The
    split survives a dump/load round-trip: the opener reads
    `<!--origin google-takeout/gmail-->`, and the derived classification carries both."""
    p = tmp_path / "ab" / ("a" * 64 + ".md")
    p.parent.mkdir(parents=True)
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64})
    records.append_origin_block(
        post, uri=None, snapshot="2026-07-21T00:00:00Z", fields={"filename": "full.mbox"}
    )
    assert records.set_origin_schema_id(post, "google-takeout/gmail") is True
    assert post.metadata["_origins"][-1]["id"] == "google-takeout"
    assert post.metadata["_origins"][-1]["subtype"] == "gmail"

    records.dump(post, p)
    raw = p.read_text("utf-8")
    assert "<!--origin google-takeout/gmail" in raw

    loaded = records.load(p)
    origin = next(iter(records.iter_origin_blocks(loaded)))
    assert origin["id"] == "google-takeout"
    assert origin["subtype"] == "gmail"
    assert records.derived_classifications(loaded) == ["origin/google-takeout/gmail"]


def test_set_origin_schema_id_bare_clears_stale_subtype():
    """Re-stamping with a BARE id fully replaces the prior compound stamp — a stale
    subtype from an earlier (wrong) stamp doesn't survive a corrective re-stamp."""
    post = frontmatter.Post("")
    records.append_origin_block(post, uri=None, snapshot="2026-07-21T00:00:00Z")
    assert records.set_origin_schema_id(post, "google-takeout/gmail") is True
    assert post.metadata["_origins"][-1]["subtype"] == "gmail"
    assert records.set_origin_schema_id(post, "google-takeout") is True
    assert post.metadata["_origins"][-1]["id"] == "google-takeout"
    assert post.metadata["_origins"][-1]["subtype"] is None


def test_append_origin_block_compound_schema_id_splits():
    """The ingest-sidecar seam: `append_origin_block(schema_id="google-takeout/gmail")`
    (what `_derive_capture_origin` feeds it verbatim from `origin_schema:`) splits the
    same way `set_origin_schema_id` does — this is the actual fresh-ingest/re-encounter
    stamping path, not `set_origin_schema_id`."""
    post = frontmatter.Post("")
    records.append_origin_block(
        post,
        uri=None,
        snapshot="2026-07-21T00:00:00Z",
        schema_id="google-takeout/gmail",
        fields={"filename": "full.mbox"},
    )
    origin = post.metadata["_origins"][0]
    assert origin["id"] == "google-takeout"
    assert origin["subtype"] == "gmail"


def test_append_origin_block_explicit_subtype_wins_over_schema_id_slash():
    """An explicit `subtype=` kwarg (the `restub` replay path, passing an already-parsed
    block's own `id`/`subtype` back in) wins over any slash embedded in `schema_id`."""
    post = frontmatter.Post("")
    records.append_origin_block(
        post,
        uri=None,
        snapshot="2026-07-21T00:00:00Z",
        schema_id="a/b",
        subtype="explicit",
    )
    origin = post.metadata["_origins"][0]
    assert origin["id"] == "a"
    assert origin["subtype"] == "explicit"


# ---------- qualify_origin_blocks (origin-block host qualification, spec §7.2) ---------- #


def _origin_corpus(tmp_path: Path, **overlays: dict) -> Path:
    """A minimal corpus tree with the given origin overlays under schema/origin/web/
    (`name=applies_to-dict`), for exercising `qualify_origin_blocks`."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    d = root / "schema" / "origin" / "web"
    d.mkdir(parents=True)
    for name, applies_to in overlays.items():
        (d / f"{name}.yaml").write_text(
            yaml.safe_dump({"applies_to": applies_to}, sort_keys=False), encoding="utf-8"
        )
    schemas.cache_clear()
    return root


def test_qualify_origin_blocks_stamps_matching_bare_block(tmp_path):
    root = _origin_corpus(tmp_path, video={"host_pattern": "video.example"})
    post = frontmatter.Post("")
    records.append_origin_block(
        post, uri="https://video.example/v/1", snapshot="2026-06-02T00:00:00Z"
    )
    stamped = records.qualify_origin_blocks(post, root)
    assert stamped == ["video"]
    assert post.metadata["_origins"][0]["id"] == "video"
    assert records.derived_classifications(post) == ["origin/video"]


def test_qualify_origin_blocks_no_match_stays_bare(tmp_path):
    root = _origin_corpus(tmp_path, video={"host_pattern": "video.example"})
    post = frontmatter.Post("")
    records.append_origin_block(
        post, uri="https://unrelated.example/x", snapshot="2026-06-02T00:00:00Z"
    )
    assert records.qualify_origin_blocks(post, root) == []
    assert post.metadata["_origins"][0]["id"] is None


def test_qualify_origin_blocks_never_touches_existing_id(tmp_path):
    """Producer-declared / already-qualified ids are sacrosanct — never re-stamped, never
    downgraded, even when a differently-matching overlay exists."""
    root = _origin_corpus(tmp_path, other={"host_pattern": "video.example"})
    post = frontmatter.Post("")
    records.append_origin_block(
        post,
        uri="https://video.example/v/1",
        snapshot="2026-06-02T00:00:00Z",
        schema_id="producer-declared",
    )
    assert records.qualify_origin_blocks(post, root) == []
    assert post.metadata["_origins"][0]["id"] == "producer-declared"


def test_qualify_origin_blocks_iterates_every_block(tmp_path):
    """A re-capture may carry more than one origin block — qualification is per-block, not
    just-the-latest (contrast `set_origin_schema_id`, which is deliberately most-recent-only
    for the producer-declared path)."""
    root = _origin_corpus(
        tmp_path,
        a={"host_pattern": "a.example"},
        b={"host_pattern": "b.example"},
    )
    post = frontmatter.Post("")
    records.append_origin_block(post, uri="https://a.example/1", snapshot="2026-06-02T00:00:00Z")
    records.append_origin_block(
        post,
        uri="https://b.example/2",
        snapshot="2026-06-03T00:00:00Z",
        schema_id="already-set",
    )
    records.append_origin_block(
        post, uri="https://unmatched.example/3", snapshot="2026-06-04T00:00:00Z"
    )
    assert records.qualify_origin_blocks(post, root) == ["a"]
    ids = [o["id"] for o in post.metadata["_origins"]]
    assert ids == ["a", "already-set", None]


def test_qualify_origin_blocks_idempotent(tmp_path):
    root = _origin_corpus(tmp_path, video={"host_pattern": "video.example"})
    post = frontmatter.Post("")
    records.append_origin_block(
        post, uri="https://video.example/v/1", snapshot="2026-06-02T00:00:00Z"
    )
    assert records.qualify_origin_blocks(post, root) == ["video"]
    # Second run finds nothing left unqualified — no re-stamp, no change reported.
    assert records.qualify_origin_blocks(post, root) == []
    assert post.metadata["_origins"][0]["id"] == "video"


def test_qualify_origin_blocks_subdomain_matching(tmp_path):
    root = _origin_corpus(
        tmp_path, video={"host_pattern": "video.example", "include_subdomains": True}
    )
    post = frontmatter.Post("")
    records.append_origin_block(
        post, uri="https://cdn.video.example/v/1", snapshot="2026-06-02T00:00:00Z"
    )
    assert records.qualify_origin_blocks(post, root) == ["video"]


def test_qualify_origin_blocks_no_uri_stays_bare(tmp_path):
    """A uri-less (local-file) origin has nothing to match against — stays bare, exactly
    like a uri present but unmatched (spec §7.2: local-file origins bind only through the
    producer-declared path, `set_origin_schema_id`)."""
    root = _origin_corpus(tmp_path, video={"host_pattern": "video.example"})
    post = frontmatter.Post("")
    records.append_origin_block(
        post, uri=None, snapshot="2026-06-02T00:00:00Z", fields={"filename": "chat.html"}
    )
    assert records.qualify_origin_blocks(post, root) == []
    assert post.metadata["_origins"][0]["id"] is None


def test_local_origin_dedups_by_filename():
    """Re-encountering the same bytes under the SAME filename appends no duplicate local
    origin (dedup by filename — even when the mtime differs); a DIFFERENT filename is a
    distinct local source and gets its own origin."""
    from corpus._cli.ingest import _append_origin_if_new

    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64})
    records.append_origin_block(
        post,
        uri=None,
        snapshot="2026-06-29T00:00:00Z",
        fields={"filename": "scan.pdf", "source_modified": "2025-11-03T14:22:09Z"},
    )
    # Same filename, different mtime → skipped (filename is the key).
    assert (
        _append_origin_if_new(
            post,
            None,
            "2026-06-30T00:00:00Z",
            {"filename": "scan.pdf", "source_modified": "2099-01-01T00:00:00Z"},
        )
        is False
    )
    assert len(post.metadata["_origins"]) == 1
    # Different filename → a second local origin.
    added = _append_origin_if_new(post, None, "2026-06-30T00:00:00Z", {"filename": "copy.pdf"})
    assert added is True
    assert len(post.metadata["_origins"]) == 2


def test_segments_module_does_not_recognize_embed_openers():
    """Reconciliation #1: the roster belongs to records.py, not segments.py."""
    body = "<!--embed image/png\naddress: page=1\ntransport: blake3:abc\n-->\n"
    blocks = segments.iter_blocks(body)
    # The embed line isn't an opener in the content-zone grammar — nothing parses.
    assert blocks == []


def test_dump_emits_canonical_frontmatter_field_order(tmp_path):
    post, p = _make_golden(tmp_path)
    records.dump(post, p)
    raw = p.read_text("utf-8")
    # The core fields appear in spec order before the closing `---`. `status` is retired
    # (§4.1, §12.19) — never emitted, so it's not one of them.
    pre = raw.split("---", 2)[1]
    indices = []
    for key in ["id", "description", "transport", "touch"]:
        indices.append(pre.index(f"{key}:"))
    assert indices == sorted(indices)


def test_dump_never_emits_legacy_status(tmp_path):
    """A record parsed with a legacy `status:` key reads tolerantly (it survives in
    `post.metadata` for lint's `frontmatter-legacy-status` rule to see) but `dumps()` never
    re-emits it — any write drops it (spec §4.1, §12.19)."""
    post, p = _make_golden(tmp_path)
    assert post.metadata["status"] == "draft"  # the fixture carries a legacy status key

    text = records.dumps(post)
    assert "status:" not in text.split("---", 2)[1]

    records.dump(post, p)
    reloaded = records.load(p)
    assert "status" not in reloaded.metadata
