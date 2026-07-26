"""text/vcard `card=<N>` member addressing — the 3.0 manifest rework (spec §12.18 step 4,
§12.11, §8.1). A `.vcf` is a MANIFEST: each contact card is a byte-exact `text/vcard` member
embed at `card=<N>`, attested eagerly at ingest, promotable to its own record. The 2.x per-card
`el=` text-segment drafting is retired.

The fixture `.vcf` is built in-test from known card byte-strings (so member blake3s are exact):
a CRLF card, an LF card with a folded continuation line + only `N` (formed display name), a CRLF
card carrying an embedded-bytes PHOTO (bytes stay INSIDE the card), and a trailing malformed
card (a `BEGIN:VCARD` with no `END:VCARD`).
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
from pathlib import Path

import blake3

from corpus import (
    containment,
    hashing,
    lint,
    mime,
    paths,
    records,
    resolver,
    schemas,
    segments,
    vcardfile,
)
from corpus import functional_uri as furi
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli
from corpus._cli import reattest as reattest_cli
from corpus.store import LocalArtifactStore

# A real 1x1 PNG (magic-sniffable), used for the embedded-photo-stays-inside path.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
_PNG_B64 = base64.b64encode(_PNG).decode()


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


# ---------- fixture cards (exact bytes) ---------- #

# Card 1 — CRLF, FN display name.
_C1 = (
    b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ada Lovelace\r\n"
    b"TEL;TYPE=CELL:+15550001111\r\nPRODID:-//Test//EN\r\nEND:VCARD\r\n"
)
# Card 2 — bare LF, a FOLDED continuation line, only `N` (→ formed display name).
_C2 = (
    b"BEGIN:VCARD\nVERSION:3.0\nN:Turing;Alan;;;\n"
    b"NOTE:a long value split across two lin\n es here\nPRODID:-//Test//EN\nEND:VCARD\n"
)
# Card 3 — CRLF, an embedded-bytes PHOTO whose base64 stays inside the card's member bytes.
_C3 = (
    b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:With Photo\r\n"
    b"PHOTO;ENCODING=b;TYPE=PNG:" + _PNG_B64.encode() + b"\r\nPRODID:-//Test//EN\r\nEND:VCARD\r\n"
)
# A trailing malformed card: BEGIN with no matching END before EOF.
_MALFORMED = b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:No End Here\r\n"

_VCF = _C1 + _C2 + _C3 + _MALFORMED
_MEMBERS = [_C1, _C2, _C3]  # the three well-formed cards, in ordinal order


# ---------- corpus / pipeline harness (mirrors test_mbox.py) ---------- #


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults
    schemas.cache_clear()
    return root


def _ingest(root: Path, raw: bytes, name: str = "contacts.vcf") -> str:
    src = root / name
    src.write_bytes(raw)
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / name
    shutil.copy(src, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    rid = hashing.hash_file(src)["blake3"]
    src.unlink()
    return rid


def _record(root: Path, rid: str):
    return records.load(paths.record_path(root, rid))


def _embeds(root: Path, rid: str) -> list[dict]:
    return list(records.iter_embed_blocks(_record(root, rid)))


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


# ====================================================================== #
# A. byte-exact extraction semantics (vcardfile)
# ====================================================================== #


def test_scan_delimits_every_wellformed_card_byte_exact():
    scan = vcardfile.scan(_VCF)
    assert scan.count == 3
    assert scan.skipped == 1  # the trailing unterminated card
    for facts, member in zip(scan.facts, _MEMBERS, strict=True):
        assert _VCF[facts.start : facts.end] == member  # the pinned span is verbatim
        assert facts.blake3 == _b3(member)
        assert facts.bytes == len(member)


def test_scan_is_terminator_agnostic_crlf_and_lf():
    # Card 1 ends CRLF, card 2 ends LF — the pins are byte-exact for either terminator.
    facts = vcardfile.scan(_VCF).facts
    assert _VCF[facts[0].start : facts[0].end] == _C1 and _C1.endswith(b"END:VCARD\r\n")
    assert _VCF[facts[1].start : facts[1].end] == _C2 and _C2.endswith(b"END:VCARD\n")


def test_resolve_member_by_path(tmp_path):
    p = tmp_path / "x.vcf"
    p.write_bytes(_VCF)
    assert vcardfile.resolve_member(p, 1) == _C1
    assert vcardfile.resolve_member(p, 2) == _C2
    assert vcardfile.resolve_member(p, 3) == _C3
    # A folded continuation line stays FOLDED in the member bytes (unfolding is read-time only).
    assert b"two lin\n es here" in _C2
    import pytest

    with pytest.raises(ValueError, match="no such card"):
        vcardfile.resolve_member(p, 9)


def test_photo_bytes_stay_inside_the_card_member():
    # The embedded base64 is part of card 3's member bytes — never lifted out.
    assert _PNG_B64.encode() in _C3
    assert vcardfile.scan(_VCF).facts[2].blake3 == _b3(_C3)


def test_display_name_fallback_chain():
    raw = (
        b"BEGIN:VCARD\r\nN:Smith;Jane;;Dr.;\r\nEND:VCARD\r\n"  # no FN → formed N
        b"BEGIN:VCARD\r\nORG:Acme;RnD\r\nEND:VCARD\r\n"  # → ORG first component
        b"BEGIN:VCARD\r\nEMAIL:solo@example.com\r\nEND:VCARD\r\n"  # → EMAIL
        b"BEGIN:VCARD\r\nREV:2020-01-01T00:00:00Z\r\nEND:VCARD\r\n"  # nothing usable → ordinal
    )
    names = [f.display_name for f in vcardfile.scan(raw).facts]
    assert names == ["Dr. Jane Smith", "Acme", "solo@example.com", "Card 4"]


def test_malformed_middle_card_resumes_at_next_begin():
    # A malformed card in the MIDDLE (missing END, then a fresh BEGIN) is skipped; the next
    # card keeps a contiguous ordinal.
    raw = (
        b"BEGIN:VCARD\r\nFN:Good\r\nEND:VCARD\r\n"
        b"BEGIN:VCARD\r\nFN:Broken\r\n"  # no END before the next BEGIN
        b"BEGIN:VCARD\r\nFN:AfterBreak\r\nEND:VCARD\r\n"
    )
    scan = vcardfile.scan(raw)
    assert scan.count == 2 and scan.skipped == 1
    assert [f.display_name for f in scan.facts] == ["Good", "AfterBreak"]
    assert [f.ordinal for f in scan.facts] == [1, 2]


# ====================================================================== #
# B. attest — one text/vcard embed per card at card=<N> (eager, at ingest)
# ====================================================================== #


def test_ingest_attests_one_card_embed_per_wellformed_card(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _VCF)
    embeds = _embeds(root, rid)
    by_addr = {e["address"]: e for e in embeds}
    assert set(by_addr) == {"card=1", "card=2", "card=3"}  # malformed card left no embed

    for n, member in zip((1, 2, 3), _MEMBERS, strict=True):
        e = by_addr[f"card={n}"]
        assert e["media_type"] == "text/vcard"
        assert e["transport"] == records.format_hash("blake3", _b3(member))
        assert e["fields"]["bytes"] == len(member)
    # *(3.4)* The card's display name (FN) is NOT stored. It is a reading of the member's
    # content, so the roster's closed four-key row has no place for it (spec §4.3.1.4) — it
    # comes from the `members` derivation instead. `bytes` survives because size accounting is
    # a cross-record question the roster exists to answer without opening artifacts.
    for n in (1, 2, 3):
        assert set(by_addr[f"card={n}"]["fields"]) == {"bytes"}


def test_manifest_content_zone_is_empty_and_lints_clean(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _VCF)
    post = _record(root, rid)
    assert records.derived_state(post) == "proxy"  # embeds don't count as a stored rendering
    assert not (post.content or "").strip()  # a manifest — the members ARE the content
    blocks = segments.iter_blocks(post.content or "")
    assert not [f for f in lint.lint(post, blocks, root) if f.severity == "error"]


def test_no_image_embed_lifted_for_embedded_photo(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _VCF)
    embeds = _embeds(root, rid)
    assert all(e["media_type"] == "text/vcard" for e in embeds)  # no image/* embed at attest
    assert not any(str(e["media_type"]).startswith("image/") for e in embeds)


def test_artifact_fields_card_count_version_prodid(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _VCF)
    fields = records.artifact_block(_record(root, rid))["fields"]
    assert fields["card_count"] == 3  # malformed excluded
    assert fields["vcard_version"] == "3.0"  # uniform
    assert fields["product_id"] == "-//Test//EN"  # uniform → surfaced


def test_malformed_card_counted_in_an_issue(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _VCF)
    issues = records.iter_issue_blocks(_record(root, rid))
    mal = [i for i in issues if "malformed" in (i.get("fields") or {}).get("description", "")]
    assert mal and (mal[0].get("fields") or {}).get("skipped_cards") == 1


def test_empty_file_yields_no_cards_and_an_issue(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, b"", name="empty.vcf")
    post = _record(root, rid)
    assert _embeds(root, rid) == []
    assert records.artifact_block(post)["fields"]["card_count"] == 0
    assert any(i.get("subtype") == "empty-body" for i in records.iter_issue_blocks(post))


def test_nonuniform_prodid_omitted(tmp_path):
    root = _corpus(tmp_path)
    raw = (
        b"BEGIN:VCARD\r\nPRODID:-//A//EN\r\nFN:One\r\nEND:VCARD\r\n"
        b"BEGIN:VCARD\r\nPRODID:-//B//EN\r\nFN:Two\r\nEND:VCARD\r\n"
    )
    rid = _ingest(root, raw)
    assert "product_id" not in records.artifact_block(_record(root, rid))["fields"]


# ====================================================================== #
# C. card= resolve — exact bytes, blake3 matches the embed transport
# ====================================================================== #


def test_resolver_card_resolves_exact_member_bytes(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _VCF)
    for n, member in zip((1, 2, 3), _MEMBERS, strict=True):
        out = resolver.resolve(f"corpus://{rid}?card={n}", root)
        assert out.read_bytes() == member
        assert _b3(out.read_bytes()) == _b3(member)


def test_card_sidecar_records_engine_version(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _VCF)
    out = resolver.resolve(f"corpus://{rid}?card=1", root)
    sidecar = furi.cache_sidecar_path(out)
    data = json.loads(sidecar.read_text("utf-8"))
    assert data["engine"] == "vcard-card@1"


def test_card_cache_key_includes_engine_version(tmp_path, monkeypatch):
    """The `card=` cache key folds in `transforms.vcard.CARD_ENGINE_VERSION`, independently of
    `prop=`'s own pin — verified by swapping the (monkeypatched) pin between two resolves of the
    SAME canonical URI and observing two distinct cache files (mirrors
    `test_video_muxing.py`'s `test_cache_key_includes_engine_version`)."""
    from corpus.transforms import vcard as vcard_tf

    root = _corpus(tmp_path)
    rid = _ingest(root, _VCF)

    monkeypatch.setattr(vcard_tf, "CARD_ENGINE_VERSION", "vcard-card@fake-1")
    out1 = resolver.resolve(f"corpus://{rid}?card=1", root)
    sidecar1 = json.loads(furi.cache_sidecar_path(out1).read_text())

    monkeypatch.setattr(vcard_tf, "CARD_ENGINE_VERSION", "vcard-card@fake-2")
    out2 = resolver.resolve(f"corpus://{rid}?card=1", root)
    sidecar2 = json.loads(furi.cache_sidecar_path(out2).read_text())

    assert out1 != out2
    assert sidecar1["engine"] == "vcard-card@fake-1"
    assert sidecar2["engine"] == "vcard-card@fake-2"


# ====================================================================== #
# D. promote round-trip — a card= member becomes its own text/vcard record
# ====================================================================== #


def test_promote_card_round_trip(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _VCF)

    assert _promote(root, f"corpus://{rid}?card=2") == 0
    pid = _b3(_C2)  # the promoted id equals the embed's blake3 transport
    post = _record(root, pid)
    assert post.metadata["id"] == pid
    assert records.media_type_for(post) == "text/vcard"
    # The origin records the containment lineage as history; a card has no member filename.
    origin = next(records.iter_origin_blocks(post))["fields"]
    assert origin["uri"] == f"corpus://{rid}?card=2"
    assert "filename" not in origin
    # Bytes were NOT copied out of the .vcf …
    assert not LocalArtifactStore(root).is_local(pid, "vcf")
    # … but they resolve back through containment (extracted from the container).
    out = resolver.resolve(f"corpus://{pid}", root)
    assert out.read_bytes() == _C2


def test_containment_open_member_stream_direct(tmp_path):
    p = tmp_path / "contacts.vcf"
    p.write_bytes(_VCF)
    with containment.open_member_stream(p, "text/vcard", "card=3") as fp:
        assert fp.read() == _C3
    assert containment.member_source_metadata(p, "text/vcard", "card=3") == {}


# ====================================================================== #
# E. reattest idempotence — the attested manifest re-derives byte-for-byte
# ====================================================================== #


def test_reattest_is_idempotent(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _VCF)
    rf = paths.record_path(root, rid)
    before = rf.read_text(encoding="utf-8")
    # Re-deriving the attested layer yields byte-identical output (no touch appended).
    assert reattest_cli.reattest_record(rf, root) == before


# ====================================================================== #
# MIME detection (unchanged)
# ====================================================================== #


def test_vcf_detects_as_text_vcard(tmp_path):
    f = tmp_path / "x.vcf"
    f.write_bytes(_C1)
    assert mime.detect(f) == "text/vcard"


def test_begin_vcard_magic_detects_without_extension(tmp_path):
    f = tmp_path / "contacts_no_ext"
    f.write_bytes(_C1)
    assert mime.detect(f) == "text/vcard"
