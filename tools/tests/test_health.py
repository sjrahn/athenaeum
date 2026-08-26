"""Offline health signals + the `corpus health` CLI.

Builds a small fixture corpus spanning the derived-state layers (spec §4.1 — proxy /
rendered / formed, plus derived-editorial coverage, §4.2.3), an open issue, a missing
artifact, a structurally-invalid record, and a stray legacy `status:` key. Asserts each
signal surfaces the right records. No network.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import frontmatter

from corpus import config as config_mod
from corpus import hashing, health, locationindex, paths, records, segments, touches
from corpus._cli import dispatch
from corpus._cli import location as location_cli

A = "a0" * 32  # proxy, UNTITLED (no title candidate anywhere), missing artifact, legacy `status:`
B = "b0" * 32  # rendered (stored content, no form), titled (frontmatter override), has its pdf
C = "c0" * 32  # formed, titled via the artifact layer (text/html's packaged `role: title`)
D = "d0" * 32  # formed, titled (frontmatter override), open warning issue
E = "e0" * 32  # no origin block (invalid), titled via the artifact layer (text/html)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _write(
    root: Path,
    rid: str,
    *,
    mime: str,
    title: str = "",
    description: str = "",
    origin: bool = True,
    ext: str | None = None,
    artifact: bool = False,
    artifact_title: bool = True,
    issue: dict | None = None,
    content_blocks: list | None = None,
    legacy_status: str | None = None,
) -> None:
    fm = records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    if title:
        fm["title"] = title
    if description:
        fm["description"] = description
    post = frontmatter.Post(content="", **fm)
    artifact_fields = {"title": rid[:4]} if artifact_title else {}
    records.set_artifact_block(post, mime=mime, fields=artifact_fields)
    if origin:
        records.append_origin_block(
            post, uri=f"https://e.com/{rid[:4]}", snapshot="2026-05-31T00:00:00Z"
        )
    if content_blocks:
        post.content = segments.emit(content_blocks)
    if issue:
        records.append_issue_block(
            post,
            id=issue["id"],
            severity=issue["severity"],
            resolution=issue.get("resolution", "open"),
            detector=issue["detector"],
            address=issue.get("address"),
        )
    record_path = paths.record_path(root, rid)
    records.dump(post, record_path)
    if legacy_status:
        # `dumps()` never emits `status:` (spec §4.1) — even from an in-memory Post that
        # carries one — so simulating a pre-3.1 record that missed the migration sweep
        # means patching the written frontmatter text directly, after the fact.
        text = record_path.read_text(encoding="utf-8")
        record_path.write_text(
            text.replace("\n---\n", f"\nstatus: {legacy_status}\n---\n", 1),
            encoding="utf-8",
        )
    if artifact and ext:
        art = paths.artifact_path(root, rid, ext)
        paths.ensure_parent(art)
        art.write_bytes(b"\x89PNG\r\n\x1a\n")


def _populate(tmp_path: Path) -> Path:
    root = _corpus(tmp_path)
    # No artifact title candidate, no origin, no override → genuinely untitled (spec §4.2.3).
    # `application/octet-stream` carries no packaged mime schema — genuinely proxy, not
    # terminal (unlike `image/png`, which gained a `form: {id: passthrough}` mime default
    # in 3.3 — see `test_terminal_forms.py` for that behavior; this fixture predates and is
    # orthogonal to it).
    _write(root, A, mime="application/octet-stream", artifact_title=False, legacy_status="stub")
    _write(
        root, B, mime="application/pdf", ext="pdf", artifact=True,
        title="A Bulletin", description="A rendered bulletin with no governing form.",
        content_blocks=[segments.Segment(atom="text", address="page=1", body="hello")],
    )
    _write(
        root, C, mime="text/html", ext="html", artifact=True,
        content_blocks=[
            segments.Section(
                form="conversation",
                segments=[segments.Segment(atom="text", address="turn=1", body="hi")],
            )
        ],
    )
    _write(
        root, D, mime="image/png", ext="png", artifact=True,
        title="A Photo", description="A described, formed photo record.",
        content_blocks=[
            segments.Section(
                form="conversation",
                segments=[segments.Segment(atom="text", address="turn=1", body="hi")],
            )
        ],
        issue={
            "id": "format-loss",
            "severity": "warning",
            "detector": "corpus.draft.image@0.1.0",
            "address": "bbox=0,0,1,1",
        },
    )
    _write(root, E, mime="text/html", ext="html", artifact=True, origin=False)
    return root


def _ids(items: list[dict]) -> set[str]:
    return {i["id"] for i in items}


def test_layer_presence(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    counts = health.layer_presence(refs, root)
    assert counts["proxy"] == 2  # A, E
    assert counts["rendered"] == 1  # B
    assert counts["formed"] == 2  # C, D
    # B, D carry a frontmatter override; C, E derive a title via the artifact layer
    # (text/html's packaged `role: title` mark on its bare `title` field, §12.21 step 2);
    # A has no title candidate anywhere — genuinely untitled (spec §4.2.3).
    assert counts["titled"] == 4  # B, C, D, E
    assert counts["untitled"] == 1  # A
    assert counts["legacy_status"] == 1  # A only


def test_unshaped(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    items = health.unshaped(refs, root)
    assert _ids(items) == {A, E}
    # Neither A nor E has an origin overlay declaring a form, so neither is shapable.
    assert all(i["shapable"] is False for i in items)


def test_unresolved_issues_grouped(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    groups = health.unresolved_issues(refs)
    assert "warning" in groups
    assert {e["id"] for e in groups["warning"]} == {D}


def test_missing_artifacts(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    items = health.missing_artifacts(refs, root)
    assert A in _ids(items)  # no artifact
    assert B not in _ids(items)  # has its pdf


def test_validity_violations_no_origin(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    items = health.validity_violations(refs, root)
    by_id = {i["id"]: i for i in items}
    assert E in by_id
    assert any("origin" in p for p in by_id[E]["problems"])


# ---------- undescribed / sparse_body / stale_model_touches ---------- #


def test_undescribed_scoped_to_content_bearing_records(tmp_path):
    """Only C is flagged: A and E have stored no rendering (proxy, spec §4.1) — an empty
    description there is the honest, expected answer, not a defect. B and D both carry a
    frontmatter description override. C is formed (a real rendering) but never earns a
    description candidate on any layer."""
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    items = health.undescribed(refs, root)
    assert _ids(items) == {C}


def _pdf_with_pages(root: Path, rid: str, *, page_count: int, body_text: str) -> None:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="application/pdf", fields={"page_count": page_count})
    records.append_origin_block(
        post, uri=f"https://e.com/{rid[:4]}", snapshot="2026-08-01T00:00:00Z"
    )
    post.content = segments.emit([segments.Segment(atom="text", address="page=1", body=body_text)])
    records.dump(post, paths.record_path(root, rid))


def test_sparse_body_flags_low_density_paginated_record(tmp_path):
    root = _corpus(tmp_path)
    sparse, dense = "11" * 32, "12" * 32
    _pdf_with_pages(root, sparse, page_count=10, body_text="short")
    _pdf_with_pages(root, dense, page_count=10, body_text="x" * 4000)

    refs = health.load_all_records(root)
    items = health.sparse_body(refs, root)
    assert _ids(items) == {sparse}
    assert items[0]["page_count"] == 10


def test_sparse_body_skips_records_with_no_page_count_field(tmp_path):
    """Generalizes past the reference's PDF-only gate to any mime carrying an artifact
    `page_count` — but a mime that never populates one (plain text/html, image/png in this
    fixture) simply never enters the signal; no threshold is invented for it."""
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    assert health.sparse_body(refs, root) == []


def _compile_model_touch(root: Path, rid: str, *, model: str, repeat: int = 1) -> None:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="application/pdf")
    touch_id = f"{touches.script_identifier('compile')}+{model}"
    for _ in range(repeat):
        touches.record_touch(post, touch_id)
    records.dump(post, paths.record_path(root, rid))


def test_stale_model_touches_unconfigured_reports_distinctly_from_zero_findings(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    report = health.stale_model_touches(refs, root, preferred_models=[])
    assert report == {"configured": False, "items": []}


def test_stale_model_touches_flags_off_allowlist_and_skips_unmodeled(tmp_path):
    root = _corpus(tmp_path)
    current, stale, unmodeled = "cc" * 32, "dd" * 32, "ee" * 32
    _compile_model_touch(root, current, model="claude-opus-4-7[1m]")
    _compile_model_touch(root, stale, model="claude-opus-3-5")
    # No model touch at all (deterministic-only pass) — silently excluded, regardless
    # of what's configured; this is `unshaped`'s population, not this signal's.
    post = frontmatter.Post(
        content="",
        **records.stub_frontmatter(record_id=unmodeled, touch_id="corpus.ingest@0.1.0"),
    )
    records.set_artifact_block(post, mime="application/pdf")
    records.dump(post, paths.record_path(root, unmodeled))

    refs = health.load_all_records(root)
    report = health.stale_model_touches(refs, root, preferred_models=["claude-opus-4-7[1m]"])
    assert report["configured"] is True
    assert _ids(report["items"]) == {stale}
    assert report["items"][0]["last_model_touch"] == "claude-opus-3-5"


def test_stale_model_touches_strips_coalesced_count_suffix(tmp_path):
    """`touches.record_touch` appends a `_<count>` suffix to the WHOLE entry — model
    included — when the same compile+model touch repeats back-to-back; the model
    extraction must see through that to compare the bare model id."""
    root = _corpus(tmp_path)
    rid = "ff" * 32
    _compile_model_touch(root, rid, model="claude-opus-3-5", repeat=2)

    refs = health.load_all_records(root)
    (ref,) = refs
    assert touches.touch_list(ref.post)[-1].endswith("_2")
    report = health.stale_model_touches(refs, root, preferred_models=["claude-opus-4-7[1m]"])
    (item,) = report["items"]
    assert item["last_model_touch"] == "claude-opus-3-5"


def test_undescribed_sparse_body_stale_model_touches_cli_summary(tmp_path, capsys):
    root = _populate(tmp_path)
    rc = dispatch(
        [
            "health", "--summary",
            "--filter", "undescribed,sparse_body,stale_model_touches",
            "--corpus-root", str(root),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "undescribed: 1 " in out
    assert "sparse_body: 0 " in out
    assert "stale_model_touches: unconfigured" in out


# ---------- dangling origin refs ---------- #

LIVE = "10" * 32  # a real container record — the resolvable target
DEAD = "20" * 32  # a hash cited by origin blocks below that owns no record
WARN_ID = "30" * 32  # ONE origin block, citing DEAD — latest (and only) block is dangling
INFO_ID = "40" * 32  # TWO origin blocks — DEAD (superseded), then LIVE (latest)


def _bare_record(root: Path, rid: str, *, mime: str = "application/json") -> frontmatter.Post:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.promote@0.1.0")
    )
    records.set_artifact_block(post, mime=mime)
    return post


def _populate_dangling(tmp_path: Path) -> Path:
    root = _corpus(tmp_path)

    live_post = _bare_record(root, LIVE, mime="application/gzip")
    records.append_origin_block(
        live_post, uri="https://example.com/live.tgz", snapshot="2026-07-01T00:00:00Z"
    )
    records.dump(live_post, paths.record_path(root, LIVE))

    warn_post = _bare_record(root, WARN_ID)
    records.append_origin_block(
        warn_post,
        uri=f"corpus://{DEAD}?path=Takeout/dead.json",
        snapshot="2026-07-04T00:00:00Z",
    )
    records.dump(warn_post, paths.record_path(root, WARN_ID))

    info_post = _bare_record(root, INFO_ID)
    records.append_origin_block(
        info_post,
        uri=f"corpus://{DEAD}?path=Takeout/dead.json",
        snapshot="2026-07-04T00:00:00Z",
    )
    records.append_origin_block(
        info_post,
        uri=f"corpus://{LIVE}?path=Takeout/live.json",
        snapshot="2026-07-06T00:00:00Z",
    )
    records.dump(info_post, paths.record_path(root, INFO_ID))

    return root


def test_dangling_origin_refs_severity_by_block_position(tmp_path):
    root = _populate_dangling(tmp_path)
    refs = health.load_all_records(root)
    groups = health.dangling_origin_refs(refs, root)

    assert {e["id"] for e in groups.get("warning", [])} == {WARN_ID}
    assert {e["id"] for e in groups.get("info", [])} == {INFO_ID}
    # LIVE itself cites no corpus:// origin uri, so it is dangling-free.
    assert WARN_ID not in {e["id"] for e in groups.get("info", [])}
    assert INFO_ID not in {e["id"] for e in groups.get("warning", [])}

    warn_entry = groups["warning"][0]
    assert warn_entry["dead_hash"] == DEAD
    assert warn_entry["latest"] is True
    assert warn_entry["block_index"] == 0

    info_entry = groups["info"][0]
    assert info_entry["dead_hash"] == DEAD
    assert info_entry["latest"] is False
    assert info_entry["block_index"] == 0


def test_dangling_origin_refs_cli_summary(tmp_path, capsys):
    root = _populate_dangling(tmp_path)
    rc = dispatch(
        ["health", "--summary", "--filter", "dangling_origin_refs", "--corpus-root", str(root)]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "dangling_origin_refs: 2" in out


# ---------- shadowed copies (adoption dedup/reclaim signal, spec §12.1.1 v23) ---------- #


def _promote_location(root: Path, name: str, relpath: str) -> int:
    return location_cli.run(
        argparse.Namespace(
            action="promote",
            name=name,
            relpath=relpath,
            all_matching=None,
            source_urls=[],
            corpus_root=str(root),
        )
    )


def _adopt_location(root: Path, name: str, dest: str, relpath: str) -> int:
    return location_cli.run(
        argparse.Namespace(
            action="adopt",
            name=name,
            dest=dest,
            relpath=relpath,
            reclaim=False,
            corpus_root=str(root),
        )
    )


def test_shadowed_copies_signal(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    shadowed_file = tree / "shadowed.json"
    shadowed_file.write_bytes(b'{"case": "shadowed"}\n')
    solo_file = tree / "solo.json"
    solo_file.write_bytes(b'{"case": "attached only"}\n')

    (root / "corpus.toml").write_text(
        f"""
[[corpus.location]]
name = "loc"
kind = "attached"
path = "{tree}"
""",
        "utf-8",
    )
    attached = config_mod.load_config(root).locations[0]
    locationindex.attest_location(root, attached)

    assert _promote_location(root, "loc", "shadowed.json") == 0
    assert _promote_location(root, "loc", "solo.json") == 0

    bulk = tmp_path / "bulk"
    existing = (root / "corpus.toml").read_text("utf-8")
    existing += f"""
[[corpus.location]]
name = "bulk"
kind = "store"
path = "{bulk}"
"""
    (root / "corpus.toml").write_text(existing, "utf-8")

    # Only `shadowed.json` gets adopted — `solo.json` stays attached-only.
    assert _adopt_location(root, "loc", "bulk", "shadowed.json") == 0

    rid_shadowed = hashing.hash_file(shadowed_file, also=())["blake3"]
    rid_solo = hashing.hash_file(solo_file, also=())["blake3"]

    refs = health.load_all_records(root)
    items = health.shadowed_copies(refs, root)
    by_id = {i["id"]: i for i in items}

    assert rid_shadowed in by_id
    assert rid_solo not in by_id  # attached-only, nothing shadowing it
    entry = by_id[rid_shadowed]
    assert entry["store_location"] == "bulk"
    assert entry["attached_rows"] == [{"location": "loc", "relpath": "shadowed.json"}]


def test_shadowed_copies_excludes_stale_attached_rows(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"case": "will go stale after adoption"}\n')

    (root / "corpus.toml").write_text(
        f"""
[[corpus.location]]
name = "loc"
kind = "attached"
path = "{tree}"
""",
        "utf-8",
    )
    attached = config_mod.load_config(root).locations[0]
    locationindex.attest_location(root, attached)
    assert _promote_location(root, "loc", "a.json") == 0

    bulk = tmp_path / "bulk"
    existing = (root / "corpus.toml").read_text("utf-8")
    existing += f"""
[[corpus.location]]
name = "bulk"
kind = "store"
path = "{bulk}"
"""
    (root / "corpus.toml").write_text(existing, "utf-8")
    assert _adopt_location(root, "loc", "bulk", "a.json") == 0

    # Mutate the attached original after adoption without re-attesting: its row is
    # now stale and must drop out of the signal (a stale row resolves nowhere).
    f.write_bytes(b'{"case": "mutated post-adoption, not re-attested"}\n')

    refs = health.load_all_records(root)
    items = health.shadowed_copies(refs, root)
    assert items == []


def test_shadowed_copies_cli_summary(tmp_path, capsys):
    root = _populate(tmp_path)
    rc = dispatch(
        ["health", "--summary", "--filter", "shadowed_copies", "--corpus-root", str(root)]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "shadowed_copies: 0 record(s)" in out


# ---------- duplicate residencies (pure attached-side dedup, spec §12.1.1 v24) ---------- #


def test_duplicate_residencies_two_attached_copies_surface(tmp_path):
    root = _corpus(tmp_path)
    tree1 = tmp_path / "tree1"
    tree2 = tmp_path / "tree2"
    tree1.mkdir()
    tree2.mkdir()
    data = b"identical bytes, two attached homes"
    (tree1 / "a.bin").write_bytes(data)
    (tree2 / "b.bin").write_bytes(data)

    (root / "corpus.toml").write_text(
        f"""
[[corpus.location]]
name = "loc1"
kind = "attached"
path = "{tree1}"

[[corpus.location]]
name = "loc2"
kind = "attached"
path = "{tree2}"
""",
        "utf-8",
    )
    cfg = config_mod.load_config(root)
    for loc in cfg.locations:
        locationindex.attest_location(root, loc)

    rid = hashing.hash_file(tree1 / "a.bin", also=())["blake3"]

    refs = health.load_all_records(root)
    items = health.duplicate_residencies(refs, root)
    assert len(items) == 1
    entry = items[0]
    assert entry["hash"] == rid
    assert entry["record"] is None  # never promoted
    assert sorted(
        (r["location"], r["relpath"]) for r in entry["residencies"]
    ) == [("loc1", "a.bin"), ("loc2", "b.bin")]


def test_duplicate_residencies_single_copy_does_not_surface(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "solo.bin").write_bytes(b"only one home")
    (root / "corpus.toml").write_text(
        f"""
[[corpus.location]]
name = "loc"
kind = "attached"
path = "{tree}"
""",
        "utf-8",
    )
    loc = config_mod.load_config(root).locations[0]
    locationindex.attest_location(root, loc)

    refs = health.load_all_records(root)
    assert health.duplicate_residencies(refs, root) == []


def test_duplicate_residencies_cli_summary(tmp_path, capsys):
    root = _populate(tmp_path)
    rc = dispatch(
        ["health", "--summary", "--filter", "duplicate_residencies", "--corpus-root", str(root)]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "duplicate_residencies: 0 hash(es)" in out


# ---------- CLI ---------- #


def test_health_cli_json(tmp_path, capsys):
    root = _populate(tmp_path)
    rc = dispatch(["health", "--corpus-root", str(root)])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["total_records"] == 5
    assert "layer_presence" in report


def test_health_cli_summary_and_filter(tmp_path, capsys):
    root = _populate(tmp_path)
    rc = dispatch(
        ["health", "--summary", "--filter", "layer_presence,unshaped",
         "--corpus-root", str(root)]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "corpus health — 5 record(s)" in out
    assert "unshaped:" in out


def _write_group_record(
    root: Path, rid: str, *, filename: str, media_type: str, ext: str, payload: bytes
) -> Path:
    """A minimal ingested-looking record carrying an origin `filename:` (the join key
    `prefix_duplicate_artifacts` groups candidates on) plus its artifact bytes on disk."""
    fm = records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    post = frontmatter.Post(content="", **fm)
    records.set_artifact_block(post, mime=media_type, fields={})
    records.append_origin_block(
        post, uri=None, snapshot="2026-07-31T00:00:00Z", fields={"filename": filename}
    )
    records.dump(post, paths.record_path(root, rid))
    art = paths.artifact_path(root, rid, ext)
    paths.ensure_parent(art)
    art.write_bytes(payload)
    return art


def _index_bytes(root: Path, rid: str, path: Path, recipes) -> None:
    """Compute + upsert real hash-index rows for `path` under `rid` — the same rows
    ingest/reattest would write (spec §12.9.1), so the fixtures exercise the real
    screen/confirm logic rather than hand-typed hex."""
    from corpus import hashindex
    from corpus import hashing as hashing_mod

    values = hashing_mod.compute_hashes(path, recipes)
    rows = [
        hashindex.HashRow(record_id=rid, recipe=v.recipe, algo=v.tag, value=v.hex, param=v.param)
        for v in values
    ]
    with hashindex.open_index(root) as conn:
        hashindex.upsert_rows(conn, rows)


def test_prefix_duplicate_artifacts_confirmed_prefix(tmp_path):
    """A record whose bytes are an exact byte-prefix of another's, same origin filename —
    the grown-export case (#147) — is screened via the `blake3-prefix-ladder` index rows and
    confirmed via bounded streaming, never a whole-group `read_bytes()` (spec §7.9, §12.9.1).
    A third same-name record is deliberately left unindexed to exercise that reporting
    alongside a real confirmed pair — it must be excluded from screening entirely, not
    silently read around."""
    from corpus import hashing as hashing_mod

    root = _corpus(tmp_path)
    rid_a, rid_b, rid_other = "f0" * 32, "f1" * 32, "f2" * 32
    base = b"<html>" + b"x" * 5000 + b"</html>"
    grown = base + b"<p>more</p>"
    other = b"<html>unrelated</html>"

    path_a = _write_group_record(
        root, rid_a, filename="window.html", media_type="text/html", ext="html", payload=base
    )
    path_b = _write_group_record(
        root, rid_b, filename="window.html", media_type="text/html", ext="html", payload=grown
    )
    _write_group_record(
        root, rid_other, filename="window.html", media_type="text/html", ext="html",
        payload=other,
    )
    _index_bytes(root, rid_a, path_a, hashing_mod.DEFAULT_SET)
    _index_bytes(root, rid_b, path_b, hashing_mod.DEFAULT_SET)

    refs = health.load_all_records(root)
    report = health.prefix_duplicate_artifacts(refs, root)
    assert report["groups_scanned"] == 1
    assert report["total_pairs"] == 1
    (pair,) = report["pairs"]
    assert pair["kind"] == "prefix"
    assert pair["shorter"] == rid_a
    assert pair["longer"] == rid_b
    assert report["unindexed_count"] == 1
    assert report["unindexed_ids"] == [rid_other]


def test_prefix_duplicate_artifacts_rung_match_rejected_by_confirm(tmp_path):
    """A rung match is a SCREEN, not a proof (spec §7.9): two files sharing an identical
    first 4 KiB (so their `blake3-4k` rung agrees) but diverging immediately after — well
    within the shorter file's own length — must pass the index screen (only rung reached by
    both is checked) and then be REJECTED by the streaming confirm, never reported as a
    pair."""
    from corpus import hashing as hashing_mod

    root = _corpus(tmp_path)
    rid_a, rid_b = "a1" * 32, "a2" * 32
    shared_head = b"H" * 4096
    a_payload = shared_head + b"A" * 900  # 4996 bytes — reaches the 4k rung, not 64k
    b_payload = shared_head + b"B" * 900 + b"C" * 200  # diverges right after the shared head

    path_a = _write_group_record(
        root, rid_a, filename="dup.bin", media_type="application/octet-stream", ext="bin",
        payload=a_payload,
    )
    path_b = _write_group_record(
        root, rid_b, filename="dup.bin", media_type="application/octet-stream", ext="bin",
        payload=b_payload,
    )
    _index_bytes(root, rid_a, path_a, hashing_mod.DEFAULT_SET)
    _index_bytes(root, rid_b, path_b, hashing_mod.DEFAULT_SET)

    refs = health.load_all_records(root)
    report = health.prefix_duplicate_artifacts(refs, root)
    assert report["groups_scanned"] == 1
    assert report["pairs_compared"] == 1  # the 4k rung screen passed
    assert report["total_pairs"] == 0  # the streaming confirm rejected it
    assert report["pairs"] == []
    assert report["unconfirmed"] == []


def test_prefix_duplicate_artifacts_unconfirmed_missing_local_bytes(tmp_path):
    """A screen-passing candidate whose local bytes are gone (evicted to a remote store,
    §12.9.1's flush/hydrate economics) is reported `unconfirmed` — never read around, and
    never counted as a confirmed pair. Nothing here pulls remote bytes for a health scan."""
    from corpus import hashing as hashing_mod

    root = _corpus(tmp_path)
    rid_a, rid_b = "b1" * 32, "b2" * 32
    payload = b"<html>" + b"z" * 5000 + b"</html>"
    path_a = _write_group_record(
        root, rid_a, filename="w.html", media_type="text/html", ext="html", payload=payload
    )
    path_b = _write_group_record(
        root, rid_b, filename="w.html", media_type="text/html", ext="html", payload=payload
    )
    _index_bytes(root, rid_a, path_a, hashing_mod.DEFAULT_SET)
    _index_bytes(root, rid_b, path_b, hashing_mod.DEFAULT_SET)
    path_b.unlink()  # indexed, but no longer locally resident

    refs = health.load_all_records(root)
    report = health.prefix_duplicate_artifacts(refs, root)
    assert report["pairs_compared"] == 1
    assert report["total_pairs"] == 0
    assert report["unconfirmed_count"] == 1
    (entry,) = report["unconfirmed"]
    assert sorted(entry["ids"]) == sorted([rid_a, rid_b])


def test_prefix_duplicate_artifacts_no_index_file(tmp_path):
    """The fresh-clone case (spec §12.9.1): no `cache/hashes.db` at all → every candidate
    reports unindexed, zero reads, fast — and the read-only scan must not create the index
    file as a side effect."""
    from corpus import hashindex

    root = _corpus(tmp_path)
    rid_a, rid_b = "c1" * 32, "c2" * 32
    payload = b"hello world " * 500
    _write_group_record(
        root, rid_a, filename="dup.bin", media_type="application/octet-stream", ext="bin",
        payload=payload,
    )
    _write_group_record(
        root, rid_b, filename="dup.bin", media_type="application/octet-stream", ext="bin",
        payload=payload,
    )
    assert not hashindex.db_path(root).exists()

    refs = health.load_all_records(root)
    report = health.prefix_duplicate_artifacts(refs, root)
    assert report["groups_scanned"] == 1
    assert report["pairs_compared"] == 0
    assert report["total_pairs"] == 0
    assert report["unindexed_count"] == 2
    assert set(report["unindexed_ids"]) == {rid_a, rid_b}
    assert not hashindex.db_path(root).exists()  # never created by a read-only scan


# ---------- canonical_duplicate_clusters (html-stampfree@1 join) ---------- #


def test_canonical_duplicate_clusters_stampfree_join(tmp_path):
    """Two captures of the byte-identical delivered content, differing only in the
    corpus-injected capture-stamp meta tag, join on `html-stampfree@1` — a pure index join,
    zero artifact reads (spec §7.9, §12.9.1). A third, genuinely different document stays
    out; a fourth is left unindexed to exercise that reporting."""
    from corpus import hashing as hashing_mod

    root = _corpus(tmp_path)
    rid_a, rid_b, rid_c, rid_d = "d1" * 32, "d2" * 32, "d3" * 32, "d4" * 32
    doc_a = (
        b'<html><head><meta name="corpus-origin-period" content="2025-12"></head>'
        b"<body><p>hello</p></body></html>"
    )
    doc_b = (
        b'<html><head><meta name="corpus-origin-period" content="2026-W01"></head>'
        b"<body><p>hello</p></body></html>"
    )
    doc_c = b"<html><head></head><body><p>unrelated</p></body></html>"
    doc_d = b"<html><head></head><body><p>never indexed</p></body></html>"

    path_a = _write_group_record(
        root, rid_a, filename="a.html", media_type="text/html", ext="html", payload=doc_a
    )
    path_b = _write_group_record(
        root, rid_b, filename="b.html", media_type="text/html", ext="html", payload=doc_b
    )
    path_c = _write_group_record(
        root, rid_c, filename="c.html", media_type="text/html", ext="html", payload=doc_c
    )
    _write_group_record(
        root, rid_d, filename="d.html", media_type="text/html", ext="html", payload=doc_d
    )
    _index_bytes(root, rid_a, path_a, (hashing_mod.HTML_STAMPFREE_1,))
    _index_bytes(root, rid_b, path_b, (hashing_mod.HTML_STAMPFREE_1,))
    _index_bytes(root, rid_c, path_c, (hashing_mod.HTML_STAMPFREE_1,))
    # rid_d deliberately left unindexed

    refs = health.load_all_records(root)
    report = health.canonical_duplicate_clusters(refs, root)
    assert report["total_clusters"] == 1
    (cluster,) = report["clusters"]
    assert sorted(cluster["ids"]) == sorted([rid_a, rid_b])
    assert report["unindexed_count"] == 1
    assert report["unindexed_ids"] == [rid_d]


def test_canonical_duplicate_clusters_no_index_file(tmp_path):
    """No `cache/hashes.db` at all → every `text/html` record reports unindexed, zero reads,
    and the scan does not create the index file."""
    from corpus import hashindex

    root = _corpus(tmp_path)
    rid = "e1" * 32
    _write_group_record(
        root, rid, filename="only.html", media_type="text/html", ext="html",
        payload=b"<html></html>",
    )
    assert not hashindex.db_path(root).exists()

    refs = health.load_all_records(root)
    report = health.canonical_duplicate_clusters(refs, root)
    assert report["total_clusters"] == 0
    assert report["unindexed_count"] == 1
    assert report["unindexed_ids"] == [rid]
    assert not hashindex.db_path(root).exists()
