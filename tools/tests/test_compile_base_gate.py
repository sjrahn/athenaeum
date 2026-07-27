"""`corpus compile`'s base gate and dry run (#76).

`compile` rewrites a record in full, so the dangerous input is not a wrong TARGET but a stale
BASE: a working dir whose record has moved on since it was decomposed writes the record
backward, completely, with `git diff` as the only evidence. The first test here is the
incident that opened the ticket, reproduced end to end — a scratch copy of a working dir,
compiled after the real one had landed its edit.

The stamp this leans on (`orig_sha256` in `.corpus-decompose.json`) was written by decompose
all along and read by nobody, which is why the trap existed at all.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import frontmatter

from corpus import records, schemas, segments
from corpus._cli import dispatch

_ID = "a" * 64


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


_SEAL = "The GM authentic-service seal, a round badge with the gm wordmark."


def _record(root: Path, *, legacy: bool = False) -> Path:
    """A minimal canonical record with a two-segment content zone to edit.

    `legacy=True` puts its roster in the pre-3.4 per-asset form, carrying the retired
    descriptive fields the members block cannot hold.
    """
    p = root / "records" / "aa" / f"{_ID}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": _ID,
            "transport": "sha256:" + "b" * 64,
            "touch": ["corpus.ingest@0.1.0"],
        }
    )
    records.set_artifact_block(post, mime="application/pdf", fields={"page_count": 2})
    records.append_origin_block(
        post, uri="https://example.com/g.pdf", snapshot="2026-05-31T00:00:00Z"
    )
    if not legacy:
        records.append_member(
            post,
            media_type="image/png",
            address="el=1",
            transport="blake3:" + "c" * 64,
            fields={"bytes": 4118},
        )
    post.content = segments.emit(
        [
            segments.Section(
                address="pages=1-2",
                segments=[
                    segments.Segment(atom="text", address="page=1", body="One."),
                    segments.Segment(atom="text", address="page=2", body="Two."),
                ],
            )
        ]
    )
    records.dump(post, p)
    if legacy:
        # Written as text, not through `append_member`: the authoring API enforces the closed
        # four-key row and strips exactly the retired fields this fixture needs. Legacy blocks
        # sit last in the metadata zone, so they go immediately before the content zone.
        text = p.read_text("utf-8")
        p.write_text(text.replace("<!--section", _LEGACY_ROSTER + "\n<!--section", 1), "utf-8")
    return p


_LEGACY_ROSTER = (
    "<!--embed image/png\n"
    "address: el=1\n"
    "transport: blake3:" + "c" * 64 + "\n"
    "width: 315\n"
    "height: 315\n"
    "alt: seal\n"
    f"description: {_SEAL}\n"
    "-->\n"
)


def _legacy_roster_record(root: Path) -> Path:
    p = _record(root, legacy=True)
    assert records.pending_member_descriptions(records.load(p))  # the fixture is pre-3.4
    assert "<!--embed image/png" in p.read_text("utf-8")
    return p


def _decompose(root: Path, into: Path) -> None:
    assert dispatch(["decompose", _ID[:12], "--into", str(into), "--corpus-root", str(root)]) == 0


def _compile(root: Path, workdir: Path, *extra: str) -> int:
    return dispatch(
        ["compile", str(workdir), "--no-lint", "--corpus-root", str(root), *extra]
    )


def _edit_first_body(workdir: Path, text: str) -> None:
    body = sorted((workdir / "bodies").glob("*.md"))[0]
    body.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- the incident


def test_compile_refuses_a_working_dir_whose_base_moved_on(tmp_path, capsys):
    """The #76 incident exactly: one decompose, two working dirs. The real one lands its
    edit; the scratch copy — which predates that edit — must not rewrite the record back."""
    root = _corpus(tmp_path)
    rec = _record(root)
    work, scratch = tmp_path / "w", tmp_path / "scratch"

    _decompose(root, work)
    shutil.copytree(work, scratch)  # the scratch copy, taken to test a tooling question

    _edit_first_body(work, "One, corrected.\n")
    assert _compile(root, work) == 0
    landed = rec.read_text("utf-8")
    assert "One, corrected." in landed
    capsys.readouterr()

    assert _compile(root, scratch) == 1
    assert rec.read_text("utf-8") == landed  # the correction survives, byte for byte
    err = capsys.readouterr().err
    assert "REFUSING" in err
    assert "changed after this working dir was decomposed" in err
    assert "--ignore-base-drift" in err  # the refusal names its own override


def test_ignore_base_drift_overwrites_deliberately(tmp_path, capsys):
    root = _corpus(tmp_path)
    rec = _record(root)
    work, scratch = tmp_path / "w", tmp_path / "scratch"
    _decompose(root, work)
    shutil.copytree(work, scratch)
    _edit_first_body(work, "One, corrected.\n")
    assert _compile(root, work) == 0
    capsys.readouterr()

    assert _compile(root, scratch, "--ignore-base-drift") == 0
    assert "One, corrected." not in rec.read_text("utf-8")  # clobbered, as asked


def test_missing_record_at_the_target_is_drift(tmp_path, capsys):
    """A working dir compiled against a corpus root that does not hold its record — the
    cross-hub mistake — is drift, not a fresh write."""
    root = _corpus(tmp_path)
    _record(root)
    work = tmp_path / "w"
    _decompose(root, work)

    other = _corpus(tmp_path / "other")
    assert _compile(other, work) == 1
    err = capsys.readouterr().err
    assert "different corpus root" in err
    assert not (other / "records" / "aa" / f"{_ID}.md").exists()


def test_an_unstamped_working_dir_warns_and_proceeds(tmp_path, capsys):
    """No stamp is not drift. A pre-stamp or hand-built dir holds edits that re-decomposing
    would destroy, so it must warn rather than refuse."""
    root = _corpus(tmp_path)
    rec = _record(root)
    work = tmp_path / "w"
    _decompose(root, work)
    (work / ".corpus-decompose.json").unlink()
    _edit_first_body(work, "One, from an unstamped dir.\n")

    assert _compile(root, work) == 0
    assert "One, from an unstamped dir." in rec.read_text("utf-8")
    assert "carries no decompose stamp" in capsys.readouterr().err


# ------------------------------------------------------------------- the dry run


def test_dry_run_writes_nothing_and_prints_the_diff(tmp_path, capsys):
    root = _corpus(tmp_path)
    rec = _record(root)
    before = rec.read_text("utf-8")
    work = tmp_path / "w"
    _decompose(root, work)
    _edit_first_body(work, "One, corrected.\n")

    assert _compile(root, work, "--dry-run") == 0
    assert rec.read_text("utf-8") == before  # untouched
    out = capsys.readouterr().out
    assert "+One, corrected." in out
    assert "-One." in out
    assert "would write" in out
    assert str(rec) in out


def test_dry_run_names_a_no_op_edit(tmp_path, capsys):
    """Straight from decompose, the only delta is the compile touch — say so, rather than
    showing a touch-line diff and letting it read as a real change."""
    root = _corpus(tmp_path)
    _record(root)
    work = tmp_path / "w"
    _decompose(root, work)

    assert _compile(root, work, "--dry-run") == 0
    assert "no change beyond the compile touch" in capsys.readouterr().out


def test_dry_run_exit_status_predicts_a_refusal_but_still_shows_the_diff(tmp_path, capsys):
    """A stale base is exactly when you most need to see the diff — it is what compiling
    would destroy — so the dry run reports the refusal and prints it anyway."""
    root = _corpus(tmp_path)
    rec = _record(root)
    work, scratch = tmp_path / "w", tmp_path / "scratch"
    _decompose(root, work)
    shutil.copytree(work, scratch)
    _edit_first_body(work, "One, corrected.\n")
    assert _compile(root, work) == 0
    landed = rec.read_text("utf-8")
    capsys.readouterr()

    assert _compile(root, scratch, "--dry-run") == 1
    captured = capsys.readouterr()
    assert "would refuse" in captured.err
    assert "-One, corrected." in captured.out  # what the clobber would have cost
    assert rec.read_text("utf-8") == landed


# ------------------------------------ the form-preserving round trip (§12.26)


def test_compiling_a_legacy_roster_does_not_convert_it(tmp_path, capsys):
    """§12.26: serialization is form-preserving, so touching a record for an unrelated reason
    never converts its roster. Conversion belongs to re-attestation, which reports what it
    sheds; a compile that converted would delete the retired descriptions in silence."""
    root = _corpus(tmp_path)
    rec = _legacy_roster_record(root)
    work = tmp_path / "w"
    _decompose(root, work)

    assert _compile(root, work) == 0
    after = rec.read_text("utf-8")
    assert "<!--embed image/png" in after  # still legacy
    assert "<!--members" not in after
    assert _SEAL in after  # the prose survives the round trip
    assert "width: 315" in after and "height: 315" in after and "alt: seal" in after


def test_a_legacy_record_round_trips_byte_identically(tmp_path, capsys):
    """The strongest form of the same claim: decompose → compile changes nothing but the
    compile touch, on a record whose roster the substrate cannot even express."""
    root = _corpus(tmp_path)
    _legacy_roster_record(root)
    work = tmp_path / "w"
    _decompose(root, work)

    assert _compile(root, work, "--dry-run") == 0
    assert "no change beyond the compile touch" in capsys.readouterr().out


def test_the_manifest_still_refuses_to_carry_member_narration(tmp_path):
    """Preserving what a record stores is a different obligation from letting an author write
    it: the roster stays closed to editing even while the round trip keeps the legacy fields."""
    root = _corpus(tmp_path)
    _legacy_roster_record(root)
    work = tmp_path / "w"
    _decompose(root, work)

    member_line = next(
        ln
        for ln in (work / "manifest.corpus").read_text("utf-8").splitlines()
        if ln.startswith("member ")
    )
    assert "desc=" not in member_line
    assert "description" not in member_line
    assert "width" not in member_line
    # It rides in meta.yaml instead, as opaque carry-through.
    assert "roster_form: legacy" in (work / "meta.yaml").read_text("utf-8")


def test_a_record_already_on_the_members_block_still_writes_one(tmp_path, capsys):
    """Form preservation must not become form freezing — a 3.4 record stays 3.4."""
    root = _corpus(tmp_path)
    rec = _record(root)
    work = tmp_path / "w"
    _decompose(root, work)
    assert "roster_form" not in (work / "meta.yaml").read_text("utf-8")

    assert _compile(root, work) == 0
    after = rec.read_text("utf-8")
    assert "<!--members" in after
    assert "<!--embed " not in after


# ----------------------------------------------------------------------- --out


def test_out_writes_elsewhere_and_skips_the_base_check(tmp_path, capsys):
    """The escape hatch for the experiment that caused the incident: compile behaviour can
    be exercised with no authored record at risk, so a stale base is irrelevant."""
    root = _corpus(tmp_path)
    rec = _record(root)
    work, scratch = tmp_path / "w", tmp_path / "scratch"
    _decompose(root, work)
    shutil.copytree(work, scratch)
    _edit_first_body(work, "One, corrected.\n")
    assert _compile(root, work) == 0
    landed = rec.read_text("utf-8")
    capsys.readouterr()

    elsewhere = tmp_path / "sandbox" / "probe.md"
    assert _compile(root, scratch, "--out", str(elsewhere)) == 0
    assert elsewhere.is_file()
    assert "One, corrected." not in elsewhere.read_text("utf-8")  # the scratch dir's content
    assert rec.read_text("utf-8") == landed  # the corpus record is untouched
    assert "the corpus record is untouched" in capsys.readouterr().out
