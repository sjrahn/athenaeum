"""The `contact-card` shaper (spec §7.8, §12.5.0, §12.19 step 6): one vCard's decomposition
into quotable, single-line `text/field` property facts.

Registered under the FORM id `contact-card` (vCard is a universal format — no per-origin JSON
mapping is needed, unlike the conversation shaper). Covers: the FN→N→ORG→NICKNAME→EMAIL→TEL
display-name fallback riding the role-marked `display_name` title field, RFC 6350 unfolding
(already done by `vcardfile`, exercised here through a folded long value), QUOTED-PRINTABLE
hex-escape decoding (incl. an explicit `CHARSET`), RFC 6350 §3.4 backslash-escape decoding
(`\\n` → a real newline, `\\;`/`\\,`/`\\\\` → the literal character) independent of any
`ENCODING`, the `b`/`BASE64` embedded-bytes exclusion (PHOTO renders header-only), grouped
(`item1.ADR`) properties, and the promoted-record integration path (containment-resolved
bytes, an origin overlay's `form: {id: contact-card}` declaration, the `corpus shape` CLI).
"""

from __future__ import annotations

import argparse
import base64

import frontmatter

from corpus import containment, lint, paths, recordbuild, records, schemas, segments, vcardfile
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli
from corpus._cli import shape as shape_cli
from corpus.shape import contact_card, get_shaper

_FAKE_SHA256 = "sha256:" + "a" * 64


def _corpus(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _ingest(root, raw: bytes, name: str = "contacts.vcf") -> str:
    from corpus import hashing

    src = root / name
    src.write_bytes(raw)
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / name
    import shutil

    shutil.copy(src, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    rid = hashing.hash_file(src)["blake3"]
    src.unlink()
    return rid


def _promote(root, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


def _record(root, rid: str) -> frontmatter.Post:
    return records.load(paths.record_path(root, rid))


def _shape(root, rid: str) -> frontmatter.Post:
    post = _record(root, rid)
    build = recordbuild.begin_from_post(post, root)
    contact_card.shape_contact_card(build, post, root, {})
    return recordbuild.finish(build)


def _section(post: frontmatter.Post) -> segments.Section:
    (sec,) = segments.iter_blocks(post.content or "")
    assert isinstance(sec, segments.Section)
    return sec


# ====================================================================== #
# A. pure helpers — decode/escape/binary detection (no corpus needed)
# ====================================================================== #


def _prop(line: str) -> vcardfile.Property:
    (card,), _skipped = vcardfile.parse_cards(
        f"BEGIN:VCARD\r\n{line}\r\nEND:VCARD\r\n".encode()
    )
    return card.properties[0]


def test_backslash_unescape_independent_of_encoding():
    # A bare component separator (`;`) stays a separator; only the ESCAPED one decodes, and
    # `\n` becomes a real embedded newline (RFC 6350 §3.4) — the ADR real-data finding.
    p = _prop(r"ADR:;;1235 11 AVE SW\nUNIT 1107;Calgary;AB;T3C0M5\;Extra;Canada")
    assert contact_card._decoded_value(p) == (
        ";;1235 11 AVE SW\nUNIT 1107;Calgary;AB;T3C0M5;Extra;Canada"
    )


def test_backslash_unescape_comma_and_backslash():
    p = _prop(r"NOTE:Comma\, backslash\\ done")
    assert contact_card._decoded_value(p) == "Comma, backslash\\ done"


def test_unknown_escape_left_verbatim():
    p = _prop(r"NOTE:weird \q escape")
    assert contact_card._decoded_value(p) == r"weird \q escape"  # parse-tolerant, not guessed


def test_quoted_printable_decode_with_explicit_charset():
    # 'é' as ISO-8859-1 0xE9, QP-escaped — the vCard 2.1 CHARSET+ENCODING combination.
    p = _prop("NOTE;ENCODING=QUOTED-PRINTABLE;CHARSET=ISO-8859-1:caf=E9")
    assert contact_card._decoded_value(p) == "café"


def test_quoted_printable_defaults_to_utf8_without_charset():
    text = "café".encode()
    qp = "".join(f"={b:02X}" if b > 127 else chr(b) for b in text)
    p = _prop(f"NOTE;ENCODING=QUOTED-PRINTABLE:{qp}")
    assert contact_card._decoded_value(p) == "café"


def test_qp_soft_break_and_hex_decode_compose():
    # A long QP value folded across TWO physical lines (2.1-style QP soft break: the value
    # line ends with `=` and the continuation carries NO leading whitespace — distinct from
    # the ordinary RFC 6350 fold, which vcardfile's unfold() checks first). vcardfile already
    # rejoins the soft break; this module then hex-decodes the composed QP escape. 'é' as
    # UTF-8 is the two bytes C3 A9 (no CHARSET declared → the default), split across the
    # fold so the soft-break rejoin is genuinely exercised mid-character.
    raw = b"BEGIN:VCARD\r\nNOTE;ENCODING=QUOTED-PRINTABLE:caf=C3=\r\n=A9 au lait\r\nEND:VCARD\r\n"
    (card,), _ = vcardfile.parse_cards(raw)
    assert contact_card._decoded_value(card.properties[0]) == "café au lait"


def test_binary_encoding_b_is_detected():
    p = _prop("PHOTO;ENCODING=b;TYPE=PNG:aGVsbG8=")
    assert contact_card._is_binary(p) is True


def test_binary_bare_base64_token_is_detected():
    # vCard 2.1 bare-type style: `;BASE64` with no `ENCODING=` key at all.
    p = _prop("PHOTO;BASE64;TYPE=PNG:aGVsbG8=")
    assert contact_card._is_binary(p) is True


def test_non_binary_folded_blob_is_not_detected_as_binary():
    # Apple's X-ADDRESSING-GRAMMAR / VND-...-CONFIG: a long opaque value with NO `ENCODING`
    # param at all — RFC 6350 generic line-folding applies to any value, not just base64/QP,
    # so this must render (not be excluded) even though it LOOKS like base64.
    p = _prop("X-ADDRESSING-GRAMMAR:looksLikeBase64ButIsNot==")
    assert contact_card._is_binary(p) is False


def test_rendered_params_keyed_and_bare():
    p = _prop("TEL;TYPE=CELL;PREF:5551234")
    assert contact_card._rendered_params(p) == ["TYPE=CELL", "PREF"]


def test_shaper_registered_under_form_id_contact_card():
    assert get_shaper("contact-card") is contact_card.shape_contact_card
    # Distinct from the conversation shapers (no accidental key collision).
    assert get_shaper("contact-card") is not get_shaper("conversation")


# ====================================================================== #
# B. real records — ingest → promote → shape (containment-resolved bytes)
# ====================================================================== #

_CARD_STEVEN = (
    b"BEGIN:VCARD\r\nVERSION:3.0\r\nN:Rahn;Steven;;;\r\nFN:Steven Rahn\r\n"
    b"ORG:CarbonAi;\r\n"
    b"EMAIL;TYPE=INTERNET;TYPE=HOME;TYPE=pref:sjrahn@example.com\r\n"
    b"TEL;TYPE=CELL;TYPE=VOICE;TYPE=pref:+15550001234\r\n"
    b"item1.ADR;TYPE=HOME;TYPE=pref:;;1235 11 AVE SW\\nUNIT 1107;Calgary;AB;T3C0M5;Canada\r\n"
    b"item1.X-ABADR:CA\r\n"
    b"BDAY;VALUE=date:1991-05-30\r\n"
    b"REV:2026-06-26T18:57:51Z\r\n"
    b"END:VCARD\r\n"
)
_CARD_NO_FN = (  # display-name fallback: N present, FN absent → formed N
    b"BEGIN:VCARD\r\nVERSION:3.0\r\nN:Turing;Alan;;;\r\nEND:VCARD\r\n"
)
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
_CARD_WITH_PHOTO = (
    b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:With Photo\r\n"
    b"PHOTO;ENCODING=b;TYPE=PNG:" + base64.b64encode(_PNG) + b"\r\n"
    b"END:VCARD\r\n"
)

_VCF = _CARD_STEVEN + _CARD_NO_FN + _CARD_WITH_PHOTO


def _promoted(root, ordinal: int, member: bytes):
    import blake3

    rid = _ingest(root, _VCF)
    assert _promote(root, f"corpus://{rid}?card={ordinal}") == 0
    pid = blake3.blake3(member).hexdigest()
    return pid


def test_display_name_no_longer_marks_the_title(tmp_path):
    root = _corpus(tmp_path)
    pid = _promoted(root, 1, _CARD_STEVEN)
    post = _shape(root, pid)
    sec = _section(post)
    assert sec.form == "contact-card"
    assert sec.extra["display_name"] == "Steven Rahn"
    records.dump(post, paths.record_path(root, pid))
    reloaded = _record(root, pid)
    # *(3.7, §12.29)* The form layer is out of the derived-editorial ladder. The shaped
    # `display_name` is still the span's own attested fact — it is simply not the record's
    # display title, because no section contributes one (§4.2.3, stated in 3.5).
    title = records.derived_editorial_field(reloaded, root, "title")
    assert title.layer != "form"


def test_display_name_falls_back_to_formed_n_without_fn(tmp_path):
    root = _corpus(tmp_path)
    pid = _promoted(root, 2, _CARD_NO_FN)
    post = _shape(root, pid)
    assert _section(post).extra["display_name"] == "Alan Turing"


def test_every_property_becomes_one_prop_addressed_segment(tmp_path):
    root = _corpus(tmp_path)
    pid = _promoted(root, 1, _CARD_STEVEN)
    post = _shape(root, pid)
    sec = _section(post)
    names = [s.extra["name"] for s in sec.segments]
    assert names == [
        "VERSION", "N", "FN", "ORG", "EMAIL", "TEL", "ADR", "X-ABADR", "BDAY", "REV",
    ]
    assert [s.address for s in sec.segments] == [f"prop={n}" for n in range(1, 11)]


def test_email_params_and_group_and_unfold_and_unescape(tmp_path):
    root = _corpus(tmp_path)
    pid = _promoted(root, 1, _CARD_STEVEN)
    post = _shape(root, pid)
    sec = _section(post)
    by_name = {s.extra["name"]: s for s in sec.segments if s.extra["name"] not in ("ADR",)}
    email = by_name["EMAIL"]
    assert email.extra["params"] == ["TYPE=INTERNET", "TYPE=HOME", "TYPE=pref"]
    assert email.body.strip() == "sjrahn@example.com"
    tel = by_name["TEL"]
    assert tel.body.strip() == "+15550001234"

    adr = next(s for s in sec.segments if s.extra["name"] == "ADR")
    assert adr.extra["group"] == "item1"
    # The escaped `\n` decoded to a REAL newline; the bare `;` separators are untouched.
    assert adr.body == ";;1235 11 AVE SW\nUNIT 1107;Calgary;AB;T3C0M5;Canada"

    abadr = next(s for s in sec.segments if s.extra["name"] == "X-ABADR")
    assert abadr.extra["group"] == "item1"


def test_photo_renders_header_only_no_body(tmp_path):
    root = _corpus(tmp_path)
    pid = _promoted(root, 3, _CARD_WITH_PHOTO)
    post = _shape(root, pid)
    sec = _section(post)
    photo = next(s for s in sec.segments if s.extra["name"] == "PHOTO")
    assert photo.body == ""
    assert "ENCODING=b" in photo.extra["params"]
    assert base64.b64encode(_PNG).decode() not in (post.content or "")  # never transcribed


def test_shaped_record_lints_clean_and_is_formed(tmp_path):
    root = _corpus(tmp_path)
    pid = _promoted(root, 1, _CARD_STEVEN)
    post = _shape(root, pid)
    records.dump(post, paths.record_path(root, pid))
    reloaded = _record(root, pid)
    blocks = segments.iter_blocks(reloaded.content or "")
    errors = [f for f in lint.lint(reloaded, blocks, root) if f.severity == "error"]
    assert not errors
    assert records.derived_state(reloaded) == "formed"


def test_bytes_resolve_containment_aware_like_a_promoted_conversation(tmp_path):
    # `_load_card` must go through `containment.ensure_local_bytes`, not a direct local file
    # read — the promoted record's bytes are bodiless, resident only in the parent `.vcf`.
    root = _corpus(tmp_path)
    pid = _promoted(root, 1, _CARD_STEVEN)
    from corpus import mime

    path = containment.ensure_local_bytes(root, pid, mime.extension_for("text/vcard"))
    assert path.read_bytes() == _CARD_STEVEN


# ====================================================================== #
# C. integration — an origin overlay's `form: {id: contact-card}` + `corpus shape`
# ====================================================================== #

_ORIGIN_OVERLAY = """\
description: a promoted contact card, test double for icloud-contacts-card
form:
  id: contact-card
"""


def _corpus_with_overlay(tmp_path):
    root = _corpus(tmp_path)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "test-contact-card.yaml").write_text(_ORIGIN_OVERLAY, encoding="utf-8")
    schemas.cache_clear()
    return root


def test_corpus_shape_cli_dispatches_via_declared_origin_form(tmp_path, capsys):
    root = _corpus_with_overlay(tmp_path)
    rid = _ingest(root, _VCF)
    assert _promote(root, f"corpus://{rid}?card=1") == 0
    import blake3

    pid = blake3.blake3(_CARD_STEVEN).hexdigest()
    post = _record(root, pid)
    records.append_origin_block(
        post, snapshot="2026-01-01T00:00:00Z", schema_id="test-contact-card",
        fields={"filename": "contacts.vcf", "source_modified": "2026-01-01T00:00:00"},
    )
    records.dump(post, paths.record_path(root, pid))

    assert shape_cli.run(argparse.Namespace(targets=[pid], corpus_root=str(root))) == 0
    out = capsys.readouterr().out
    assert f"shaped {pid[:12]} (contact-card)" in out

    reloaded = _record(root, pid)
    assert records.derived_state(reloaded) == "formed"
    # *(3.7, §12.29)* The form layer is out of the derived-editorial ladder. The shaped
    # `display_name` is still the span's own attested fact — it is simply not the record's
    # display title, because no section contributes one (§4.2.3, stated in 3.5).
    title = records.derived_editorial_field(reloaded, root, "title")
    assert title.layer != "form"
