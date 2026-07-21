"""Mailbox chrome strip (spec §12.3.13), origin-declared: the HeaderStrip filter (folded
continuations, header-zone-only, case-insensitive), the strip ACTION declared on the
producer's origin overlay (namespace-walked) with the mime schema carrying only the
corpus-local `default_origin` BINDING, schema-declared auto-strip at ingest (identity
over stripped bytes + delivered-hash provenance), and `corpus mbox-window` resolving the
same chain — including a pre-strip (label-full) lineage crossed as-if-stripped, the
no-declaration negative control, and the namespace-walk finality rule (a stamped origin's
silence never falls through to the default binding).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import blake3
import yaml

import corpus as corpus_pkg
from corpus import hashing, mboxfile, records, schemas
from corpus._cli import ingest as ingest_cli
from corpus._cli import mbox_window

CRLF = b"\r\n"

STRIP = mboxfile.normalize_strip_headers(["X-Gmail-Labels"])

_PACKAGED_MBOX_SCHEMA = (
    Path(corpus_pkg.__file__).parent
    / "schemas_default/mime/application/application_mbox.yaml"
)


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _sep(i: int) -> bytes:
    return f"From {i}@xxx Mon Jan 01 00:00:00 +0000 2024".encode() + CRLF


def _msg(subject: str, labels: str | None, body: bytes = b"body" + CRLF) -> bytes:
    head = b"From: a@x.com" + CRLF
    if labels is not None:
        head += b"X-Gmail-Labels: " + labels.encode() + CRLF
    head += f"Subject: {subject}".encode() + CRLF
    head += b"Date: Mon, 01 Jan 2024 00:00:00 +0000" + CRLF
    return head + CRLF + body


def _mbox(tmp_path: Path, name: str, *raw_members: bytes) -> Path:
    out = b""
    for i, member in enumerate(raw_members, start=1):
        out += _sep(i) + member
    p = tmp_path / name
    p.write_bytes(out)
    return p


def _stripped(member: bytes) -> bytes:
    """The member with its single-line X-Gmail-Labels header removed (fixture-shaped)."""
    lines = member.split(CRLF)
    return CRLF.join(ln for ln in lines if not ln.startswith(b"X-Gmail-Labels:"))


def _corpus(tmp_path: Path, default_origin: str | None = None) -> Path:
    """A test corpus; with `default_origin`, a corpus-local shadow of the packaged
    application/mbox schema binds `default_origin: <id>` — the whole-file-wins rung
    rule (§3) means the shadow must carry the full packaged content."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    if default_origin:
        _mime_shadow(root, default_origin)
    schemas.cache_clear()
    return root


def _mime_shadow(root: Path, default_origin: str) -> None:
    """(Re)write the corpus-local mbox mime shadow binding `default_origin: <id>` —
    whole-file-wins, so it carries the full packaged text plus the binding."""
    local = root / "schema/mime/application/application_mbox.yaml"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(_PACKAGED_MBOX_SCHEMA.read_text() + f"\ndefault_origin: {default_origin}\n")
    schemas.cache_clear()


def _origin_overlay(root: Path, origin_id: str, strip_headers: list[str] | None) -> None:
    """Write an origin overlay at `origin/<id>.yaml` (nested namespace dirs created as
    needed) declaring `strip_headers` — a list, possibly empty (`[]` = declared off)."""
    path = root / "schema" / "origin" / f"{origin_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["description: test origin overlay"]
    if strip_headers:
        lines.append("strip_headers:")
        lines.extend(f"- {h}" for h in strip_headers)
    else:
        lines.append("strip_headers: []")
    path.write_text("\n".join(lines) + "\n")
    schemas.cache_clear()


def _write_sidecar(source: Path, origin_schema: str) -> None:
    sidecar = source.with_suffix(source.suffix + ".capture.yaml")
    sidecar.write_text(yaml.safe_dump({"origin_schema": origin_schema}))


def _ingest(root: Path, artifact: Path) -> str:
    """Stage + ingest; returns the RESULTING record id (post-canonicalization)."""
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


# ---------- the filter ---------- #


def test_strip_removes_header_and_folded_continuation():
    s = mboxfile.HeaderStrip(STRIP)
    assert s.keep(b"From: a@x.com" + CRLF)
    assert not s.keep(b"X-Gmail-Labels: Inbox," + CRLF)
    assert not s.keep(b" Category Updates,Unread" + CRLF)  # folded continuation goes too
    assert s.keep(b"Subject: hi" + CRLF)
    assert s.dropped == 2


def test_strip_is_case_insensitive_and_header_zone_only():
    s = mboxfile.HeaderStrip(STRIP)
    assert not s.keep(b"x-gmail-labels: Archived" + CRLF)
    assert s.keep(CRLF)  # blank line ends the header zone
    assert s.keep(b"X-Gmail-Labels: in a body line, untouched" + CRLF)
    assert s.dropped == 1


def test_scan_hashes_as_if_stripped(tmp_path):
    labelled = _msg("one", "Inbox,Category Updates,Unread")
    bare = _msg("two", None)
    p = _mbox(tmp_path, "m.mbox", labelled, bare)
    scan = mboxfile.scan(p, None, strip=STRIP)
    assert scan.facts[1].blake3 == _b3(_stripped(labelled))
    assert scan.facts[2].blake3 == _b3(bare)
    assert scan.stripped_members == 1


def test_extract_emits_stripped_members(tmp_path):
    labelled = _msg("one", "Archived,Opened")
    p = _mbox(tmp_path, "m.mbox", labelled)
    out = tmp_path / "out.mbox"
    with out.open("wb") as fh:
        assert mboxfile.extract_raw_members(p, {1}, fh, strip=STRIP) == 1
    data = out.read_bytes()
    assert b"X-Gmail-Labels" not in data
    rescan = mboxfile.scan(out, None)
    assert rescan.facts[1].blake3 == _b3(_stripped(labelled))


# ---------- schema resolution ---------- #


def test_resolve_strip_headers_precedence(tmp_path):
    declared = _corpus(tmp_path / "a", default_origin="google-takeout/gmail")
    _origin_overlay(declared, "google-takeout/gmail", ["X-Gmail-Labels"])
    assert schemas.resolve_strip_headers(declared, "application/mbox") == ["X-Gmail-Labels"]
    # CLI override beats everything, including a declaring binding.
    assert schemas.resolve_strip_headers(declared, "application/mbox", ["X-Other"]) == ["X-Other"]
    bare = _corpus(tmp_path / "b")
    assert schemas.resolve_strip_headers(bare, "application/mbox") == []


def test_resolve_default_origin_binding(tmp_path):
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    assert schemas.resolve_default_origin(root, "application/mbox") == "google-takeout/gmail"
    bare = _corpus(tmp_path / "bare")
    assert schemas.resolve_default_origin(bare, "application/mbox") is None


def test_origin_id_walk_reaches_namespace_ancestor(tmp_path):
    """The stamped id `google-takeout/gmail` has no overlay file of its own — only its
    namespace PARENT `google-takeout` declares `strip_headers` — and the walk still
    finds it (one ancestor hop)."""
    root = _corpus(tmp_path)
    _origin_overlay(root, "google-takeout", ["X-Gmail-Labels"])
    assert schemas.resolve_strip_headers(
        root, "application/mbox", origin_id="google-takeout/gmail"
    ) == ["X-Gmail-Labels"]


def test_origin_id_finality_no_cross_namespace_fallback(tmp_path):
    """A stamped origin in a DIFFERENT namespace with no declaration anywhere on ITS
    walk yields NO strip — even though `default_origin` exists and declares. Finality:
    the default binding is consulted ONLY when no origin id was given at all."""
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _origin_overlay(root, "google-takeout/gmail", ["X-Gmail-Labels"])
    assert schemas.resolve_strip_headers(
        root, "application/mbox", origin_id="imessage-export"
    ) == []


def test_origin_declared_empty_list_is_declared_off(tmp_path):
    """`strip_headers: []` on the stamped overlay is a DECLARATION (off), distinct from
    no overlay declaring at all — both read `[]` through `resolve_strip_headers`, but
    the internal walk distinguishes "declared empty" (`[]`) from "undeclared" (`None`)."""
    root = _corpus(tmp_path)
    _origin_overlay(root, "quiet-origin", [])
    assert schemas.resolve_strip_headers(
        root, "application/mbox", origin_id="quiet-origin"
    ) == []
    assert schemas._origin_strip_declaration(root, "quiet-origin") == []
    assert schemas._origin_strip_declaration(root, "no-such-origin") is None


# ---------- origin-overlay editorial templates (§4.2.3, extended) ---------- #


def test_origin_overlay_title_template_resolves(tmp_path):
    root = _corpus(tmp_path)
    overlay = root / "schema/origin/mail-window.yaml"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    overlay.write_text(
        "description: test mail-window overlay\n"
        "editorial:\n"
        "  title_template: \"Mail window — {window_start} → {window_end}\"\n"
        "extended_fields:\n"
        "  window_start: {type: string}\n"
        "  window_end: {type: string}\n"
    )
    schemas.cache_clear()

    source = _mbox(tmp_path, "m.mbox", _msg("one", None))
    rid = _ingest(root, source)
    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    records.merge_origin_fields(post, {"window_start": "2026-01-01", "window_end": "2026-07-21"})
    assert records.set_origin_schema_id(post, "mail-window")
    assert records.title_for(post, root) == "Mail window — 2026-01-01 → 2026-07-21"
    # All-or-nothing: an unresolvable placeholder falls the template through.
    post.metadata["_origins"][-1]["fields"].pop("window_end")
    assert records.title_for(post, root) == ""


def test_origin_overlay_title_template_cascade_resolves_later_entry(tmp_path):
    """A `title_template` LIST — the cascade form: the first entry needs a field the
    record doesn't carry (falls through, all-or-nothing), so the SECOND entry wins."""
    root = _corpus(tmp_path)
    overlay = root / "schema/origin/mail-window-cascade.yaml"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    overlay.write_text(
        "description: test cascade overlay\n"
        "editorial:\n"
        "  title_template:\n"
        "  - \"{unresolvable} — {window_start}\"\n"
        "  - \"Mail window — {window_start} → {window_end}\"\n"
        "extended_fields:\n"
        "  window_start: {type: string}\n"
        "  window_end: {type: string}\n"
        "  title_fallback:\n"
        "    type: string\n"
        "    role: title\n"
    )
    schemas.cache_clear()

    source = _mbox(tmp_path, "m.mbox", _msg("one", None))
    rid = _ingest(root, source)
    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    records.merge_origin_fields(post, {"window_start": "2026-01-01", "window_end": "2026-07-21"})
    assert records.set_origin_schema_id(post, "mail-window-cascade")
    assert records.title_for(post, root) == "Mail window — 2026-01-01 → 2026-07-21"


def test_origin_overlay_title_template_cascade_falls_through_to_role_mark(tmp_path):
    """When EVERY cascade entry fails to resolve, fall-through to a role-marked field is
    preserved — the cascade is one candidate kind among the layer's usual precedence."""
    root = _corpus(tmp_path)
    overlay = root / "schema/origin/mail-window-cascade.yaml"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    overlay.write_text(
        "description: test cascade overlay\n"
        "editorial:\n"
        "  title_template:\n"
        "  - \"{unresolvable} — {window_start}\"\n"
        "  - \"Mail window — {window_start} → {window_end}\"\n"
        "extended_fields:\n"
        "  window_start: {type: string}\n"
        "  window_end: {type: string}\n"
        "  title_fallback:\n"
        "    type: string\n"
        "    role: title\n"
    )
    schemas.cache_clear()

    source = _mbox(tmp_path, "m.mbox", _msg("one", None))
    rid = _ingest(root, source)
    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    records.merge_origin_fields(post, {"title_fallback": "Fallback Title"})
    assert records.set_origin_schema_id(post, "mail-window-cascade")
    assert records.title_for(post, root) == "Fallback Title"


def test_origin_subtype_overlay_editorial_wins_over_parent_without_editorial(tmp_path):
    """The exact migration shape (spec §4.3.1, §7.2): the PARENT id overlay exists (it
    declares something else — here, the mbox chrome strip) but carries no `editorial`
    block at all; the SUBTYPE overlay's own `editorial` cascade resolves — the parent
    must never eclipse the more-specific subtype overlay."""
    root = _corpus(tmp_path)
    parent = root / "schema/origin/google-takeout.yaml"
    parent.parent.mkdir(parents=True, exist_ok=True)
    parent.write_text(
        "description: producer overlay, no editorial\nstrip_headers:\n- X-Gmail-Labels\n"
    )
    subtype = root / "schema/origin/google-takeout/gmail.yaml"
    subtype.parent.mkdir(parents=True, exist_ok=True)
    subtype.write_text(
        "description: gmail subtype overlay\n"
        "editorial:\n"
        "  title_template: \"Mail window — {window_start} → {window_end}\"\n"
        "extended_fields:\n"
        "  window_start: {type: string}\n"
        "  window_end: {type: string}\n"
    )
    schemas.cache_clear()

    source = _mbox(tmp_path, "m.mbox", _msg("one", None))
    rid = _ingest(root, source)
    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    records.merge_origin_fields(post, {"window_start": "2026-01-01", "window_end": "2026-07-21"})
    assert records.set_origin_schema_id(post, "google-takeout/gmail")
    assert records.title_for(post, root) == "Mail window — 2026-01-01 → 2026-07-21"


# ---------- ingest auto-strip ---------- #


def test_ingest_auto_strips_via_default_binding_no_sidecar(tmp_path):
    """The unconditional-enforcement guarantee: with NO sidecar at all, the mime
    schema's `default_origin` binding resolves and its declared strip auto-applies."""
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _origin_overlay(root, "google-takeout/gmail", ["X-Gmail-Labels"])
    m1 = _msg("one", "Inbox,Category Updates,Unread")
    m2 = _msg("two", None)
    source = _mbox(tmp_path, "full.mbox", m1, m2)
    delivered_b3 = hashing.hash_file(source)["blake3"]

    rid = _ingest(root, source)
    assert rid != delivered_b3  # identity is over the CANONICALIZED bytes

    stored = root / "artifacts" / rid[:2] / f"{rid}.mbox"
    data = stored.read_bytes()
    assert b"X-Gmail-Labels" not in data
    assert hashing.hash_file(stored)["blake3"] == rid
    scan = mboxfile.scan(stored, None)
    assert {f.blake3 for f in scan.facts.values()} == {_b3(_stripped(m1)), _b3(m2)}

    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    fields = next(iter(records.iter_origin_blocks(post))).get("fields") or {}
    assert fields["stripped_headers"] == ["X-Gmail-Labels"]
    assert fields["stripped_members"] == 1
    assert fields["source_transport"] == f"blake3:{delivered_b3}"


def test_ingest_sidecar_stamp_walks_to_parent_declaration(tmp_path):
    """A sidecar stamps the SUB-overlay id `google-takeout/gmail`, which has no overlay
    file of its own; the declaration sits on the namespace PARENT `google-takeout` — the
    walk finds it (one ancestor hop). No `default_origin` binding is set at all, so this
    exercises the stamped-origin path in isolation. Also the compound-stamping check
    (spec §4.3.1): the sidecar's `origin_schema: google-takeout/gmail` lands on the
    record's origin block SPLIT into `id`/`subtype` — never the raw compound string —
    and the derived classification composes `origin/<id>/<subtype>`."""
    root = _corpus(tmp_path)
    _origin_overlay(root, "google-takeout", ["X-Gmail-Labels"])
    source = _mbox(tmp_path, "full.mbox", _msg("one", "Inbox,Unread"))
    _write_sidecar(source, "google-takeout/gmail")

    rid = _ingest(root, source)
    stored = root / "artifacts" / rid[:2] / f"{rid}.mbox"
    assert b"X-Gmail-Labels" not in stored.read_bytes()
    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    origin = next(iter(records.iter_origin_blocks(post)))
    fields = origin.get("fields") or {}
    assert fields["stripped_headers"] == ["X-Gmail-Labels"]
    assert origin["id"] == "google-takeout"
    assert origin["subtype"] == "gmail"
    assert records.derived_classifications(post) == [
        "mime/application/mbox",
        "origin/google-takeout/gmail",
    ]


def test_ingest_sidecar_stamp_different_namespace_no_declaration_wins_over_default(tmp_path):
    """Finality: a stamped origin in a namespace with NO declaration anywhere on its
    walk gets NO strip — even though the corpus's `default_origin` binding exists and
    DOES declare. The stamped id's silence is never overridden by the default."""
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _origin_overlay(root, "google-takeout/gmail", ["X-Gmail-Labels"])
    source = _mbox(tmp_path, "full.mbox", _msg("one", "Inbox,Unread"))
    _write_sidecar(source, "imessage-export")  # different namespace, no overlay at all
    delivered_b3 = hashing.hash_file(source)["blake3"]

    rid = _ingest(root, source)
    assert rid == delivered_b3  # untouched
    stored = root / "artifacts" / rid[:2] / f"{rid}.mbox"
    assert b"X-Gmail-Labels" in stored.read_bytes()


def test_ingest_stamped_overlay_explicit_empty_list_is_declared_off(tmp_path):
    """`strip_headers: []` on the stamped overlay stops the walk and strips nothing —
    even though the corpus's `default_origin` binding (a different, non-stamped path)
    would otherwise declare a strip."""
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _origin_overlay(root, "google-takeout/gmail", ["X-Gmail-Labels"])
    _origin_overlay(root, "google-takeout/gmail-raw", [])  # explicit off
    source = _mbox(tmp_path, "full.mbox", _msg("one", "Inbox,Unread"))
    _write_sidecar(source, "google-takeout/gmail-raw")
    delivered_b3 = hashing.hash_file(source)["blake3"]

    rid = _ingest(root, source)
    assert rid == delivered_b3
    stored = root / "artifacts" / rid[:2] / f"{rid}.mbox"
    assert b"X-Gmail-Labels" in stored.read_bytes()


def test_ingest_untouched_without_declaration(tmp_path):
    root = _corpus(tmp_path)
    source = _mbox(tmp_path, "full.mbox", _msg("one", "Inbox,Unread"))
    delivered_b3 = hashing.hash_file(source)["blake3"]
    rid = _ingest(root, source)
    assert rid == delivered_b3  # hash-what-staged holds when nothing is declared
    stored = root / "artifacts" / rid[:2] / f"{rid}.mbox"
    assert b"X-Gmail-Labels" in stored.read_bytes()


def test_ingest_already_canonical_passes_through(tmp_path):
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _origin_overlay(root, "google-takeout/gmail", ["X-Gmail-Labels"])
    source = _mbox(tmp_path, "clean.mbox", _msg("one", None))
    delivered_b3 = hashing.hash_file(source)["blake3"]
    rid = _ingest(root, source)
    assert rid == delivered_b3  # nothing to strip → no rewrite, no provenance
    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    fields = next(iter(records.iter_origin_blocks(post))).get("fields") or {}
    assert "stripped_headers" not in fields


# ---------- mbox-window resolves the same config ---------- #


def test_window_config_strip_crosses_prestrip_lineage(tmp_path):
    """The lineage baseline is ingested LABEL-FULL in a corpus with no binding/overlay;
    the corpus then adopts the strip (binding + origin-overlay declaration), and a
    window run with NO --strip/--origin flag resolves it from config: churned members
    are excluded as-if-stripped, the emitted delta member is label-free, and the sidecar
    is auto-stamped from the binding it resolved through."""
    root = _corpus(tmp_path)
    baseline_id = _ingest(
        root,
        _mbox(
            tmp_path,
            "baseline.mbox",
            _msg("one", "Inbox,Category Updates,Unread"),
            _msg("two", "Inbox"),
        ),
    )
    # The corpus adopts the strip AFTER the label-full baseline landed.
    _mime_shadow(root, "google-takeout/gmail")
    _origin_overlay(root, "google-takeout/gmail", ["X-Gmail-Labels"])

    new_msg = _msg("three", "Archived")
    source = _mbox(
        tmp_path,
        "full.mbox",
        _msg("one", "Archived,Opened,Category Personal"),
        _msg("two", "Archived,Opened"),
        new_msg,
    )
    assert (
        mbox_window.run(
            argparse.Namespace(
                source=str(source),
                against=[baseline_id],
                origin=None,
                strip=None,  # ← resolved from the schema declaration, not the CLI
                dry_run=False,
                corpus_root=str(root),
            )
        )
        == 0
    )
    bundles = sorted((root / "capture").glob("*-window-*.mbox"))
    assert len(bundles) == 1
    scan = mboxfile.scan(bundles[0], None)
    assert scan.count == 1
    assert scan.facts[1].blake3 == _b3(_stripped(new_msg))
    assert b"X-Gmail-Labels" not in bundles[0].read_bytes()

    sidecar = yaml.safe_load(
        bundles[0].with_suffix(bundles[0].suffix + ".capture.yaml").read_text()
    )
    fields = sidecar["origin_fields"]
    assert fields["excluded_count"] == 2
    assert fields["stripped_headers"] == ["X-Gmail-Labels"]
    # Auto-stamped from the binding it resolved through (no --origin given).
    assert sidecar["origin_schema"] == "google-takeout/gmail"


def test_window_without_declaration_readmits_label_churn(tmp_path):
    """The negative control: no schema declaration, no --strip → label churn re-admits."""
    root = _corpus(tmp_path)
    baseline_id = _ingest(
        root, _mbox(tmp_path, "baseline.mbox", _msg("one", "Inbox,Unread"), _msg("two", "Inbox"))
    )
    source = _mbox(
        tmp_path, "full.mbox", _msg("one", "Archived,Opened"), _msg("two", "Archived,Opened")
    )
    assert (
        mbox_window.run(
            argparse.Namespace(
                source=str(source),
                against=[baseline_id],
                origin=None,
                strip=None,
                dry_run=False,
                corpus_root=str(root),
            )
        )
        == 0
    )
    bundles = sorted((root / "capture").glob("*-window-*.mbox"))
    assert len(bundles) == 1
    assert mboxfile.scan(bundles[0], None).count == 2  # label churn re-admitted everything
