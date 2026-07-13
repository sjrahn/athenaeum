"""message/rfc822 drafter v2 — headers on the artifact block, reply-only body (quoted-history
trim), and every non-body MIME part as a `part=<N>` embed, promotable via containment
(spec §8.1 / §12.11). Fixtures are built in-test with `email`.
"""

from __future__ import annotations

import argparse
import io
import shutil
import zipfile
from email import policy
from email.message import EmailMessage
from pathlib import Path

import blake3
import pytest

from corpus import emlfile, hashing, lint, paths, records, resolver, schemas, segments
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli
from corpus._cli import redraft as redraft_cli
from corpus.draft import eml as emldraft
from corpus.store import LocalArtifactStore

_PDF = b"%PDF-1.4\nfake contract payload\n"
_PNG = b"\x89PNG\r\n\x1a\ninline-image-bytes"
_TXT = b"attached notes line one\nattached notes line two\n"
_PLAIN = (
    "Reply body first line.\nReply body second line.\n\n"
    "On Mon, 1 Jan 2020 Bob <b@x> wrote:\n> old quoted line\n> more quoted\n"
)


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _rich_eml() -> bytes:
    """mixed[ alternative[ plain(base64), related[ html, image(inline) ] ], pdf, txt(QP), msg ].
    Addressable parts (DFS): 1 plain, 2 html, 3 image, 4 pdf, 5 txt, 6 nested-message.
    Body = plain (part 1); skip {1,2}; embeds {3,4,5,6}."""
    em = EmailMessage()
    em["From"] = "=?utf-8?q?Bj=C3=B6rn?= <bjorn@example.com>"
    em["To"] = "sjrahn@example.com"
    em["Cc"] = "=?utf-8?q?Ren=C3=A9e?= <renee@example.com>"
    em["Date"] = "Tue, 02 Feb 2021 09:00:00 +0000"
    em["Subject"] = "=?utf-8?q?Caf=C3=A9_meeting?="
    em["Message-ID"] = "<msg-2@example.com>"
    em["In-Reply-To"] = "<msg-1@example.com>"
    em["References"] = "<msg-0@example.com> <msg-1@example.com>"
    em["X-GM-THRID"] = "1784205551234567890"
    em.set_content(_PLAIN, cte="base64")
    em.add_alternative("<html><body><p>Reply body html.</p></body></html>", subtype="html")
    html_part = em.get_payload()[1]
    html_part.add_related(_PNG, maintype="image", subtype="png", cid="inline-img-1")
    em.add_attachment(_PDF, maintype="application", subtype="pdf", filename="contract.pdf")
    em.add_attachment(_TXT.decode(), filename="notes.txt", cte="quoted-printable")  # text/plain, QP
    inner = EmailMessage()
    inner["Subject"] = "Forwarded inner"
    inner.set_content("inner message body\n")
    em.add_attachment(inner, filename="forwarded.eml")
    return em.as_bytes(policy=policy.SMTP)


# ---------- corpus harness ---------- #


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _ingest(root: Path, artifact: Path) -> str:
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / artifact.name
    shutil.copy(artifact, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    return hashing.hash_file(artifact)["blake3"]


def _draft(root: Path, target: str, messages: str | None = None) -> int:
    from tests._draftlib import draft_for_test

    return draft_for_test(root, target, messages=messages)


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


def _ingest_eml(tmp_path: Path, root: Path, raw: bytes, name: str = "m.eml") -> str:
    eml = tmp_path / name
    eml.write_bytes(raw)
    return _ingest(root, eml)


# ---------- part enumeration + body-skip (unit) ---------- #


def test_addressable_parts_and_body_skip():
    msg = emlfile.parse(_rich_eml())
    parts = emlfile.addressable_parts(msg)
    assert [p.get_content_type() for p in parts] == [
        "text/plain",
        "text/html",
        "image/png",
        "application/pdf",
        "text/plain",
        "message/rfc822",
    ]
    skip = emlfile.body_skip_ids(msg)
    # The plain body and its html alternative are skipped; inline image + attachments are not.
    assert {i for i, p in enumerate(parts, 1) if id(p) in skip} == {1, 2}


# ---------- headers → artifact block ---------- #


def test_headers_lift_to_artifact_block(tmp_path):
    root = _corpus(tmp_path)
    eid = _ingest_eml(tmp_path, root, _rich_eml())
    assert _draft(root, eid) == 0
    post = records.load(paths.record_path(root, eid))
    fields = records.artifact_block(post)["fields"]
    assert fields["subject"] == "Café meeting"
    assert fields["title"] == "Café meeting"
    assert fields["from"] == "Björn <bjorn@example.com>"
    assert fields["cc"] == "Renée <renee@example.com>"
    assert fields["message_id"] == "<msg-2@example.com>"
    assert fields["in_reply_to"] == "<msg-1@example.com>"
    assert fields["references"] == ["<msg-0@example.com>", "<msg-1@example.com>"]  # file order
    assert fields["thread_id"] == "1784205551234567890"
    # Headers are gone from the body.
    body = post.content or ""
    assert "**From:**" not in body and "Subject:" not in body


def test_recipient_headers_split_per_mailbox(tmp_path):
    """to/cc/bcc are string-or-list: one mailbox stays a str, several split into a str[] —
    and a comma inside a quoted display name is never a split point."""
    em = EmailMessage()
    em["From"] = "a@example.com"
    em["To"] = '"Rahn, Steven" <s@example.com>, =?utf-8?q?Ren=C3=A9e?= <renee@example.com>'
    em["Cc"] = "solo@example.com"
    em["Subject"] = "recipient split"
    em.set_content("body")
    root = _corpus(tmp_path)
    eid = _ingest_eml(tmp_path, root, em.as_bytes(policy=policy.SMTP))
    assert _draft(root, eid) == 0
    post = records.load(paths.record_path(root, eid))
    fields = records.artifact_block(post)["fields"]
    assert fields["to"] == ['"Rahn, Steven" <s@example.com>', "Renée <renee@example.com>"]
    assert fields["cc"] == "solo@example.com"
    assert "bcc" not in fields


# ---------- reply-only body ---------- #


def test_body_is_reply_only(tmp_path):
    root = _corpus(tmp_path)
    eid = _ingest_eml(tmp_path, root, _rich_eml())
    _draft(root, eid)
    body = records.load(paths.record_path(root, eid)).content or ""
    assert "Reply body first line." in body
    assert "old quoted line" not in body  # trailing quoted history trimmed
    assert "On Mon" not in body  # attribution trimmed


# No-marker replies that must survive untouched (prefer false negatives).
_KEEP_PLAIN = "just a normal reply\nno markers here\nregards"
_KEEP_WROTE = "On call we agreed X. I wrote the doc.\nDone."  # "wrote" mid-sentence, no `>` after


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hello\n\nBest, A\n\nOn Tue Bob <b@x> wrote:\n> q\n> q2\n", "hello\n\nBest, A"),
        ("see below\n\n-----Original Message-----\nFrom: X\nblah\n", "see below"),
        ("reply\n________________\nFrom: X\nSent: today\n", "reply"),
        ("body\nFrom: a@x\nSent: mon\nTo: b@x\nSubject: s\n", "body"),
        ("top\n> quoted to eof\n> more\n", "top"),
        (_KEEP_PLAIN, _KEEP_PLAIN),
        (_KEEP_WROTE, _KEEP_WROTE),
    ],
)
def test_trim_quoted_history_variants(text, expected):
    assert emldraft._trim_quoted_history(text) == expected


# ---------- part embeds ---------- #


def test_part_embeds(tmp_path):
    root = _corpus(tmp_path)
    eid = _ingest_eml(tmp_path, root, _rich_eml())
    _draft(root, eid)
    embeds = {e["address"]: e for e in _embeds(root, eid)}
    assert set(embeds) == {"part=3", "part=4", "part=5", "part=6"}  # body parts 1,2 skipped

    assert embeds["part=3"]["media_type"] == "image/png"
    assert embeds["part=3"]["fields"]["disposition"] == "inline"
    assert embeds["part=3"]["fields"]["content_id"] == "inline-img-1"

    assert embeds["part=4"]["media_type"] == "application/pdf"
    assert embeds["part=4"]["fields"]["filename"] == "contract.pdf"
    assert embeds["part=4"]["fields"]["disposition"] == "attachment"
    assert embeds["part=4"]["transport"] == records.format_hash("blake3", _b3(_PDF))

    assert embeds["part=5"]["media_type"] == "text/plain"  # QP attachment
    assert embeds["part=5"]["fields"]["filename"] == "notes.txt"
    # QP round-trip: the embed transport is blake3 of the CTE-decoded bytes the transform yields
    # (email normalizes a text part's line endings to CRLF on serialization).
    out5 = resolver.resolve(f"corpus://{eid}?part=5", root).read_bytes()
    assert b"attached notes line one" in out5
    assert embeds["part=5"]["transport"] == records.format_hash("blake3", _b3(out5))

    assert embeds["part=6"]["media_type"] == "message/rfc822"  # nested message
    assert embeds["part=6"]["fields"]["filename"] == "forwarded.eml"


def test_part_addresses_are_deterministic(tmp_path):
    root = _corpus(tmp_path)
    eid = _ingest_eml(tmp_path, root, _rich_eml())
    _draft(root, eid)
    first = [(e["address"], e["transport"]) for e in _embeds(root, eid)]
    # Re-derive from the same bytes → identical ordinals + transports (redraft path).
    text = redraft_cli.redraft_record(paths.record_path(root, eid), root)
    paths.record_path(root, eid).write_text(text, encoding="utf-8")
    second = [(e["address"], e["transport"]) for e in _embeds(root, eid)]
    assert first == second


# ---------- part= transform + promote a part ---------- #


def test_part_transform_and_promote_pdf(tmp_path):
    root = _corpus(tmp_path)
    eid = _ingest_eml(tmp_path, root, _rich_eml())
    _draft(root, eid)

    # The transform decodes the pdf part's bytes.
    out = resolver.resolve(f"corpus://{eid}?part=4", root)
    assert out.read_bytes() == _PDF

    # Promote the pdf part → a first-class application/pdf record; bytes never leave the message.
    assert _promote(root, f"corpus://{eid}?part=4") == 0
    pid = _b3(_PDF)
    post = records.load(paths.record_path(root, pid))
    assert records.media_type_for(post) == "application/pdf"
    assert not LocalArtifactStore(root).is_local(pid, "pdf")
    origin = next(records.iter_origin_blocks(post))["fields"]
    assert origin["uri"] == f"corpus://{eid}?part=4"
    assert origin["filename"] == "contract.pdf"  # the part named itself
    # Resolves back through containment.
    assert resolver.resolve(f"corpus://{pid}", root).read_bytes() == _PDF


def test_promote_docx_part_refines_zip_mime(tmp_path):
    """A promoted OOXML attachment types as its package mime, not application/zip — the
    ordinal `part=` address carries no extension, so the sniff name comes from the embed's
    declared `filename` and refines the zip-magic head within the family."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<w:document/>")
    docx_bytes = buf.getvalue()
    em = EmailMessage()
    em["From"] = "a@x"
    em["Subject"] = "handbook"
    em.set_content("see attached")
    em.add_attachment(
        docx_bytes,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="Volunteer Handbook.docx",
    )
    root = _corpus(tmp_path)
    eid = _ingest_eml(tmp_path, root, em.as_bytes(policy=policy.SMTP))
    _draft(root, eid)
    assert _promote(root, f"corpus://{eid}?part=2") == 0
    post = records.load(paths.record_path(root, _b3(docx_bytes)))
    assert (
        records.media_type_for(post)
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


# ---------- charset tolerance ---------- #


def test_non_utf8_charset_body(tmp_path):
    root = _corpus(tmp_path)
    em = EmailMessage()
    em["From"] = "a@x"
    em["Subject"] = "latin1"
    em.set_content("café costs £5", charset="iso-8859-1")
    eid = _ingest_eml(tmp_path, root, em.as_bytes(policy=policy.SMTP))
    assert _draft(root, eid) == 0
    body = records.load(paths.record_path(root, eid)).content or ""
    assert "caf" in body and "costs" in body  # decoded without raising


# ---------- lint ---------- #


def test_embed_unreferenced_relaxed_for_message(tmp_path):
    root = _corpus(tmp_path)
    eid = _ingest_eml(tmp_path, root, _rich_eml())
    _draft(root, eid)
    post = records.load(paths.record_path(root, eid))
    blocks = segments.iter_blocks(post.content or "")
    # A message record has a body segment AND part embeds; the embeds must NOT be flagged.
    assert list(lint._rule_embed_unreferenced(post, blocks, root)) == []


# ---------- redraft v1 → v2 ---------- #


def test_redraft_upgrades_v1_shape_to_v2(tmp_path):
    root = _corpus(tmp_path)
    eid = _ingest_eml(tmp_path, root, _rich_eml())
    _draft(root, eid)  # v2

    # Mangle the record into the v1 shape: a headers-block body + attachment inventory, and
    # strip the part embeds — as if drafted by the previous drafter.
    rf = paths.record_path(root, eid)
    post = records.load(rf)
    post.metadata["_embeds"] = []
    from corpus import recordbuild

    v1_body = "**From:** old\n\nbody\n\n**Attachments (1):**\n- x"
    build = recordbuild.begin_from_post(post, root)
    recordbuild.add_blocks(build, [segments.Segment(atom="text", address="block=1", body=v1_body)])
    recordbuild.finish(build)
    records.dump(post, rf)

    # Redraft re-derives from the retained artifact → the v2 shape.
    text = redraft_cli.redraft_record(rf, root)
    rf.write_text(text, encoding="utf-8")
    post = records.load(rf)
    assert "**From:**" not in (post.content or "")  # headers no longer in body
    assert records.artifact_block(post)["fields"]["from"] == "Björn <bjorn@example.com>"
    assert {e["address"] for e in records.iter_embed_blocks(post)} == {
        "part=3",
        "part=4",
        "part=5",
        "part=6",
    }


# ---------- three-hop: zip → mbox msg=N → eml part=K ---------- #


def test_three_hop_promote_and_resolve(tmp_path):
    """A contract PDF three containers deep: zip bundle → mbox message → eml part. Promote each
    hop and resolve the part — bytes cross three container hops (spec §12.9)."""
    root = _corpus(tmp_path)
    CRLF = b"\r\n"
    m = _rich_eml()
    mbox = b"From 1@x Mon Jan 01 00:00:00 +0000 2020" + CRLF + m
    z = tmp_path / "bundle.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Takeout/Mail/all.mbox", mbox)

    zid = _ingest(root, z)
    zpost = records.load(paths.record_path(root, zid))
    draft_cli.derive_record(zpost, root)
    records.dump(zpost, paths.record_path(root, zid))
    mbox_id = _b3(mbox)

    _promote(root, f"corpus://{zid}?path=Takeout/Mail/all.mbox")
    _draft(root, mbox_id, messages="1")
    eml_id = _b3(m)  # message 1's un-stuffed bytes == the eml bytes (no stuffing here)

    _promote(root, f"corpus://{mbox_id}?msg=1")
    _draft(root, eml_id)  # declares the eml's part embeds

    _promote(root, f"corpus://{eml_id}?part=4")
    pid = _b3(_PDF)
    assert not LocalArtifactStore(root).is_local(pid, "pdf")
    out = resolver.resolve(f"corpus://{pid}", root)  # zip → mbox → eml → part
    assert out.read_bytes() == _PDF


def _embeds(root: Path, rid: str) -> list[dict]:
    return list(records.iter_embed_blocks(records.load(paths.record_path(root, rid))))
