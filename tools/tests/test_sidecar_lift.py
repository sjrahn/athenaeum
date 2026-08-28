"""The container-member sidecar lift (spec/corpus.md §7.2 `sidecar:`, v41) — driven by
TWO producer-shaped fixtures and ZERO producer branches in code.

Producer A (`photo-export`) pairs `<member>.json` beside each still and lifts scalars,
a filtered list, a flag set, and two roster-resolved sibling references; producer B
(`mail-export`) pairs `<stem>.metadata.json` beside each message, lifts from a nested
payload, and names an export-level member that pairs with nothing. Both join by
declaration alone — the engine never learns which is which. The names are deliberately
NOT any real producer's: the test is that the declaration grammar carries everything.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import shutil
import zipfile
from pathlib import Path

import blake3
import pytest
import yaml
from PIL import Image

from corpus import hashing, lint, paths, records, schemas, segments, sidecar
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import inspect_ as inspect_cli
from corpus._cli import period_split
from corpus._cli import promote as promote_cli
from corpus._cli import reattest as reattest_cli

# ---------- producer A: a photo-library shape ---------- #

_PHOTO_OVERLAY = """\
description: producer A — a per-item JSON beside each still
sidecar:
  pairing: {template: "{member}.json"}
  format: json
  prefix: px_
  subtype: item
  lift:
    uuid: uuid
    taken: date_original
    modified: date_modified
    place_name: place.name
    at_home: place.ishome
    persons: {path: persons, omit: [_UNKNOWN_]}
    albums: albums
    favorite: favorite
    kind: {flags: [live_photo, screenshot]}
    make: exif_info.camera_make
    scores: score
  references:
    edited: {template: "{stem}_edited.jpeg", when: hasadjustments}
    live: {template: "{stem}.mov", when: live_photo}
"""

_PHOTO_SUBTYPE_OVERLAY = """\
description: producer A — the promoted item
extended_fields:
  px_uuid: {type: string, required: false, role: title, description: item id}
  px_taken: {type: string, required: false, semantic_type: timestamp, description: taken}
  px_modified: {type: string, required: false, description: modified}
  px_place_name: {type: string, required: false, description: place}
  px_at_home: {type: boolean, required: false, description: at home}
  px_persons: {type: string_or_list, required: false, description: named persons}
  px_albums: {type: string_or_list, required: false, description: albums}
  px_favorite: {type: boolean, required: false, description: favourite}
  px_kind: {type: string_or_list, required: false, description: kind flags}
  px_make: {type: string, required: false, description: camera make}
  px_scores: {type: string, required: false, description: never lifted (nested)}
  px_edited: {type: string, required: false, description: edited render member}
  px_live: {type: string, required: false, description: live twin member}
"""


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (6, 4), (200, 100, 50)).save(buf, format="PNG")
    return buf.getvalue()


_SIDECAR_0001 = {
    "uuid": "0001-UUID",
    "date_original": "2026-07-11T23:04:28.312000-06:00",
    "date_modified": None,
    "place": {"name": "Calgary, Alberta, Canada", "ishome": True, "address": {"city": "C"}},
    "persons": ["_UNKNOWN_", "Alice", "_UNKNOWN_"],
    "albums": [],
    "favorite": False,
    "hasadjustments": True,
    "live_photo": True,
    "screenshot": False,
    "exif_info": {"camera_make": "Acme", "aperture": 1.78},
    "score": {"overall": 0.5},
    "title": None,
}

_SIDECAR_0002 = {
    "uuid": "0002-UUID",
    "date_original": "2025-11-01T10:00:00-06:00",
    "persons": ["_UNKNOWN_"],
    "hasadjustments": False,
    "live_photo": False,
    "screenshot": True,
    "exif_info": {"camera_make": "Acme"},
}

_PHOTO_MEMBERS = {
    "IMG_0001.HEIC": _png(),
    "IMG_0001.HEIC.json": json.dumps(_SIDECAR_0001).encode(),
    "IMG_0001_edited.jpeg": b"edited render bytes\n",
    "IMG_0001.mov": b"live twin bytes\n",
    "IMG_0002.HEIC": b"still two bytes\n",
    "IMG_0002.HEIC.json": json.dumps(_SIDECAR_0002).encode(),
    "notes.txt": b"unrelated member\n",
}

# ---------- producer B: a mail-export shape ---------- #

_MAIL_OVERLAY = """\
description: producer B — a metadata JSON beside each message, plus an export-level roster
sidecar:
  pairing: {template: "{stem}.metadata.json", export_level: [labels.json]}
  prefix: pm_
  subtype: message
  lift:
    subject: Payload.Subject
    time: Payload.Time
    labels: Payload.LabelIDs
"""

_MAIL_SUBTYPE_OVERLAY = """\
description: producer B — the promoted message
extended_fields:
  pm_subject: {type: string, required: false, role: title, description: subject}
  pm_time: {type: integer, required: false, description: epoch seconds}
  pm_labels: {type: string_or_list, required: false, description: label ids}
"""

_MAIL_MEMBERS = {
    "abc.eml": b"From: a@b\nSubject: hi\n\nbody\n",
    "abc.metadata.json": json.dumps(
        {"Payload": {"Subject": "Hello", "Time": 1700000000, "LabelIDs": ["1"]}}
    ).encode(),
    "labels.json": json.dumps({"labels": ["Inbox"]}).encode(),
}


# ---------- fixture plumbing ---------- #


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _write_overlays(
    root: Path, origin_id: str, overlay: str, subtype: str, sub_overlay: str
) -> None:
    d = root / "schema" / "origin"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{origin_id}.yaml").write_text(overlay, encoding="utf-8")
    (d / origin_id).mkdir(exist_ok=True)
    (d / origin_id / f"{subtype}.yaml").write_text(sub_overlay, encoding="utf-8")
    schemas.cache_clear()


def _corpus(tmp_path: Path, *, producer: str = "photo") -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    if producer == "photo":
        _write_overlays(root, "photo-export", _PHOTO_OVERLAY, "item", _PHOTO_SUBTYPE_OVERLAY)
    else:
        _write_overlays(root, "mail-export", _MAIL_OVERLAY, "message", _MAIL_SUBTYPE_OVERLAY)
    return root


def _container(tmp_path: Path, root: Path, members: dict[str, bytes], origin_id: str) -> str:
    """Ingest a zip of `members` as a manifest container whose origin block is qualified
    with `origin_id` (a producer-declared, uri-less local-file origin, spec §7.2)."""
    z = tmp_path / f"{origin_id}.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    shutil.copy(z, cap / z.name)
    assert ingest_cli._ingest_one(root, cap / z.name) == 0
    cid = hashing.hash_file(z)["blake3"]
    rf = paths.record_path(root, cid)
    post = records.load(rf)
    draft_cli.derive_record(post, root)
    for blk in records.iter_origin_blocks(post):
        blk["id"] = origin_id
    records.dump(post, rf)
    return cid


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


def _origin(root: Path, rid: str) -> dict:
    return next(iter(records.iter_origin_blocks(records.load(paths.record_path(root, rid)))))


def _lint(root: Path, rid: str) -> set[str]:
    post = records.load(paths.record_path(root, rid))
    return {f.rule_id for f in lint.lint(post, segments.iter_blocks(post.content or ""), root)}


@pytest.fixture
def photo(tmp_path):
    root = _corpus(tmp_path, producer="photo")
    cid = _container(tmp_path, root, _PHOTO_MEMBERS, "photo-export")
    return root, cid


@pytest.fixture
def mail(tmp_path):
    root = _corpus(tmp_path, producer="mail")
    cid = _container(tmp_path, root, _MAIL_MEMBERS, "mail-export")
    return root, cid


# ---------- 1. promote: the lift ---------- #


def test_primary_promotes_with_the_lifted_block(photo):
    root, cid = photo
    assert _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC") == 0
    pid = _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"])
    block = _origin(root, pid)
    # The lineage opener is qualified `<producer>/<subtype>`; the uri stays the lineage.
    assert (block["id"], block["subtype"]) == ("photo-export", "item")
    f = block["fields"]
    assert f["uri"] == f"corpus://{cid}?path=IMG_0001.HEIC"
    assert f["filename"] == "IMG_0001.HEIC"
    # Scalars, a filtered list, a flag set, a nested-path scalar, a boolean.
    assert f["px_uuid"] == "0001-UUID"
    assert f["px_taken"] == "2026-07-11T23:04:28.312000-06:00"
    assert f["px_place_name"] == "Calgary, Alberta, Canada"
    assert f["px_at_home"] is True
    assert f["px_persons"] == ["Alice"]
    assert f["px_kind"] == ["live_photo"]
    assert f["px_make"] == "Acme"
    # Present-only: null, empty list, false, and a nested object write nothing.
    for absent in ("px_modified", "px_albums", "px_favorite", "px_scores"):
        assert absent not in f
    # Sibling references resolved against the roster, stored as member addresses.
    assert f["px_edited"] == "path=IMG_0001_edited.jpeg"
    assert f["px_live"] == "path=IMG_0001.mov"
    # Declaration order, after the universal lineage fields.
    keys = list(f)
    assert keys[:4] == ["uri", "snapshot", "filename", "source_modified"]
    assert keys[4:] == [
        "px_uuid", "px_taken", "px_place_name", "px_at_home", "px_persons", "px_kind",
        "px_make", "px_edited", "px_live",
    ]
    # The artifact block attested from the bytes as usual (a PNG under a .HEIC name).
    post = records.load(paths.record_path(root, pid))
    assert records.media_type_for(post) == "image/png"
    assert (records.artifact_block(post) or {}).get("fields", {}).get("width") == 6
    assert _lint(root, pid).isdisjoint({"sidecar-member-promoted", "sidecar-field-undeclared"})


def test_no_gate_no_reference_no_flag(photo):
    root, cid = photo
    assert _promote(root, f"corpus://{cid}?path=IMG_0002.HEIC") == 0
    f = _origin(root, _b3(_PHOTO_MEMBERS["IMG_0002.HEIC"]))["fields"]
    assert f["px_uuid"] == "0002-UUID"
    assert f["px_kind"] == ["screenshot"]
    assert "px_persons" not in f  # every entry omitted → nothing
    assert "px_edited" not in f and "px_live" not in f  # gates false → never invented


def test_consumed_sidecar_address_is_refused_naming_the_primary(photo):
    root, cid = photo
    with pytest.raises(SystemExit, match=r"consumed sidecar of member 'IMG_0001\.HEIC'"):
        _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC.json")
    assert not paths.record_path(root, _b3(_PHOTO_MEMBERS["IMG_0001.HEIC.json"])).exists()


def test_member_with_no_sidecar_stays_bare(photo):
    root, cid = photo
    for member in ("IMG_0001_edited.jpeg", "notes.txt"):
        assert _promote(root, f"corpus://{cid}?path={member}") == 0
        block = _origin(root, _b3(_PHOTO_MEMBERS[member]))
        assert block["id"] is None
        assert not [k for k in block["fields"] if k.startswith("px_")]


def test_re_promote_is_idempotent(photo, capsys):
    root, cid = photo
    uri = f"corpus://{cid}?path=IMG_0001.HEIC"
    assert _promote(root, uri) == 0
    rf = paths.record_path(root, _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"]))
    first = records.load(rf)
    assert _promote(root, uri) == 0
    assert "already-promoted" in capsys.readouterr().out
    second = records.load(rf)
    assert list(records.iter_origin_blocks(first)) == list(records.iter_origin_blocks(second))


def test_promote_reports_the_lift(photo, capsys):
    root, cid = photo
    assert promote_cli.run(argparse.Namespace(
        uri=f"corpus://{cid}?path=IMG_0001.HEIC", json=True, corpus_root=str(root)
    )) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["sidecar"] == "path=IMG_0001.HEIC.json"
    assert out["origin_schema"] == "photo-export/item"
    assert "px_edited" in out["lifted"] and "px_modified" not in out["lifted"]


# ---------- 2. re-attest: strip + regenerate the owned names only ---------- #


def test_reattest_regenerates_owned_names_and_keeps_operator_stamps(photo):
    root, cid = photo
    assert _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC") == 0
    rf = paths.record_path(root, _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"]))
    post = records.load(rf)
    block = next(iter(records.iter_origin_blocks(post)))
    block["fields"]["px_uuid"] = "TAMPERED"
    block["fields"]["operator_note"] = "keep me"  # not declaration-owned
    records.dump(post, rf)

    rf.write_text(reattest_cli.reattest_record(rf, root), encoding="utf-8")
    f = _origin(root, rf.stem)["fields"]
    assert f["px_uuid"] == "0001-UUID"
    assert f["operator_note"] == "keep me"
    assert f["px_edited"] == "path=IMG_0001_edited.jpeg"
    # Idempotent: a second re-attest re-derives byte-for-byte.
    text = rf.read_text(encoding="utf-8")
    assert reattest_cli.reattest_record(rf, root) == text


def test_reattest_follows_a_changed_declaration(photo):
    """The lift is a function of (container + declaration): drop `make` from the lift
    map and add `model`, and re-attest moves the block to the new declaration — the
    retired name gone, the new one present, everything else untouched."""
    root, cid = photo
    assert _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC") == 0
    rf = paths.record_path(root, _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"]))
    assert "px_make" in _origin(root, rf.stem)["fields"]

    changed = _PHOTO_OVERLAY.replace("    make: exif_info.camera_make\n", "")
    changed = changed.replace(
        "    scores: score\n", "    scores: score\n    aperture: exif_info.aperture\n"
    )
    _write_overlays(root, "photo-export", changed, "item", _PHOTO_SUBTYPE_OVERLAY)
    rf.write_text(reattest_cli.reattest_record(rf, root), encoding="utf-8")
    f = _origin(root, rf.stem)["fields"]
    assert "px_make" not in f
    assert f["px_aperture"] == 1.78
    assert f["px_uuid"] == "0001-UUID"


def test_reattest_leaves_a_block_alone_when_the_container_declares_nothing(photo):
    root, cid = photo
    assert _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC") == 0
    rf = paths.record_path(root, _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"]))
    # Retire the declaration entirely: nothing is owned any more, so nothing is stripped —
    # the fields already on the block are history, not a defect.
    _write_overlays(
        root, "photo-export", "description: no sidecar\n", "item", _PHOTO_SUBTYPE_OVERLAY
    )
    before = _origin(root, rf.stem)["fields"]
    rf.write_text(reattest_cli.reattest_record(rf, root), encoding="utf-8")
    assert _origin(root, rf.stem)["fields"] == before


# ---------- 3. lint ---------- #


def _lineage_only_record(root: Path, cid: str, member: str, data: bytes, *, extra_uri=None):
    rid = _b3(data)
    post = records.loads("")
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.promote@0"))
    records.set_artifact_block(post, mime="application/json", fields={})
    records.append_origin_block(
        post, uri=f"corpus://{cid}?path={member}", snapshot="2026-01-01T00:00:00Z"
    )
    if extra_uri:
        records.append_origin_block(post, uri=extra_uri, snapshot="2026-01-02T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_lint_flags_a_record_whose_sole_lineage_is_a_consumed_sidecar(photo):
    root, cid = photo
    rid = _lineage_only_record(
        root, cid, "IMG_0001.HEIC.json", _PHOTO_MEMBERS["IMG_0001.HEIC.json"]
    )
    post = records.load(paths.record_path(root, rid))
    findings = lint.lint(post, [], root, rules=["sidecar-member-promoted"])
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].fields["primary"] == "path=IMG_0001.HEIC"


def test_lint_leaves_a_record_with_another_origin_alone(photo):
    root, cid = photo
    rid = _lineage_only_record(
        root, cid, "IMG_0001.HEIC.json", _PHOTO_MEMBERS["IMG_0001.HEIC.json"],
        extra_uri="https://example.com/standalone",
    )
    assert "sidecar-member-promoted" not in _lint(root, rid)
    # ... and a primary's lineage is never a finding.
    rid2 = _lineage_only_record(root, cid, "IMG_0002.HEIC", _PHOTO_MEMBERS["IMG_0002.HEIC"])
    assert "sidecar-member-promoted" not in _lint(root, rid2)


def test_lint_flags_an_undeclared_lifted_field(photo):
    root, cid = photo
    assert _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC") == 0
    pid = _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"])
    assert "sidecar-field-undeclared" not in _lint(root, pid)
    thinner = _PHOTO_SUBTYPE_OVERLAY.replace(
        "  px_make: {type: string, required: false, description: camera make}\n", ""
    )
    _write_overlays(root, "photo-export", _PHOTO_OVERLAY, "item", thinner)
    post = records.load(paths.record_path(root, pid))
    findings = lint.lint(post, [], root, rules=["sidecar-field-undeclared"])
    assert [f.fields["fields"] for f in findings] == [["px_make"]]


def test_lint_reports_a_malformed_declaration(photo):
    root, cid = photo
    rid = _lineage_only_record(root, cid, "IMG_0002.HEIC", _PHOTO_MEMBERS["IMG_0002.HEIC"])
    _write_overlays(
        root, "photo-export", "description: broken\nsidecar:\n  pairing: {}\n", "item",
        _PHOTO_SUBTYPE_OVERLAY,
    )
    assert "sidecar-declaration-invalid" in _lint(root, rid)
    with pytest.raises(SystemExit, match="pairing"):
        _promote(root, f"corpus://{cid}?path=IMG_0002.HEIC")


# ---------- 4. the second producer, by declaration alone ---------- #


def test_mail_shape_lifts_from_a_nested_payload(mail):
    root, cid = mail
    assert _promote(root, f"corpus://{cid}?path=abc.eml") == 0
    block = _origin(root, _b3(_MAIL_MEMBERS["abc.eml"]))
    assert (block["id"], block["subtype"]) == ("mail-export", "message")
    f = block["fields"]
    assert f["pm_subject"] == "Hello"
    assert f["pm_time"] == 1700000000
    assert f["pm_labels"] == ["1"]
    with pytest.raises(SystemExit, match=r"consumed sidecar of member 'abc\.eml'"):
        _promote(root, f"corpus://{cid}?path=abc.metadata.json")
    # An export-level member pairs with no primary: an ordinary, promotable member.
    assert _promote(root, f"corpus://{cid}?path=labels.json") == 0
    assert _origin(root, _b3(_MAIL_MEMBERS["labels.json"]))["id"] is None


# ---------- 5. period-split reads the same declaration ---------- #


def test_period_split_pairs_through_the_declaration(tmp_path):
    root = _corpus(tmp_path, producer="mail")
    overlay = (root / "schema" / "origin" / "mail-export.yaml")
    overlay.write_text(overlay.read_text() + "partition:\n  grain: month\n  undated: standing\n")
    schemas.cache_clear()
    src = tmp_path / "export"
    src.mkdir()
    for name, data in _MAIL_MEMBERS.items():
        (src / name).write_bytes(data)
    rc = period_split.run(argparse.Namespace(
        source=str(src), origin="mail-export", date_from="sidecar:Payload.Time",
        current_period="2026-02", corpus_root=str(root),
    ))
    assert rc == 0
    z = root / "capture" / "export-2023-11.zip"  # 1700000000 → 2023-11-14 UTC
    assert z.exists()
    with zipfile.ZipFile(z) as zf:
        assert sorted(zf.namelist()) == ["abc.eml", "abc.metadata.json"]
    stamped = yaml.safe_load(z.with_suffix(".zip.capture.yaml").read_text())
    assert stamped["origin_fields"]["export_level_metadata"] == ["labels.json"]


# ---------- 6. inspect ---------- #


def test_inspect_prints_the_lift(photo, capsys):
    root, cid = photo
    assert _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC") == 0
    pid = _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"])
    assert inspect_cli.run(argparse.Namespace(target=pid, corpus_root=str(root))) == 0
    out = capsys.readouterr().out
    assert "[photo-export/item]" in out
    assert "lifted (px_*, 7):" in out
    assert "px_uuid=0001-UUID" in out
    assert "references (2): px_edited=path=IMG_0001_edited.jpeg, px_live=path=IMG_0001.mov" in out


# ---------- 7. the declaration grammar ---------- #


def test_expand_template_placeholders():
    assert sidecar.expand_template("{member}.json", "a/b.c/IMG_1.HEIC") == "a/b.c/IMG_1.HEIC.json"
    assert (
        sidecar.expand_template("{stem}_edited.jpeg", "a/b.c/IMG_1.HEIC")
        == "a/b.c/IMG_1_edited.jpeg"
    )
    assert sidecar.expand_template("{dir}meta/{name}.json", "x/y/z.eml") == "x/y/meta/z.eml.json"
    assert sidecar.expand_template("{stem}.metadata.json", "noext") == "noext.metadata.json"


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ({}, "pairing"),
        ({"pairing": {"template": "fixed.json"}}, "no placeholder"),
        ({"pairing": {"template": "{nope}.json"}}, "unknown placeholder"),
        ({"pairing": {"template": "{member}.json"}, "format": "xml"}, "format"),
        ({"pairing": {"template": "{member}.json"}, "lift": {"a": "a"}}, "prefix"),
        ({"pairing": {"template": "{member}.json"}, "prefix": "p_", "lift": {"a": "a"}}, "subtype"),
        (
            {"pairing": {"template": "{member}.json"}, "prefix": "p_", "subtype": "s",
             "lift": {"a": {"path": "a", "flags": ["b"]}}},
            "flags",
        ),
        (
            {"pairing": {"template": "{member}.json"}, "prefix": "p_", "subtype": "s",
             "lift": {"a": "a"}, "references": {"a": {"template": "{stem}.x"}}},
            "declared twice",
        ),
        (
            {"pairing": {"template": "{member}.json"}, "prefix": "p_", "subtype": "s",
             "lift": {"bad name": "a"}},
            "not a valid field name",
        ),
    ],
)
def test_declaration_validation(raw, match):
    with pytest.raises(sidecar.DeclarationError, match=match):
        sidecar.parse_declaration(raw, source_id="t")


def test_pairing_only_declaration_is_valid():
    decl = sidecar.parse_declaration({"pairing": {"template": "{member}.json"}}, source_id="t")
    assert decl.qualified_id is None and not decl.owns("anything")
    roster = ("a.txt", "a.txt.json", "b.txt")
    assert decl.sidecar_for("a.txt", roster) == "a.txt.json"
    assert decl.sidecar_for("b.txt", roster) is None
    assert decl.primary_of("a.txt.json", roster) == "a.txt"
    assert decl.primary_of("b.txt", roster) is None


def test_project_is_present_only_and_never_lifts_objects():
    decl = sidecar.parse_declaration(
        {
            "pairing": {"template": "{member}.json"}, "prefix": "p_", "subtype": "s",
            "lift": {
                "n": "n", "z": "z", "e": "e", "f": "f", "o": "o",
                "l": {"path": "l", "omit": ["skip"]}, "flags": {"flags": ["x", "y", "w"]},
            },
            "references": {"r": {"template": ["{stem}.a", "{stem}.b"]}},
        },
        source_id="t",
    )
    doc = {
        "n": 0, "z": "", "e": [], "f": False, "o": {"k": 1},
        "l": ["skip", "keep", {"nested": 1}, None, 2],
        "x": True, "y": False, "w": "truthy-but-not-a-flag",
    }
    out = sidecar.project(decl, doc, "m.txt", ("m.txt", "m.b"))
    # 0 is a value; "", [], false, and an object are not.
    assert out == {"p_n": 0, "p_l": ["keep", 2], "p_flags": ["x"], "p_r": "path=m.b"}


# ---------- 8. the genericity guard ---------- #


def test_engine_paths_carry_no_producer_branch():
    """The owner's constraint (2026-08-27) as a test: no identifier, dict key, or
    comparison operand in the engine paths names a producer or a field meaning. Prose
    (docstrings, comments, help text) may use examples; code may not branch on them."""
    from corpus import derive
    from corpus import lint as lint_mod
    from corpus import sidecar as sidecar_mod
    from corpus._cli import period_split as ps_mod
    from corpus._cli import promote as promote_mod

    tokens = ("osx", "proton", "ytdlp", "photoinfo", "hasadjustments", "live_photo")
    for mod in (sidecar_mod, promote_mod, ps_mod, derive, lint_mod):
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        offenders: list[str] = []
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(node.name)
            elif isinstance(node, ast.Name):
                names.append(node.id)
            elif isinstance(node, ast.Attribute):
                names.append(node.attr)
            elif isinstance(node, ast.arg):
                names.append(node.arg)
            elif isinstance(node, ast.Compare):
                for operand in (node.left, *node.comparators):
                    if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                        names.append(operand.value)
            elif isinstance(node, ast.Dict):
                names.extend(
                    k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                )
            offenders.extend(n for n in names if any(t in n.lower() for t in tokens))
        assert not offenders, f"{mod.__name__}: producer-shaped code: {offenders}"
