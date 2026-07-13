"""text/vcard drafter — one `el=`-addressable text segment per contact card, faithful labeled
rendering, RFC 6350 unfolding, embedded-PHOTO lift to an image embed + marker, and house
parse-tolerance (skip a malformed card, never fail the file). Fixtures are built in-test.
"""

from __future__ import annotations

import base64
import shutil
from pathlib import Path

import blake3

from corpus import hashing, lint, mime, paths, records, schemas, segments
from corpus._cli import ingest as ingest_cli
from corpus.draft import vcard

# A real 1x1 PNG (magic-sniffable), used for the embedded-photo path.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
_PNG_B64 = base64.b64encode(_PNG).decode()


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _card(*lines: str) -> str:
    body = "".join(f"{line}\r\n" for line in lines)
    return "BEGIN:VCARD\r\nVERSION:3.0\r\n" + body + "END:VCARD\r\n"


# ---------- corpus harness (mirrors test_eml.py) ---------- #


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _ingest_vcf(tmp_path: Path, root: Path, raw: bytes, name: str = "contacts.vcf") -> str:
    src = tmp_path / name
    src.write_bytes(raw)
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / name
    shutil.copy(src, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    return hashing.hash_file(src)["blake3"]


def _draft(root: Path, target: str) -> int:
    from tests._draftlib import draft_for_test

    return draft_for_test(root, target)


def _record(root: Path, rid: str):
    return records.load(paths.record_path(root, rid))


def _blocks(post):
    return segments.iter_blocks(post.content or "")


def _drafted(tmp_path, raw: bytes):
    root = _corpus(tmp_path)
    rid = _ingest_vcf(tmp_path, root, raw)
    assert _draft(root, rid) == 0
    post = _record(root, rid)
    return root, rid, post


# ---------- unfolding (unit) ---------- #


def _unfolded(text: str) -> list[str]:
    # A file's trailing newline leaves a harmless empty logical line (ignored downstream).
    return [line for line in vcard.unfold(text) if line]


def test_unfold_rejoins_continuation_lines():
    text = "NOTE:one long value split across two physical li\r\n nes here\r\nFN:X\r\n"
    assert _unfolded(text) == ["NOTE:one long value split across two physical lines here", "FN:X"]


def test_unfold_tolerates_tab_continuation_and_bare_lf():
    text = "NOTE:a\n\tb\nFN:Y\n"  # tab continuation, LF-only endings
    assert _unfolded(text) == ["NOTE:ab", "FN:Y"]


def test_unfold_qp_softbreak_continuation():
    # A vCard 2.1 QUOTED-PRINTABLE `=`-terminated line continues onto the next physical line.
    text = "NOTE;ENCODING=QUOTED-PRINTABLE:caf=C3=A9 =\r\nnext\r\n"
    assert _unfolded(text) == ["NOTE;ENCODING=QUOTED-PRINTABLE:caf=C3=A9 next"]


# ---------- one segment per card ---------- #


def test_one_text_segment_per_card_flat_with_entries(tmp_path):
    raw = (_card("FN:Ada Lovelace") + _card("FN:Alan Turing") + _card("FN:Grace Hopper")).encode()
    _root, _rid, post = _drafted(tmp_path, raw)
    blocks = _blocks(post)
    assert all(isinstance(b, segments.Segment) and b.atom == "text" for b in blocks)
    assert [b.address for b in blocks] == ["el=1", "el=2", "el=3"]
    assert [b.entry for b in blocks] == ["Ada Lovelace", "Alan Turing", "Grace Hopper"]
    assert records.artifact_block(post)["fields"]["card_count"] == 3


def test_body_renders_every_property_faithfully(tmp_path):
    raw = _card(
        "FN:Adam Dickins",
        "N:Dickins;Adam;;;",
        "TEL;TYPE=CELL:+15551234567",
        "EMAIL;TYPE=HOME:adam@example.com",
        "item1.TEL;type=pref:58083",
        "CATEGORIES:myContacts",
    ).encode()
    _root, _rid, post = _drafted(tmp_path, raw)
    body = _blocks(post)[0].body
    assert "- **FN**: Adam Dickins" in body
    assert "- **N**: Dickins;Adam;;;" in body  # structured value verbatim
    assert "- **TEL** (TYPE=CELL): +15551234567" in body  # meaningful param preserved
    assert "- **EMAIL** (TYPE=HOME): adam@example.com" in body
    assert "- **item1.TEL** (type=pref): 58083" in body  # apple group prefix preserved
    assert "- **CATEGORIES**: myContacts" in body


# ---------- display-name fallback ---------- #


def test_display_name_fallback_chain(tmp_path):
    raw = (
        _card("N:Smith;Jane;;Dr.;")  # no FN → formed N
        + _card("ORG:Acme;RnD")  # no FN/N → ORG first component
        + _card("EMAIL:solo@example.com")  # → EMAIL
        + _card("REV:2020-01-01T00:00:00Z")  # nothing usable → ordinal
    ).encode()
    _root, _rid, post = _drafted(tmp_path, raw)
    assert [b.entry for b in _blocks(post)] == [
        "Dr. Jane Smith",
        "Acme",
        "solo@example.com",
        "Card 4",
    ]


# ---------- embedded photo extraction ---------- #


def test_embedded_photo_lifts_to_embed_and_marker(tmp_path):
    raw = (
        _card("FN:With Photo", f"PHOTO;ENCODING=b;TYPE=PNG:{_PNG_B64}")
        + _card("FN:No Photo")
    ).encode()
    root, _rid, post = _drafted(tmp_path, raw)

    embeds = list(records.iter_embed_blocks(post))
    assert len(embeds) == 1
    assert embeds[0]["media_type"] == "image/png"
    assert embeds[0]["address"] == "el=1"
    assert embeds[0]["transport"] == records.format_hash("blake3", _b3(_PNG))

    blocks = _blocks(post)
    # text el=1 (with entry) + image marker el=1 (body-empty, no entry) + text el=2.
    assert (blocks[0].atom, blocks[0].address, blocks[0].entry) == ("text", "el=1", "With Photo")
    assert (blocks[1].atom, blocks[1].address, blocks[1].entry, blocks[1].body) == (
        "image",
        "el=1",
        None,
        "",
    )
    assert (blocks[2].atom, blocks[2].address, blocks[2].entry) == ("text", "el=2", "No Photo")
    # The megabytes are NOT in any body.
    assert _PNG_B64 not in (post.content or "")

    # Lint: text + image at el=1 do NOT collide (distinct opener-ids); the marker leaves the
    # expected entry-missing advisory but no errors (the task's pre-approved draft warning).
    findings = lint.lint(post, blocks, root)
    assert not [f for f in findings if f.severity == "error"]
    assert not [f for f in findings if f.rule_id == "embed-missing-target"]
    assert not [f for f in findings if f.rule_id == "embed-unreferenced"]
    assert [f for f in findings if f.rule_id == "entry-missing"]


def test_repeated_photo_dedups_to_one_embed_with_address_list(tmp_path):
    raw = (
        _card("FN:A", f"PHOTO;ENCODING=b;TYPE=PNG:{_PNG_B64}")
        + _card("FN:B", f"PHOTO;ENCODING=b;TYPE=PNG:{_PNG_B64}")
    ).encode()
    _root, _rid, post = _drafted(tmp_path, raw)
    embeds = list(records.iter_embed_blocks(post))
    assert len(embeds) == 1  # same bytes → one embed
    assert embeds[0]["address"] == ["el=1", "el=2"]  # both card positions


def test_photo_url_is_a_field_not_an_embed(tmp_path):
    # Google Contacts exports every photo as an external URL — never embedded bytes.
    raw = _card("FN:Adam", "PHOTO:https://lh3.googleusercontent.com/contacts/AB123").encode()
    _root, _rid, post = _drafted(tmp_path, raw)
    assert list(records.iter_embed_blocks(post)) == []
    assert "- **PHOTO**: https://lh3.googleusercontent.com/contacts/AB123" in _blocks(post)[0].body


# ---------- malformed-card tolerance ---------- #


def test_malformed_card_skipped_not_fatal(tmp_path):
    good = _card("FN:Good One")
    raw = (good + "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:No End Here\r\n").encode()  # 2nd unterminated
    _root, _rid, post = _drafted(tmp_path, raw)
    blocks = _blocks(post)
    assert [b.entry for b in blocks] == ["Good One"]  # good card survived; broken one skipped
    assert records.artifact_block(post)["fields"]["card_count"] == 1
    issues = records.iter_issue_blocks(post)
    assert any("malformed" in (i.get("fields") or {}).get("description", "") for i in issues)


# ---------- quoted-printable ---------- #


def test_quoted_printable_value_decoded_to_content(tmp_path):
    raw = _card("FN:QP", "NOTE;ENCODING=QUOTED-PRINTABLE;CHARSET=UTF-8:caf=C3=A9").encode()
    _root, _rid, post = _drafted(tmp_path, raw)
    body = _blocks(post)[0].body
    assert "- **NOTE**: café" in body  # decoded; consumed ENCODING/CHARSET params dropped
    assert "QUOTED-PRINTABLE" not in body


# ---------- empty file ---------- #


def test_empty_file_yields_no_cards_and_an_issue(tmp_path):
    _root, _rid, post = _drafted(tmp_path, b"")
    assert _blocks(post) == []
    assert records.artifact_block(post)["fields"]["card_count"] == 0
    assert any(i.get("subtype") == "empty-body" for i in records.iter_issue_blocks(post))


# ---------- artifact fields ---------- #


def test_artifact_fields_version_and_uniform_prodid(tmp_path):
    raw = (
        _card("PRODID:-//Test//EN", "FN:One") + _card("PRODID:-//Test//EN", "FN:Two")
    ).encode()
    _root, _rid, post = _drafted(tmp_path, raw)
    fields = records.artifact_block(post)["fields"]
    assert fields["card_count"] == 2
    assert fields["vcard_version"] == "3.0"
    assert fields["product_id"] == "-//Test//EN"  # uniform → surfaced


def test_nonuniform_prodid_is_omitted(tmp_path):
    raw = (_card("PRODID:-//A//EN", "FN:One") + _card("PRODID:-//B//EN", "FN:Two")).encode()
    _root, _rid, post = _drafted(tmp_path, raw)
    assert "product_id" not in records.artifact_block(post)["fields"]


# ---------- clean lint on a realistic (photo-free) directory ---------- #


def test_photo_free_directory_lints_clean(tmp_path):
    raw = (
        _card("FN:Ada Lovelace", "TEL;TYPE=CELL:+15550001111")
        + _card("N:Turing;Alan;;;", "EMAIL:alan@example.com")
        + _card("ORG:Acme;", "item1.TEL;type=pref:58083")
    ).encode()
    root, _rid, post = _drafted(tmp_path, raw)
    assert lint.lint(post, _blocks(post), root) == []


# ---------- mime detection ---------- #


def test_vcf_detects_as_text_vcard(tmp_path):
    f = tmp_path / "x.vcf"
    f.write_bytes(_card("FN:Ada").encode())
    assert mime.detect(f) == "text/vcard"


def test_begin_vcard_magic_detects_without_extension(tmp_path):
    f = tmp_path / "contacts_no_ext"
    f.write_bytes(_card("FN:Ada").encode())
    assert mime.detect(f) == "text/vcard"
