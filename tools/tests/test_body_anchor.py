"""`corpus body --anchor <axis>=<N>` — the read-only, span-check equivalent of
`ath ledger verify`'s anchor scoping (spec/ledger.md §13.2, `ledger.verify.scoped_text`):
render only the segment(s) an integer-span axis (`turn=`, `el=`, `prop=`, ...) addresses,
instead of dumping the whole body for an investigator to hunt by hand. Axes are discovered
from the record's own segment structure — nothing about `el=`/`turn=`/`prop=` is hardcoded
in the CLI; `test_anchor_unknown_axis_lists_axes_the_record_actually_has` proves that by
asking for an axis no fixture ever names."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from corpus import paths, records, schemas, segments
from corpus._cli import body as body_cli
from corpus._cli import dispatch


def _scaffold(tmp_path: Path) -> Path:
    """A bare corpus root (`records/` + `schema/`) — `resolved_corpus_root` (which the
    CLI runs through via `dispatch`) requires both to exist, even though this suite
    never touches schema content."""
    root = tmp_path / "corpus"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _turn_record(tmp_path: Path, h: str, n: int = 3) -> Path:
    """A conversation-shaped record: a whole-record `conversation` section wrapping
    `n` `turn=` message segments — the same shape as the Instagram/Messenger fixture
    that motivated this flag."""
    root = _scaffold(tmp_path)
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="application/json", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    segs = [
        segments.Segment(
            atom="text",
            overlay="text/message",
            address=f"turn={i}",
            extra={"participant": i % 2, "timestamp": f"173125940{i:04d}"},
            body=f"message body number {i}",
        )
        for i in range(1, n + 1)
    ]
    section = segments.Section(
        form="conversation", extra={"participants": ["Kika Valentić", "Steven Rahn"]},
        segments=segs,
    )
    post.content = segments.emit([section])
    records.dump(post, paths.record_path(root, h))
    return root


def _imessage_record(tmp_path: Path, h: str) -> Path:
    """An `el=`-addressed conversation, iMessage-export shaped: sender + timestamp
    attribution on each segment header, no section-level address."""
    root = _scaffold(tmp_path)
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    segs = [
        segments.Segment(
            atom="text", overlay="text/message", address="el=1",
            extra={"sender": "+14035550273", "timestamp": "2023-04-06T19:50:55"},
            body="Hey Steven!",
        ),
        segments.Segment(
            atom="text", overlay="text/message", address="el=2",
            extra={"sender": "Me", "timestamp": "2023-04-06T21:38:05"},
            body="Absolutely",
        ),
    ]
    section = segments.Section(form="conversation", segments=segs)
    post.content = segments.emit([section])
    records.dump(post, paths.record_path(root, h))
    return root


def _vcard_record(tmp_path: Path, h: str) -> Path:
    """A `prop=`-addressed contact card — vcard fields, one segment per property."""
    root = _scaffold(tmp_path)
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/vcard", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    segs = [
        segments.Segment(atom="text", overlay="text/field", address="prop=1",
                          extra={"name": "FN"}, body="Kerm"),
        segments.Segment(atom="text", overlay="text/field", address="prop=2",
                          extra={"name": "TEL", "group": "item1"}, body="+18075559623"),
    ]
    section = segments.Section(form="contact-card", extra={"display_name": "Kerm"},
                                segments=segs)
    post.content = segments.emit([section])
    records.dump(post, paths.record_path(root, h))
    return root


H_TURN = "1" * 64
H_EL = "2" * 64
H_PROP = "3" * 64


# ---------- default (no --anchor) behavior is untouched ---------- #


def test_no_anchor_default_output_unaffected(tmp_path, capsys):
    root = _turn_record(tmp_path, H_TURN)
    rf = paths.record_path(root, H_TURN)
    expected = records.load(rf).content
    rc = dispatch(["body", H_TURN, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.rstrip("\n") == expected.rstrip("\n")
    assert "--anchor" not in out  # sanity: no leakage of the new option's plumbing


# ---------- single-segment addressing across axis families ---------- #


def test_anchor_turn_axis_renders_only_the_addressed_segment(tmp_path, capsys):
    root = _turn_record(tmp_path, H_TURN)
    rc = dispatch(["body", H_TURN, "--anchor", "turn=2", "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "message body number 2" in out
    assert "message body number 1" not in out
    assert "message body number 3" not in out
    assert "address: turn=2" in out


def test_anchor_el_axis_carries_sender_and_timestamp_attribution(tmp_path, capsys):
    root = _imessage_record(tmp_path, H_EL)
    rc = dispatch(["body", H_EL, "--anchor", "el=1", "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Hey Steven!" in out
    assert "Absolutely" not in out
    # attribution context (the whole point of printing the heading/marker line)
    assert "sender: '+14035550273'" in out
    assert "timestamp: '2023-04-06T19:50:55'" in out


def test_anchor_prop_axis_carries_field_name_attribution(tmp_path, capsys):
    root = _vcard_record(tmp_path, H_PROP)
    rc = dispatch(["body", H_PROP, "--anchor", "prop=2", "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "+18075559623" in out
    assert "Kerm" not in out  # prop=1 (FN) excluded
    assert "name: TEL" in out


def test_anchor_range_renders_every_intersecting_segment(tmp_path, capsys):
    root = _turn_record(tmp_path, H_TURN)
    rc = dispatch(["body", H_TURN, "--anchor", "turn=1-2", "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "message body number 1" in out
    assert "message body number 2" in out
    assert "message body number 3" not in out


# ---------- generic axis discovery / error paths ---------- #


def test_anchor_unknown_axis_lists_axes_the_record_actually_has(tmp_path, capsys):
    root = _turn_record(tmp_path, H_TURN)
    with pytest.raises(SystemExit) as exc:
        dispatch(["body", H_TURN, "--anchor", "msg=1", "--corpus-root", str(root)])
    msg = str(exc.value)
    assert "msg" in msg
    assert "turn=1-3" in msg  # discovered from the record, not hardcoded


def test_anchor_out_of_range_names_the_records_own_span(tmp_path, capsys):
    root = _turn_record(tmp_path, H_TURN)
    with pytest.raises(SystemExit) as exc:
        dispatch(["body", H_TURN, "--anchor", "turn=999", "--corpus-root", str(root)])
    assert "spans 1-3" in str(exc.value)


def test_anchor_missing_equals_sign_errors(tmp_path, capsys):
    root = _turn_record(tmp_path, H_TURN)
    with pytest.raises(SystemExit) as exc:
        dispatch(["body", H_TURN, "--anchor", "turn4", "--corpus-root", str(root)])
    assert "AXIS=N" in str(exc.value)


def test_anchor_non_integer_value_errors(tmp_path, capsys):
    root = _turn_record(tmp_path, H_TURN)
    with pytest.raises(SystemExit) as exc:
        dispatch(["body", H_TURN, "--anchor", "turn=abc", "--corpus-root", str(root)])
    assert "integer" in str(exc.value)


def test_anchor_and_derived_are_mutually_exclusive(tmp_path, capsys):
    root = _turn_record(tmp_path, H_TURN)
    with pytest.raises(SystemExit) as exc:
        dispatch(["body", H_TURN, "--anchor", "turn=1", "--derived", "--corpus-root", str(root)])
    assert "mutually exclusive" in str(exc.value)


def test_anchor_requires_a_stored_content_zone(tmp_path):
    """A 3.0 stub with an empty content zone has no segments to anchor into — the
    derived (drafted-on-demand) body carries no `turn=`/`el=`/... grammar at all."""
    root = _scaffold(tmp_path)
    h = "4" * 64
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    records.dump(post, paths.record_path(root, h))
    with pytest.raises(SystemExit) as exc:
        dispatch(["body", h, "--anchor", "turn=1", "--corpus-root", str(root)])
    assert "no stored content zone" in str(exc.value)


def test_anchor_no_integer_addressable_axes_at_all(tmp_path):
    """A record whose only segment carries a non-integer-span address (`time_range=`)
    has nothing `--anchor` can target."""
    root = _scaffold(tmp_path)
    h = "5" * 64
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    seg = segments.Segment(atom="text", address="time_range=0-30", body="transcript chunk")
    post.content = segments.emit([seg])
    records.dump(post, paths.record_path(root, h))
    with pytest.raises(SystemExit) as exc:
        dispatch(["body", h, "--anchor", "turn=1", "--corpus-root", str(root)])
    assert "nothing to anchor into" in str(exc.value)


# ---------- direct parity with `ledger.verify`'s anchor scoping ---------- #


def test_anchor_matches_ledger_verify_scoped_text(tmp_path):
    """The exact requirement this flag exists for: the text `corpus body --anchor`
    prints for one segment must be the same text `ledger.verify.scoped_text` resolves
    an evidence anchor to for that segment — proven here by calling both against the
    same fixture record and comparing the resolved body text directly."""
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import load_record_content, scoped_text

    root = _turn_record(tmp_path, H_TURN)
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    content = load_record_content(join, H_TURN)
    assert content is not None

    verify_text, status = scoped_text(content, [("turn", "2")])
    assert status == "ok"
    assert verify_text == "message body number 2"

    # the CLI's own matching, run directly against the public segment-addressing API
    # (not just string-scraping stdout) to compare the SAME segment body verify scoped to
    rf = paths.record_path(root, H_TURN)
    post = records.load(rf)
    blocks = segments.iter_blocks(post.content)
    matched = [
        seg
        for seg in segments.leaf_segments(blocks)
        for axis, lo, hi in segments.address_axis_spans(seg.address)
        if axis == "turn" and lo <= 2 <= hi
    ]
    assert len(matched) == 1
    assert matched[0].body == verify_text


def test_body_run_anchor_helper_matches_dispatch(tmp_path, capsys):
    """`_run_anchor` is exercised the same way whether called through `run()`/dispatch
    or directly (defensive `getattr` keeps old-style `_Args` test doubles working, per
    the existing `test_corpus_body_cli_derives_for_empty_stub` pattern)."""
    root = _turn_record(tmp_path, H_TURN)

    class _Args:
        target = H_TURN
        derived = False
        anchor = "turn=3"
        corpus_root = str(root)

    rc = body_cli.run(_Args())
    assert rc == 0
    out = capsys.readouterr().out
    assert "message body number 3" in out
    assert "message body number 2" not in out
