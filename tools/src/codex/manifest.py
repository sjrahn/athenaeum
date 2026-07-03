"""`codex.yaml` — the codex manifest (`spec/codex.md` §2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class CodexError(RuntimeError):
    pass


@dataclass(frozen=True)
class Scope:
    types: tuple[str, ...] = ()
    roots: tuple[str, ...] = ()
    traverse_types: tuple[str, ...] = ()  # traversal bound; defaults to `types`
    tags: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()  # visible editorial carve-outs

    @property
    def traversal_bound(self) -> tuple[str, ...]:
        return self.traverse_types or self.types


@dataclass(frozen=True)
class CodexManifest:
    name: str
    display_name: str
    description: str
    scope: Scope
    profiles: dict[str, dict] = field(default_factory=dict)
    root: Path = Path(".")


def load_codex(codex_root: Path) -> CodexManifest:
    path = codex_root / "codex.yaml"
    if not path.is_file():
        raise CodexError(f"{codex_root} has no codex.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    scope = data.get("scope") or {}
    if not isinstance(scope, dict):
        raise CodexError("codex.yaml scope: must be a mapping")

    def strs(key: str) -> tuple[str, ...]:
        v = scope.get(key) or []
        if not isinstance(v, list):
            raise CodexError(f"codex.yaml scope.{key}: must be a list")
        return tuple(str(x) for x in v)

    profiles = data.get("profiles") or {}
    for pname, spec in profiles.items():
        redact = (spec or {}).get("redact", "exclude")
        if redact not in ("exclude", "stub"):
            raise CodexError(f"profile {pname!r}: redact must be exclude|stub")
    return CodexManifest(
        name=str(data.get("name") or codex_root.name),
        display_name=str(data.get("display_name") or data.get("name") or codex_root.name),
        description=str(data.get("description") or ""),
        scope=Scope(
            types=strs("types"),
            roots=strs("roots"),
            traverse_types=strs("traverse_types"),
            tags=strs("tags"),
            exclude=strs("exclude"),
        ),
        profiles={str(k): dict(v or {}) for k, v in profiles.items()},
        root=codex_root,
    )
