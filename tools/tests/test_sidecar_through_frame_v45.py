"""A container-member sidecar is metadata of its frame, never a member (spec v45, owner
ruling 2026-09-22 — codex-steven R-0037).

v41 kept the sidecar a roster row, addressable by `?path=<sidecar>` and refused only at
promote. v45 finishes the thought: a sidecar the container's `sidecar:` declaration pairs to
a present frame is not a roster row, has no address of its own (`path=<sidecar>` is refused,
naming the frame), and is read only THROUGH the frame — `?path=<frame>&sidecar` verbatim, the
frame's `members` descriptor carrying its projection, and `promote` lifting it as before.
Pairing is physical (the container's own entries), since the roster no longer lists it.

Fixtures reuse the v41 suite's two fictional producers: the engine still knows neither.
"""

from __future__ import annotations

import argparse
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from corpus import functional_uri as furi
from corpus import paths, records, resolver, sidecar
from corpus import transforms as transforms_mod
from corpus._cli import inspect_ as inspect_cli
from corpus._cli import reattest as reattest_cli
from tests.test_sidecar_lift import (
    _MAIL_MEMBERS,
    _PHOTO_MEMBERS,
    _SIDECAR_0001,
    _b3,
    _container,
    _corpus,
    _lint,
    _origin,
    _promote,
)


def _reattest(root: Path, rid: str) -> None:
    rf = paths.record_path(root, rid)
    rf.write_text(reattest_cli.reattest_record(rf, root), encoding="utf-8")


def _roster(root: Path, rid: str) -> list[str]:
    return list(sidecar.container_roster(records.load(paths.record_path(root, rid))))


@pytest.fixture
def photo_pre(tmp_path):
    """A container attested BEFORE its origin was known — the pre-v45 roster shape (the
    sidecars are still rows), exactly what an instance holds until it re-attests."""
    root = _corpus(tmp_path, producer="photo")
    cid = _container(tmp_path, root, _PHOTO_MEMBERS, "photo-export")
    return root, cid


@pytest.fixture
def photo(photo_pre):
    root, cid = photo_pre
    _reattest(root, cid)
    return root, cid


# ---------- the roster ---------- #


def test_pre_v45_roster_is_linted_and_reattest_drops_the_sidecar_rows(photo_pre):
    root, cid = photo_pre
    assert "IMG_0001.HEIC.json" in _roster(root, cid)
    assert "sidecar-member-rostered" in _lint(root, cid)

    _reattest(root, cid)
    roster = _roster(root, cid)
    assert "IMG_0001.HEIC.json" not in roster
    assert "IMG_0002.HEIC.json" not in roster
    # every frame and every non-sidecar member stays a row
    assert set(roster) == {
        "IMG_0001.HEIC",
        "IMG_0001_edited.jpeg",
        "IMG_0001.mov",
        "IMG_0002.HEIC",
        "notes.txt",
    }
    assert "sidecar-member-rostered" not in _lint(root, cid)
    # archive facts stay physical: the container still holds seven files
    post = records.load(paths.record_path(root, cid))
    assert (records.artifact_block(post) or {})["fields"]["member_count"] == 7
    # idempotent: a second re-attest changes nothing
    rf = paths.record_path(root, cid)
    assert reattest_cli.reattest_record(rf, root) == rf.read_text(encoding="utf-8")


def test_an_unpaired_json_stays_an_ordinary_member(tmp_path):
    root = _corpus(tmp_path, producer="photo")
    members = {**_PHOTO_MEMBERS, "IMG_0009.HEIC.json": b'{"uuid": "orphan"}'}
    cid = _container(tmp_path, root, members, "photo-export")
    _reattest(root, cid)
    assert "IMG_0009.HEIC.json" in _roster(root, cid)  # its frame is not in this container
    out = resolver.resolve(f"corpus://{cid}?path=IMG_0009.HEIC.json", root)
    assert json.loads(out.read_text("utf-8")) == {"uuid": "orphan"}


def test_mail_shape_export_level_file_stays_a_member(tmp_path):
    root = _corpus(tmp_path, producer="mail")
    cid = _container(tmp_path, root, _MAIL_MEMBERS, "mail-export")
    _reattest(root, cid)
    assert set(_roster(root, cid)) == {"abc.eml", "labels.json"}


# ---------- no address of its own ---------- #


@pytest.mark.parametrize("fixture", ["photo_pre", "photo"])
def test_sidecar_path_is_refused_naming_the_frame(fixture, request):
    root, cid = request.getfixturevalue(fixture)
    with pytest.raises(ValueError, match=r"is the sidecar of path=IMG_0001\.HEIC") as exc:
        resolver.resolve(f"corpus://{cid}?path=IMG_0001.HEIC.json", root)
    assert f"corpus://{cid}?path=IMG_0001.HEIC&sidecar" in str(exc.value)


def test_promote_of_a_sidecar_is_refused_after_the_row_is_gone(photo):
    root, cid = photo
    with pytest.raises(SystemExit, match=r"is the sidecar of member 'IMG_0001\.HEIC'"):
        _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC.json")


# ---------- read through the frame ---------- #


def test_sidecar_reading_is_the_bytes_verbatim(photo):
    root, cid = photo
    out = resolver.resolve(f"corpus://{cid}?path=IMG_0001.HEIC&sidecar", root)
    assert out.read_bytes() == _PHOTO_MEMBERS["IMG_0001.HEIC.json"]
    meta = json.loads(furi.cache_sidecar_path(out).read_text("utf-8"))
    assert meta["mime"] == "application/json"
    assert meta["engine"] == resolver.SIDECAR_ENGINE_VERSION == "sidecar@1"
    # cached under the canonical URI: a repeat resolve is the same file
    assert resolver.resolve(f"corpus://{cid}?path=IMG_0001.HEIC&sidecar", root) == out


def test_sidecar_reading_on_a_promoted_frame_routes_through_its_container(photo):
    root, cid = photo
    assert _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC") == 0
    pid = _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"])
    out = resolver.resolve(f"corpus://{pid}?sidecar", root)
    assert out.read_bytes() == _PHOTO_MEMBERS["IMG_0001.HEIC.json"]


@pytest.mark.parametrize("member", ["IMG_0001_edited.jpeg", "notes.txt"])
def test_a_frame_without_a_sidecar_says_so(photo, member):
    root, cid = photo
    with pytest.raises(ValueError, match="has no sidecar in this container"):
        resolver.resolve(f"corpus://{cid}?path={member}&sidecar", root)


@pytest.mark.parametrize(
    ("params", "match"),
    [
        ("sidecar", "terminal reading of ONE container member"),
        ("path=IMG_0001.HEIC&sidecar&fit=llm", "terminal reading of ONE container member"),
        ("path=IMG_0001.HEIC&sidecar=x", "flag-style"),
        ("path=IMG_0001.HEIC.json&sidecar", r"is the sidecar of path=IMG_0001\.HEIC"),
    ],
)
def test_sidecar_reading_shape_errors(photo, params, match):
    root, cid = photo
    with pytest.raises(ValueError, match=match):
        resolver.resolve(f"corpus://{cid}?{params}", root)


def test_a_container_declaring_nothing_has_no_sidecar_reading(tmp_path):
    root = _corpus(tmp_path, producer="photo")
    cid = _container(tmp_path, root, _PHOTO_MEMBERS, "unrelated-export")
    with pytest.raises(ValueError, match="declares no `sidecar:`"):
        resolver.resolve(f"corpus://{cid}?path=IMG_0001.HEIC&sidecar", root)
    # ... and its .json members stay ordinary, addressable members
    out = resolver.resolve(f"corpus://{cid}?path=IMG_0001.HEIC.json", root)
    assert json.loads(out.read_text("utf-8"))["uuid"] == "0001-UUID"


def test_sidecar_is_a_reading_class_op_an_anchor_may_end_with():
    assert transforms_mod.op_class("sidecar") == transforms_mod.OP_CLASS_READING
    assert transforms_mod.anchor_class_defects([("path", "x.HEIC"), ("sidecar", None)]) == []
    assert resolver.engine_version_for_param("sidecar") == "sidecar@1"


def test_ledger_verifies_a_quote_through_the_frame(photo):
    """The remap target for the pilot's `path=<frame>.json` anchors: the same quote, found
    in the same bytes, through the frame's address."""
    from ledger import verify as ledger_verify

    root, cid = photo
    uri = f"corpus://{cid}?path=IMG_0001.HEIC&sidecar"
    params = [(k, v or "") for k, v in furi.parse(uri).params]
    ok, text, reason, pins = ledger_verify._derived_resolution(
        root, uri, "application/zip", params, {}
    )
    assert ok, reason
    assert '"date_original": "2026-07-11T23:04:28.312000-06:00"' in text
    assert pins.get("path") == "archive-path@2"


# ---------- the members descriptor carries the projection ---------- #


def test_members_descriptor_carries_what_promote_lifts(photo):
    root, cid = photo
    out = resolver.resolve(f"corpus://{cid}?members", root)
    payload = json.loads(out.read_text("utf-8"))
    by_addr = {m["address"]: m for m in payload["members"]}
    assert "path=IMG_0001.HEIC.json" not in by_addr
    frame = by_addr["path=IMG_0001.HEIC"]
    assert frame["px_uuid"] == "0001-UUID"
    assert frame["px_taken"] == _SIDECAR_0001["date_original"]
    assert frame["px_persons"] == ["Alice"]
    assert frame["px_edited"] == "path=IMG_0001_edited.jpeg"
    # a member with no sidecar carries no projection
    assert not any(k.startswith("px_") for k in by_addr["path=notes.txt"])
    assert json.loads(furi.cache_sidecar_path(out).read_text("utf-8"))["engine"] == "members@2"

    # one projection: the promoted record's lift is the same field set, same values
    assert _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC") == 0
    lifted = {
        k: v
        for k, v in _origin(root, _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"]))["fields"].items()
        if k.startswith("px_")
    }
    assert lifted == {k: v for k, v in frame.items() if k.startswith("px_")}


def test_promote_and_reattest_still_lift_with_the_sidecar_off_the_roster(photo):
    root, cid = photo
    assert _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC") == 0
    pid = _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"])  # real image bytes, so it re-attests
    assert _origin(root, pid)["fields"]["px_uuid"] == "0001-UUID"
    rf = paths.record_path(root, pid)
    before = rf.read_text(encoding="utf-8")
    assert reattest_cli.reattest_record(rf, root) == before  # physical pairing, idempotent


def test_inspect_names_the_sidecar_reading(photo, capsys):
    root, cid = photo
    inspect_cli._print_resolver_ops(root, records.load(paths.record_path(root, cid)))
    out = capsys.readouterr().out
    assert "path=<frame>&sidecar -> json" in out
    assert "[engine: sidecar@1] [reading]" in out


# ---------- the engine, directly ---------- #


def _decl(template: str = "{member}.json") -> sidecar.Declaration:
    return sidecar.parse_declaration({"pairing": {"template": template}}, source_id="t")


def test_consumed_pairs_only_present_frames_and_never_chains():
    d = _decl()
    assert d.consumed(["a.HEIC", "a.HEIC.json", "b.HEIC.json", "c.txt"]) == {
        "a.HEIC.json": "a.HEIC"
    }
    # x → x.json → x.json.json: only the chain's head is a frame
    assert d.consumed(["x", "x.json", "x.json.json"]) == {"x.json": "x"}


def test_drop_consumed_rows_keeps_other_positions_of_a_deduplicated_row():
    d = _decl()
    embeds = [
        {"address": "path=a.HEIC", "transport": "blake3:aa", "media_type": "image/heic"},
        {
            "address": ["path=a.HEIC.json", "path=copy.json"],
            "transport": "blake3:bb",
            "media_type": "application/json",
        },
        {"address": "path=b.HEIC", "transport": "blake3:cc", "media_type": "image/heic"},
        {"address": "path=b.HEIC.json", "transport": "blake3:dd", "media_type": "application/json"},
    ]
    kept, consumed = sidecar.drop_consumed_rows(embeds, d)
    assert consumed == {"a.HEIC.json": "a.HEIC", "b.HEIC.json": "b.HEIC"}
    assert [r["address"] for r in kept] == ["path=a.HEIC", "path=copy.json", "path=b.HEIC"]


def test_physical_pairing_reads_a_tar_container_too(tmp_path):
    t = tmp_path / "x.tar"
    with tarfile.open(t, "w") as tf:
        for name, data in {"a.HEIC": b"frame", "a.HEIC.json": b'{"k": 1}'}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    d = _decl()
    assert sidecar.read_paired_sidecar(d, t, "application/x-tar", "a.HEIC") == (
        "a.HEIC.json",
        {"k": 1},
    )
    assert sidecar.read_paired_sidecar(d, t, "application/x-tar", "b.HEIC") is None


def test_a_missing_zip_member_is_member_missing_and_still_a_value_error(tmp_path):
    from corpus.ziparchive import MemberMissing, resolve_member

    z = tmp_path / "x.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a.txt", b"a")
    with pytest.raises(MemberMissing):
        resolve_member(z, "nope.txt")
    assert issubclass(MemberMissing, ValueError)


def test_promote_cli_json_names_the_through_frame_address(photo, capsys):
    root, cid = photo
    from corpus._cli import promote as promote_cli

    rc = promote_cli.run(
        argparse.Namespace(
            uri=f"corpus://{cid}?path=IMG_0001.HEIC", json=True, corpus_root=str(root)
        )
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["sidecar"] == "path=IMG_0001.HEIC&sidecar"
    assert out["sidecar_file"] == "IMG_0001.HEIC.json"


def test_reattest_origin_filter_selects_the_migration_set(photo_pre, tmp_path, capsys):
    """`corpus reattest --origin <overlay-id>` — the selector the v45 migration needs: a
    uri-less producer-declared origin that `--host` cannot reach."""
    root, cid = photo_pre
    other = _container(tmp_path, root, {"a.txt": b"a\n"}, "unrelated-export")
    capsys.readouterr()  # drop the fixture's ingest chatter

    def run(origin: str) -> str:
        ns = argparse.Namespace(
            target=None,
            mime="application/zip",
            host=None,
            origin=origin,
            state="any",
            dry_run=True,
            fingerprint=None,
            messages=None,
            corpus_root=str(root),
        )
        assert reattest_cli.run(ns) == 0
        return capsys.readouterr().out

    out = run("photo-export")
    assert f"records/{cid[:2]}/{cid}.md" in out and other not in out
    assert "would re-attest 1 record(s); 1 changed" in out
    assert "would re-attest 0 record(s)" in run("photo-export/item")  # the container is bare
    assert "would re-attest 1 record(s); 0 changed, 1 unchanged" in run("unrelated-export")


def test_ledger_verifies_a_quote_through_a_promoted_frame(photo):
    """`corpus://<promoted frame>?sidecar` — the bare form on the frame's own record — is a
    record-level reading no mime pipeline lists; verify still attempts it, and pins it."""
    from ledger import verify as ledger_verify

    root, cid = photo
    assert _promote(root, f"corpus://{cid}?path=IMG_0001.HEIC") == 0
    pid = _b3(_PHOTO_MEMBERS["IMG_0001.HEIC"])
    uri = f"corpus://{pid}?sidecar"
    ok, text, reason, pins = ledger_verify._derived_resolution(
        root, uri, "image/png", [("sidecar", "")], {}
    )
    assert ok, reason
    assert '"uuid": "0001-UUID"' in text
    assert pins == {"sidecar": "sidecar@1"}
