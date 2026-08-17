"""Per-record diagnostic snapshot — the normalizer's open-the-pass tool.

`corpus diagnose <hash>` emits a single markdown one-pager: the §4.2 core frontmatter, each
metadata-zone block, the content-zone block TOC, the derived classifications/issues/uris views,
and a quick-lint section. A normalizer pass runs this first. The Lint section here is the
`DIAGNOSE_QUICK_RULES` subset — the full overlay-aware ruleset (body sanity, embed
integrity, …) is the verification gate at `corpus lint <hash>`, which the pass must clear
before the queue's `finalize` closes it (spec §8.5's pass gate, 3.2: formed-where-declared
+ lint clean).

`--json` emits the same data as one JSON object. Markdown to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from corpus import derived_views, paths, records, segments
from corpus import lint as _lint
from corpus import mime as _mime
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

CORE_FIELDS = (
    "id",
    "title",
    "description",
    "hash",
    "visibility",
    "touch",
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="record id (hash / ≥4-char prefix) or path to record .md.")
    parser.add_argument(
        "--skip-remote-check",
        action="store_true",
        help="accepted for compatibility; athenaeum's artifact check is local-only (no-op).",
    )
    parser.add_argument("--json", action="store_true", help="emit a single JSON object.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    record_id, record_file = paths.resolve_record(corpus_root, args.target)
    post = records.load(record_file)
    blocks = list(segments.iter_blocks(post.content or ""))

    findings = [
        {"code": f.rule_id, "severity": f.severity, "message": f.message}
        for f in _lint.lint(post, blocks, corpus_root, rules=_lint.DIAGNOSE_QUICK_RULES)
    ]
    artifact_info = _check_artifact(corpus_root, record_id, post)

    if args.json:
        _emit_json(corpus_root, record_id, post, blocks, findings, artifact_info)
    else:
        _emit(corpus_root, record_id, post, blocks, findings, artifact_info)
    return 0


def _check_artifact(corpus_root: Path, record_id: str, post) -> dict[str, Any]:
    """Local artifact-presence snapshot (no remote probe)."""
    media_type = records.media_type_for(post)
    if not media_type:
        return {"skip": True, "reason": "record has no <!--artifact--> block"}
    try:
        ext = _mime.extension_for(media_type)
    except Exception:
        ext = ""
    if not ext or ext == "bin":
        return {"skip": True, "reason": f"no known extension for mime {media_type!r}"}
    expected = paths.artifact_path(corpus_root, record_id, ext)
    local = expected.is_file()
    return {
        "media_type": media_type,
        "extension": ext,
        "expected_path": str(expected.relative_to(corpus_root)),
        "local": local,
        "fix": "" if local else f"not hydrated locally. run: corpus store fetch {record_id[:12]}",
    }


# ---------- markdown ---------- #


def _emit(corpus_root, record_id, post, blocks, findings, artifact_info) -> None:
    metadata = post.metadata
    title_field = records.derived_editorial_field(post, corpus_root, "title")
    desc_field = records.derived_editorial_field(post, corpus_root, "description")
    state = records.derived_state(post, corpus_root)
    media_type = records.media_type_for(post)
    touch_chain = metadata.get("touch") or []
    if isinstance(touch_chain, str):
        touch_chain = [touch_chain]
    last = touch_chain[-1] if touch_chain else ""

    print(f"# {record_id[:12]}… — {title_field.value}\n")
    print(
        f"`state: {state}` · `title: {title_field.layer or 'none'}` · "
        f"`description: {desc_field.layer or 'none'}` · `mime: {media_type}` · "
        f"`touch: {len(touch_chain)}` · `last: {last}`\n"
    )

    print("## Lint\n")
    if not findings:
        print("✓ no findings.")
    else:
        errs = sum(1 for f in findings if f["severity"] == "error")
        warns = sum(1 for f in findings if f["severity"] == "warning")
        bits = [f"{errs} error(s)"] if errs else []
        if warns:
            bits.append(f"{warns} warning(s)")
        print(f"⚠ {' · '.join(bits) or f'{len(findings)} finding(s)'}.\n")
        for f in findings:
            print(f"- {'❌' if f['severity'] == 'error' else '⚠'} **{f['code']}**: {f['message']}")
    print()

    print("## Artifact\n")
    if artifact_info.get("skip"):
        print(f"_skipped — {artifact_info.get('reason', 'no mime')}._")
    else:
        print(f"- expected: `{artifact_info['expected_path']}`")
        print(f"- local:    {'present' if artifact_info['local'] else '**MISSING**'}")
        if artifact_info.get("fix"):
            print(f"\n⚠ {artifact_info['fix']}")
    print()

    print("## Frontmatter (§4.2 core)\n")
    print("```yaml")
    yaml.safe_dump(
        {k: metadata[k] for k in CORE_FIELDS if k in metadata},
        sys.stdout,
        sort_keys=False,
        allow_unicode=True,
        width=10**9,
    )
    print("```\n")

    artifact = records.artifact_block(post)
    if artifact:
        print(f"## `<!--artifact-->` block\n\nmime: `{artifact.get('mime')}`\n")
        _yaml_block(artifact.get("fields") or {}, empty="_(no extended fields)_")

    _emit_block_group("`<!--origin-->`", list(records.iter_origin_blocks(post)), _origin_label)
    _emit_block_group("`<!--context-->`", list(records.iter_context_blocks(post)), _ns_label)

    print("## Derived views\n")
    print(f"- **classifications[]**: {records.derived_classifications(post) or '_(empty)_'}")
    print(f"- **issues[]**: {len(derived_views.issues(post))} entry(s)")
    print(f"- **uris[]**: {derived_views.uris(corpus_root, post)}\n")

    _emit_toc(post, blocks)


def _yaml_block(fields: dict, *, empty: str) -> None:
    if fields:
        print("```yaml")
        yaml.safe_dump(fields, sys.stdout, sort_keys=False, allow_unicode=True, width=10**9)
        print("```")
    else:
        print(empty)
    print()


def _origin_label(ob: dict) -> str:
    id_ = ob.get("id") or "_(unqualified)_"
    return f"{id_}/{ob['subtype']}" if ob.get("subtype") else id_


def _ns_label(cb: dict) -> str:
    ns = cb.get("namespace")
    id_ = cb.get("id")
    label = id_ if ns == id_ else f"{ns}/{id_}"
    return f"{label}/{cb['subtype']}" if cb.get("subtype") else label


def _emit_block_group(kind: str, items: list[dict], labeller) -> None:
    if not items:
        return
    print(f"## {kind} blocks ({len(items)})\n")
    for i, blk in enumerate(items, 1):
        print(f"### {i}. {labeller(blk)}\n")
        _yaml_block(blk.get("fields") or {}, empty="_(no fields)_")


def _emit_toc(post, blocks) -> None:
    total_segments = sum(len(b.segments) if isinstance(b, segments.Section) else 1 for b in blocks)
    embed_count = len(list(records.iter_embed_blocks(post)))
    print(
        f"## Content-zone blocks ({len(blocks)} top-level, {total_segments} segment(s), "
        f"{embed_count} embed(s))\n"
    )
    print("| # | kind | atom | children | entry |")
    print("|---|------|------|----------|-------|")
    for i, blk in enumerate(blocks, 1):
        entry = (getattr(blk, "entry", None) or "*(unnormalized)*").replace("|", "\\|").replace("\n", " ")
        if isinstance(blk, segments.Section):
            print(f"| {i} | section | | {len(blk.segments)} | {entry} |")
        else:
            print(f"| {i} | segment | {blk.atom} | — | {entry} |")


# ---------- json ---------- #


def _emit_json(corpus_root, record_id, post, blocks, findings, artifact_info) -> None:
    toc = [
        {
            "kind": "section" if isinstance(b, segments.Section) else "segment",
            "atom": None if isinstance(b, segments.Section) else b.atom,
            "children": len(b.segments) if isinstance(b, segments.Section) else None,
            "entry": getattr(b, "entry", None),
        }
        for b in blocks
    ]
    title_field = records.derived_editorial_field(post, corpus_root, "title")
    desc_field = records.derived_editorial_field(post, corpus_root, "description")
    json.dump(
        {
            "record": record_id,
            "title": title_field.value,
            "title_layer": title_field.layer,
            "description": desc_field.value,
            "description_layer": desc_field.layer,
            "state": records.derived_state(post, corpus_root),
            "mime": records.media_type_for(post),
            "lint": findings,
            "artifact": artifact_info,
            "classifications": records.derived_classifications(post),
            "issues": len(derived_views.issues(post)),
            "uris": derived_views.uris(corpus_root, post),
            "blocks": toc,
        },
        sys.stdout,
        indent=2,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
