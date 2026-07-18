"""The vcard `prop=<N>` resolver transform (spec §6.2, §12.11) — `transforms/vcard.py`.

Defect: the resolver had no `prop=` transform at all (`transform "prop" not applicable to
working kind "vcard"`), so a `?prop=N` citation anchor — the same datum `ath ledger verify`
checks for a formed contact-card record — couldn't be resolved directly. The fix registers
`prop=` on the `vcard` working kind, decoding each property EXACTLY as the `contact-card`
shaper does (`shape/contact_card.py`) — both now share `vcardfile.is_binary` /
`vcardfile.decoded_value`, one point of truth, so a `prop=N` citation always resolves to the
same text the formed record's `prop=N` segment renders. Covers: plain-text properties,
QUOTED-PRINTABLE decoding, the binary (PHOTO/BASE64) exclusion as a clear error (never a
guessed rendering), out-of-range / non-positive ordinals, the engine-version cache pin, and
the CRITICAL parity check against the shaper's own segment bodies.
"""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

import pytest

from corpus import functional_uri as furi
from corpus import hashing, paths, recordbuild, records, resolver, schemas, segments
from corpus._cli import ingest as ingest_cli
from corpus.shape import contact_card

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
_PNG_B64 = base64.b64encode(_PNG)

# Properties, in order: 1=VERSION, 2=FN (plain text), 3=NOTE (QUOTED-PRINTABLE, decodes to
# "Hello, World"), 4=PHOTO (binary — no decoded text, header-only like the shaper's segment).
_CARD = (
    b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ada Lovelace\r\n"
    b"NOTE;ENCODING=QUOTED-PRINTABLE:Hello=2C World\r\n"
    b"PHOTO;ENCODING=b;TYPE=PNG:" + _PNG_B64 + b"\r\n"
    b"END:VCARD\r\n"
)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _ingest(root: Path, raw: bytes, name: str = "contact.vcf") -> str:
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


def test_prop_resolves_plain_text_property(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _CARD)
    out = resolver.resolve(f"corpus://{rid}?prop=2", root)
    assert out.read_text("utf-8") == "Ada Lovelace"


def test_prop_quoted_printable_decodes(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _CARD)
    out = resolver.resolve(f"corpus://{rid}?prop=3", root)
    assert out.read_text("utf-8") == "Hello, World"


def test_prop_binary_property_raises_clear_error_not_a_guess(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _CARD)
    with pytest.raises(ValueError, match="binary-encoded"):
        resolver.resolve(f"corpus://{rid}?prop=4", root)


def test_prop_out_of_range_raises_clear_error(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _CARD)
    with pytest.raises(ValueError, match=r"out of range \(4 propert"):
        resolver.resolve(f"corpus://{rid}?prop=99", root)


def test_prop_zero_is_rejected_as_non_1_indexed(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _CARD)
    with pytest.raises(ValueError, match="1-indexed"):
        resolver.resolve(f"corpus://{rid}?prop=0", root)


def test_prop_non_integer_ordinal_raises_clear_error(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _CARD)
    with pytest.raises(ValueError, match="not an integer ordinal"):
        resolver.resolve(f"corpus://{rid}?prop=two", root)


def test_prop_sidecar_records_engine_version(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, _CARD)
    out = resolver.resolve(f"corpus://{rid}?prop=2", root)
    sidecar = furi.cache_sidecar_path(out)
    data = json.loads(sidecar.read_text("utf-8"))
    assert data["engine"] == "vcard-prop@1"


def test_prop_matches_the_shaped_segment_body_exactly(tmp_path):
    """The CRITICAL parity requirement: `resolve(...?prop=N)` must hand back EXACTLY what the
    `contact-card` shaper renders at that same `prop=N` segment address — a citation and the
    formed record's own rendering are the same datum, never two hand-drifted copies."""
    root = _corpus(tmp_path)
    rid = _ingest(root, _CARD)
    post = records.load(paths.record_path(root, rid))
    build = recordbuild.begin_from_post(post, root)
    contact_card.shape_contact_card(build, post, root, {})
    shaped = recordbuild.finish(build)
    (sec,) = segments.iter_blocks(shaped.content or "")
    assert len(sec.segments) == 4  # VERSION, FN, NOTE, PHOTO

    checked_binary = False
    for seg in sec.segments:
        n = int(seg.address.split("=", 1)[1])
        if not seg.body:
            # The binary PHOTO property: header-only (empty body) in the shaped record, and
            # the resolver refuses the same way — a clear error, never a guessed rendering.
            with pytest.raises(ValueError, match="binary-encoded"):
                resolver.resolve(f"corpus://{rid}?prop={n}", root)
            checked_binary = True
            continue
        out = resolver.resolve(f"corpus://{rid}?prop={n}", root)
        assert out.read_text("utf-8") == seg.body
    assert checked_binary  # sanity: the binary branch was actually exercised
