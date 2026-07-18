"""The `row=<N>[&col=<name-or-index>]` CSV unit op (spec §6.2, §7.1) —
`transforms/csv.py` + `schemas_default/mime/text/text_csv.yaml`.

Covers: RFC-4180-aware quoting (embedded commas/newlines/escaped quotes), header-name vs
integer-index column resolution, out-of-range/bad-column errors, a schema-declared dialect
override (no delimiter/quoting/header-presence knowledge hardcoded in the engine), the
zip-member streaming path a promoted CSV takes (mirrors `test_containment.py`'s
`test_promoted_member_resolves_by_streaming`), and the `form/passthrough` terminal-state
default (spec §7.8/§7.1)."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

import frontmatter
import pytest
import yaml

from corpus import functional_uri as furi
from corpus import hashing, paths, records, resolver, schemas
from corpus import mime as mime_mod
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli
from corpus.store import LocalArtifactStore


def _text(p: Path) -> str:
    """Decode a resolved file's bytes verbatim — `Path.read_text` defaults to universal-
    newlines translation, which would silently collapse a preserved `\\r\\n` and defeat
    the exact-bytes assertions below."""
    return p.read_bytes().decode("utf-8")


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _stage_record(root: Path, data: bytes, *, mime: str, name: str) -> str:
    """Stage `data` as a standalone record under `mime` — bypassing the CLI's own mime
    sniff, since the fixture asserts the schema-routing contract directly. Stores the
    artifact under whatever extension `mime.extension_for(mime)` resolves to, so a
    resolve's `containment.ensure_local_bytes(..., mime_mod.extension_for(media_type))`
    lookup finds it."""
    src = root.parent / name
    src.write_bytes(data)
    rid = hashing.hash_file(src)["blake3"]
    ext = mime_mod.extension_for(mime)

    LocalArtifactStore(root).put(rid, ext, src)
    post = frontmatter.Post("")
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"))
    records.set_artifact_block(post, mime=mime, fields={})
    records.append_origin_block(
        post, snapshot="2026-07-18T00:00:00Z", fields={"filename": name, "source_modified": ""}
    )
    records.dump(post, paths.record_path(root, rid))
    return rid


def _ingest_bytes(root: Path, data: bytes, *, name: str = "data.csv") -> str:
    return _stage_record(root, data, mime="text/csv", name=name)


_SIMPLE = (
    b"city,fare,note\r\n"
    b"Calgary,11.03,plain\r\n"
    b'Winnipeg,"9,50","quoted, comma"\r\n'
    b'Regina,7.25,"multi\r\nline note"\r\n'
    b'Banff,3.00,"she said ""hi"""\r\n'
)


def test_row_returns_raw_data_row_verbatim(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    out = resolver.resolve(f"corpus://{rid}?row=1", root)
    assert _text(out) == "Calgary,11.03,plain\r\n"


def test_row_header_excluded_from_data_ordinals(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    # 4 data rows total; row=4 is the last one (Banff), never the header.
    out = resolver.resolve(f"corpus://{rid}?row=4", root)
    assert _text(out).startswith("Banff,")


def test_row_embedded_comma_inside_quotes_stays_one_field(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    out = resolver.resolve(f"corpus://{rid}?row=2&col=note", root)
    assert _text(out) == "quoted, comma"


def test_row_embedded_newline_inside_quotes_rides_the_same_row(tmp_path):
    """The 3rd data row (`Regina`, whose `note` field embeds a raw newline inside
    quotes) must resolve as ONE logical row, both for `row=` alone and for a `col=`
    refinement — never truncated at the first embedded newline."""
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    raw = _text(resolver.resolve(f"corpus://{rid}?row=3", root))
    assert raw == 'Regina,7.25,"multi\r\nline note"\r\n'
    field = _text(resolver.resolve(f"corpus://{rid}?row=3&col=note", root))
    assert field == "multi\r\nline note"


def test_row_doubled_quote_escape_decodes_to_one_quote_char(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    out = resolver.resolve(f"corpus://{rid}?row=4&col=note", root)
    assert _text(out) == 'she said "hi"'


def test_col_header_name_match_preferred(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    out = resolver.resolve(f"corpus://{rid}?row=1&col=fare", root)
    assert _text(out) == "11.03"


def test_col_integer_index_fallback_when_not_a_header_name(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    # column 1 = city, by 1-indexed position — "1" is not itself a header name.
    out = resolver.resolve(f"corpus://{rid}?row=1&col=1", root)
    assert _text(out) == "Calgary"


def test_row_out_of_range_raises_clear_error(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    with pytest.raises(ValueError, match=r"row=99: out of range \(4 data row\(s\)\)"):
        resolver.resolve(f"corpus://{rid}?row=99", root)


def test_col_unknown_header_name_raises_clear_error(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    with pytest.raises(ValueError, match=r"no such header"):
        resolver.resolve(f"corpus://{rid}?row=1&col=not_a_column", root)


def test_bare_col_without_row_is_rejected_clearly(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    with pytest.raises(ValueError, match=r"col.*not applicable to working kind 'csv'"):
        resolver.resolve(f"corpus://{rid}?col=fare", root)


def test_col_out_of_range_index_raises_clear_error(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    with pytest.raises(ValueError, match=r"row has 3 field\(s\)"):
        resolver.resolve(f"corpus://{rid}?row=1&col=99", root)


def test_sidecar_records_engine_version(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    out = resolver.resolve(f"corpus://{rid}?row=1&col=fare", root)
    sidecar = furi.cache_sidecar_path(out)
    data = json.loads(sidecar.read_text("utf-8"))
    assert data["engine"] == "csv-row-col@1"


# ---------- dialect is schema-declared, never hardcoded (§7.1) ---------- #

_ALT_MIME = "text/x-test-semicolon-csv"


def _write_alt_dialect_schema(root: Path, **dialect: object) -> None:
    schema_dir = root / "schema" / "mime" / "text"
    schema_dir.mkdir(parents=True, exist_ok=True)
    (schema_dir / "text_x-test-semicolon-csv.yaml").write_text(
        yaml.safe_dump(
            {
                "applies_to": {"content_types": [_ALT_MIME]},
                "working_kind": "csv",
                "csv_dialect": dialect,
                "form": {"id": "passthrough"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    schemas.cache_clear()


def test_custom_delimiter_from_schema_not_hardcoded(tmp_path):
    root = _corpus(tmp_path)
    _write_alt_dialect_schema(root, delimiter=";", header_row=True, quoting="minimal")
    data = b"city;fare\r\nCalgary;11.03\r\nWinnipeg;9.50\r\n"
    rid = _stage_record(root, data, mime=_ALT_MIME, name="semi.csv")

    out = resolver.resolve(f"corpus://{rid}?row=2&col=city", root)
    assert _text(out) == "Winnipeg"


def test_header_row_false_treats_first_line_as_data_and_needs_integer_col(tmp_path):
    root = _corpus(tmp_path)
    _write_alt_dialect_schema(root, delimiter=",", header_row=False, quoting="minimal")
    data = b"Calgary,11.03\r\nWinnipeg,9.50\r\n"
    rid = _stage_record(root, data, mime=_ALT_MIME, name="noheader.csv")

    # row=1 is the FIRST physical line — no header to skip.
    out = resolver.resolve(f"corpus://{rid}?row=1&col=1", root)
    assert _text(out) == "Calgary"
    with pytest.raises(ValueError, match=r"declares no header row"):
        resolver.resolve(f"corpus://{rid}?row=1&col=city", root)


# ---------- the zip-member streaming path (mirrors test_containment.py) ---------- #


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return path


def _ingest_and_draft(root: Path, archive: Path) -> str:
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / archive.name
    shutil.copy(archive, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    rid = hashing.hash_file(archive)["blake3"]
    post = records.load(paths.record_path(root, rid))
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, rid))
    return rid


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


def test_row_resolves_through_promoted_zip_member_streaming(tmp_path):
    """A CSV that arrives as a zip member (the real corpus-private shape this op was
    built against — a promoted `Uber Data/Rider/trips_data-0.csv`) resolves `row=`/`col=`
    by STREAMING through the container, never requiring a standalone artifact copy —
    exactly the promoted-member contract `test_containment.py` exercises for `path=`."""
    root = _corpus(tmp_path)
    payload = _SIMPLE
    z = _zip(tmp_path / "export.zip", {"trips.csv": payload})
    cid = _ingest_and_draft(root, z)

    assert _promote(root, f"corpus://{cid}?path=trips.csv") == 0
    import blake3

    pid = blake3.blake3(payload).hexdigest()
    assert not LocalArtifactStore(root).is_local(pid, "csv")  # no standalone residence

    out = resolver.resolve(f"corpus://{pid}?row=2&col=fare", root)
    assert _text(out) == "9,50"
    assert "cache" in out.parts  # materialized into the resolver cache, not artifacts/


# ---------- terminal state (spec §7.8/§7.1 `form: {id: passthrough}`) ---------- #


def test_csv_record_derives_terminal_state(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_bytes(root, _SIMPLE)
    post = records.load(paths.record_path(root, rid))
    assert records.derived_state(post, root) == "terminal"


# ---------- functional-URI grammar acceptance (spec §6.1) ---------- #


def test_functional_uri_grammar_accepts_row_and_col():
    parsed = furi.parse("corpus://" + "a" * 64 + "?row=37&col=city_name")
    assert parsed.params == (("row", "37"), ("col", "city_name"))
    assert furi.canonical(parsed) == "corpus://" + "a" * 64 + "?row=37&col=city_name"
