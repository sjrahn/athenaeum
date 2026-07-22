"""JSON-family field strip (spec §12.3.14) — the mailbox chrome strip's amendment to any
JSON-family export: the byte-offset-preserving scanner (`corpus.jsonfields`), the
span-surgical removal grammar (first/middle/last/only member, array traversal via `[]`,
absent-key no-op, duplicate keys), byte-preservation outside the removed spans,
determinism, `schemas.resolve_strip_fields`'s ladder (identical to the header strip's),
and the ingest-time canonicalization wiring.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

import corpus as corpus_pkg
from corpus import hashing, jsonfields, records, schemas
from corpus._cli import ingest as ingest_cli

_PACKAGED_JSON_SCHEMA = (
    Path(corpus_pkg.__file__).parent
    / "schemas_default/mime/application/application_json.yaml"
)


# ---------- scanner (parse()) ---------- #


def test_parse_records_key_and_value_spans_for_flat_object():
    data = b'{"a": 1, "b": "two"}'
    root = jsonfields.parse(data)
    assert root.kind == "object"
    assert [m.key for m in root.members] == ["a", "b"]
    a, b = root.members
    assert data[a.key_start : a.value_end] == b'"a": 1'
    assert data[b.key_start : b.value_end] == b'"b": "two"'
    assert a.comma_before is None and a.comma_after is not None
    assert b.comma_before == a.comma_after and b.comma_after is None


def test_parse_handles_escaped_quotes_and_backslashes_in_keys_and_values():
    data = b'{"a\\"b": "value with \\\\ and \\"quotes\\""}'
    root = jsonfields.parse(data)
    assert len(root.members) == 1
    member = root.members[0]
    assert member.key == 'a"b'
    # The value span covers the WHOLE escaped string, backslash-escapes included.
    assert data[member.key_start : member.value_end] == data[1:-1]


def test_parse_handles_unicode_escape_and_raw_utf8_bytes():
    # é (é) as an escape, and a raw UTF-8 é in the same string.
    data = '{"a": "caf\\u00e9 and café"}'.encode()
    root = jsonfields.parse(data)
    assert root.members[0].key == "a"
    # Span bytes are untouched (still the raw escape + raw UTF-8 bytes) — parse() never
    # rewrites bytes, only records offsets.
    a = root.members[0]
    assert data[a.key_start : a.value_end] == data[1:-1]


def test_parse_handles_astral_surrogate_pair_escape():
    # U+1F600 (😀) as a UTF-16 surrogate pair 😀 — decoded key comparison must
    # combine the pair correctly (exercised indirectly via a dotted-path match below).
    data = '{"😀": 1}'.encode("utf-8", errors="surrogatepass")
    # Re-encode the key as its \u escape pair so the JSON bytes are ASCII-safe.
    data = b'{"\\ud83d\\ude00": 1}'
    root = jsonfields.parse(data)
    assert root.members[0].key == "\U0001F600"


def test_parse_nested_objects_and_arrays_track_spans():
    data = b'{"a": {"b": [1, 2, {"c": 3}]}}'
    root = jsonfields.parse(data)
    a = root.members[0]
    assert a.value.kind == "object"
    b = a.value.members[0]
    assert b.value.kind == "array"
    assert len(b.value.elements) == 3
    assert b.value.elements[2].kind == "object"
    assert b.value.elements[2].members[0].key == "c"


def test_parse_raises_on_malformed_json():
    import pytest

    with pytest.raises(jsonfields.JSONParseError):
        jsonfields.parse(b'{"a": }')
    with pytest.raises(jsonfields.JSONParseError):
        jsonfields.parse(b'{"a": 1')  # unterminated object
    with pytest.raises(jsonfields.JSONParseError):
        jsonfields.parse(b"")  # empty input
    with pytest.raises(jsonfields.JSONParseError):
        jsonfields.parse(b'{"a": 1} garbage')  # trailing content


# ---------- removal grammar ---------- #


def _strip(data: bytes, paths: list[str]) -> tuple[bytes, int]:
    return jsonfields.strip_spans(data, jsonfields.normalize_strip_fields(paths))


def test_strip_removes_middle_member():
    data = b'{"a": 1, "b": 2, "c": 3}'
    out, n = _strip(data, ["b"])
    assert n == 1
    assert json.loads(out) == {"a": 1, "c": 3}
    assert b"b" not in out


def test_strip_removes_first_member():
    data = b'{"a": 1, "b": 2, "c": 3}'
    out, n = _strip(data, ["a"])
    assert n == 1
    assert json.loads(out) == {"b": 2, "c": 3}


def test_strip_removes_last_member():
    data = b'{"a": 1, "b": 2, "c": 3}'
    out, n = _strip(data, ["c"])
    assert n == 1
    assert json.loads(out) == {"a": 1, "b": 2}


def test_strip_removes_only_member_leaves_empty_object():
    data = b'{"a": 1}'
    out, n = _strip(data, ["a"])
    assert n == 1
    assert json.loads(out) == {}


def test_strip_array_traversal_removes_key_from_every_element():
    data = json.dumps(
        {
            "messages": [
                {"id": 1, "callEndedTimestamp": "t1", "body": "hi"},
                {"id": 2, "body": "bye"},  # no matching key — no-op for this element
                {"id": 3, "callEndedTimestamp": "t3", "body": "yo"},
            ]
        }
    ).encode()
    out, n = _strip(data, ["messages[].callEndedTimestamp"])
    assert n == 2  # only the two elements that HAD the key
    parsed = json.loads(out)
    assert all("callEndedTimestamp" not in m for m in parsed["messages"])
    assert [m["id"] for m in parsed["messages"]] == [1, 2, 3]


def test_strip_nested_dotted_path():
    data = json.dumps({"guild": {"id": 1, "iconUrl": "http://x", "name": "g"}}).encode()
    out, n = _strip(data, ["guild.iconUrl"])
    assert n == 1
    assert json.loads(out) == {"guild": {"id": 1, "name": "g"}}


def test_strip_absent_key_is_a_noop():
    data = b'{"a": 1}'
    out, n = _strip(data, ["nonexistent"])
    assert n == 0
    assert out == data


def test_strip_absent_intermediate_key_is_a_noop():
    """A dotted path whose intermediate segment doesn't exist (or isn't an object/array
    where the path expects one) contributes nothing — tolerant, not an error."""
    data = b'{"a": 1}'
    out, n = _strip(data, ["missing.nested.key"])
    assert n == 0
    assert out == data
    data2 = b'{"a": 1}'  # "a" exists but is a scalar, not an object
    out2, n2 = _strip(data2, ["a.nested"])
    assert n2 == 0
    assert out2 == data2


def test_strip_duplicate_keys_removes_every_occurrence():
    data = b'{"a": 1, "a": 2, "b": 3}'
    out, n = _strip(data, ["a"])
    assert n == 2
    # json.loads only keeps the LAST "a" on parse, so assert via a raw byte check too.
    assert b'"a"' not in out
    assert json.loads(out) == {"b": 3}


def test_strip_adjacent_members_both_removed_last_one_included():
    """The bug this module must get right: removing the last TWO members of an object
    together must not strand a trailing comma before the closing brace."""
    data = b'{"a":1,"b":2,"c":3}'
    out, n = _strip(data, ["b", "c"])
    assert n == 2
    assert json.loads(out) == {"a": 1}


def test_strip_removes_every_member_leaves_valid_empty_object():
    data = b'{"a":1,"b":2}'
    out, n = _strip(data, ["a", "b"])
    assert n == 2
    assert json.loads(out) == {}


def test_strip_multiple_independent_paths_in_one_pass():
    data = b'{"exportedAt": "t", "keep": 1, "guild": {"iconUrl": "u", "name": "g"}}'
    out, n = _strip(data, ["exportedAt", "guild.iconUrl"])
    assert n == 2
    assert json.loads(out) == {"keep": 1, "guild": {"name": "g"}}


def test_strip_no_matchers_is_noop():
    data = b'{"a": 1}'
    assert jsonfields.strip_spans(data, None) == (data, 0)
    assert jsonfields.strip_spans(data, jsonfields.normalize_strip_fields([])) == (data, 0)


def test_normalize_strip_fields_drops_malformed_entries_tolerantly():
    # "" and "[]" (no key at all) are structurally invalid — dropped, not raised.
    assert jsonfields.normalize_strip_fields(["a", "", "[]", "b.[]"]) is not None
    assert jsonfields.normalize_strip_fields(["", "[]"]) is None
    assert jsonfields.normalize_strip_fields(None) is None
    assert jsonfields.normalize_strip_fields([]) is None


# ---------- byte-preservation ---------- #


def test_untouched_bytes_are_byte_identical_odd_whitespace_and_key_order():
    """A fixture `json.dumps` would destroy: irregular indentation, a space before a
    colon, keys in non-alphabetical order, a trailing member with unusual spacing. Every
    byte OUTSIDE the removed span must survive verbatim."""
    data = (
        b'{   "zeta" :1,\n\t"alpha":   2,\n"middle_to_remove":  "gone" ,  "omega":4   }'
    )
    out, n = _strip(data, ["middle_to_remove"])
    assert n == 1
    assert json.loads(out) == {"zeta": 1, "alpha": 2, "omega": 4}
    # The surviving members' own bytes (including their odd spacing) are UNCHANGED.
    assert b'"zeta" :1' in out
    assert b'"alpha":   2' in out
    assert b'"omega":4' in out
    assert b"gone" not in out


# ---------- determinism ---------- #


def test_strip_is_deterministic():
    data = b'{"a": 1, "strip_me": "x", "b": {"strip_me": "y", "c": 2}}'
    matchers = jsonfields.normalize_strip_fields(["strip_me", "b.strip_me"])
    r1 = jsonfields.strip_spans(data, matchers)
    r2 = jsonfields.strip_spans(data, matchers)
    assert r1 == r2


# ---------- resolve_strip_fields ladder (mirrors resolve_strip_headers) ---------- #


def _corpus(tmp_path: Path, default_origin: str | None = None) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    if default_origin:
        _mime_shadow(root, default_origin)
    schemas.cache_clear()
    return root


def _mime_shadow(root: Path, default_origin: str) -> None:
    local = root / "schema/mime/application/application_json.yaml"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(_PACKAGED_JSON_SCHEMA.read_text() + f"\ndefault_origin: {default_origin}\n")
    schemas.cache_clear()


def _origin_overlay(root: Path, origin_id: str, strip_fields: list[str] | None) -> None:
    path = root / "schema" / "origin" / f"{origin_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["description: test origin overlay"]
    if strip_fields:
        lines.append("strip_fields:")
        lines.extend(f"- {p}" for p in strip_fields)
    else:
        lines.append("strip_fields: []")
    path.write_text("\n".join(lines) + "\n")
    schemas.cache_clear()


def test_resolve_strip_fields_subtype_overlay_wins_over_parent(tmp_path):
    root = _corpus(tmp_path)
    _origin_overlay(root, "discord", ["exportedAt"])
    _origin_overlay(root, "discord/guild-export", ["guild.iconUrl"])
    assert schemas.resolve_strip_fields(
        root, "application/json", origin_id="discord/guild-export"
    ) == ["guild.iconUrl"]


def test_resolve_strip_fields_walks_to_parent_when_subtype_silent(tmp_path):
    root = _corpus(tmp_path)
    _origin_overlay(root, "discord", ["exportedAt"])
    # No overlay file at all for "discord/guild-export" — the walk climbs to the parent.
    assert schemas.resolve_strip_fields(
        root, "application/json", origin_id="discord/guild-export"
    ) == ["exportedAt"]


def test_resolve_strip_fields_falls_back_to_default_origin_binding(tmp_path):
    root = _corpus(tmp_path, default_origin="discord/guild-export")
    _origin_overlay(root, "discord/guild-export", ["exportedAt", "guild.iconUrl"])
    assert schemas.resolve_strip_fields(root, "application/json") == [
        "exportedAt",
        "guild.iconUrl",
    ]


def test_resolve_strip_fields_stamped_origin_never_falls_to_default_binding(tmp_path):
    root = _corpus(tmp_path, default_origin="discord/guild-export")
    _origin_overlay(root, "discord/guild-export", ["exportedAt"])
    assert (
        schemas.resolve_strip_fields(root, "application/json", origin_id="meta-export")
        == []
    )


def test_resolve_strip_fields_none_declared_is_empty(tmp_path):
    root = _corpus(tmp_path)
    assert schemas.resolve_strip_fields(root, "application/json") == []
    assert schemas.resolve_strip_fields(root, "application/json", origin_id="nothing") == []


def test_resolve_strip_fields_declared_empty_list_is_declared_off(tmp_path):
    root = _corpus(tmp_path, default_origin="discord/guild-export")
    _origin_overlay(root, "discord/guild-export", None)  # explicit strip_fields: []
    assert schemas.resolve_strip_fields(root, "application/json") == []


def test_resolve_strip_fields_cli_override_wins(tmp_path):
    root = _corpus(tmp_path, default_origin="discord/guild-export")
    _origin_overlay(root, "discord/guild-export", ["exportedAt"])
    assert schemas.resolve_strip_fields(root, "application/json", ["cli.field"]) == [
        "cli.field"
    ]


# ---------- ingest end-to-end ---------- #


def _write_sidecar(source: Path, origin_schema: str) -> None:
    sidecar = source.with_suffix(source.suffix + ".capture.yaml")
    sidecar.write_text(yaml.safe_dump({"origin_schema": origin_schema}))


def _ingest(root: Path, artifact: Path) -> str:
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / artifact.name
    if staged != artifact:
        shutil.copy(artifact, staged)
        sidecar = artifact.with_suffix(artifact.suffix + ".capture.yaml")
        if sidecar.is_file():
            shutil.copy(sidecar, cap / sidecar.name)
    assert ingest_cli._ingest_one(root, staged) == 0
    recs = sorted((root / "records").rglob("*.md"))
    by_mtime = max(recs, key=lambda p: p.stat().st_mtime)
    return by_mtime.stem


def test_ingest_canonicalizes_via_stamped_origin(tmp_path):
    root = _corpus(tmp_path)
    _origin_overlay(root, "discord/guild-export", ["exportedAt", "guild.iconUrl"])
    source = tmp_path / "export.json"
    source.write_text(
        json.dumps(
            {
                "exportedAt": "2026-01-01T00:00:00Z",
                "guild": {"id": 1, "iconUrl": "http://x", "name": "g"},
                "messages": [],
            }
        )
    )
    _write_sidecar(source, "discord/guild-export")
    delivered_b3 = hashing.hash_file(source)["blake3"]

    rid = _ingest(root, source)
    assert rid != delivered_b3  # identity is over the CANONICALIZED bytes

    stored = root / "artifacts" / rid[:2] / f"{rid}.json"
    data = stored.read_bytes()
    assert b"exportedAt" not in data
    assert b"iconUrl" not in data
    assert hashing.hash_file(stored)["blake3"] == rid
    parsed = json.loads(data)
    assert parsed == {"guild": {"id": 1, "name": "g"}, "messages": []}

    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    fields = next(iter(records.iter_origin_blocks(post))).get("fields") or {}
    assert fields["stripped_fields"] == ["exportedAt", "guild.iconUrl"]
    assert fields["stripped_field_count"] == 2
    assert fields["source_transport"] == f"blake3:{delivered_b3}"


def test_ingest_untouched_without_declaration(tmp_path):
    root = _corpus(tmp_path)
    source = tmp_path / "export.json"
    source.write_text(json.dumps({"exportedAt": "2026-01-01T00:00:00Z", "a": 1}))
    delivered_b3 = hashing.hash_file(source)["blake3"]
    rid = _ingest(root, source)
    assert rid == delivered_b3
    stored = root / "artifacts" / rid[:2] / f"{rid}.json"
    assert b"exportedAt" in stored.read_bytes()


def test_ingest_already_canonical_passes_through(tmp_path):
    root = _corpus(tmp_path)
    _origin_overlay(root, "discord/guild-export", ["exportedAt"])
    source = tmp_path / "export.json"
    source.write_text(json.dumps({"a": 1}))  # nothing to strip
    _write_sidecar(source, "discord/guild-export")
    delivered_b3 = hashing.hash_file(source)["blake3"]

    rid = _ingest(root, source)
    assert rid == delivered_b3  # nothing to strip → no rewrite, no provenance
    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    fields = next(iter(records.iter_origin_blocks(post))).get("fields") or {}
    assert "stripped_fields" not in fields


def test_ingest_malformed_json_left_as_is(tmp_path, capsys):
    """Parse tolerance at the ingest boundary: a strip IS declared, but the staged file
    isn't valid JSON — ingest proceeds untouched rather than raising."""
    root = _corpus(tmp_path)
    _origin_overlay(root, "discord/guild-export", ["exportedAt"])
    source = tmp_path / "export.json"
    source.write_text('{"exportedAt": }')  # malformed
    _write_sidecar(source, "discord/guild-export")
    delivered_b3 = hashing.hash_file(source)["blake3"]

    rid = _ingest(root, source)
    assert rid == delivered_b3
    assert "not valid JSON" in capsys.readouterr().err
