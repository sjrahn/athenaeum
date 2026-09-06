"""A terminal `part=<N>` on a textual MIME part decodes to text (spec §6.2 "Member
re-chaining": a terminal member address "decodes only an already-textual member (JSON, plain
text) to its text, so a citation prints cleanly rather than as an opaque cache path").

Defect: `corpus resolve '...?msg=10&part=1'` (or `?part=1` on a promoted eml) printed a
`.bin` cache path for the message's `text/plain` body part. `_rechain_member`'s textual-decode
check keys off a byte sniff with the address value as the filename hint — and a MIME part is
addressed by ORDINAL, so `"1"` guesses nothing, plain text has no magic, and the part sniffed
`unknown` → opaque `bytes`. The container knew the type all along (the part's own
Content-Type, the very fact its embed carries); an archive `path=notes.txt` member decoded
fine only because its NAME carried the extension. Consequence downstream: `ath ledger verify`
could not string-match a quote against a `msg=<N>&part=<M>` anchor — a textual surface the
spec promises is verifiable (`ledger.md` §13.2: "no honest citation form remains
unverifiable by construction").

Fix: the `part=` handler hands the part's declared facts (media type as its embed would carry
it, filename, charset) to the resolver through the render context; `_rechain_member` uses the
declaration where the sniff is blank (a positive sniff — magic, message shape — still wins),
decodes per the declared charset, and the same declaration lets a `text/html` part re-enter
the HTML pipeline (`part=<N>&el=<M>`). `part=` gains its own engine pin (`eml-part@1`) so a
stale pre-fix `.bin` under the old cache key is never served and a ledger binding through
`part=` pins the op like every other derivation axis.
"""

from __future__ import annotations

import json
from email import policy
from email.message import EmailMessage
from pathlib import Path

import frontmatter
import pytest

from corpus import hashing, paths, records, resolver, schemas
from corpus import mime as mime_mod
from corpus.store import LocalArtifactStore
from corpus.transforms import NotMaterializable

_PLAIN = "Reply body first line.\nItinerary: Kelowna → YVR, seat 12A.\n"
_HTML = "<html><body><h1>Title</h1><p>Reply body html.</p></body></html>"
_PDF = b"%PDF-1.4\nfake contract payload\n"
_NOTES = "attached notes line one\n"
_LATIN = "café latin\n"
CRLF = b"\r\n"


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults
    schemas.cache_clear()
    return root


def _stage_record(root: Path, data: bytes, *, mime: str, name: str) -> str:
    """Stage `data` as a standalone record under `mime`, bypassing ingest/draft — the
    resolver only needs the artifact block + bytes (mirrors `test_resolver_member_rechain`)."""
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


def _eml() -> bytes:
    """mixed[ alternative[ plain(base64), html ], pdf, txt(QP), latin-1 txt, msg ].
    Addressable parts (DFS): 1 plain, 2 html, 3 pdf, 4 notes.txt, 5 latin.txt, 6 nested."""
    em = EmailMessage()
    em["From"] = "Björn <bjorn@example.com>"
    em["To"] = "s@example.com"
    em["Date"] = "Tue, 02 Feb 2021 09:00:00 +0000"
    em["Subject"] = "Café meeting"
    em["Message-ID"] = "<m1@example.com>"
    em.set_content(_PLAIN, cte="base64")
    em.add_alternative(_HTML, subtype="html")
    em.add_attachment(_PDF, maintype="application", subtype="pdf", filename="contract.pdf")
    em.add_attachment(_NOTES, filename="notes.txt", cte="quoted-printable")
    em.add_attachment(
        _LATIN.encode("iso-8859-1"), maintype="text", subtype="plain",
        filename="latin.txt", cte="8bit",
    )
    em.get_payload()[-1].set_param("charset", "iso-8859-1")
    inner = EmailMessage()
    inner["Subject"] = "Fwd inner"
    inner.set_content("inner body\n")
    em.add_attachment(inner, filename="fwd.eml")
    return em.as_bytes(policy=policy.SMTP)


def _mbox_around(raw_eml: bytes) -> bytes:
    """A two-message mboxrd: a trivial first message, then `raw_eml` as `msg=2`."""
    return (
        b"From 111@xxx Mon Jan 01 00:00:00 +0000 2020" + CRLF
        + b"From: a@example.com" + CRLF + b"Subject: one" + CRLF + CRLF + b"body one" + CRLF
        + b"From 222@xxx Tue Feb 02 09:00:00 +0000 2021" + CRLF
        + raw_eml
    )


@pytest.fixture
def eml_record(tmp_path):
    root = _corpus(tmp_path)
    return root, _stage_record(root, _eml(), mime="message/rfc822", name="m.eml")


@pytest.fixture
def mbox_record(tmp_path):
    root = _corpus(tmp_path)
    return root, _stage_record(root, _mbox_around(_eml()), mime="application/mbox", name="m.mbox")


def _sidecar(out: Path) -> dict:
    (side,) = out.parent.glob(out.stem + "*.json")
    return json.loads(side.read_text("utf-8"))


# ---------- the defect: a text/plain part prints as text ---------- #


def test_terminal_text_plain_part_decodes_to_text(eml_record):
    root, rid = eml_record
    out = resolver.resolve(f"corpus://{rid}?part=1", root)
    assert out.suffix == ".txt"
    assert out.read_text("utf-8") == _PLAIN  # CTE-decoded (base64) AND charset-decoded
    side = _sidecar(out)
    assert side["mime"] == "text/plain"
    assert side["engine"] == "eml-part@1"


def test_named_text_attachment_decodes_to_text(eml_record):
    """A filename-bearing text part (QP-encoded) — the name feeds the sniff's extension
    refinement; the result is the transfer-decoded text either way."""
    root, rid = eml_record
    out = resolver.resolve(f"corpus://{rid}?part=4", root)
    assert out.suffix == ".txt"
    assert out.read_text("utf-8").rstrip("\r\n") == _NOTES.rstrip("\n")


def test_declared_charset_governs_the_decode(eml_record):
    """A `charset=iso-8859-1` part decodes per its declaration — `café`, not a
    replacement character — so a ledger quote matches what the message actually says."""
    root, rid = eml_record
    out = resolver.resolve(f"corpus://{rid}?part=5", root)
    assert out.suffix == ".txt"
    assert out.read_text("utf-8").startswith("café latin")


def test_text_html_part_prints_its_source_when_terminal(eml_record):
    root, rid = eml_record
    out = resolver.resolve(f"corpus://{rid}?part=2", root)
    assert out.suffix == ".txt"
    assert "<h1>Title</h1>" in out.read_text("utf-8")
    assert _sidecar(out)["mime"] == "text/html"


# ---------- the declaration is a fallback: positively-sniffed bytes are untouched ---------- #


def test_binary_attachment_stays_raw_bytes_with_its_real_extension(eml_record):
    root, rid = eml_record
    out = resolver.resolve(f"corpus://{rid}?part=3", root)
    assert out.suffix == ".pdf"
    assert out.read_bytes() == _PDF
    assert _sidecar(out)["mime"] == "application/pdf"


def test_nested_message_part_stays_eml_bytes(eml_record):
    root, rid = eml_record
    out = resolver.resolve(f"corpus://{rid}?part=6", root)
    assert out.suffix == ".eml"
    assert b"Subject: Fwd inner" in out.read_bytes()
    assert _sidecar(out)["mime"] == "message/rfc822"


# ---------- an html part re-chains into the HTML pipeline (§6.2) ---------- #


def test_text_html_part_rechains_into_el(eml_record):
    """`part=<N>&el=<M>` reaches the HTML pipeline: `el=1` names the `<h1>` — a REAL text
    element with no byte surface, which the html transform reports as `NotMaterializable`
    exactly as it does on a top-level HTML record (never `transform 'el' not applicable to
    working kind 'bytes'`, the pre-fix failure)."""
    root, rid = eml_record
    with pytest.raises(NotMaterializable, match="el=1 resolved to <h1>"):
        resolver.resolve(f"corpus://{rid}?part=2&el=1", root)


# ---------- through an mbox: msg=<N>&part=<M> ---------- #


def test_mbox_message_part_decodes_to_text(mbox_record):
    """The composition the defect was reported on: `msg=<N>&part=<M>` on the mailbox
    itself, no promotion — the text/plain alternative prints as text, keyed on the part
    step's own pin (the more specific op governs the bytes served)."""
    root, mid = mbox_record
    # the message itself (terminal `msg=`) is unchanged: raw `.eml` bytes under the mbox pin
    msg = resolver.resolve(f"corpus://{mid}?msg=2", root)
    assert msg.suffix == ".eml" and _sidecar(msg)["engine"] == "mbox-msg@1"
    out = resolver.resolve(f"corpus://{mid}?msg=2&part=1", root)
    assert out.suffix == ".txt"
    assert out.read_text("utf-8") == _PLAIN
    assert _sidecar(out)["engine"] == "eml-part@1"


def test_mbox_message_html_part_rechains_into_el(mbox_record):
    root, mid = mbox_record
    with pytest.raises(NotMaterializable, match="el=1 resolved to <h1>"):
        resolver.resolve(f"corpus://{mid}?msg=2&part=2&el=1", root)


# ---------- the pin is introspectable (what a ledger binding stamps) ---------- #


def test_part_op_carries_its_engine_pin(eml_record):
    root, _ = eml_record
    ops = {op.param: op for op in resolver.ops_for_media_type(root, "message/rfc822")}
    assert ops["part"].engine_version == "eml-part@1"
    assert resolver.engine_version_for_param("part") == "eml-part@1"


# ---------- ledger: a msg=&part= anchor verifies against the derived text ---------- #


def test_ledger_verifies_quote_through_msg_and_part(mbox_record):
    """The report that surfaced the defect: citations anchored `msg=<N>&part=<M>` came back
    `unverifiable` ("derived surface is not textual (.bin)"). Now the resolver hands verify a
    textual surface and the quote matches verbatim; the binding pins the part op."""
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    root, mid = mbox_record
    ledger = root.parent / "ledger"
    (ledger / "facts" / "event").mkdir(parents=True)
    (ledger / "facts" / "event" / "trip.json").write_text(json.dumps({
        "id": "trip", "type": "event", "name": "Kelowna trip",
        "sources": {"s1": {"record": mid}},
        "claims": [{"id": "trip:seat", "predicate": "seat", "value": "12A",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "msg=2&part=1",
                                  "quote": "Kelowna → YVR, seat 12A",
                                  "kind": "authoritative"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=True, today="2026-09-02")
    assert res.unverifiable == 0 and not res.errors, (res.errors, res.notes)
    assert res.verified == 1 and res.derived_resolved == 1
    fact = json.loads((ledger / "facts" / "event" / "trip.json").read_text())
    assert fact["sources"]["s1"]["verified"]["ops"] == {"msg": "mbox-msg@1"}
