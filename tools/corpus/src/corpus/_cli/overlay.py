"""Describe an overlay — the field-spec + tactics lookup for the normalizer.

`corpus overlay <ns>/<id>[/<subtype>]` describes a **classification** (composite) overlay:
its `applies_to` (MIME + cues + excludes), the union of `extended_fields` from the namespace
yaml and (when given) the subclass yaml as a table, the source paths, the description, and the
`normalization.guidance`. Use it before `corpus classify <hash> <ns>/<id> --field …` to know
what fields are valid.

`corpus overlay <host>` describes an **origin** overlay (`schema/origin/<host>.yaml`): its
host match, the operational sections it declares (capture/transcription/canonical/metadata),
and its `normalization.guidance` — so the normalizer can read a host's guidance at normalize
time without opening the yaml (the same guidance `corpus guidance <id>` shows once an origin
overlay is applied to a record).

Markdown to stdout; non-zero when neither a composite namespace nor an origin overlay matches.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from corpus import records, schemas
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "class_id", help="overlay id, e.g. `source/majority-report`, `article`, `alldata/wiring`."
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    namespace, id_, subtype = records._split_namespaced(args.class_id)
    schema = schemas.load_classification_schema(corpus_root, namespace)
    if schema is None:
        # Not a composite namespace — try an origin overlay (`schema/origin/<host>.yaml`)
        # so `corpus overlay <host>` surfaces a host's guidance, the way `corpus guidance`
        # does once that origin overlay is applied to a record.
        origin = schemas.load_origin_overlay_by_id(corpus_root, args.class_id)
        if origin is not None:
            return _run_origin(corpus_root, args.class_id, origin)
        sys.exit(
            f"no overlay {args.class_id!r}: neither a composite namespace "
            f"(schema/composite/{namespace}/{namespace}.yaml) nor an origin overlay "
            f"(schema/origin/{args.class_id}.yaml)."
        )

    sub_schema: dict[str, Any] | None = None
    sub_label = ""
    if id_ != namespace:
        sub_schema = schemas.load_classification_subclass(corpus_root, namespace, id_)
        if not isinstance(sub_schema, dict):
            available = (
                ", ".join(schemas.list_classification_subclasses(corpus_root, namespace))
                or "(none declared)"
            )
            sys.exit(f"no subclass {id_!r} in namespace {namespace!r}. available: {available}")
        sub_label = f"/{id_}"

    full_id = f"{namespace}{sub_label}" + (f"/{subtype}" if subtype else "")
    kind = str(schema.get("kind") or "").strip() or "(unspecified)"
    print(f"# overlay {full_id}  (kind: {kind})\n")
    src = f"_source: `schema/composite/{namespace}/{namespace}.yaml`"
    src += f" + `schema/composite/{namespace}/{id_}.yaml`_" if sub_schema is not None else "_"
    print(src + "\n")

    print("## applies_to\n")
    _print_applies_to("namespace", schema.get("applies_to") or {})
    if sub_schema is not None:
        _print_applies_to(f"subclass {id_}", sub_schema.get("applies_to") or {})
    print()

    print("## extended_fields\n")
    ns_fields = (schema.get("extended_fields") or {}) if isinstance(schema, dict) else {}
    sub_fields = (sub_schema.get("extended_fields") or {}) if sub_schema is not None else {}
    if not ns_fields and not sub_fields:
        print("_(none declared)_\n")
    else:
        if ns_fields:
            print(f"_From `schema/composite/{namespace}/{namespace}.yaml`:_\n")
            _print_fields_table(ns_fields)
            print()
        if sub_fields:
            print(f"_From subclass `{id_}`:_\n")
            _print_fields_table(sub_fields)
            print()

    desc_ns = str(schema.get("description") or "").strip()
    desc_sub = str((sub_schema or {}).get("description") or "").strip()
    if desc_ns or desc_sub:
        print("## description\n")
        if desc_ns:
            print(f"_Namespace:_  {desc_ns[:800]}{'…' if len(desc_ns) > 800 else ''}\n")
        if desc_sub:
            print(f"_Subclass:_   {desc_sub[:800]}{'…' if len(desc_sub) > 800 else ''}\n")

    guid_ns = _guidance(schema)
    guid_sub = _guidance(sub_schema)
    if guid_ns or guid_sub:
        print("## normalization.guidance\n")
        print(
            "_The tactical guidance to apply once you've decided this overlay applies — "
            "read it here rather than opening the yaml._\n"
        )
        if guid_ns:
            print(f"### namespace `{namespace}`\n\n{guid_ns}\n")
        if guid_sub:
            print(f"### subclass `{id_}`\n\n{guid_sub}\n")

    print(f"_To apply: `corpus classify <hash> {full_id} --field key=value ...`_")
    return 0


def _run_origin(corpus_root, oid: str, overlay: dict[str, Any]) -> int:
    print(f"# overlay {oid}  (origin)\n")
    print(f"_source: `{_origin_relpath(corpus_root, oid)}`_\n")

    print("## applies_to\n")
    applies = overlay.get("applies_to") or {}
    pats = [str(applies["host_pattern"])] if applies.get("host_pattern") else []
    pats += [str(p) for p in (applies.get("host_patterns") or [])]
    if pats:
        print(f"- host: {', '.join(pats)}")
        if applies.get("include_subdomains"):
            print("- include_subdomains: true")
    else:
        print(f"- _(matched by id `{oid}` — no host pattern declared)_")
    print()

    declared = [
        k
        for k in ("capture", "transcription", "canonical", "metadata")
        if isinstance(overlay.get(k), dict) and overlay.get(k)
    ]
    if declared:
        print("## declares\n")
        print("_Operational sections (capture/draft pathways), not normalizer fields:_\n")
        for k in declared:
            print(f"- `{k}`")
        print()

    print("## normalization.guidance\n")
    print(
        "_The tactical guidance to apply when normalizing a record from this origin — "
        "read it here rather than opening the yaml._\n"
    )
    guid = _guidance(overlay)
    print(guid if guid else "_(no `normalization.guidance` declared)_")
    print()
    return 0


def _origin_relpath(corpus_root, oid: str) -> str:
    """Athenaeum's flat `origin/<id>.yaml`, falling back to the back-compat `web/`/`otherwise/`."""
    base = corpus_root / "schema" / "origin"
    for sub in ("", "web", "otherwise"):
        cand = (base / sub / f"{oid}.yaml") if sub else (base / f"{oid}.yaml")
        if cand.is_file():
            return str(cand.relative_to(corpus_root))
    return f"schema/origin/{oid}.yaml"


def _guidance(schema: dict[str, Any] | None) -> str:
    if not isinstance(schema, dict):
        return ""
    norm = schema.get("normalization")
    return str(norm.get("guidance") or "").strip() if isinstance(norm, dict) else ""


def _print_applies_to(label: str, applies_to: dict[str, Any]) -> None:
    types = applies_to.get("content_types") or []
    cues_block = applies_to.get("cues") or {}
    body = cues_block.get("body_contains") or [] if isinstance(cues_block, dict) else []
    if not applies_to or (not types and not body):
        print(f"- **{label}**: _(no axes declared — overlay applies by shape only)_")
        return
    print(f"- **{label}**:")
    if types:
        print(f"  - content_types: {', '.join(str(t) for t in types)}")
    if body:
        print(f"  - cues.body_contains: {len(body)} phrase(s)")
        for phrase in body[:10]:
            print(f"    - {phrase!s}")
        if len(body) > 10:
            print(f"    - _(+{len(body) - 10} more)_")
    excl = cues_block.get("excludes") if isinstance(cues_block, dict) else None
    if isinstance(excl, dict) and excl:
        print(f"  - cues.excludes: {dict(excl)}")


def _print_fields_table(fields: dict[str, Any]) -> None:
    print("| field | type | required | source | description |")
    print("|---|---|---|---|---|")
    for name, spec in fields.items():
        if not isinstance(spec, dict):
            print(f"| `{name}` | _(unspecified)_ | | | |")
            continue
        ftype = str(spec.get("type") or "string")
        required = "yes" if spec.get("required") else "no"
        source = str(spec.get("source") or "")
        desc = " ".join(str(spec.get("description") or "").split())[:80].replace("|", "\\|")
        print(f"| `{name}` | {ftype} | {required} | {source} | {desc} |")
