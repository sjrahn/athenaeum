"""The index-file date axis — `corpus period-split --date-from index:<path>` (spec §7.2
`date_index:` / §12.3.14, v44): a Meta-shaped export whose media members carry no
per-member sidecar and whose dates live in `stories.json` (`{ig_stories: [{uri,
creation_timestamp}]}`) and `posts_N.json` (a top-level list of posts each with
`media: [{uri, creation_timestamp}]`). Bucketing over both shapes in one run, index
members excluded and disclosed, unmatched entries and two-way-dated members counted,
epoch-is-UTC and rendered-local value rules shared with the sidecar axis, zip-source
parity, and the CLI contract (declaration required, malformed declaration refused, no
index member present → exit).
"""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from corpus import schemas
from corpus._cli import period_split

ORIGIN = "instagram-export"
_MONTH = "partition:\n  grain: month\n  undated: standing\n"
_DATE_INDEX = (
    "date_index:\n"
    "- file: your_instagram_activity/media/stories.json\n"
    "  entries: ig_stories\n"
    "  key: uri\n"
    "- file: 'your_instagram_activity/media/posts_*.json'\n"
    "  entries: media\n"
    "  key: uri\n"
)


def _corpus(tmp_path: Path, overlay_yaml: str) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    schema_dir = root / "schema" / "origin"
    schema_dir.mkdir(parents=True)
    (schema_dir / f"{ORIGIN}.yaml").write_text(f"description: test\n{overlay_yaml}")
    schemas.cache_clear()
    return root


def _epoch(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp())


def _touch(p: Path, iso: str = "2026-09-20T00:00:00+00:00") -> None:
    ts = datetime.fromisoformat(iso).timestamp()
    os.utime(p, (ts, ts))


def _file(src: Path, name: str, data: bytes | str) -> None:
    p = src / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode())
    _touch(p)  # every mtime is the export-run time — the mtime axis is useless here


def _build_meta_tree(src: Path) -> None:
    """Stories: 2019-06 (closed), a -06:00 instant that is 2026-02 in UTC (closed), one
    member dated two ways (→ undated), one entry naming a member that is not in the
    export (→ unmatched). Posts across two index files: 2026-01 (closed) and 2026-03
    (current under `--current-period 2026-03`). One media member with no entry at all
    (→ undated)."""
    for m in (
        "media/stories/201906/s1.mp4",
        "media/stories/202602/s2.mp4",
        "media/stories/202602/dup.mp4",
        "media/posts/p1.jpg",
        "media/posts/p2.jpg",
        "media/posts/orphan.jpg",
    ):
        _file(src, m, f"bytes-of-{m}")
    stories = {
        "ig_stories": [
            {
                "uri": "media/stories/201906/s1.mp4",
                "creation_timestamp": _epoch("2019-06-15T12:00:00+00:00"),
            },
            {
                "uri": "media/stories/202602/s2.mp4",
                "creation_timestamp": _epoch("2026-01-31T23:30:00-06:00"),
            },
            {
                "uri": "media/stories/202602/dup.mp4",
                "creation_timestamp": _epoch("2026-02-10T12:00:00+00:00"),
            },
            {
                "uri": "media/stories/202602/dup.mp4",
                "creation_timestamp": _epoch("2026-03-10T12:00:00+00:00"),
            },
            {
                "uri": "media/stories/201906/gone.mp4",
                "creation_timestamp": _epoch("2019-06-16T12:00:00+00:00"),
            },
        ]
    }
    posts_1 = [
        {
            "media": [
                {
                    "uri": "media/posts/p1.jpg",
                    "creation_timestamp": _epoch("2026-01-15T12:00:00+00:00"),
                }
            ]
        }
    ]
    posts_2 = [
        {
            "media": [
                {
                    "uri": "media/posts/p2.jpg",
                    "creation_timestamp": _epoch("2026-03-05T12:00:00+00:00"),
                }
            ]
        }
    ]
    _file(src, "your_instagram_activity/media/stories.json", json.dumps(stories))
    _file(src, "your_instagram_activity/media/posts_1.json", json.dumps(posts_1))
    _file(src, "your_instagram_activity/media/posts_2.json", json.dumps(posts_2))


def _zip_tree(src_dir: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w") as z:
        for p in sorted(f for f in src_dir.rglob("*") if f.is_file()):
            rel = p.relative_to(src_dir).as_posix()
            dt = datetime.fromtimestamp(p.stat().st_mtime, UTC)
            zi = zipfile.ZipInfo(
                rel, date_time=(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
            )
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, p.read_bytes())


def _run(
    root: Path,
    source: Path,
    *,
    date_from: str = "index:creation_timestamp",
    current_period: str | None = "2026-03",
    render_timezone: str | None = None,
) -> int:
    return period_split.run(
        argparse.Namespace(
            source=str(source),
            origin=ORIGIN,
            date_from=date_from,
            current_period=current_period,
            render_timezone=render_timezone,
            corpus_root=str(root),
        )
    )


def _sidecar(zip_path: Path) -> dict:
    return yaml.safe_load(zip_path.with_suffix(zip_path.suffix + ".capture.yaml").read_text())


def _members(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as z:
        return sorted(z.namelist())


# ---------- bucketing over both index shapes ---------- #


def test_index_axis_buckets_stories_and_posts_in_one_run(tmp_path):
    root = _corpus(tmp_path, _MONTH + _DATE_INDEX)
    src = tmp_path / "instagram-sjrahn-2026-09-20-abc"
    src.mkdir()
    _build_meta_tree(src)
    assert _run(root, src) == 0
    cap = root / "capture"
    stem = src.name
    assert _members(cap / f"{stem}-2019-06.zip") == ["media/stories/201906/s1.mp4"]
    assert _members(cap / f"{stem}-2026-01.zip") == ["media/posts/p1.jpg"]
    # the -06:00 instant is 2026-02-01T05:30Z — the epoch is UTC by definition (v34/v36)
    assert _members(cap / f"{stem}-2026-02.zip") == ["media/stories/202602/s2.mp4"]
    assert _members(cap / f"{stem}-current-2026-03.zip") == ["media/posts/p2.jpg"]
    # no entry at all, and dated two ways — both undated, neither guessed
    assert _members(cap / f"{stem}-undated.zip") == [
        "media/posts/orphan.jpg",
        "media/stories/202602/dup.mp4",
    ]
    # index members are in NO bucket
    for z in cap.glob("*.zip"):
        assert not any(n.endswith(".json") for n in _members(z)), z.name


def test_index_axis_disclosure_on_every_sidecar(tmp_path):
    root = _corpus(tmp_path, _MONTH + _DATE_INDEX)
    src = tmp_path / "export"
    src.mkdir()
    _build_meta_tree(src)
    assert _run(root, src) == 0
    cap = root / "capture"
    for name in ("export-2019-06.zip", "export-current-2026-03.zip", "export-undated.zip"):
        fields = _sidecar(cap / name)["origin_fields"]
        assert fields["date_axis"] == "index:creation_timestamp"
        assert fields["date_index_files"] == [
            "your_instagram_activity/media/posts_1.json",
            "your_instagram_activity/media/posts_2.json",
            "your_instagram_activity/media/stories.json",
        ]
        assert fields["date_index_unmatched"] == 1  # gone.mp4
        assert fields["date_index_conflicts"] == 1  # dup.mp4
        assert fields["sidecar_count"] == 0
    undated = _sidecar(cap / "export-undated.zip")["origin_fields"]
    assert "period" not in undated
    assert undated["member_count"] == 2


def test_index_axis_zip_source_equivalent(tmp_path):
    root_a = _corpus(tmp_path / "a", _MONTH + _DATE_INDEX)
    src = tmp_path / "export"
    src.mkdir()
    _build_meta_tree(src)
    assert _run(root_a, src) == 0
    zipped = tmp_path / "export.zip"
    _zip_tree(src, zipped)
    root_b = _corpus(tmp_path / "b", _MONTH + _DATE_INDEX)
    assert _run(root_b, zipped) == 0
    for name in ("export-2019-06.zip", "export-2026-02.zip", "export-undated.zip"):
        assert _members(root_a / "capture" / name) == _members(root_b / "capture" / name)
    fields_b = _sidecar(root_b / "capture" / "export-2019-06.zip")["origin_fields"]
    assert fields_b["source_transport"].startswith("blake3:")
    assert fields_b["date_index_files"][-1] == "your_instagram_activity/media/stories.json"


# ---------- value rules are the sidecar axis's ---------- #


def test_index_axis_iso_naive_face_value_vs_render_timezone(tmp_path):
    decl = "date_index:\n  file: index.json\n  entries: items\n  key: path\n"
    src = tmp_path / "export"
    _file(src, "a.jpg", "a")
    _file(
        src, "index.json", json.dumps({"items": [{"path": "a.jpg", "when": "2026-01-31 22:00:00"}]})
    )
    # naive, no zone: face value → January (closed)
    root = _corpus(tmp_path / "x", _MONTH + decl)
    assert _run(root, src, date_from="index:when") == 0
    assert (root / "capture" / "export-2026-01.zip").exists()
    # the same value through a declared render zone: 2026-02-01T05:00Z → February
    root2 = _corpus(tmp_path / "y", _MONTH + decl)
    assert _run(root2, src, date_from="index:when", render_timezone="America/Edmonton") == 0
    assert (root2 / "capture" / "export-2026-02.zip").exists()
    assert (
        _sidecar(root2 / "capture" / "export-2026-02.zip")["origin_fields"]["render_timezone"]
        == "America/Edmonton"
    )


def test_index_axis_unparseable_value_is_undated_not_a_conflict(tmp_path):
    decl = "date_index:\n  file: index.json\n  entries: ''\n  key: path\n"
    src = tmp_path / "export"
    _file(src, "a.jpg", "a")
    _file(src, "b.jpg", "b")
    index = [
        {"path": "a.jpg", "ts": "not-a-date"},
        {"path": "a.jpg", "ts": _epoch("2026-01-10T00:00:00+00:00")},  # same member, one real date
        {"path": "b.jpg", "ts": True},  # bool is never a date
    ]
    _file(src, "index.json", json.dumps(index))
    root = _corpus(tmp_path / "c0", _MONTH + decl)
    assert _run(root, src, date_from="index:ts") == 0
    assert _members(root / "capture" / "export-2026-01.zip") == ["a.jpg"]
    assert _members(root / "capture" / "export-undated.zip") == ["b.jpg"]
    assert (
        "date_index_conflicts"
        not in _sidecar(root / "capture" / "export-undated.zip")["origin_fields"]
    )


# ---------- the entries walk ---------- #


@pytest.mark.parametrize(
    ("doc", "path", "expected"),
    [
        ({"ig_stories": [{"uri": "a"}, {"uri": "b"}]}, "ig_stories", ["a", "b"]),
        (
            [{"media": [{"uri": "a"}]}, {"media": [{"uri": "b"}, {"uri": "c"}]}],
            "media",
            ["a", "b", "c"],
        ),
        ([{"media": [{"uri": "a"}]}], "[].media[]", ["a"]),
        ([{"uri": "a"}, {"uri": "b"}], "", ["a", "b"]),
        ({"x": {"y": [{"uri": "a"}]}}, "x.y", ["a"]),
        ({"x": "not-an-array"}, "x", []),
        ({"x": [1, "two", None]}, "x", []),
    ],
)
def test_index_entries_walk(doc, path, expected):
    assert [e["uri"] for e in period_split._index_entries(doc, path)] == expected


# ---------- CLI contract ---------- #


def test_parse_date_axis_index():
    assert period_split._parse_date_axis("index:creation_timestamp") == (
        "index",
        "creation_timestamp",
    )
    assert period_split._parse_date_axis(" index:a.b ") == ("index", "a.b")
    with pytest.raises(SystemExit):
        period_split._parse_date_axis("index:")
    with pytest.raises(SystemExit):
        period_split._parse_date_axis("indexes:x")


def test_index_axis_requires_declaration(tmp_path, capsys):
    root = _corpus(tmp_path, _MONTH)  # partition, but no date_index:
    src = tmp_path / "export"
    _file(src, "a.jpg", "a")
    with pytest.raises(SystemExit) as exc:
        _run(root, src)
    assert "date_index" in str(exc.value)
    assert "--date-from mtime" in str(exc.value)


@pytest.mark.parametrize(
    ("decl", "needle"),
    [
        ("date_index: []\n", "non-empty list"),
        ("date_index: {entries: a, key: b}\n", "`file`"),
        ("date_index: {file: x.json, key: ''}\n", "`key`"),
        ("date_index: {file: x.json, entries: 'a..b', key: k}\n", "`entries`"),
        ("date_index: {file: x.json, key: k, date: d}\n", "unknown key"),
        ("date_index: 7\n", "must be a mapping"),
    ],
)
def test_index_declaration_malformed_is_refused(tmp_path, decl, needle):
    root = _corpus(tmp_path, _MONTH + decl)
    src = tmp_path / "export"
    _file(src, "a.jpg", "a")
    with pytest.raises(SystemExit) as exc:
        _run(root, src)
    assert needle in str(exc.value)
    assert "date_index" in str(exc.value)


def test_index_axis_no_index_member_present_exits(tmp_path):
    root = _corpus(tmp_path, _MONTH + _DATE_INDEX)
    src = tmp_path / "export"
    _file(src, "media/posts/a.jpg", "a")  # no stories.json / posts_*.json in this export
    with pytest.raises(SystemExit) as exc:
        _run(root, src)
    assert "no member matches the declared date_index" in str(exc.value)


def test_index_axis_non_json_index_exits(tmp_path):
    decl = "date_index:\n  file: index.json\n  entries: items\n  key: path\n"
    root = _corpus(tmp_path, _MONTH + decl)
    src = tmp_path / "export"
    _file(src, "a.jpg", "a")
    _file(src, "index.json", "{not json")
    with pytest.raises(SystemExit) as exc:
        _run(root, src, date_from="index:ts")
    assert "not JSON" in str(exc.value)


def test_resolve_date_index_walks_the_ladder(tmp_path):
    """`instagram-export/media` (no key) climbs to `instagram-export` (declares); a
    single mapping normalizes to a one-item list; an origin with nothing declared is
    None, not an error."""
    root = _corpus(tmp_path, _MONTH + "date_index: {file: idx.json, key: uri}\n")
    got = schemas.resolve_date_index(root, "application/zip", origin_id=f"{ORIGIN}/media")
    assert got == [{"file": "idx.json", "entries": "", "key": "uri"}]
    assert schemas.resolve_date_index(root, "application/zip", origin_id="other-export") is None
