"""v50: a stored rendering of text the artifact itself carries rides a named form (spec §4.1,
§7.8), enforced at the write — `compile` refuses a document-shaped content zone no form
governs, and `finalize`'s pass gate refuses to close a pass over one (§8.5).

Born from arbre-ath-steven's 96-run PDF eval (2026-09-28): normalize passes wrote new
sectionless page renderings on every PDF with no declared form, in every arm, and lint passed
them clean every time; one lost its `statement` form to a bare `<!--section` opener. What is
NOT gated is the shape that is extraction rather than rendering (§4.3.2.2) — text read out of
pixels or sound, and one whole-transport segment — which 4k+ live records carry legitimately.
"""

from __future__ import annotations

import sys
from pathlib import Path

import frontmatter
import pytest

from corpus import records, segments

sys.path.insert(0, str(Path(__file__).parent))
import test_compile_base_gate as base


def _post(mime: str, blocks: list) -> frontmatter.Post:
    post = frontmatter.Post(segments.emit(blocks))
    post.metadata.update({"id": "a" * 64, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime=mime, fields={})
    return post


def _text(addr, body="Words the artifact itself carries.", overlay=None):
    return segments.Segment(atom="text", address=addr, body=body, overlay=overlay)


@pytest.mark.parametrize(
    ("mime", "blocks", "shaped"),
    [
        # the eval's defect: PDF pages rendered with no form
        ("application/pdf", [_text("page=1"), _text("page=2")], True),
        # ... and the same under a section that names no form
        ("application/pdf", [segments.Section(segments=[_text("page=1")])], True),
        ("text/html", [_text("el=4")], True),
        # formed: the rendering rides `document`
        ("application/pdf", [segments.Section(form="document", segments=[_text("page=1")])],
         False),
        # sparse extraction: OCR of a scanned page, a transcript sweep
        ("application/pdf", [_text("page=1&bbox=0,0,1,0.2", overlay="text/ocr")], False),
        ("audio/mpeg", [_text("t=0-30", overlay="text/transcript")], False),
        # any text of an image is extraction — a screenshot's table included
        ("image/png", [_text("bbox=0,0,1,0.5", overlay="text/data-table"),
                       _text("bbox=0,0.5,1,0.5")], False),
        # one whole-transport segment: a plain-text artifact rendered whole
        ("text/plain", [_text(None)], False),
        # markers and byte-marks alone store no rendering
        ("application/pdf", [segments.Segment(atom="image", address="page=1")], False),
    ],
)
def test_what_counts_as_document_shaped(mime, blocks, shaped):
    assert records.is_document_shaped(_post(mime, blocks)) is shaped


def _manifest(work: Path) -> Path:
    return work / "manifest.corpus"


def test_compile_refuses_a_formless_document_rendering(tmp_path, capsys):
    root = base._corpus(tmp_path)
    rec = base._record(root)
    before = rec.read_text("utf-8")
    work = tmp_path / "w"
    base._decompose(root, work)
    m = _manifest(work)
    m.write_text(m.read_text().replace("section form=document ", "section "), "utf-8")

    assert base._compile(root, work, "--dry-run") == 1  # the dry run predicts it
    assert base._compile(root, work) == 1
    err = capsys.readouterr().err
    assert "document-shaped content zone with no form" in err
    assert "adds 1 section opener(s) with no form id" in err
    assert rec.read_text("utf-8") == before


def test_a_pass_may_leave_the_record_proxy_instead(tmp_path):
    """The other exit: store no rendering. The record reads as the artifact's proxy."""
    root = base._corpus(tmp_path)
    rec = base._record(root)
    work = tmp_path / "w"
    base._decompose(root, work)
    m = _manifest(work)
    kept = [ln for ln in m.read_text().splitlines() if not ln.startswith(("section", "seg "))]
    m.write_text("\n".join(kept) + "\n", "utf-8")
    assert base._compile(root, work) == 0
    assert records.derived_state(records.load(rec)) == "proxy"


def test_a_new_bare_opener_beside_a_form_warns_but_writes(tmp_path, capsys):
    """Formed elsewhere, so not refused — but the formless opener is almost always a form id
    the pass meant and dropped."""
    root = base._corpus(tmp_path)
    base._record(root)
    work = tmp_path / "w"
    base._decompose(root, work)
    m = _manifest(work)
    seg1 = "seg text addr=page=1 body=@bodies/0001-s1-page-1.md\n"
    text = m.read_text().replace(
        "section form=document addr=pages=1-2\n" + seg1,
        "section form=document addr=pages=1-1\n" + seg1 + "section addr=pages=2-2\n",
    )
    m.write_text(text, "utf-8")
    assert base._compile(root, work) == 0
    err = capsys.readouterr().err
    assert "adds 1 section opener(s) with no form id" in err
    assert "document-shaped" not in err


def test_out_is_exempt_nothing_authored_is_written(tmp_path):
    root = base._corpus(tmp_path)
    base._record(root)
    work = tmp_path / "w"
    base._decompose(root, work)
    m = _manifest(work)
    m.write_text(m.read_text().replace("section form=document ", "section "), "utf-8")
    assert base._compile(root, work, "--out", str(tmp_path / "x.md")) == 0


def test_finalize_refuses_to_close_a_pass_over_one(tmp_path, capsys):
    import test_normalize_queue as nq

    from corpus import paths, queue
    from corpus._cli import dispatch

    root = nq._corpus(tmp_path)
    post = frontmatter.Post(
        content=segments.emit([_text("page=1"), _text("page=2")]),
        **records.stub_frontmatter(record_id=nq.RID, touch_id="corpus.ingest@0.1.0"),
    )
    records.set_artifact_block(post, mime="application/pdf")
    records.append_origin_block(post, uri="file:///x.pdf", snapshot="2026-09-28T00:00:00Z")
    records.dump(post, paths.record_path(root, nq.RID))
    queue.enqueue(root, nq.RID)
    queue.drain(root)
    assert dispatch(["finalize", nq.RID, "--corpus-root", str(root)]) == 1
    assert "document-shaped content zone with no form" in capsys.readouterr().err
    assert queue.state(root, nq.RID)["state"] == "claimed"  # the claim is left intact
