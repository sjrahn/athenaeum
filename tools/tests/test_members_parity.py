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


@pytest.mark.skipif(not _HAVE_CORPORA, reason=_NO_CORPORA_REASON)
@pytest.mark.parametrize("fixture_path", _FIXTURE_PATHS, ids=lambda p: p.stem)
def test_derivation_reproduces_mechanical_fields(fixture_path: Path) -> None:
    """The `members` derivation reproduces every MECHANICAL field the retired block stored.

    This is the proof the 3.4 collapse rests on: the four-key row (spec §4.3.1.4) drops
    dimensions, `alt`, filenames and header facts on the argument that they are re-derivable,
    and this test holds that argument to the real corpus rather than taking it on trust.

    `description` is deliberately EXCLUDED, and the exclusion is the other half of the finding.
    Census of the stored values showed it is interpretive, normalizer-authored prose on the
    `el=`/`part=`/`path=` axes ("Page 5: Issue #1 (after Gen 9.4 CDMA EOL upgrade…)") — not in
    the bytes, not reproducible by any mechanical pass, and not idempotent if an LLM re-ran it.
    That is exactly why 3.4 RE-HOMES those descriptions onto the block that places the asset
    (authored layer) instead of expecting a derivation to bring them back. `card=` is the one
    axis whose `description` IS mechanical — the vCard `FN` property — so it is asserted, not
    excluded.
    """
    from corpus import resolver

    fixture = _load_fixture(fixture_path)
    corpus_root = _CORPUS_ROOTS[fixture["hub"]]
    record_path = corpus_root / fixture["relpath"]
    record_id = records.load(record_path).metadata["id"]

    try:
        out = resolver.resolve(f"corpus://{record_id}?members", corpus_root, regenerate=True)
    except Exception as exc:  # bytes not resident / no drafter — the documented degradation
        pytest.skip(f"members derivation unavailable for {fixture['relpath']}: {exc}")
    payload = json.loads(out.read_text(encoding="utf-8"))
    if payload.get("derived_from", "").startswith("stored-roster"):
        pytest.skip(f"derivation fell back to the stored roster: {payload['derived_from']}")

    by_addr: dict[str, dict] = {}
    for entry in payload["members"]:
        by_addr.setdefault(str(entry["address"]), entry)

    checked = 0
    for stored in fixture["embeds"]:
        addrs = stored["address"]
        first = str(addrs[0] if isinstance(addrs, list) else addrs)
        derived = by_addr.get(first)
        assert derived is not None, f"{fixture_path.name}: derivation omitted {first!r}"
        assert derived["transport"] == stored["transport"], (
            f"{fixture_path.name} {first}: transport drift — the extractor is not deterministic"
        )
        assert derived["media_type"] == stored["media_type"], f"{fixture_path.name} {first}: mime"
        checked += 2  # transport + media_type are themselves parity assertions
        for key, expected in (stored.get("fields") or {}).items():
            if key == "description" and fixture["axis"] != "card":
                # Authored prose — see the docstring. Its absence is the point.
                assert "description" not in derived or derived["description"] != expected
                continue
            assert derived.get(key) == expected, (
                f"{fixture_path.name} {first}: derived {key}={derived.get(key)!r}, "
                f"stored {key}={expected!r}"
            )
            checked += 1
    assert checked or not fixture["embeds"], f"{fixture_path.name}: nothing was actually compared"
