"""v43 (spec §6.2): `text` / `el=<N>&text` on HTML, and `cid:` intra-container references.

(1) `text` — the markup's own text reduction, whole-document (`?text`) and element-scoped
(`el=<N>&text`): document order, block-aware line breaks, cells tab-separated, `<head>`/
`<script>`/`<style>` dropped, whitespace normalized; never a rendering, nothing removed on
judgment. The citable surface of an HTML-only message (`msg=<N>&part=<M>&text`).

(2) `cid:` — an `<img src="cid:…">` (or media/attachment carrier) in message-borne HTML names
a sibling MIME part by Content-ID (RFC 2392). It materializes THROUGH the enclosing message
the `part=` handler leaves in the render context — never inlined into stored bytes — and
with no enclosing message it is a hard error naming the missing part.

(3) A container member's `el=` speaks the current ordinal grammar (no record, no stamp):
`_rechain_member` stamps it, so `msg=<N>&part=<M>&el=<K>` counts every element, not the
frozen pre-3.6 whitelist.
"""

from __future__ import annotations

import io
import json
from email import policy
from email.message import EmailMessage
from pathlib import Path

import frontmatter
import pytest
from bs4 import BeautifulSoup
from PIL import Image

from corpus import hashing, paths, records, resolver, schemas
from corpus import mime as mime_mod
from corpus.store import LocalArtifactStore
from corpus.transforms import html as html_tf

CRLF = b"\r\n"
_HTML = (
    "<html><head><title>Ignored title</title><style>p{color:red}</style></head>"
    "<body><h1>Itinerary</h1>"
    "<p>Kelowna &rarr; YVR,\n   seat   <b>12A</b>.</p>"
    "<script>var x = 1;</script>"
    "<table><tr><th>Flight</th><th>Date</th></tr><tr><td>AC 8421</td><td>Sept 19</td></tr></table>"
    "<div>Line one<br>Line two</div>"
    '<img src="cid:logo@example.com" alt="logo">'
    "</body></html>"
)
_EXPECTED_TEXT = (
    "Itinerary\n\n"
    "Kelowna → YVR, seat 12A.\n\n"
    "Flight\tDate\n\n"
    "AC 8421\tSept 19\n\n"
    "Line one\nLine two\n"
)


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 3), (10, 200, 30)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _png()


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _stage_record(root: Path, data: bytes, *, mime: str, name: str, fields=None) -> str:
    src = root.parent / name
    src.write_bytes(data)
    rid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(rid, mime_mod.extension_for(mime), src)
    post = frontmatter.Post("")
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"))
    records.set_artifact_block(post, mime=mime, fields=fields or {})
    records.append_origin_block(
        post, snapshot="2026-07-18T00:00:00Z", fields={"filename": name, "source_modified": ""}
    )
    records.dump(post, paths.record_path(root, rid))
    return rid


def _html_only_eml() -> bytes:
    """related[ html(cid img), png(Content-ID) ] — an HTML-only message with one inline
    image. Addressable parts: 1 html, 2 png."""
    em = EmailMessage()
    em["From"] = "Expedia <noreply@example.com>"
    em["To"] = "s@example.com"
    em["Date"] = "Tue, 02 Feb 2021 09:00:00 +0000"
    em["Subject"] = "Your e-ticket"
    em["Message-ID"] = "<t1@example.com>"
    em.set_content(_HTML, subtype="html")
    em.make_related()
    em.add_related(_PNG, maintype="image", subtype="png", cid="<logo@example.com>")
    return em.as_bytes(policy=policy.SMTP)


def _mbox_around(raw_eml: bytes) -> bytes:
    return (
        b"From 111@xxx Mon Jan 01 00:00:00 +0000 2020" + CRLF
        + b"From: a@example.com" + CRLF + b"Subject: one" + CRLF + CRLF + b"body one" + CRLF
        + b"From 222@xxx Tue Feb 02 09:00:00 +0000 2021" + CRLF
        + raw_eml
    )


def _img_ordinal() -> int:
    soup = BeautifulSoup(_HTML, "html.parser")
    root = html_tf.path_root(soup)
    for tag in html_tf.iter_elements_preorder(root):
        if tag.name == "img":
            return html_tf.element_ordinal(tag, root)
    raise AssertionError("no <img> in fixture")


# ---------- (1) the text reduction ---------- #


def test_html_text_reduction_is_block_aware_and_drops_non_text():
    assert html_tf.html_text(BeautifulSoup(_HTML, "html.parser")) == _EXPECTED_TEXT


def test_text_op_on_an_html_record(tmp_path):
    root = _corpus(tmp_path)
    total = html_tf.total_element_count(BeautifulSoup(_HTML, "html.parser"))
    rid = _stage_record(
        root, _HTML.encode(), mime="text/html", name="page.html",
        fields={"addressing": {"parser": "html.parser", "elements": total, "scheme": "ordinal"}},
    )
    out = resolver.resolve(f"corpus://{rid}?text", root)
    assert out.suffix == ".txt"
    assert out.read_text("utf-8") == _EXPECTED_TEXT


def test_el_text_is_element_scoped(tmp_path):
    root = _corpus(tmp_path)
    soup = BeautifulSoup(_HTML, "html.parser")
    total = html_tf.total_element_count(soup)
    rid = _stage_record(
        root, _HTML.encode(), mime="text/html", name="page.html",
        fields={"addressing": {"parser": "html.parser", "elements": total, "scheme": "ordinal"}},
    )
    proot = html_tf.path_root(soup)
    (table,) = [t for t in html_tf.iter_elements_preorder(proot) if t.name == "table"]
    n = html_tf.element_ordinal(table, proot)
    out = resolver.resolve(f"corpus://{rid}?el={n}&text", root)
    assert out.read_text("utf-8") == "Flight\tDate\n\nAC 8421\tSept 19\n"


def test_text_ops_are_introspectable_for_html(tmp_path):
    root = _corpus(tmp_path)
    ops = {(op.from_kind, op.param) for op in resolver.ops_for_media_type(root, "text/html")}
    assert ("html", "text") in ops and ("htmlel", "text") in ops


# ---------- (2)+(3) cid: through the enclosing message; member el= is ordinal ---------- #


@pytest.fixture
def mbox_record(tmp_path):
    root = _corpus(tmp_path)
    return root, _stage_record(
        root, _mbox_around(_html_only_eml()), mime="application/mbox", name="m.mbox"
    )


def test_html_only_message_body_reduces_to_text_through_the_mbox(mbox_record):
    """The report's motivating case: an HTML-only message, cited at
    `msg=<N>&part=<M>&text` — the forwarded content included, no reply-only trim."""
    root, mid = mbox_record
    out = resolver.resolve(f"corpus://{mid}?msg=2&part=1&text", root)
    assert out.suffix == ".txt"
    assert out.read_text("utf-8") == _EXPECTED_TEXT


def test_cid_image_materializes_through_the_enclosing_message(mbox_record):
    root, mid = mbox_record
    n = _img_ordinal()  # ordinal grammar — (3): a member's el= is never the legacy whitelist
    out = resolver.resolve(f"corpus://{mid}?msg=2&part=1&el={n}", root)
    assert out.suffix == ".png"
    with Image.open(out) as im:
        assert im.size == (4, 3)
    # and the image-op chain promotes through the same route
    crop = resolver.resolve(f"corpus://{mid}?msg=2&part=1&el={n}&bbox=0,0,0.5,1", root)
    with Image.open(crop) as im:
        assert im.size == (2, 3)


def test_cid_image_on_a_promoted_message_record(tmp_path):
    """`part=<M>&el=<K>` on a standalone message/rfc822 record: the record IS the
    enclosing message."""
    root = _corpus(tmp_path)
    rid = _stage_record(root, _html_only_eml(), mime="message/rfc822", name="t.eml")
    out = resolver.resolve(f"corpus://{rid}?part=1&el={_img_ordinal()}", root)
    assert out.suffix == ".png"


def test_cid_without_an_enclosing_message_is_a_hard_error(tmp_path):
    """A standalone HTML artifact carrying a `cid:` carrier: the reference names a part
    this route cannot reach — an error that says so, never a quiet blank or a
    NotMaterializable 'declared coverage'."""
    root = _corpus(tmp_path)
    total = html_tf.total_element_count(BeautifulSoup(_HTML, "html.parser"))
    rid = _stage_record(
        root, _HTML.encode(), mime="text/html", name="page.html",
        fields={"addressing": {"parser": "html.parser", "elements": total, "scheme": "ordinal"}},
    )
    with pytest.raises(ValueError, match="enclosing message"):
        resolver.resolve(f"corpus://{rid}?el={_img_ordinal()}", root)


def test_unknown_content_id_names_the_missing_part(tmp_path):
    root = _corpus(tmp_path)
    html = _HTML.replace("cid:logo@example.com", "cid:nope@example.com")
    em = EmailMessage()
    em["Subject"] = "x"
    em.set_content(html, subtype="html")
    rid = _stage_record(root, em.as_bytes(policy=policy.SMTP), mime="message/rfc822", name="u.eml")
    with pytest.raises(ValueError, match=r"no part with Content-ID <nope@example\.com>"):
        resolver.resolve(f"corpus://{rid}?part=1&el={_img_ordinal()}", root)


def test_carrier_cid_helper_shapes():
    soup = BeautifulSoup(
        '<img src="CID:a@x"><video><source src="cid:v@x"></video><a href="cid:f@x">f</a>'
        '<img src="https://x/y.png"><a href="mailto:x">m</a>',
        "html.parser",
    )
    img, video, a, remote_img, mail_a = soup.find_all(["img", "video", "a"])
    assert html_tf.carrier_cid(img) == "a@x"
    assert html_tf.carrier_cid(video) == "v@x"
    assert html_tf.carrier_cid(a) == "f@x"
    assert html_tf.carrier_cid(remote_img) is None
    assert html_tf.carrier_cid(mail_a) is None


# ---------- ledger: an HTML-only message verifies at msg=&part=&text ---------- #


def test_ledger_verifies_quote_against_html_only_message_text(mbox_record):
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    root, mid = mbox_record
    ledger = root.parent / "ledger"
    (ledger / "facts" / "event").mkdir(parents=True)
    (ledger / "facts" / "event" / "trip.json").write_text(json.dumps({
        "id": "trip", "type": "event", "name": "Kelowna trip",
        "sources": {"s1": {"record": mid}},
        "claims": [{"id": "trip:flight", "predicate": "flight", "value": "AC 8421",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "msg=2&part=1&text",
                                  "quote": "AC 8421\tSept 19",
                                  "kind": "authoritative"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=True, today="2026-09-02")
    assert res.unverifiable == 0 and not res.errors, (res.errors, res.notes)
    assert res.verified == 1 and res.derived_resolved == 1
