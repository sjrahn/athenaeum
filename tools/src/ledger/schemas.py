"""Concept schemas — `schemas/{type}.yaml` (§4.4): declared, validating shapes.

A schema is data the checker reads, never code that produces anything. Only
mis-shape is an error; missing schema-declared fields are frontier for the
work-list, never validation failures.
"""

from __future__ import annotations

from pathlib import Path

import yaml

SCHEMA_KEYS = {"type", "description", "fields", "roster_roles"}
FIELD_KEYS = {"target", "description", "expected"}


def load_schemas(ledger_root: Path) -> tuple[dict[str, dict], list[str]]:
    """All concept schemas → ({type: schema}, shape errors)."""
    out: dict[str, dict] = {}
    errors: list[str] = []
    base = ledger_root / "schemas"
    if not base.is_dir():
        return out, errors
    for f in sorted(base.glob("*.yaml")):
        where = f"schemas/{f.name}"
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as e:
            errors.append(f"{where}: invalid YAML — {e}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{where}: top level must be a mapping")
            continue
        if data.get("type") != f.stem:
            errors.append(f"{where}: type {data.get('type')!r} != filename stem {f.stem!r}")
        unknown = set(data) - SCHEMA_KEYS
        if unknown:
            errors.append(f"{where}: unknown keys {sorted(unknown)}")
        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            errors.append(f"{where}: fields must be a mapping")
            fields = {}
        for fname, fspec in fields.items():
            if fspec is None:
                continue
            if not isinstance(fspec, dict):
                errors.append(f"{where}: field {fname!r} must be a mapping (or empty)")
                continue
            bad = set(fspec) - FIELD_KEYS
            if bad:
                errors.append(f"{where}: field {fname!r} unknown keys {sorted(bad)}")
            target = fspec.get("target")
            if target is not None and not (
                isinstance(target, str)
                or (isinstance(target, list)
                    and all(isinstance(t, str) for t in target))
            ):
                errors.append(f"{where}: field {fname!r} target must be a type "
                              "or a list of admissible types")
            if not isinstance(fspec.get("expected", False), bool):
                errors.append(f"{where}: field {fname!r} expected must be a bool")
        roles = data.get("roster_roles")
        if roles is not None and not (
            isinstance(roles, list) and all(isinstance(r, str) for r in roles)
        ):
            errors.append(f"{where}: roster_roles must be a list of strings")
        out[f.stem] = data
    return out, errors
