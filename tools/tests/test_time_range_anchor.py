"""time_range span-precise anchor resolution (spec §7.8, ledger.md §13.2): a claim's
evidence anchor `time_range=A-B` cites transcript segments precisely — the same
integer-axis span-check machinery (`el=`, `turn=`, `prop=`, ...) extended to a numeric
timecode axis, never a lexicographic string compare (`9:59` < `10:00`).

Three surfaces share this fix: `corpus.segments.parse_time_range` (the numeric parse
`address_axis_spans`'s `time_range` branch uses), `corpus body --anchor
time_range=...` (the read-only CLI equivalent), and `ledger.verify.scoped_text` (the
evidence-verification path `ath ledger verify` runs) — plus the derived-surface
fallback's error message when a citation lands on a media leaf whose transcript was
never drafted/stored."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import frontmatter
import pytest

from corpus import paths, records, segments
from corpus._cli import dispatch
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.verify import verify_ledger

_HAVE_FFMPEG = shutil.which("ffmpeg") is not None

H_TRANSCRIPT = "6" * 64


# ---------- shared fixture: a drafted transcript, three time_range segments ---------- #


def _transcript_record(tmp_path: Path, h: str = H_TRANSCRIPT) -> Path:
    """A drafted `text/transcript`-atom record: three flat segments addressed by
    `time_range=`, matching the whisper drafter's own shape (`draft/_transcript.py`) —
    no wrapping Section (transcript grouping is internal bookkeeping, never a stored
    span, §153). The 9:59/10:15 boundary is deliberate: a lexicographic compare would
    sort `'09:59'` after `'10:15'`."""
    root = tmp_path / "corpus"
    (root / "records").mkdir(parents=True, exist_ok=True)
    (root / "schema").mkdir(exist_ok=True)
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="audio/mpeg", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    segs = [
        segments.Segment(atom="text", overlay="text/transcript",
                          address="time_range=00:00-09:59",
                          extra={"speaker": 1}, body="the first thing they said"),
        segments.Segment(atom="text", overlay="text/transcript",
                          address="time_range=09:59-10:15",
                          extra={"speaker": 1}, body="right at the ten minute mark"),
        segments.Segment(atom="text", overlay="text/transcript",
                          address="time_range=24:52-25:00",
                          extra={"speaker": 2}, body="a much later remark entirely"),
    ]
    post.content = segments.emit(segs)
    records.dump(post, paths.record_path(root, h))
    return root


def _corpora(root: Path) -> list[RegisteredCorpus]:
    return [RegisteredCorpus("corpus", root, private=False)]


def _scaffold_ledger(tmp_path: Path) -> Path:
    ledger = tmp_path / "ledger"
    (ledger / "facts").mkdir(parents=True)
    return ledger


def _fact(ledger: Path, h: str, anchor: str, quote: str, *, status: str = "confirmed") -> None:
    (ledger / "facts" / "thing").mkdir(parents=True, exist_ok=True)
    (ledger / "facts" / "thing" / "widget.json").write_text(json.dumps({
        "id": "widget", "type": "thing", "name": "Widget",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "widget:said", "predicate": "said", "value": "x",
                    "status": status, "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": anchor,
                                  "quote": quote, "kind": "direct"}]}],
    }))


# ---------- corpus.segments: the numeric parse ---------- #


def test_parse_timecode_mm_ss_and_h_mm_ss():
    assert segments.parse_timecode("09:59") == 599
    assert segments.parse_timecode("1:02:03") == 3723


def test_parse_timecode_is_numeric_not_lexicographic():
    # "9:59" sorts AFTER "10:00" as strings — the exact bug a numeric parse must avoid.
    assert "9:59" > "10:00"
    assert segments.parse_timecode("9:59") < segments.parse_timecode("10:00")


def test_parse_timecode_rejects_malformed():
    assert segments.parse_timecode("abc") is None
    assert segments.parse_timecode("") is None
    assert segments.parse_timecode("12") is None  # no colon at all


def test_parse_time_range_normalizes_order_and_accepts_a_single_instant():
    assert segments.parse_time_range("24:52-25:00") == (1492.0, 1500.0)
    assert segments.parse_time_range("25:00-24:52") == (1492.0, 1500.0)  # order-normalized
    assert segments.parse_time_range("24:52") == (1492.0, 1492.0)  # bare instant
    assert segments.parse_time_range("garbage") is None


def test_address_axis_spans_now_includes_time_range():
    """Was excluded entirely before this fix (`_UNCHECKED_AXES`); now scopes exactly
    like the integer axes."""
    assert segments.address_axis_spans("time_range=24:52-25:00") == \
        [("time_range", 1492.0, 1500.0)]


# ---------- `corpus body --anchor time_range=...` ---------- #


def test_body_anchor_time_range_renders_only_the_addressed_segment(tmp_path, capsys):
    root = _transcript_record(tmp_path)
    rc = dispatch(["body", H_TRANSCRIPT, "--anchor", "time_range=24:52-25:00",
                   "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "a much later remark entirely" in out
    assert "right at the ten minute mark" not in out
    assert "address: time_range=24:52-25:00" in out


def test_body_anchor_time_range_overlap_spans_two_segments(tmp_path, capsys):
    root = _transcript_record(tmp_path)
    rc = dispatch(["body", H_TRANSCRIPT, "--anchor", "time_range=09:00-10:00",
                   "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "the first thing they said" in out
    assert "right at the ten minute mark" in out
    assert "a much later remark entirely" not in out


def test_body_anchor_time_range_out_of_range_names_the_records_own_span(tmp_path):
    root = _transcript_record(tmp_path)
    with pytest.raises(SystemExit) as exc:
        dispatch(["body", H_TRANSCRIPT, "--anchor", "time_range=99:00-99:10",
                  "--corpus-root", str(root)])
    assert "spans 00:00-25:00" in str(exc.value)


def test_body_anchor_time_range_malformed_value_errors(tmp_path):
    root = _transcript_record(tmp_path)
    with pytest.raises(SystemExit) as exc:
        dispatch(["body", H_TRANSCRIPT, "--anchor", "time_range=abc",
                  "--corpus-root", str(root)])
    assert "timecode" in str(exc.value)


# ---------- `ath ledger verify`: span-precise resolution ---------- #


def test_verify_time_range_anchor_resolves_span_precise(tmp_path):
    root = _transcript_record(tmp_path)
    ledger = _scaffold_ledger(tmp_path)
    _fact(ledger, H_TRANSCRIPT, "time_range=24:52-25:00", "a much later remark entirely")
    join = CorpusJoin(_corpora(root))
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1
    assert res.record_scoped == 0  # anchor-scoped, not the weaker whole-record fallback
    assert not res.errors and not res.warnings


def test_verify_time_range_numeric_ordering_at_the_boundary(tmp_path):
    """The 9:59/10:15 segment boundary: an anchor just past it must select segment 2 —
    proof `scoped_text` compares timecodes numerically, never as strings (`'9:59'` would
    otherwise sort after `'10:00'`)."""
    root = _transcript_record(tmp_path)
    ledger = _scaffold_ledger(tmp_path)
    _fact(ledger, H_TRANSCRIPT, "time_range=10:00-10:05", "right at the ten minute mark")
    join = CorpusJoin(_corpora(root))
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1
    assert res.record_scoped == 0
    assert not res.errors and not res.warnings


def test_verify_time_range_anchor_overlapping_two_segments_spans_both(tmp_path):
    root = _transcript_record(tmp_path)
    ledger = _scaffold_ledger(tmp_path)
    _fact(ledger, H_TRANSCRIPT, "time_range=09:00-10:00",
          "the first thing they said right at the ten minute mark")
    join = CorpusJoin(_corpora(root))
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1
    assert res.record_scoped == 0
    assert not res.errors and not res.warnings


def test_verify_time_range_anchor_within_transcript_but_untouched_is_bad_anchor(tmp_path):
    """Unlike a record with NO time_range segments at all (below), a record that DOES
    carry them but is cited outside every one of them is a genuine confabulated anchor —
    the same el=/integer-axis precedent (never a silent record-scoped pass)."""
    root = _transcript_record(tmp_path)
    ledger = _scaffold_ledger(tmp_path)
    _fact(ledger, H_TRANSCRIPT, "time_range=99:00-99:10", "anything", status="provisional")
    join = CorpusJoin(_corpora(root))
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 0
    assert any("anchor does not resolve" in w for w in res.warnings)


def test_verify_time_range_anchor_with_no_stored_transcript_falls_back_record_scoped(
    tmp_path: Path,
) -> None:
    """A record with no `time_range`-addressed segments at all has nothing for
    `scoped_text` to scope against — `unchecked`, not a hard `bad-anchor`: the quote
    search falls back to the whole record and, when the quote genuinely lives on the
    record's own byte-facts, still verifies, `record_scoped` (mirrors the existing
    `row=`/`col=` precedent, `test_verify_row_axis_falls_back_to_record_scoped`)."""
    root = tmp_path / "corpus"
    h = "7" * 64
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(
        post, snapshot="2026-01-01T00:00:00Z", fields={"filename": "notes.txt"}
    )
    records.dump(post, paths.record_path(root, h))
    ledger = _scaffold_ledger(tmp_path)
    _fact(ledger, h, "time_range=00:00-00:05", "notes.txt", status="provisional")
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1 and res.record_scoped == 1
    assert not res.errors and not res.warnings


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg not installed")
def test_verify_time_range_on_unstored_media_leaf_gives_actionable_error(tmp_path):
    """(1.x) A `time_range=` citation against a media leaf whose transcript was never
    drafted/stored has no segments to scope against (`scoped_text` → unchecked) and the
    quote isn't anywhere in the record's own metadata — the derivation-op fallback then
    tries to resolve `time_range=` through the resolver, which (absent `?transcribe`)
    muxes an audio CLIP, never text. The honest gap must name the actionable fix — store
    the transcript first — not the confusing byte-format detail of what it muxed
    instead."""
    root = tmp_path / "corpus"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    clip = tmp_path / "audio.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=4", "-c:a", "libmp3lame", str(clip)],
        check=True, capture_output=True,
    )
    h = "8" * 64
    art = paths.artifact_path(root, h, "mp3")
    paths.ensure_parent(art)
    art.write_bytes(clip.read_bytes())
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="audio/mpeg", fields={"title": "clip"})
    records.append_origin_block(
        post, uri=f"https://e.com/{h}.mp3", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(root, h))

    ledger = _scaffold_ledger(tmp_path)
    _fact(ledger, h, "time_range=00:00-00:02",
          "this line only exists in the spoken audio", status="provisional")
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 0
    assert res.unverifiable == 1
    note = next(n for n in res.notes if h[:12] in n)
    assert "transcript must be stored" in note
    assert "not textual" not in note
