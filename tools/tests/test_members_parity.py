"""Parity battery for the `<!--embed-->` → `<!--members-->` collapse (spec §4.3.1.4).

The `<!--members-->` block replaces `<!--embed-->` with rows carrying ONLY four keys —
`address`, `media_type`, `transport`, `bytes` — on the argument that every other field
currently stored on an embed (`width`, `height`, `alt`, `filename`, `from`, `subject`,
`date`, `description`, `content_id`, `disposition`, ...) is mechanically re-derivable from
the artifact on demand.

This module makes that argument checkable rather than assumed. `tests/data/members_parity/`
freezes the exact fields stored today, on a small set of real records chosen to cover every
address axis (`el`, `path`, `msg`, `part`, `card`, `stream_id` — the full set found; see
`AXIS_FIELD_CENSUS`) and every distinct field-vocabulary combination within each axis. Each
fixture's `note` explains why that record was chosen. Some fixtures freeze every embed in the
record (`frozen: "all"`); a couple of oversized records are deliberately sliced
(`frozen: "slice"`, with `source_indices` giving the exact original positions kept) rather than
bloating the fixture — see `2b22ee42.json` and `302af31a.json`.

Three tests:
  - `test_fixtures_match_live_records` — the frozen snapshot still matches the live corpus
    record (skipped when the corpora aren't cloned; see `_HAVE_CORPORA`).
  - `test_axis_field_vocabulary_is_covered` — the fixture set collectively exercises every
    axis and every field key in `AXIS_FIELD_CENSUS`, so the battery can't silently miss one.
  - `test_derivation_reproduces_stored_fields` — placeholder for the `members` derivation
    (plan step 4); skipped until it exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from corpus import records

# tools/tests/test_members_parity.py -> parents[2] is the athenaeum workspace root (see
# test_ccsession.py's OVERLAY path for the same convention).
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_CORPORA_ROOT = _WORKSPACE_ROOT / "corpora"
_CORPUS_ROOTS = {
    "corpus": _CORPORA_ROOT / "corpus",
    "corpus-private": _CORPORA_ROOT / "corpus-private",
}
_HAVE_CORPORA = all(root.is_dir() for root in _CORPUS_ROOTS.values())
_NO_CORPORA_REASON = (
    "corpora/corpus and corpora/corpus-private are untracked clones not present "
    "in this checkout"
)

_DATA_DIR = Path(__file__).resolve().parent / "data" / "members_parity"
_FIXTURE_PATHS = sorted(_DATA_DIR.glob("*.json"))

# Census taken 2026-07-26 across BOTH hubs (corpora/corpus + corpora/corpus-private),
# parsed via `records.iter_embed_blocks` (real API, not regex): 11,824 records scanned,
# 91,802 `<!--embed-->` blocks total, 0 parse errors. Per-axis block counts and the field
# keys each axis's blocks carry (with how many of the axis's blocks carry each key) — this
# is the field vocabulary the `members` derivation must reproduce.
#
#   axis        blocks   field keys (count of blocks carrying it)
#   card           150   bytes:150  description:150
#   el          19,592   width:19449  height:19449  description:15661  alt:13052
#   msg          3,019   bytes:3019  from:3017  subject:3017  date:2661
#   part           142   bytes:142  disposition:142  filename:140  content_id:123
#                        description:57
#   path        68,897   bytes:68897  description:104
#   stream_id        2   bytes:2  filename:2
#
# No other address axis carries an `<!--embed-->` block in either hub. `spine=` (the
# `spine=<N>&el=<K>` address the epub drafter's docstring describes, corpus/epub.py) does
# NOT appear on any embed block in either corpus — no record has actually been drafted
# through that path yet, so it is not in this census and has no fixture. `block=`, `frame=`,
# `line=`, `page=`, `pages=`, `prop=`, `sheet=`, `time_range=`, `turn=` all exist in the
# corpora but address `<!--segment-->` blocks in the content zone, a different address
# space from `<!--embed-->`'s metadata-zone addressing — out of scope for this battery.
AXIS_FIELD_CENSUS: dict[str, dict[str, int]] = {
    "card": {"bytes": 150, "description": 150},
    "el": {"width": 19449, "height": 19449, "description": 15661, "alt": 13052},
    "msg": {"bytes": 3019, "from": 3017, "subject": 3017, "date": 2661},
    "part": {
        "bytes": 142,
        "disposition": 142,
        "filename": 140,
        "content_id": 123,
        "description": 57,
    },
    "path": {"bytes": 68897, "description": 104},
    "stream_id": {"bytes": 2, "filename": 2},
}


def _axis_of(address: str | list[str]) -> str:
    """The leading `key=` of an embed address — same convention the census script used."""
    first = address[0] if isinstance(address, list) else address
    return first.split("=", 1)[0] if "=" in first else "(no-param)"


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _live_embeds(fixture: dict) -> list[dict]:
    """Re-parse the fixture's record from the live corpus and return its embed blocks."""
    corpus_root = _CORPUS_ROOTS[fixture["hub"]]
    record_path = corpus_root / fixture["relpath"]
    post = records.load(record_path)
    return list(records.iter_embed_blocks(post))


@pytest.mark.skipif(not _HAVE_CORPORA, reason=_NO_CORPORA_REASON)
@pytest.mark.parametrize("fixture_path", _FIXTURE_PATHS, ids=lambda p: p.stem)
def test_fixtures_match_live_records(fixture_path: Path) -> None:
    """The frozen snapshot still matches what's stored on disk today.

    This guards the snapshot itself, not the (not-yet-built) derivation: if a record named
    here gets re-attested and its embed fields change, this test fails and tells us the
    baseline this parity battery relies on has moved.
    """
    fixture = _load_fixture(fixture_path)
    live = _live_embeds(fixture)

    assert len(live) == fixture["total_embeds_in_record"], (
        f"{fixture_path.name}: record now has {len(live)} embeds, "
        f"fixture recorded {fixture['total_embeds_in_record']}"
    )

    chosen_live = [live[i] for i in fixture["source_indices"]]
    assert chosen_live == fixture["embeds"], (
        f"{fixture_path.name}: stored embed fields at {fixture['source_indices']} "
        f"no longer match the frozen snapshot"
    )


def test_axis_field_vocabulary_is_covered() -> None:
    """The fixture set must exercise every axis and every field key in the census.

    Without this, an axis or a field key could silently drop out of the parity battery
    (e.g. if a fixture were deleted) and nobody would notice until the derivation shipped.
    """
    covered_axes: set[str] = set()
    covered_fields: dict[str, set[str]] = {axis: set() for axis in AXIS_FIELD_CENSUS}

    assert _FIXTURE_PATHS, "no fixtures found under tests/data/members_parity/"

    for fixture_path in _FIXTURE_PATHS:
        fixture = _load_fixture(fixture_path)
        for embed in fixture["embeds"]:
            axis = _axis_of(embed["address"])
            covered_axes.add(axis)
            if axis in covered_fields:
                covered_fields[axis].update(embed["fields"].keys())

    missing_axes = set(AXIS_FIELD_CENSUS) - covered_axes
    assert not missing_axes, f"axes with no fixture coverage: {sorted(missing_axes)}"

    for axis, census_fields in AXIS_FIELD_CENSUS.items():
        missing = set(census_fields) - covered_fields[axis]
        assert not missing, (
            f"axis {axis!r}: field key(s) {sorted(missing)} not exercised by any fixture"
        )


@pytest.mark.skip(
    reason="the `members` derivation does not exist yet — unskip when "
    "`corpus://<id>?members` derives fields from the artifact (plan step 4)"
)
@pytest.mark.skipif(not _HAVE_CORPORA, reason=_NO_CORPORA_REASON)
@pytest.mark.parametrize("fixture_path", _FIXTURE_PATHS, ids=lambda p: p.stem)
def test_derivation_reproduces_stored_fields(fixture_path: Path) -> None:
    """The `members` derivation must reproduce, field-for-field, what is stored today.

    Written now so it works the moment `corpus://<id>?members` (or whatever the derivation's
    entry point turns out to be named) lands — swap `_derive_members` below for the real call.
    """
    from corpus import derive  # local import: module may not exist yet on this branch

    fixture = _load_fixture(fixture_path)
    corpus_root = _CORPUS_ROOTS[fixture["hub"]]
    record_path = corpus_root / fixture["relpath"]
    post = records.load(record_path)
    live = list(records.iter_embed_blocks(post))
    chosen_live = [live[i] for i in fixture["source_indices"]]

    for stored in chosen_live:
        derived = derive.members_for_address(  # placeholder entry point — adjust to the real API
            post,
            corpus_root=corpus_root,
            address=stored["address"],
        )
        assert derived["media_type"] == stored["media_type"]
        assert derived["transport"] == stored["transport"]
        for field_key, expected_value in stored["fields"].items():
            assert derived["fields"].get(field_key) == expected_value, (
                f"{fixture_path.name} address={stored['address']!r}: "
                f"derived {field_key}={derived['fields'].get(field_key)!r}, "
                f"stored {field_key}={expected_value!r}"
            )
