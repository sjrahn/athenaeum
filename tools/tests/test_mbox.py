"""mbox `msg=<N>` member addressing — extraction semantics, containment streaming, the
resolver transform, selective manifest declaration, promotion, and the message/rfc822
drafter (spec §8.1 / §12.9 / §12.11).

The fixture mailbox is built in-test: CRLF (mboxrd), a plain message carrying a `>From `
stuffed body line, a multipart/mixed message (base64 text part nested in
multipart/alternative + a fake attachment), and a second plain message.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from email import policy
from email.message import EmailMessage
from pathlib import Path

import blake3
import pytest

from corpus import containment, hashing, mboxfile, mime, paths, records, resolver, schemas
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli
from corpus.draft import mbox_manifest
from corpus.store import LocalArtifactStore

CRLF = b"\r\n"


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


# ---------- fixture construction ---------- #


def _sep(sender: str, date: str) -> bytes:
    """An mboxrd separator line (CRLF): `From <sender> <asctime>`."""
    return f"From {sender} {date}".encode() + CRLF


_MSG1 = (
    b"From: alice@example.com" + CRLF
    + b"Subject: First message" + CRLF
    + b"Date: Mon, 01 Jan 2020 00:00:00 +0000" + CRLF
    + CRLF
    + b">From the top: this body line was mbox-stuffed" + CRLF  # mboxrd `>From ` stuffing
    + b"an ordinary body line" + CRLF
)

# The un-stuffed member bytes msg1 must resolve to (one leading `>` dropped).
_MSG1_MEMBER = _MSG1.replace(b">From the top", b"From the top", 1)

_MSG3 = (
    b"From: carol@example.com" + CRLF
    + b"Subject: Third message" + CRLF
    + b"Date: Wed, 03 Mar 2022 00:00:00 +0000" + CRLF
    + CRLF
    + b"plain third body" + CRLF
)


def _multipart_message() -> bytes:
    """A multipart/mixed message: a base64 text/plain nested in multipart/alternative with a
    text/html sibling, plus a fake PDF attachment. Serialized CRLF (policy.SMTP)."""
    em = EmailMessage()
    em["From"] = "Björn <bjorn@example.com>"
    em["To"] = "sjrahn@example.com"
    em["Date"] = "Tue, 02 Feb 2021 09:00:00 +0000"
    em["Subject"] = "Café meeting"
    em["Message-ID"] = "<multi-1@example.com>"
    em.set_content("Plain body line one.\nPlain body line two.\n", cte="base64")
    em.add_alternative("<html><body><p>HTML body paragraph.</p></body></html>", subtype="html")
    em.add_attachment(
        b"%PDF-1.4\nfake pdf payload bytes\n",
        maintype="application",
        subtype="pdf",
        filename="report.pdf",
    )
    return em.as_bytes(policy=policy.SMTP)


def _build_mbox() -> tuple[bytes, list[bytes]]:
    """Return `(mbox_bytes, [member1, member2, member3])` — the members are the un-stuffed
    per-message bytes the scan/transform/promote must reproduce."""
    m2 = _multipart_message()
    mbox = (
        _sep("111@xxx", "Mon Jan 01 00:00:00 +0000 2020") + _MSG1
        + _sep("222@xxx", "Tue Feb 02 09:00:00 +0000 2021") + m2
        + _sep("333@xxx", "Wed Mar 03 00:00:00 +0000 2022") + _MSG3
    )
    return mbox, [_MSG1_MEMBER, m2, _MSG3]


def _write_mbox(tmp_path: Path) -> tuple[Path, list[bytes]]:
    mbox_bytes, members = _build_mbox()
    p = tmp_path / "mail.mbox"
    p.write_bytes(mbox_bytes)
    return p, members


# ---------- corpus / pipeline harness ---------- #


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults
    schemas.cache_clear()
    return root


def _ingest(root: Path, artifact: Path) -> str:
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / artifact.name
    shutil.copy(artifact, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    return hashing.hash_file(artifact)["blake3"]


def _draft_cli(root: Path, target: str, messages: str | None = None) -> int:
    from tests._draftlib import draft_for_test

    return draft_for_test(root, target, messages=messages)


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


def _embeds(root: Path, rid: str) -> list[dict]:
    return list(records.iter_embed_blocks(records.load(paths.record_path(root, rid))))


# ---------- A. extraction semantics (separators / ordinals / un-stuffing) ---------- #


def test_scan_counts_extracts_and_unstuffs(tmp_path):
    p, members = _write_mbox(tmp_path)
    scan = mboxfile.scan(p, {1, 2, 3})
    assert scan.count == 3
    for n, member in zip((1, 2, 3), members, strict=True):
        assert scan.facts[n].blake3 == _b3(member)
        assert scan.facts[n].bytes == len(member)


def test_resolve_member_is_exact_and_unstuffed(tmp_path):
    p, members = _write_mbox(tmp_path)
    assert mboxfile.resolve_member(p, 1) == members[0]
    assert b">From the top" not in members[0] and b"From the top" in members[0]
    assert mboxfile.resolve_member(p, 2) == members[1]
    assert mboxfile.resolve_member(p, 3) == members[2]


def test_scan_headers_are_rfc2047_decoded_single_line(tmp_path):
    p, _ = _write_mbox(tmp_path)
    facts = mboxfile.scan(p, {2}).facts[2]
    assert facts.sender == "Björn <bjorn@example.com>"
    assert facts.subject == "Café meeting"
    assert facts.date == "Tue, 02 Feb 2021 09:00:00 +0000"


def test_out_of_range_ordinal_raises(tmp_path):
    p, _ = _write_mbox(tmp_path)
    with pytest.raises(ValueError, match="out of range"):
        mboxfile.scan(p, {9})
    with pytest.raises(ValueError, match="no such message"):
        mboxfile.resolve_member(p, 9)


def test_date_span_from_separator_lines(tmp_path):
    p, _ = _write_mbox(tmp_path)
    scan = mboxfile.scan(p, set())
    span = mboxfile.date_span(scan.first_sep, scan.last_sep)
    assert span == ("2020-01-01T00:00:00+00:00", "2022-03-03T00:00:00+00:00")


def test_message_spec_parser():
    assert mbox_manifest.parse_message_spec("5,12,90-95") == [5, 12, 90, 91, 92, 93, 94, 95]
    assert mbox_manifest.parse_message_spec("3, 1 ,2,1") == [1, 2, 3]
    with pytest.raises(ValueError):
        mbox_manifest.parse_message_spec("0")
    with pytest.raises(ValueError):
        mbox_manifest.parse_message_spec("5-2")


# ---------- MIME detection ---------- #


def test_detection_mbox_vs_eml(tmp_path):
    p, members = _write_mbox(tmp_path)
    assert mime.detect(p) == "application/mbox"  # `From ` at offset 0 wins
    eml = tmp_path / "one.eml"
    eml.write_bytes(members[1])
    assert mime.detect(eml) == "message/rfc822"
    # A promoted member carries no extension (basename is the ordinal) — header shape decides.
    assert mime.sniff_head(members[1][:512], "2") == "message/rfc822"
    # An ordinary one-line `key: value` text file is NOT misread as a message.
    assert mime.sniff_head(b"note: buy milk\n", "todo.txt") != "message/rfc822"


# ---------- C. resolver transform ---------- #


def test_transform_resolves_message_bytes(tmp_path):
    root = _corpus(tmp_path)
    p, members = _write_mbox(tmp_path)
    mbox_id = _ingest(root, p)
    out = resolver.resolve(f"corpus://{mbox_id}?msg=2", root)
    assert out.read_bytes() == members[1]


# ---------- D. selective declaration + idempotence ---------- #


def test_draft_declares_selected_messages(tmp_path):
    root = _corpus(tmp_path)
    p, members = _write_mbox(tmp_path)
    mbox_id = _ingest(root, p)

    assert _draft_cli(root, mbox_id, messages="1,3") == 0
    embeds = _embeds(root, mbox_id)
    by_addr = {e["address"]: e for e in embeds}
    assert set(by_addr) == {"msg=1", "msg=3"}
    assert by_addr["msg=1"]["media_type"] == "message/rfc822"
    assert by_addr["msg=1"]["transport"] == records.format_hash("blake3", _b3(members[0]))
    assert by_addr["msg=3"]["transport"] == records.format_hash("blake3", _b3(members[2]))

    post = records.load(paths.record_path(root, mbox_id))
    assert post.metadata["status"] == "draft"
    # Summary lives on the artifact block; content zone is empty (a manifest record).
    fields = records.artifact_block(post)["fields"]
    assert fields["message_count"] == 3
    assert fields["declared_count"] == 2
    assert fields["date_start"].startswith("2020-01-01")
    assert not (post.content or "").strip()


def test_draft_is_cumulative_and_folds_identical(tmp_path):
    root = _corpus(tmp_path)
    p, _ = _write_mbox(tmp_path)
    mbox_id = _ingest(root, p)

    _draft_cli(root, mbox_id, messages="1")
    _draft_cli(root, mbox_id, messages="1,2")  # re-declares 1 (folds), adds 2
    addrs = sorted(e["address"] for e in _embeds(root, mbox_id))
    assert addrs == ["msg=1", "msg=2"]  # no duplicate msg=1


def test_reattest_changed_hash_is_a_hard_error(tmp_path):
    """A changed hash for an already-declared mbox ordinal is a hard error (§12.11) — surfaced
    by `corpus reattest --messages` (the 3.0 home of the mbox declaration)."""
    from corpus._cli import reattest as reattest_cli

    root = _corpus(tmp_path)
    p, _ = _write_mbox(tmp_path)
    mbox_id = _ingest(root, p)
    _draft_cli(root, mbox_id, messages="2")

    # Corrupt the declared transport so re-extraction disagrees → hard error.
    post = records.load(paths.record_path(root, mbox_id))
    for emb in post.metadata["_embeds"]:
        if emb["address"] == "msg=2":
            emb["transport"] = "blake3:" + "0" * 64
    records.dump(post, paths.record_path(root, mbox_id))

    with pytest.raises(SystemExit, match="stale"):
        reattest_cli.run(
            argparse.Namespace(
                target=mbox_id, mime=None, host=None, status="any", dry_run=False,
                fingerprint=None, messages="2", corpus_root=str(root),
            )
        )


def test_plain_draft_is_empty_manifest(tmp_path):
    root = _corpus(tmp_path)
    p, _ = _write_mbox(tmp_path)
    mbox_id = _ingest(root, p)
    assert _draft_cli(root, mbox_id) == 0
    post = records.load(paths.record_path(root, mbox_id))
    assert post.metadata["status"] == "draft"
    assert list(records.iter_embed_blocks(post)) == []  # no messages declared
    assert records.artifact_block(post)["fields"]["message_count"] == 3


def test_messages_flag_rejected_on_non_mbox(tmp_path):
    """3.0: the mbox `--messages` declaration re-homed to `corpus reattest --messages`, which
    rejects it on a non-mbox record (§12.4.1)."""
    from corpus._cli import reattest as reattest_cli

    root = _corpus(tmp_path)
    z = tmp_path / "plain.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a.txt", b"hello world\n")
    zid = _ingest(root, z)
    with pytest.raises(SystemExit, match="only valid for an mbox"):
        reattest_cli.run(
            argparse.Namespace(
                target=zid, mime=None, host=None, status="any", dry_run=False,
                fingerprint=None, messages="1", corpus_root=str(root),
            )
        )


# ---------- D+B+E. declare → promote → resolve round trip ---------- #


def test_declare_then_promote_round_trip(tmp_path):
    root = _corpus(tmp_path)
    p, members = _write_mbox(tmp_path)
    mbox_id = _ingest(root, p)
    _draft_cli(root, mbox_id, messages="2")

    assert _promote(root, f"corpus://{mbox_id}?msg=2") == 0
    pid = _b3(members[1])  # the promoted id equals the embed's blake3 transport
    post = records.load(paths.record_path(root, pid))
    assert post.metadata["id"] == pid
    assert records.media_type_for(post) == "message/rfc822"
    assert str(post.metadata.get("transport")).startswith("sha256:")
    # The origin records the containment lineage as history; a message has no member filename.
    origin = next(records.iter_origin_blocks(post))["fields"]
    assert origin["uri"] == f"corpus://{mbox_id}?msg=2"
    assert "filename" not in origin
    # Bytes were NOT copied out of the mailbox.
    assert not LocalArtifactStore(root).is_local(pid, "eml")
    # …but they resolve back through containment (streamed out of the mbox).
    out = resolver.resolve(f"corpus://{pid}", root)
    assert out.read_bytes() == members[1]


# ---------- rfc822 drafter (v2): see test_eml.py ---------- #


def test_promoted_message_drafts_v2_shape(tmp_path):
    """Sanity that a message promoted out of the mbox drafts cleanly (headers on the artifact
    block, reply-only body). Full eml v2 coverage lives in test_eml.py."""
    root = _corpus(tmp_path)
    p, members = _write_mbox(tmp_path)
    mbox_id = _ingest(root, p)
    _draft_cli(root, mbox_id, messages="2")
    _promote(root, f"corpus://{mbox_id}?msg=2")
    pid = _b3(members[1])

    assert _draft_cli(root, pid) == 0
    post = records.load(paths.record_path(root, pid))
    fields = records.artifact_block(post)["fields"]
    assert fields["subject"] == "Café meeting" and fields["title"] == "Café meeting"
    assert fields["from"] == "Björn <bjorn@example.com>"
    assert "Plain body line one." in (post.content or "")  # base64 text/plain decoded
    assert "**From:**" not in (post.content or "")  # headers no longer in the body


# ---------- B. nested containment (mbox inside a zip bundle) ---------- #


def test_nested_mbox_in_zip_promote_and_resolve(tmp_path):
    """The mbox lives inside a zip bundle: promote the mbox out, declare a message, promote
    it, and resolve — the message's bytes cross two container hops (spec §12.9)."""
    root = _corpus(tmp_path)
    mbox_bytes, members = _build_mbox()
    z = tmp_path / "bundle.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Takeout/Mail/mail.mbox", mbox_bytes)

    # Ingest + draft the zip so the mbox is an indexed member.
    zid = _ingest(root, z)
    zpost = records.load(paths.record_path(root, zid))
    draft_cli.derive_record(zpost, root)
    records.dump(zpost, paths.record_path(root, zid))
    mbox_id = _b3(mbox_bytes)

    # Promote the mbox out of the zip; it has no standalone artifact.
    assert _promote(root, f"corpus://{zid}?path=Takeout/Mail/mail.mbox") == 0
    assert not LocalArtifactStore(root).is_local(mbox_id, "mbox")

    # Declaring a message drafts the mbox from its containment-resolved bytes.
    _draft_cli(root, mbox_id, messages="3")
    assert _promote(root, f"corpus://{mbox_id}?msg=3") == 0
    mid = _b3(members[2])
    out = resolver.resolve(f"corpus://{mid}", root)
    assert out.read_bytes() == members[2]
    assert _b3(out.read_bytes()) == mid


def test_containment_open_member_stream_direct(tmp_path):
    p, members = _write_mbox(tmp_path)
    with containment.open_member_stream(p, "application/mbox", "msg=1") as fp:
        assert fp.read() == members[0]
    assert containment.member_source_metadata(p, "application/mbox", "msg=1") == {}
