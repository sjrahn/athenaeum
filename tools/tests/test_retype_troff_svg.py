"""The #149 retype sweep — `scripts/retype_troff_svg.py`.

Builds the exact shape the ticket found: an HTML page carrying an inline `data:` SVG, the
member promoted to its own record, and that record's artifact mime flipped to
`application/x-troff-man` the way the pre-fix sniffer typed it. The sweep must retype it,
refuse anything whose bytes disagree, and leave the population empty on a second run.
"""

from __future__ import annotations

import argparse
import base64
import runpy
import shutil
import sys
from pathlib import Path

import blake3

from corpus import hashing, paths, records, schemas, touches
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli

SWEEP = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "retype_troff_svg.py"))

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>'
PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 40


def _page_with_inline(tmp_path: Path, payload: bytes, media: str) -> tuple[Path, Path, str]:
    """A corpus holding one HTML container whose `el=1.2.2` member is `payload`, promoted —
    then mistyped as troff. Returns `(root, member record path, member id)`."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults
    schemas.cache_clear()

    b64 = base64.b64encode(payload).decode()
    src = tmp_path / "page.html"
    src.write_bytes(
        b"<!doctype html><html><body><div><p>hi</p><div><span>x</span>"
        + f'<img src="data:{media};base64,{b64}"></div></div></body></html>'.encode()
    )
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    shutil.copy(src, cap / src.name)
    assert ingest_cli._ingest_one(root, cap / src.name) == 0

    cid = hashing.hash_file(src)["blake3"]
    container = paths.record_path(root, cid)
    post = records.load(container)
    draft_cli.derive_record(post, root)
    records.dump(post, container)
    assert (
        promote_cli.run(
            argparse.Namespace(uri=f"corpus://{cid}?el=1.2.2", json=False, corpus_root=str(root))
        )
        == 0
    )

    mid = blake3.blake3(payload).hexdigest()
    member = paths.record_path(root, mid)
    member.write_text(member.read_text().replace(media, "application/x-troff-man"))
    return root, member, mid


def _run(monkeypatch, root: Path, *, apply: bool) -> None:
    argv = ["retype_troff_svg.py", "--corpus-root", str(root)] + (["--apply"] if apply else [])
    monkeypatch.setattr(sys, "argv", argv)
    assert SWEEP["main"]() == 0


def test_sweep_retypes_a_verified_inline_svg(tmp_path, monkeypatch):
    root, member, _mid = _page_with_inline(tmp_path, SVG, "image/svg+xml")

    _run(monkeypatch, root, apply=False)
    assert "application/x-troff-man" in member.read_text()  # dry run writes nothing

    _run(monkeypatch, root, apply=True)
    post = records.load(member)
    assert records.media_type_for(post) == "image/svg+xml"
    # The single-string touch becomes a two-item chain; the promote pass is preserved.
    assert touches.touch_list(post)[-2:] == [
        "corpus.promote@0.1.0",
        "corpus.migrate.retype-149@0.1.0",
    ]
    # The record leaves the population, so a re-run is a no-op.
    before = member.read_text()
    _run(monkeypatch, root, apply=True)
    assert member.read_text() == before


def test_sweep_retypes_to_what_the_bytes_prove(tmp_path, monkeypatch):
    # A mistyped PNG is the same defect wearing different bytes (the private hub's 44 are
    # DNGs): the sweep writes the type the sniffer proves from the bytes, not a preconceived
    # one — and refuses only when the bytes prove nothing.
    root, member, _mid = _page_with_inline(tmp_path, PNG, "image/png")

    _run(monkeypatch, root, apply=True)
    assert records.media_type_for(records.load(member)) == "image/png"


def test_sweep_refuses_bytes_it_cannot_name(tmp_path, monkeypatch):
    # Signature-less bytes sniff `unknown` with no filename: the troff type is wrong, but a
    # sweep that cannot prove the right type writes nothing.
    root, member, _mid = _page_with_inline(tmp_path, b"\x00\x01no signature here", "text/plain")

    _run(monkeypatch, root, apply=True)
    assert records.media_type_for(records.load(member)) == "application/x-troff-man"


def test_sweep_refuses_a_record_whose_id_is_not_its_bytes(tmp_path, monkeypatch):
    root, member, mid = _page_with_inline(tmp_path, SVG, "image/svg+xml")
    bogus = "ab" + "0" * 62
    forged = paths.record_path(root, bogus)
    forged.parent.mkdir(parents=True, exist_ok=True)
    forged.write_text(member.read_text().replace(mid, bogus))

    _run(monkeypatch, root, apply=True)
    assert records.media_type_for(records.load(forged)) == "application/x-troff-man"
    # …and the honest record beside it is still retyped.
    assert records.media_type_for(records.load(member)) == "image/svg+xml"
