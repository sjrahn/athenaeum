"""The `turn=` unit ops (spec §6.2, 3.0). `turn=<N>` returns the verbatim N-th unit located by
the origin overlay's form mapping (§7.2); `turn=<N>&att=<M>` materializes an attachment through
lineage-chained resolution (fails loudly when the record has no containment parent)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import frontmatter
import pytest

from corpus import hashing, paths, records, resolver, schemas
from corpus.store import LocalArtifactStore

_OVERLAY = """\
applies_to:
  schemes: [convexport]
kind: interpretive
form:
  id: conversation
  mapping:
    messages: messages
    author_id: author.id
    author_name: author.name
    text: content
    attachments: attachments
    attachment_url: url
    attachment_path: path
"""

_CHAT = {
    "messages": [
        {"author": {"id": "u1", "name": "Andy"}, "content": "Yo"},
        {"author": {"id": "u2", "name": "Steven"}, "content": "pic",
         "attachments": [{"url": "https://cdn/x.png", "path": "media/x.png"}]},
    ]
}


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "conv-export.yaml").write_text(_OVERLAY, encoding="utf-8")
    schemas.cache_clear()
    return root


def _ingest_chat(root: Path, *, lineage_uri: str | None = None) -> str:
    raw = json.dumps(_CHAT).encode()
    src = root / "chat.json"
    src.write_bytes(raw)
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "json", src)
    src.unlink()
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "", "status": "stub",
         "transport": f"sha256:{h['sha256']}", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/json", fields={})
    # The lineage origin (promotion history) carries the container uri; a standalone record has
    # a uri-less origin only.
    if lineage_uri:
        records.append_origin_block(post, uri=lineage_uri, snapshot="2026-01-01T00:00:00Z",
                                    schema_id="conv-export")
    else:
        records.append_origin_block(post, uri=None, snapshot="2026-01-01T00:00:00Z",
                                    schema_id="conv-export", fields={"filename": "chat.json"})
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_turn_returns_the_nth_unit(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_chat(root)
    out = resolver.resolve(f"corpus://{rid}?turn=1", root)
    assert out.suffix == ".json"
    unit = json.loads(out.read_text("utf-8"))
    assert unit["author"]["name"] == "Andy"
    assert unit["content"] == "Yo"
    # turn=2 is a distinct unit; cache is stable.
    unit2 = json.loads(resolver.resolve(f"corpus://{rid}?turn=2", root).read_text("utf-8"))
    assert unit2["content"] == "pic"
    assert resolver.resolve(f"corpus://{rid}?turn=1", root) == out


def test_turn_out_of_range_errors(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_chat(root)
    with pytest.raises(ValueError, match="out of range"):
        resolver.resolve(f"corpus://{rid}?turn=9", root)


def test_att_without_lineage_fails_loudly(tmp_path):
    """A standalone conversation record (no containment parent) can't materialize an
    attachment — it fails loudly rather than papering over (§4.3.1.4)."""
    root = _corpus(tmp_path)
    rid = _ingest_chat(root)
    with pytest.raises(ValueError, match="not lineage-resolvable"):
        resolver.resolve(f"corpus://{rid}?turn=2&att=1", root)


def test_att_resolves_through_lineage(tmp_path):
    """turn=N&att=M materializes the attachment as a member of the blake3-pinned container
    (the promotion-lineage origin)."""
    root = _corpus(tmp_path)
    # A container zip holding the media the attachment references.
    zsrc = root / "export.zip"
    with zipfile.ZipFile(zsrc, "w") as zf:
        zf.writestr("media/x.png", b"\x89PNG\r\n\x1a\nFAKEPNGBYTES")
    zh = hashing.hash_file(zsrc)
    cid = zh["blake3"]
    LocalArtifactStore(root).put(cid, "zip", zsrc)
    zsrc.unlink()
    # The container needs a record so the resolver can extract `path=` from it.
    cpost = frontmatter.Post("")
    cpost.metadata.update(
        {"id": cid, "title": "", "description": "", "status": "stub",
         "transport": f"sha256:{zh['sha256']}", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(cpost, mime="application/zip", fields={})
    records.append_origin_block(cpost, uri=None, snapshot="2026-01-01T00:00:00Z",
                                fields={"filename": "export.zip"})
    records.dump(cpost, paths.record_path(root, cid))
    # The conversation record, promoted out of the container (lineage uri points at it).
    rid = _ingest_chat(root, lineage_uri=f"corpus://{cid}?path=conv.json")

    out = resolver.resolve(f"corpus://{rid}?turn=2&att=1", root)
    assert out.read_bytes() == b"\x89PNG\r\n\x1a\nFAKEPNGBYTES"  # the container member's bytes
