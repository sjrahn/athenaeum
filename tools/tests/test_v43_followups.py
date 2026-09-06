"""v43 follow-ups (spec §6.2): `header=<name>` on a message, and "textual by content" for
a member whose declared type and name are both silent.

- `header=` — one header, RFC 2047-decoded to a single line, repeats newline-joined; an
  absent header is an error. Address-class, pinned `eml-header@1`, the `prop=` shape on the
  mail axis: `msg=<N>&header=subject` cites the envelope on the mailbox itself.
- textual-by-content — `config/docker.cfg` in a zip has no mimetypes entry and no magic;
  under `archive-path@1` it stayed an opaque `.bin` and its ledger citation was
  "unverifiable (.bin)". Valid UTF-8 with no NUL is plain text; a NUL or non-UTF-8 stays
  bytes. The archive axis re-pins `archive-path@2`.
"""

from __future__ import annotations

import io
import json
import zipfile
from email import policy
from email.message import EmailMessage
from pathlib import Path

import frontmatter
import pytest

from corpus import hashing, paths, records, resolver, schemas, transforms
from corpus import mime as mime_mod
from corpus.store import LocalArtifactStore

CRLF = b"\r\n"


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _stage_record(root: Path, data: bytes, *, mime: str, name: str) -> str:
    src = root.parent / name
    src.write_bytes(data)
    rid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(rid, mime_mod.extension_for(mime), src)
    post = frontmatter.Post("")
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"))
    records.set_artifact_block(post, mime=mime, fields={})
    records.append_origin_block(
        post, snapshot="2026-07-18T00:00:00Z", fields={"filename": name, "source_modified": ""}
    )
    records.dump(post, paths.record_path(root, rid))
    return rid


def _sidecar(out: Path) -> dict:
    (side,) = out.parent.glob(out.stem + "*.json")
    return json.loads(side.read_text("utf-8"))


# ---------- header= ---------- #


def _eml() -> bytes:
    em = EmailMessage()
    em["From"] = "=?utf-8?q?Bj=C3=B6rn?= <bjorn@example.com>"
    em["To"] = "s@example.com"
    em["Date"] = "Tue, 02 Feb 2021 09:00:00 +0000"
    em["Subject"] = "=?utf-8?q?Caf=C3=A9_meeting_=E2=80=94_agenda?="
    em["Message-ID"] = "<m1@example.com>"
    # long enough that policy.SMTP folds it on the wire — the parse must unfold it back
    em["References"] = " ".join(f"<m{i:02d}@example.com>" for i in range(6))
    em["Received"] = "from a.example.com by b.example.com; Tue, 02 Feb 2021 09:00:01 +0000"
    em["Received"] = "from b.example.com by c.example.com; Tue, 02 Feb 2021 09:00:02 +0000"
    em.set_content("body\n")
    return em.as_bytes(policy=policy.SMTP)


def _mbox_around(raw_eml: bytes) -> bytes:
    return (
        b"From 111@xxx Mon Jan 01 00:00:00 +0000 2020" + CRLF
        + b"From: a@example.com" + CRLF + b"Subject: one" + CRLF + CRLF + b"body one" + CRLF
        + b"From 222@xxx Tue Feb 02 09:00:00 +0000 2021" + CRLF
        + raw_eml
    )


def test_header_decodes_rfc2047_to_one_line(tmp_path):
    root = _corpus(tmp_path)
    rid = _stage_record(root, _eml(), mime="message/rfc822", name="m.eml")
    out = resolver.resolve(f"corpus://{rid}?header=subject", root)
    assert out.suffix == ".txt"
    assert out.read_text("utf-8") == "Café meeting — agenda\n"
    assert _sidecar(out)["engine"] == "eml-header@1"
    assert resolver.resolve(f"corpus://{rid}?header=From", root).read_text("utf-8") == (
        "Björn <bjorn@example.com>\n"
    )


def test_header_folds_continuations_and_joins_repeats(tmp_path):
    root = _corpus(tmp_path)
    rid = _stage_record(root, _eml(), mime="message/rfc822", name="m.eml")
    raw = _eml()
    assert b"References:" in raw and raw.count(b"@example.com>\r\n <m") >= 1  # folded on the wire
    refs = resolver.resolve(f"corpus://{rid}?header=references", root).read_text("utf-8")
    assert refs == " ".join(f"<m{i:02d}@example.com>" for i in range(6)) + "\n"  # one line
    received = resolver.resolve(f"corpus://{rid}?header=received", root).read_text("utf-8")
    assert received.splitlines() == [
        "from a.example.com by b.example.com; Tue, 02 Feb 2021 09:00:01 +0000",
        "from b.example.com by c.example.com; Tue, 02 Feb 2021 09:00:02 +0000",
    ]


def test_header_absent_is_an_error(tmp_path):
    root = _corpus(tmp_path)
    rid = _stage_record(root, _eml(), mime="message/rfc822", name="m.eml")
    with pytest.raises(ValueError, match="no such header"):
        resolver.resolve(f"corpus://{rid}?header=x-nope", root)


def test_header_through_the_mailbox_keys_on_its_own_pin(tmp_path):
    root = _corpus(tmp_path)
    mid = _stage_record(root, _mbox_around(_eml()), mime="application/mbox", name="m.mbox")
    out = resolver.resolve(f"corpus://{mid}?msg=2&header=subject", root)
    assert out.read_text("utf-8") == "Café meeting — agenda\n"
    assert _sidecar(out)["engine"] == "eml-header@1"


def test_header_is_address_class_and_introspectable(tmp_path):
    root = _corpus(tmp_path)
    assert transforms.op_class("header") == "address"
    ops = {op.param: op for op in resolver.ops_for_media_type(root, "message/rfc822")}
    assert ops["header"].op_class == "address"
    assert ops["header"].engine_version == "eml-header@1"
    assert ops["part"].engine_version == "eml-part@1"  # independently pinned


def test_ledger_verifies_a_subject_cited_on_the_mailbox(tmp_path):
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    root = _corpus(tmp_path)
    mid = _stage_record(root, _mbox_around(_eml()), mime="application/mbox", name="m.mbox")
    ledger = root.parent / "ledger"
    (ledger / "facts" / "event").mkdir(parents=True)
    (ledger / "facts" / "event" / "m.json").write_text(json.dumps({
        "id": "m", "type": "event", "name": "Meeting",
        "sources": {"s1": {"record": mid}},
        "claims": [{"id": "m:subject", "predicate": "titled", "value": "Café meeting",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "msg=2&header=subject",
                                  "quote": "Café meeting — agenda",
                                  "kind": "authoritative"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert not res.errors and res.unverifiable == 0, (res.errors, res.notes)
    assert res.verified == 1 and res.derived_resolved == 1


# ---------- textual by content ---------- #


def _zip_with(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


_CFG = b'# docker\nDOCKER_ENABLED="yes"\nDOCKER_IMAGE_FILE="/mnt/cache/docker.img"\n'
_LATIN_CFG = "caf\xe9=1\n".encode("latin-1")
_BINARY = b"\x00\x01\xfe\xfd" + bytes(range(200))


def test_looks_textual_judgement():
    assert mime_mod.looks_textual(_CFG)
    assert not mime_mod.looks_textual(_LATIN_CFG)  # not UTF-8 → stays bytes
    assert not mime_mod.looks_textual(_BINARY)  # NUL → binary
    assert not mime_mod.looks_textual(b"")


def test_cfg_member_with_no_known_extension_decodes_to_text(tmp_path):
    root = _corpus(tmp_path)
    rid = _stage_record(
        root, _zip_with({"config/docker.cfg": _CFG, "config/latin.cfg": _LATIN_CFG,
                         "blob.dat": _BINARY}),
        mime="application/zip", name="diag.zip",
    )
    out = resolver.resolve(f"corpus://{rid}?path=config/docker.cfg", root)
    assert out.suffix == ".txt"
    assert out.read_text("utf-8") == _CFG.decode()
    assert _sidecar(out)["engine"] == "archive-path@2"
    assert _sidecar(out)["mime"] == "text/plain"
    # conservative on both tells
    assert resolver.resolve(f"corpus://{rid}?path=config/latin.cfg", root).suffix == ".bin"
    assert resolver.resolve(f"corpus://{rid}?path=blob.dat", root).suffix == ".bin"


def test_attested_member_media_type_is_untouched_by_the_content_test():
    """`sniff_head` — what a roster row's `media_type` comes from — never applies the
    content test: an unknown-extension text member still attests as it always did."""
    assert mime_mod.sniff_head(_CFG, "config/docker.cfg") == "unknown"


def test_ledger_verifies_a_quote_in_a_cfg_member(tmp_path):
    """The reference instance's four standing unverifiable citations, in miniature."""
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    root = _corpus(tmp_path)
    rid = _stage_record(root, _zip_with({"config/docker.cfg": _CFG}),
                        mime="application/zip", name="diag.zip")
    ledger = root.parent / "ledger"
    (ledger / "facts" / "asset").mkdir(parents=True)
    (ledger / "facts" / "asset" / "srv.json").write_text(json.dumps({
        "id": "srv", "type": "asset", "name": "srv",
        "sources": {"s1": {"record": rid}},
        "claims": [{"id": "srv:docker", "predicate": "runs", "value": "docker",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "path=config/docker.cfg",
                                  "quote": 'DOCKER_ENABLED="yes"',
                                  "kind": "authoritative"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=True, today="2026-09-02")
    assert not res.errors and res.unverifiable == 0, (res.errors, res.notes)
    assert res.verified == 1 and res.derived_resolved == 1
    fact = json.loads((ledger / "facts" / "asset" / "srv.json").read_text())
    assert fact["sources"]["s1"]["verified"]["ops"] == {"path": "archive-path@2"}
