"""`corpus compile`'s retirement gate (#116), and the census it shares with the sweep.

`corpus drop-retired` is the migration; this is the contract. Without it the migration is
undone by the next pass — a 20-record normalize pilot (2026-08-07) wrote +17 retired `entry:`
fields against -2 removed, roughly one per record, every one of them through `compile` and
past `lint` at zero errors.

The gate's whole shape is in the asymmetry these tests pin: **acquiring** a retired field is
refused, **carrying** one never is. ~7,300 records carry one today; a gate that turned those
red would be a gate everyone passes `--allow-retired` to.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest
import yaml

from corpus import records, retired, schemas, segments
from corpus._cli import dispatch
from corpus.segments import Section, Segment

_ID = "d" * 64


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _record(root: Path, *, entry: str | None = None) -> Path:
    """A minimal two-segment record. `entry` gives the FIRST content segment the retired
    §4.3.2.2 label, for the tests about carrying one rather than acquiring one."""
    p = root / "records" / "dd" / f"{_ID}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": _ID, "transport": "sha256:" + "e" * 64, "touch": ["corpus.ingest@0.1.0"]}
    )
    records.set_artifact_block(post, mime="application/pdf", fields={"page_count": 2})
    records.append_origin_block(
        post, uri="https://example.com/g.pdf", snapshot="2026-05-31T00:00:00Z"
    )
    post.content = segments.emit(
        [
            Section(
                form="document",
                address="page=[1-2]",
                segments=[
                    Segment(atom="text", address="page=1", body="One.", entry=entry),
                    Segment(atom="text", address="page=2", body="Two."),
                ],
            )
        ]
    )
    records.dump(post, p)
    return p


def _decompose(root: Path, into: Path) -> None:
    assert dispatch(["decompose", _ID[:12], "--into", str(into), "--corpus-root", str(root)]) == 0


def _compile(root: Path, workdir: Path, *extra: str) -> int:
    return dispatch(["compile", str(workdir), "--no-lint", "--corpus-root", str(root), *extra])


def _edit_manifest(workdir: Path, old: str, new: str) -> None:
    """Rewrite one manifest line — the surface an authoring pass actually edits, which is why
    a retired field can be minted without anyone reaching for the record grammar."""
    manifest = workdir / "manifest.corpus"
    text = manifest.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in the manifest"
    manifest.write_text(text.replace(old, new, 1), encoding="utf-8")


def _mint_segment_entry(workdir: Path) -> None:
    """Add a retired `entry:` to the first content segment — the pilot's exact move."""
    line = next(
        ln
        for ln in (workdir / "manifest.corpus").read_text("utf-8").splitlines()
        if ln.startswith("seg ")
    )
    _edit_manifest(workdir, line, line + " entry='A TOC label.'")


def _issue_record(root: Path, *, description: str | None = None) -> Path:
    """A minimal record carrying one real `issue` block (spec §4.3.3.2) — `description`
    gives it the retired free-prose field, for the tests about carrying one rather than
    acquiring one."""
    p = root / "records" / "dd" / f"{_ID}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": _ID, "transport": "sha256:" + "e" * 64, "touch": ["corpus.ingest@0.1.0"]}
    )
    records.set_artifact_block(post, mime="application/pdf", fields={"page_count": 1})
    records.append_origin_block(
        post, uri="https://example.com/g.pdf", snapshot="2026-05-31T00:00:00Z"
    )
    post.content = segments.emit(
        [Section(form="document", address="page=1",
                 segments=[Segment(atom="text", address="page=1", body="One.")])]
    )
    fields = {"description": description} if description else None
    records.append_issue_block(
        post, id="partial-content", severity="warning",
        detector="claude-opus-4-8[1m]", address="page=1", fields=fields,
    )
    records.dump(post, p)
    return p


def _mint_issue_description(workdir: Path) -> None:
    """Add a retired `desc=` to the `issue` line — the manifest still reads it tolerantly
    for round-trip (#153/#152), which is exactly the surface an authoring pass could still
    reach for even though the printed grammar no longer teaches it."""
    (workdir / "desc").mkdir(exist_ok=True)
    (workdir / "desc" / "9999-minted.txt").write_text(
        "A sentence 3.5 retired (§4.3.3.2).\n", encoding="utf-8"
    )
    line = next(
        ln
        for ln in (workdir / "manifest.corpus").read_text("utf-8").splitlines()
        if ln.startswith("issue ")
    )
    _edit_manifest(workdir, line, line + " desc=@desc/9999-minted.txt")


# ------------------------------------------------------------------ the refusal


def test_a_rebuild_that_acquires_a_retired_field_is_refused(tmp_path, capsys):
    """The pilot, reproduced: an authoring pass adds one `entry:` to a segment that had
    none, and the write is refused before it lands."""
    root = _corpus(tmp_path)
    rec = _record(root)
    before = rec.read_text("utf-8")
    work = tmp_path / "w"
    _decompose(root, work)
    _mint_segment_entry(work)

    assert _compile(root, work) == 1
    assert rec.read_text("utf-8") == before  # nothing written
    err = capsys.readouterr().err
    assert "REFUSING" in err
    assert "segment entry  0 → 1" in err
    assert "retired at 3.5, §4.3.2.2" in err  # the amendment, cited
    assert "corpus drop-retired" in err  # what removes the ones already carried
    assert "--allow-retired" in err  # the refusal names its own override


def test_the_section_header_fields_are_gated_too(tmp_path, capsys):
    """Not one field — the whole retired grammar, off the one census (§4.3.2.1)."""
    root = _corpus(tmp_path)
    _record(root)
    work = tmp_path / "w"
    _decompose(root, work)
    line = next(
        ln
        for ln in (work / "manifest.corpus").read_text("utf-8").splitlines()
        if ln.startswith("section ")
    )
    _edit_manifest(work, line, line + " entry='A TOC label.'")

    assert _compile(root, work) == 1
    err = capsys.readouterr().err
    assert "section entry  0 → 1" in err
    assert "retired at 3.5, §4.3.2.1" in err


def test_a_frontmatter_field_reintroduced_through_meta_yaml_is_refused(tmp_path, capsys):
    """The metadata zone is the other write surface a working dir exposes — `meta.yaml`'s
    frontmatter mapping is copied through verbatim, so it can mint `canonical:` (§4.2.1)."""
    root = _corpus(tmp_path)
    _record(root)
    work = tmp_path / "w"
    _decompose(root, work)
    meta_file = work / "meta.yaml"
    meta = yaml.safe_load(meta_file.read_text("utf-8"))
    meta["frontmatter"]["canonical"] = "blake3:" + "f" * 64
    meta_file.write_text(yaml.safe_dump(meta, sort_keys=False), encoding="utf-8")

    assert _compile(root, work) == 1
    err = capsys.readouterr().err
    assert "frontmatter canonical  0 → 1" in err
    assert "retired at 3.5, §4.2.1" in err


def test_an_issue_description_acquired_through_the_manifest_is_refused(tmp_path, capsys):
    """#152's other half: an issue is a typed code at an address and carries no prose
    (spec §4.3.3.2) — minting one through the manifest's `desc=@desc/..` is gated exactly
    like a section/segment field."""
    root = _corpus(tmp_path)
    rec = _issue_record(root)
    before = rec.read_text("utf-8")
    work = tmp_path / "w"
    _decompose(root, work)
    _mint_issue_description(work)

    assert _compile(root, work) == 1
    assert rec.read_text("utf-8") == before  # nothing written
    err = capsys.readouterr().err
    assert "REFUSING" in err
    assert "issue description  0 → 1" in err
    assert "retired at 3.5, §4.3.3.2" in err
    assert "--allow-retired" in err


def test_no_base_record_at_the_target_still_refuses(tmp_path, capsys):
    """A record being written for the first time has no baseline to be no worse than, so any
    retired field it carries was acquired by definition. (The stamp goes with the record so
    the base gate warns rather than calling the absence drift — this test is about the
    retirement gate, not that one.)"""
    root = _corpus(tmp_path)
    rec = _record(root)
    work = tmp_path / "w"
    _decompose(root, work)
    _mint_segment_entry(work)
    (work / ".corpus-decompose.json").unlink()
    rec.unlink()

    assert _compile(root, work) == 1
    assert not rec.exists()
    err = capsys.readouterr().err
    assert "segment entry  0 → 1" in err


# ------------------------------------------------------- carrying is not acquiring


def test_a_record_that_already_carries_one_still_compiles(tmp_path, capsys):
    """The population this gate must not turn red: ~7,300 records carry a retired field, and
    editing one for any other reason has to keep working."""
    root = _corpus(tmp_path)
    rec = _record(root, entry="A TOC label.")
    work = tmp_path / "w"
    _decompose(root, work)
    body = sorted((work / "bodies").glob("*.md"))[0]
    body.write_text("One, corrected.\n", encoding="utf-8")

    assert _compile(root, work) == 0
    after = rec.read_text("utf-8")
    assert "One, corrected." in after
    assert "entry: A TOC label." in after  # carried through, unremarked


def test_removing_a_retired_field_compiles(tmp_path, capsys):
    """The gate is one-directional by construction: going DOWN is the sweep's own direction,
    and a hand doing it a record at a time must not be stopped."""
    root = _corpus(tmp_path)
    rec = _record(root, entry="A TOC label.")
    work = tmp_path / "w"
    _decompose(root, work)
    _edit_manifest(work, " entry='A TOC label.'", "")

    assert _compile(root, work) == 0
    assert "entry:" not in rec.read_text("utf-8")


def test_a_second_one_on_an_already_carrying_record_is_still_acquiring(tmp_path, capsys):
    """Counts, not presence — a record carrying one `entry:` may not quietly grow a second."""
    root = _corpus(tmp_path)
    _record(root, entry="A TOC label.")
    work = tmp_path / "w"
    _decompose(root, work)
    line = next(
        ln
        for ln in (work / "manifest.corpus").read_text("utf-8").splitlines()
        if ln.startswith("seg ") and "entry=" not in ln
    )
    _edit_manifest(work, line, line + " entry='Another label.'")

    assert _compile(root, work) == 1
    assert "segment entry  1 → 2" in capsys.readouterr().err


def test_an_issue_that_already_carries_a_description_still_compiles(tmp_path, capsys):
    """The same asymmetry, on the issue-prose field (#152): editing a record for an
    unrelated reason must not lose an already-carried, retired issue description."""
    root = _corpus(tmp_path)
    rec = _issue_record(root, description="A sentence 3.5 retired (§4.3.3.2).")
    work = tmp_path / "w"
    _decompose(root, work)
    body = sorted((work / "bodies").glob("*.md"))[0]
    body.write_text("One, corrected.\n", encoding="utf-8")

    assert _compile(root, work) == 0
    after = rec.read_text("utf-8")
    assert "One, corrected." in after
    assert "description: A sentence 3.5 retired" in after  # carried through, unremarked


def test_removing_an_issue_description_compiles(tmp_path, capsys):
    """Going DOWN is the sweep's own direction; a hand doing it one record at a time must
    not be stopped, same as the section/segment case."""
    root = _corpus(tmp_path)
    rec = _issue_record(root, description="A sentence 3.5 retired (§4.3.3.2).")
    work = tmp_path / "w"
    _decompose(root, work)
    line = next(
        ln
        for ln in (work / "manifest.corpus").read_text("utf-8").splitlines()
        if ln.startswith("issue ")
    )
    _edit_manifest(work, line, line.split(" desc=")[0])

    assert _compile(root, work) == 0
    assert "description:" not in rec.read_text("utf-8")


# ------------------------------------------------------------- the escape hatches


def test_allow_retired_writes_it_anyway(tmp_path, capsys):
    root = _corpus(tmp_path)
    rec = _record(root)
    work = tmp_path / "w"
    _decompose(root, work)
    _mint_segment_entry(work)

    assert _compile(root, work, "--allow-retired") == 0
    assert "entry: A TOC label." in rec.read_text("utf-8")
    err = capsys.readouterr().err
    assert "writing anyway" in err  # still says what it wrote — an override, not a silence
    assert "segment entry  0 → 1" in err


def test_out_is_exempt(tmp_path, capsys):
    """Same exemption the base gate takes: with no authored record at risk there is nothing
    to protect, and probing compile behaviour is exactly what `--out` is for."""
    root = _corpus(tmp_path)
    rec = _record(root)
    before = rec.read_text("utf-8")
    work = tmp_path / "w"
    _decompose(root, work)
    _mint_segment_entry(work)

    elsewhere = tmp_path / "sandbox" / "probe.md"
    assert _compile(root, work, "--out", str(elsewhere)) == 0
    assert "entry: A TOC label." in elsewhere.read_text("utf-8")
    assert rec.read_text("utf-8") == before
    assert "REFUSING" not in capsys.readouterr().err


# ------------------------------------------------------------------- the dry run


@pytest.mark.parametrize(
    ("flags", "expected"), [((), 1), (("--allow-retired",), 0)]
)
def test_the_dry_run_exit_status_predicts_the_real_run(tmp_path, capsys, flags, expected):
    """A dry run that returned 0 on a write the real run refuses would be worse than no dry
    run at all — it is the thing a pass checks before committing to the write."""
    root = _corpus(tmp_path)
    rec = _record(root)
    before = rec.read_text("utf-8")
    work = tmp_path / "w"
    _decompose(root, work)
    _mint_segment_entry(work)

    assert _compile(root, work, "--dry-run", *flags) == expected
    assert rec.read_text("utf-8") == before  # a dry run writes nothing either way
    captured = capsys.readouterr()
    assert ("would refuse" if expected else "writing anyway") in captured.err
    assert "+entry: A TOC label." in captured.out  # the diff still shows what it would do

    assert _compile(root, work, *flags) == expected


# ------------------------------------------------------------ the census itself


def _post(blocks, *, metadata=None, contexts=()):
    post = frontmatter.Post("")
    post.metadata.update({"id": _ID, **(metadata or {})})
    for ctx in contexts:
        post.metadata.setdefault("_contexts", []).append(ctx)
    post.content = segments.emit(blocks)
    return post


def test_the_census_counts_every_retired_construct_under_its_label():
    """One definition, and it is this one: the labels here are the sweep's own manifest
    labels, which is what makes the gate and the sweep provably the same contract."""
    post = _post(
        [
            Section(
                form="document",
                address="el=1.1",
                description="A vouch that 3.5 retired.",
                entry="A TOC label.",
                extra={"title": "An authored title."},
                segments=[
                    Segment(atom="text", address="el=1.1.2", entry="One", description="p",
                            body="One."),
                    Segment(atom="structural", address="el=1.1.1", level=1, body="Heading"),
                ],
            )
        ],
        metadata={"canonical": "blake3:" + "f" * 64, "title": "T", "description": "D"},
        contexts=[
            {"namespace": "relation", "id": "related-information", "fields": {}},
            {"namespace": "reference", "id": "cited-work", "fields": {}},
            {"namespace": "issue", "id": "generic-title", "fields": {}},
            {"namespace": "issue", "id": "partial-content", "fields": {}},  # a real one
            {
                "namespace": "issue", "id": "partial-content",
                "fields": {"description": "A sentence 3.5 retired (§4.3.3.2)."},
            },  # a real one carrying the retired prose too
        ],
    )
    assert dict(retired.census(post)) == {
        "frontmatter canonical": 1,
        "frontmatter title": 1,
        "frontmatter description": 1,
        "section title": 1,
        "section description": 1,
        "section entry": 1,
        "segment description": 1,
        "segment entry": 1,
        "context relation": 1,
        "context reference": 1,
        "context issue/generic-title": 1,
        "issue description": 1,
    }


def test_the_census_leaves_the_structural_byte_marks_own_field_alone():
    """It was never the content segment's `entry:` (§4.3.2.3) — the parser folds a legacy one
    into the body, and a mark's text is not a retired field."""
    post = _post(
        [Segment(atom="structural", address="el=1.1", level=1, body="Heading")]
    )
    assert dict(retired.census(post)) == {}


def test_the_census_reads_the_stored_section_address_off_the_bytes():
    """The one construct that is invisible once parsed: `iter_blocks` re-derives the envelope
    from the children, so the stored value can only be seen in the record's bytes (§12.29)."""
    post = _post([Section(form="document", address="el=1.1",
                          segments=[Segment(atom="text", address="el=1.1.2", body="One.")])])
    text = records.dumps(post)
    assert dict(retired.census(post, text)) == {}  # the serializer no longer writes it
    stored = text.replace("<!--section document-->", "<!--section document\naddress: el=1.1\n-->")
    assert retired.census_text(stored)["section address"] == 1


def test_the_census_is_parse_tolerant():
    """A content zone that will not parse is broken, not retired — the caller says so with a
    better message than a count can (the repo's parse-tolerantly rule)."""
    post = frontmatter.Post("<!--segment text\nthis: is: not: yaml\n-->\n")
    post.metadata.update({"id": _ID, "canonical": "blake3:" + "f" * 64})
    assert dict(retired.census(post)) == {"frontmatter canonical": 1}
    assert dict(retired.census_text("")) == {}


def test_gained_reports_only_the_increases():
    before = retired.census_text("")
    assert retired.gained(before, before) == {}
    after = {"segment entry": 3, "section entry": 1}
    before = {"segment entry": 3, "section description": 2}
    assert retired.gained(before, after) == {"section entry": (0, 1)}
