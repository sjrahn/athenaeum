"""Classify a record — dual-mode, dispatched on arity.

- `corpus classify <target>` (no class id) — **auto / derived**: evaluate every composite
  overlay's `classify_when` predicate (spec §7.4) and stamp the matches as `provenance: auto`
  classify blocks. Idempotent; safe on a `normalized` record; `--dry-run`/`--json` report.
  For a bulk sweep after authoring/editing an overlay, use `corpus reclassify`.

- `corpus classify <target> <ns>/<id> [--field k=v …]` — **manual / asserted**: the operator
  states what the record IS. Validates each `--field` against the overlay's `extended_fields`
  (key + scalar type), checks the record MIME against the overlay's `content_types`, and
  appends (or refreshes) the classify block. Stamps **no** `provenance`, so the auto sweep
  treats it as hand-asserted and never touches it. `corpus lint` re-validates the fields.
"""

from __future__ import annotations

import argparse
import json
import sys

from corpus import classify_rules, paths, records, schemas, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="record to classify (hash / hex prefix / path).")
    parser.add_argument(
        "class_id",
        nargs="?",
        default=None,
        help="manual mode: a `<ns>/<id>[/<subtype>]` to assert. Omit for the auto evaluator.",
    )
    parser.add_argument(
        "--field",
        action="append",
        metavar="KEY=VALUE",
        help="manual mode: set an extended field (repeatable); validated against the overlay.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report without writing."
    )
    parser.add_argument("--json", action="store_true", help="auto mode: emit a single JSON object.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    record_id, record_file = paths.resolve_record(corpus_root, args.target)
    post = records.load(record_file)

    if args.class_id is not None:
        return _run_manual(args, corpus_root, record_id, record_file, post)
    if args.field:
        sys.exit("--field is only valid in manual mode (give a `<ns>/<id>` class id).")
    return _run_auto(args, record_id, record_file, post, corpus_root)


# ---------- auto (classify_when) ---------- #


def _run_auto(args, record_id, record_file, post, corpus_root) -> int:
    delta = classify_rules.apply_auto_classifications(corpus_root, post)
    if delta.changed and not args.dry_run:
        records.dump(post, record_file)

    if args.json:
        json.dump(
            {
                "record": record_id,
                "added": delta.added,
                "removed": delta.removed,
                "kept": delta.kept,
                "changed": delta.changed,
                "dry_run": bool(args.dry_run),
                "why": {m.class_id: m.why for m in delta.matches},
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    if not delta.changed:
        n = len(delta.matches)
        print(f"{record_id[:12]}: no change ({n} auto classification(s) already current).")
        return 0
    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {record_id[:12]}:")
    why = {m.class_id: m.why for m in delta.matches}
    for class_id in delta.added:
        print(f"  + {class_id}  ({why.get(class_id, '')})")
    for class_id in delta.removed:
        print(f"  - {class_id}")
    return 0


# ---------- manual (asserted) ---------- #


def _run_manual(args, corpus_root, record_id, record_file, post) -> int:
    namespace, id_, subtype = records._split_namespaced(args.class_id)
    schema = schemas.load_classification_schema(corpus_root, namespace)
    if schema is None:
        sys.exit(
            f"no such classification overlay: schema/composite/{namespace}/{namespace}.yaml not found."
        )
    sub_schema = None
    if id_ != namespace:
        sub_schema = schemas.load_classification_subclass(corpus_root, namespace, id_)
        if not isinstance(sub_schema, dict):
            available = (
                ", ".join(schemas.list_classification_subclasses(corpus_root, namespace))
                or "(none declared)"
            )
            sys.exit(f"no subclass {id_!r} in namespace {namespace!r}. available: {available}")

    fields = _parse_fields(args.field, schema, sub_schema, namespace, id_)

    media_type = records.media_type_for(post)
    ns_types = (schema.get("applies_to") or {}).get("content_types") or []
    sub_types = (sub_schema.get("applies_to") or {}).get("content_types") if isinstance(sub_schema, dict) else None
    applies_types = sub_types or ns_types  # more-specific subclass declaration wins
    if applies_types and media_type and media_type not in applies_types:
        sys.exit(
            f"classification `{args.class_id}` doesn't apply to mime `{media_type}` "
            f"(declared content_types: {', '.join(applies_types)})."
        )

    found = False
    for c in records.iter_classify_blocks(post):
        if c.get("namespace") == namespace and c.get("id") == id_ and c.get("subtype") == subtype:
            c.setdefault("fields", {}).update(fields)
            found = True
            break
    if not found:
        records.append_classify_block(post, namespace=namespace, id=id_, subtype=subtype, fields=fields)

    touches.record_touch(post, touches.script_identifier("classify"))
    if not args.dry_run:
        records.dump(post, record_file)

    verb = "would classify" if args.dry_run else "classified"
    print(f"{verb}: {args.class_id} on {record_id[:12]}… ({len(fields)} field(s))")
    return 0


def _parse_fields(raw_fields, schema, sub_schema, namespace, id_) -> dict[str, object]:
    """Parse repeated `--field key=value`, validating each key against the overlay's
    `extended_fields` (namespace + subclass union) and coercing to its declared scalar type."""
    out: dict[str, object] = {}
    if not raw_fields:
        return out
    ns_fields = (schema.get("extended_fields") or {}) if isinstance(schema, dict) else {}
    sub_fields = (sub_schema.get("extended_fields") or {}) if isinstance(sub_schema, dict) else {}
    declared_specs = {**ns_fields, **sub_fields}
    ns_path = f"schema/composite/{namespace}/{namespace}.yaml"
    sub_path = f"schema/composite/{namespace}/{id_}.yaml"
    for spec in raw_fields:
        if "=" not in spec:
            sys.exit(f"--field must be key=value, got: {spec!r}")
        key, _, value = spec.partition("=")
        key = key.strip()
        if not key:
            sys.exit(f"--field has empty key: {spec!r}")
        if declared_specs and key not in declared_specs:
            where = f"{ns_path}#extended_fields" + (
                f" or {sub_path}#extended_fields" if sub_schema is not None else ""
            )
            sys.exit(f"field `{key}` not declared in {where}.")
        out[key] = _coerce_field_value(value, declared_specs.get(key), key)
    return out


def _coerce_field_value(value: str, fspec, key: str) -> object:
    """Coerce a `--field` string to the overlay's declared scalar type (integer/number/boolean);
    string and structured (array/object) declarations pass through as the raw string."""
    if not isinstance(fspec, dict):
        return value
    t = str(fspec.get("type") or "string").lower()
    if t in ("integer", "int"):
        try:
            return int(value)
        except ValueError:
            sys.exit(f"--field {key}={value!r}: declared type `integer` but value is not an integer.")
    if t in ("number", "float"):
        try:
            return float(value)
        except ValueError:
            sys.exit(f"--field {key}={value!r}: declared type `{t}` but value is not a number.")
    if t in ("boolean", "bool"):
        low = value.strip().lower()
        if low in ("true", "yes", "on", "1"):
            return True
        if low in ("false", "no", "off", "0"):
            return False
        sys.exit(f"--field {key}={value!r}: declared type `boolean` but value is not a boolean.")
    return value
