"""Producer member exclusion (spec v37, §12.3.13): `exclude_members`, a POLICY filter
resolved through the SAME §7.2 id/subtype ladder + `default_origin` binding as
`strip_headers` — the `MemberExcluder` line-based matcher (folded continuations,
header-zone-only, case-insensitive header NAME / as-delivered label value), read-then-
strip ordering (the predicate sees a header the strip ALSO removes), schema resolution
(ladder precedence, explicit-empty-stops, no cross-producer fallthrough), and the four
consumers applying the same resolved exclusion identically: ingest's standalone-mbox
auto-strip path, `mbox-split`, `mbox-window` (source + lineage enumeration), and
`export-diff`'s reconciliation.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

import blake3
import yaml

import corpus as corpus_pkg
from corpus import mboxfile, records, schemas
from corpus._cli import export_diff, mbox_split, mbox_window
from corpus._cli import ingest as ingest_cli

CRLF = b"\r\n"

_PACKAGED_MBOX_SCHEMA = (
    Path(corpus_pkg.__file__).parent
    / "schemas_default/mime/application/application_mbox.yaml"
)


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _sep(i: int) -> bytes:
    return f"From {i}@xxx Mon Jan 01 00:00:00 +0000 2024".encode() + CRLF


def _msg(
    subject: str,
    labels: str | None = None,
    date: str | None = None,
    body: bytes = b"body" + CRLF,
) -> bytes:
    head = b"From: a@x.com" + CRLF
    if labels is not None:
        head += b"X-Gmail-Labels: " + labels.encode() + CRLF
    head += f"Subject: {subject}".encode() + CRLF
    if date is not None:
        head += f"Date: {date}".encode() + CRLF
    return head + CRLF + body


def _mbox(tmp_path: Path, name: str, *raw_members: bytes) -> Path:
    out = b""
    for i, member in enumerate(raw_members, start=1):
        out += _sep(i) + member
    p = tmp_path / name
    p.write_bytes(out)
    return p


def _corpus(tmp_path: Path, default_origin: str | None = None) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    if default_origin:
        local = root / "schema/mime/application/application_mbox.yaml"
        local.parent.mkdir(parents=True)
        local.write_text(
            _PACKAGED_MBOX_SCHEMA.read_text() + f"\ndefault_origin: {default_origin}\n"
        )
    schemas.cache_clear()
    return root


def _write_overlay(
    root: Path,
    origin_id: str,
    *,
    exclude_members: list[dict] | None = None,
    strip_headers: list[str] | None = None,
) -> None:
    """Write/replace an origin overlay declaring `exclude_members` and/or
    `strip_headers` — either may be an explicit `[]` (a declaration, not silence)."""
    path = root / "schema" / "origin" / f"{origin_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["description: test origin overlay"]
    if strip_headers is not None:
        if strip_headers:
            lines.append("strip_headers:")
            lines.extend(f"- {h}" for h in strip_headers)
        else:
            lines.append("strip_headers: []")
    if exclude_members is not None:
        if exclude_members:
            lines.append("exclude_members:")
            for pred in exclude_members:
                lines.append(f"- header: {pred['header']}")
                lines.append(f"  contains: [{', '.join(pred['contains'])}]")
        else:
            lines.append("exclude_members: []")
    path.write_text("\n".join(lines) + "\n")
    schemas.cache_clear()


def _ingest(root: Path, artifact: Path) -> str:
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / artifact.name
    if staged != artifact:
        shutil.copy(artifact, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    recs = sorted((root / "records").rglob("*.md"))
    by_mtime = max(recs, key=lambda p: p.stat().st_mtime)
    return by_mtime.stem


EXCLUDE_SPAM_TRASH = mboxfile.normalize_exclude_members(
    [{"header": "X-Gmail-Labels", "contains": ["Spam", "Trash"]}]
)
STRIP_LABELS = mboxfile.normalize_strip_headers(["X-Gmail-Labels"])


# ---------- normalize + MemberExcluder ---------- #


def test_normalize_exclude_members_pools_labels_by_header_case_insensitively():
    norm = mboxfile.normalize_exclude_members(
        [
            {"header": "X-Gmail-Labels", "contains": ["Spam", "Trash"]},
            {"header": "x-gmail-labels", "contains": ["Junk"]},
        ]
    )
    assert norm == {b"x-gmail-labels:": frozenset({"Spam", "Trash", "Junk"})}


def test_normalize_exclude_members_empty_or_absent_is_none():
    assert mboxfile.normalize_exclude_members([]) is None
    assert mboxfile.normalize_exclude_members(None) is None


def test_exact_label_excludes_substring_does_not(tmp_path):
    spam = _msg("s", labels="Spam,Inbox")
    spamalot = _msg("sa", labels="Spamalot,Inbox")
    p = _mbox(tmp_path, "m.mbox", spam, spamalot)
    scan = mboxfile.scan(p, None, exclude=EXCLUDE_SPAM_TRASH)
    assert scan.excluded_ordinals == {1}


def test_folded_continuation_label_matches(tmp_path):
    folded = (
        b"From: a@x.com" + CRLF
        + b"X-Gmail-Labels: Inbox," + CRLF
        + b" Spam,Important" + CRLF
        + b"Subject: hi" + CRLF
        + CRLF
        + b"body" + CRLF
    )
    p = _mbox(tmp_path, "m.mbox", folded)
    scan = mboxfile.scan(p, None, exclude=EXCLUDE_SPAM_TRASH)
    assert scan.excluded_ordinals == {1}


def test_header_name_case_insensitive(tmp_path):
    m = (
        b"From: a@x.com" + CRLF
        + b"x-gmail-labels: Spam" + CRLF
        + b"Subject: hi" + CRLF
        + CRLF
        + b"body" + CRLF
    )
    p = _mbox(tmp_path, "m.mbox", m)
    scan = mboxfile.scan(p, None, exclude=EXCLUDE_SPAM_TRASH)
    assert scan.excluded_ordinals == {1}


def test_label_value_compares_as_delivered_not_case_folded(tmp_path):
    lower = _msg("s", labels="spam")  # declared label is "Spam"
    p = _mbox(tmp_path, "m.mbox", lower)
    scan = mboxfile.scan(p, None, exclude=EXCLUDE_SPAM_TRASH)
    assert scan.excluded_ordinals == set()


def test_body_line_never_matched(tmp_path):
    m = (
        b"From: a@x.com" + CRLF
        + b"Subject: hi" + CRLF
        + CRLF
        + b"X-Gmail-Labels: Spam" + CRLF  # body line, not a header
    )
    p = _mbox(tmp_path, "m.mbox", m)
    scan = mboxfile.scan(p, None, exclude=EXCLUDE_SPAM_TRASH)
    assert scan.excluded_ordinals == set()


def test_read_then_strip_still_excludes_when_marker_header_is_stripped(tmp_path):
    spam = _msg("s", labels="Spam")
    keep = _msg("k", labels="Inbox")
    p = _mbox(tmp_path, "m.mbox", spam, keep)
    scan = mboxfile.scan(p, None, strip=STRIP_LABELS, exclude=EXCLUDE_SPAM_TRASH)
    assert scan.excluded_ordinals == {1}
    assert scan.stripped_members == 2  # both members' header still stripped from output


# ---------- schema resolution ladder ---------- #


def test_resolve_exclude_members_from_default_binding(tmp_path):
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _write_overlay(
        root,
        "google-takeout/gmail",
        exclude_members=[{"header": "X-Gmail-Labels", "contains": ["Spam", "Trash"]}],
    )
    assert schemas.resolve_exclude_members(root, "application/mbox") == [
        {"header": "X-Gmail-Labels", "contains": ["Spam", "Trash"]}
    ]
    bare = _corpus(tmp_path / "bare")
    assert schemas.resolve_exclude_members(bare, "application/mbox") == []


def test_resolve_exclude_members_subtype_wins_over_id(tmp_path):
    root = _corpus(tmp_path)
    _write_overlay(
        root, "google-takeout", exclude_members=[{"header": "X-Foo", "contains": ["A"]}]
    )
    _write_overlay(
        root,
        "google-takeout/gmail",
        exclude_members=[{"header": "X-Gmail-Labels", "contains": ["Spam"]}],
    )
    result = schemas.resolve_exclude_members(
        root, "application/mbox", origin_id="google-takeout/gmail"
    )
    assert result == [{"header": "X-Gmail-Labels", "contains": ["Spam"]}]


def test_resolve_exclude_members_id_fallback_when_subtype_undeclared(tmp_path):
    """The subtype overlay has no file at all — the walk falls back one ancestor hop to
    the id overlay, exactly as `strip_headers`'s walk does."""
    root = _corpus(tmp_path)
    _write_overlay(
        root, "google-takeout", exclude_members=[{"header": "X-Foo", "contains": ["A"]}]
    )
    result = schemas.resolve_exclude_members(
        root, "application/mbox", origin_id="google-takeout/gmail"
    )
    assert result == [{"header": "X-Foo", "contains": ["A"]}]


def test_resolve_exclude_members_explicit_empty_list_stops_ladder(tmp_path):
    root = _corpus(tmp_path)
    _write_overlay(
        root, "google-takeout", exclude_members=[{"header": "X-Foo", "contains": ["A"]}]
    )
    _write_overlay(root, "google-takeout/gmail", exclude_members=[])
    result = schemas.resolve_exclude_members(
        root, "application/mbox", origin_id="google-takeout/gmail"
    )
    assert result == []
    assert schemas._origin_exclude_members_declaration(root, "google-takeout/gmail") == []
    assert schemas._origin_exclude_members_declaration(root, "no-such-origin") is None


def test_resolve_exclude_members_no_cross_producer_fallthrough(tmp_path):
    """Finality: a stamped origin whose OWN walk declares nothing gets NO exclusion —
    even though the corpus's `default_origin` binding exists and does declare. The
    default binding is consulted only when no origin id was given at all."""
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _write_overlay(
        root,
        "google-takeout/gmail",
        exclude_members=[{"header": "X-Gmail-Labels", "contains": ["Spam"]}],
    )
    assert (
        schemas.resolve_exclude_members(
            root, "application/mbox", origin_id="imessage-export"
        )
        == []
    )


def test_resolve_exclude_members_malformed_entries_dropped(tmp_path):
    root = _corpus(tmp_path)
    overlay = root / "schema/origin/quiet.yaml"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    overlay.write_text(
        "description: t\n"
        "exclude_members:\n"
        "- header: X-Gmail-Labels\n"
        "  contains: [Spam]\n"
        "- header: \"\"\n"
        "  contains: [Nope]\n"
        "- header: X-No-Labels\n"
        "  contains: []\n"
        "- header: X-Also-No-Labels\n"
    )
    schemas.cache_clear()
    result = schemas.resolve_exclude_members(root, "application/mbox", origin_id="quiet")
    assert result == [{"header": "X-Gmail-Labels", "contains": ["Spam"]}]


# ---------- mbox-split applies the resolved exclusion ---------- #


def test_mbox_split_excludes_and_discloses_per_bucket(tmp_path):
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _write_overlay(
        root,
        "google-takeout/gmail",
        strip_headers=["X-Gmail-Labels"],
        exclude_members=[{"header": "X-Gmail-Labels", "contains": ["Spam", "Trash"]}],
    )
    kept_2023 = _msg("a", labels="Inbox", date="Mon, 06 Mar 2023 10:00:00 +0000")
    spam_2023 = _msg("b", labels="Spam", date="Tue, 07 Mar 2023 10:00:00 +0000")
    kept_cur = _msg("c", labels="Inbox", date="Sat, 04 Jan 2025 10:00:00 +0000")
    trash_cur = _msg("d", labels="Trash", date="Sun, 05 Jan 2025 10:00:00 +0000")
    source = _mbox(tmp_path, "full.mbox", kept_2023, spam_2023, kept_cur, trash_cur)

    assert (
        mbox_split.run(
            argparse.Namespace(
                source=str(source),
                current_year=2025,
                origin=None,
                strip=None,
                corpus_root=str(root),
            )
        )
        == 0
    )
    container = root / "capture" / "full-years-2023-2023.zip"
    residue = root / "capture" / "full-current-2025.mbox"
    with zipfile.ZipFile(container) as z:
        assert z.namelist() == ["2023.mbox"]
        z.extractall(tmp_path / "x")
    assert mboxfile.scan(tmp_path / "x/2023.mbox", None).count == 1  # spam excluded
    assert mboxfile.scan(residue, None).count == 1  # trash excluded

    fields = yaml.safe_load(
        container.with_suffix(container.suffix + ".capture.yaml").read_text()
    )["origin_fields"]
    assert fields["policy_excluded_count"] == 1
    assert fields["policy_excluded_by_period"] == {"2023": 1}

    res_fields = yaml.safe_load(
        residue.with_suffix(residue.suffix + ".capture.yaml").read_text()
    )["origin_fields"]
    assert res_fields["policy_excluded_count"] == 1


def test_mbox_split_without_declaration_readmits_all(tmp_path):
    root = _corpus(tmp_path)
    spam_2023 = _msg("b", labels="Spam", date="Tue, 07 Mar 2023 10:00:00 +0000")
    kept_cur = _msg("c", labels="Inbox", date="Sat, 04 Jan 2025 10:00:00 +0000")
    source = _mbox(tmp_path, "full.mbox", spam_2023, kept_cur)
    assert (
        mbox_split.run(
            argparse.Namespace(
                source=str(source),
                current_year=2025,
                origin=None,
                strip=None,
                corpus_root=str(root),
            )
        )
        == 0
    )
    container = root / "capture" / "full-years-2023-2023.zip"
    with zipfile.ZipFile(container) as z:
        z.extractall(tmp_path / "x")
    assert mboxfile.scan(tmp_path / "x/2023.mbox", None).count == 1  # nothing excluded
    fields = yaml.safe_load(
        container.with_suffix(container.suffix + ".capture.yaml").read_text()
    )["origin_fields"]
    assert "policy_excluded_count" not in fields


# ---------- mbox-window applies the resolved exclusion (source + lineage) ---------- #


def test_mbox_window_excludes_policy_members_and_discloses(tmp_path):
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _write_overlay(
        root,
        "google-takeout/gmail",
        exclude_members=[{"header": "X-Gmail-Labels", "contains": ["Spam"]}],
    )
    baseline_id = _ingest(root, _mbox(tmp_path, "baseline.mbox", _msg("one", labels="Inbox")))

    new_spam = _msg("two", labels="Spam")
    new_keep = _msg("three", labels="Inbox")
    source = _mbox(tmp_path, "full.mbox", new_spam, new_keep)
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
    bundles = sorted((root / "capture").glob("*window*.mbox"))
    assert len(bundles) == 1
    scan = mboxfile.scan(bundles[0], None)
    assert scan.count == 1
    assert scan.facts[1].blake3 == _b3(new_keep)

    fields = yaml.safe_load(
        bundles[0].with_suffix(bundles[0].suffix + ".capture.yaml").read_text()
    )["origin_fields"]
    assert fields["policy_excluded_count"] == 1
    # Distinct from the already-persisted dedup count — never conflated.
    assert fields["excluded_count"] == 0


def test_mbox_window_lineage_enumeration_uses_same_exclusion(tmp_path):
    """A lineage record ingested BEFORE the corpus declared `exclude_members` still
    carries a Spam member (pre-policy history); the window's lineage-enumeration scan
    resolves the SAME exclusion as the source scan, so that historical member's hash is
    not folded into the "already persisted" set — it simply never mattered, since the
    source-side member with the same label is policy-excluded outright either way."""
    root = _corpus(tmp_path)
    old_spam = _msg("old-spam", labels="Spam")
    baseline_id = _ingest(
        root, _mbox(tmp_path, "baseline.mbox", _msg("one", labels="Inbox"), old_spam)
    )
    _write_overlay(
        root,
        "policy-origin",
        exclude_members=[{"header": "X-Gmail-Labels", "contains": ["Spam"]}],
    )

    source = _mbox(tmp_path, "full.mbox", old_spam, _msg("two", labels="Inbox"))
    assert (
        mbox_window.run(
            argparse.Namespace(
                source=str(source),
                against=[baseline_id],
                origin="policy-origin",
                strip=None,
                dry_run=False,
                corpus_root=str(root),
            )
        )
        == 0
    )
    bundles = sorted((root / "capture").glob("*window*.mbox"))
    assert len(bundles) == 1
    scan = mboxfile.scan(bundles[0], None)
    # old_spam is policy-excluded from the SOURCE directly; only "two" is new.
    assert scan.count == 1
    assert scan.facts[1].blake3 == _b3(_msg("two", labels="Inbox"))


def test_exclusion_set_omits_policy_excluded_lineage_hash(tmp_path):
    """`_exclusion_set`'s own lineage-artifact scan resolves `exclude` exactly as the
    source scan does (spec v37: "wherever it resolves strip config today") — a lineage
    member the predicate matches is left OUT of the "already persisted" hash set."""
    root = _corpus(tmp_path)
    old_spam = _msg("old-spam", labels="Spam")
    kept = _msg("one", labels="Inbox")
    baseline_id = _ingest(root, _mbox(tmp_path, "baseline.mbox", kept, old_spam))
    post = records.load(root / "records" / baseline_id[:2] / f"{baseline_id}.md")
    lineage = [(baseline_id, post)]

    without = mbox_window._exclusion_set(root, lineage)
    assert _b3(old_spam) in without

    with_exclude = mbox_window._exclusion_set(root, lineage, exclude=EXCLUDE_SPAM_TRASH)
    assert _b3(old_spam) not in with_exclude
    assert _b3(kept) in with_exclude


# ---------- export-diff applies the resolved exclusion to both sides ---------- #


def test_export_diff_excludes_from_both_sides(tmp_path):
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _write_overlay(
        root,
        "google-takeout/gmail",
        exclude_members=[{"header": "X-Gmail-Labels", "contains": ["Spam", "Trash"]}],
    )
    common = _msg("common", labels="Inbox")
    spam_only_a = _msg("spamA", labels="Spam")
    trash_only_b = _msg("trashB", labels="Trash")
    a = _mbox(tmp_path, "a.mbox", common, spam_only_a)
    b = _mbox(tmp_path, "b.mbox", common, trash_only_b)

    ns = argparse.Namespace(
        a=str(a), b=str(b), json_out=None, origin=None, corpus_root=str(root)
    )
    exclude, resolved = export_diff._resolve_exclude(ns)
    assert resolved is True
    report = export_diff.build_report(a, b, exclude=exclude, exclusion_resolved=resolved)
    assert report["excluded_a"] == 1
    assert report["excluded_b"] == 1
    assert report["exclusion_resolved"] is True
    assert report["only_a"] == 0
    assert report["only_b"] == 0
    assert report["identical"] == 1
    rendered = export_diff.render_report(report)
    assert "policy-excluded (exclude_members): A=1   B=1" in rendered
    assert "NOT resolved" not in rendered


def test_export_diff_without_corpus_root_measures_raw_churn(tmp_path):
    """The negative control preserving export-diff's pre-v37 behavior: with no
    `--corpus-root`/`--origin` resolved (exclude=None), a Spam-only member shows as raw
    only-A churn instead of being reconciled away — and the report/rendered text say so
    explicitly (measurement-honesty: "0 excluded, nothing matched" must never read the
    same as "0 excluded, exclusion never even checked")."""
    common = _msg("common", labels="Inbox")
    spam_only_a = _msg("spamA", labels="Spam")
    a = _mbox(tmp_path, "a.mbox", common, spam_only_a)
    b = _mbox(tmp_path, "b.mbox", common)
    report = export_diff.build_report(a, b)
    assert report["excluded_a"] == 0
    assert report["exclusion_resolved"] is False
    assert report["only_a"] == 1
    rendered = export_diff.render_report(report)
    assert "NOT resolved — no corpus reachable" in rendered

    ns = argparse.Namespace(a=str(a), b=str(b), json_out=None, origin=None, corpus_root=None)
    exclude, resolved = export_diff._resolve_exclude(ns)
    assert exclude is None and resolved is False


# ---------- ingest's standalone-mbox canonicalize-at-entry path ---------- #


def test_ingest_excludes_policy_members(tmp_path):
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _write_overlay(
        root,
        "google-takeout/gmail",
        exclude_members=[{"header": "X-Gmail-Labels", "contains": ["Spam"]}],
    )
    spam = _msg("s", labels="Spam")
    keep = _msg("k", labels="Inbox")
    source = _mbox(tmp_path, "full.mbox", spam, keep)
    rid = _ingest(root, source)
    stored = root / "artifacts" / rid[:2] / f"{rid}.mbox"
    scan = mboxfile.scan(stored, None)
    assert scan.count == 1
    assert scan.facts[1].blake3 == _b3(keep)

    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    fields = next(iter(records.iter_origin_blocks(post))).get("fields") or {}
    assert fields["policy_excluded_count"] == 1


def test_ingest_excludes_when_marker_header_is_also_stripped(tmp_path):
    """Read-then-strip at ingest, one pass: the Spam marker lives in the SAME header
    `strip_headers` removes, and the member is still excluded — spec §12.3.13's
    canonicalize-at-entry invariant covers exclusion too (v37)."""
    root = _corpus(tmp_path, default_origin="google-takeout/gmail")
    _write_overlay(
        root,
        "google-takeout/gmail",
        strip_headers=["X-Gmail-Labels"],
        exclude_members=[{"header": "X-Gmail-Labels", "contains": ["Spam"]}],
    )
    spam = _msg("s", labels="Spam")
    keep = _msg("k", labels="Inbox")
    source = _mbox(tmp_path, "full.mbox", spam, keep)
    rid = _ingest(root, source)
    stored = root / "artifacts" / rid[:2] / f"{rid}.mbox"
    data = stored.read_bytes()
    assert b"X-Gmail-Labels" not in data  # kept member's header still stripped
    scan = mboxfile.scan(stored, None)
    assert scan.count == 1  # spam member removed entirely, not just header-stripped

    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    fields = next(iter(records.iter_origin_blocks(post))).get("fields") or {}
    assert fields["policy_excluded_count"] == 1
    assert fields["stripped_headers"] == ["X-Gmail-Labels"]


def test_ingest_without_declaration_readmits_all(tmp_path):
    root = _corpus(tmp_path)
    spam = _msg("s", labels="Spam")
    source = _mbox(tmp_path, "full.mbox", spam)
    from corpus import hashing

    delivered_b3 = hashing.hash_file(source)["blake3"]
    rid = _ingest(root, source)
    assert rid == delivered_b3  # untouched — no declaration anywhere
