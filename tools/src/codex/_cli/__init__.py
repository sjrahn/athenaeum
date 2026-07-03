"""`ath codex` — the codex layer's deterministic surface (`spec/codex.md`)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ath.manifest import ManifestError, find_root, load
from ledger._cli import _system as ledger_system

_USAGE = """\
usage: ath codex <name> <command> [options...]

The codex layer's deterministic surface (spec/codex.md). <name> is a
manifest-registered codex member.

Commands:
  scope         report the materialized scope (facts + riding interpretations)
  notes         regenerate the vault (notes/) from the ledger — private profile
  build         compile a profile's content tree: resolve citations, raster
                embeds, leak-check public output, emit the build certificate
                (--profile private|<declared>; default private)
  check         validation (§7): manifest sanity, scope integrity, vault
                currency (notes/ vs a fresh generation)
"""


def _codex_root(base: Path, name: str) -> Path:
    members = {m.name: m for m in load(base) if m.layer == "codices"}
    if name not in members:
        raise ManifestError(f"no codex {name!r} in the manifest "
                            f"(have: {', '.join(sorted(members))})")
    return members[name].path


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_USAGE, end="")
        return 0
    if len(args) < 2:
        print(_USAGE, end="", file=sys.stderr)
        return 2
    name, cmd, rest = args[0], args[1], args[2:]
    ap = argparse.ArgumentParser(prog=f"ath codex {name} {cmd}")
    ap.add_argument("--root", type=Path, default=None)
    if cmd == "build":
        ap.add_argument("--profile", default="private")
    ns = ap.parse_args(rest)
    try:
        base = find_root(ns.root)
        codex_root = _codex_root(base, name)
        ledger_root, join, _ = ledger_system(ns.root)
    except ManifestError as e:
        print(f"ath codex: {e}", file=sys.stderr)
        return 2
    from codex.manifest import CodexError, load_codex

    try:
        manifest = load_codex(codex_root)
    except CodexError as e:
        print(f"ath codex: {e}", file=sys.stderr)
        return 2

    if cmd == "scope":
        from codex.scope import materialize

        scoped, riding, problems = materialize(ledger_root, manifest)
        by_type: dict[str, int] = {}
        for o in scoped.values():
            by_type[str(o.get("type"))] = by_type.get(str(o.get("type")), 0) + 1
        for t, n in sorted(by_type.items()):
            print(f"{t:<16} {n}")
        print(f"\n{len(scoped)} facts, {len(riding)} riding interpretations")
        for p in problems:
            print(f"WARN  {p}", file=sys.stderr)
        return 0

    if cmd == "notes":
        from datetime import date

        from codex.notes import generate
        from codex.scope import materialize

        scoped, riding, problems = materialize(ledger_root, manifest)
        vault = generate(scoped, riding, join, profile="private",
                         today=date.today().isoformat())
        import shutil

        notes_dir = codex_root / "notes"
        if notes_dir.exists():
            shutil.rmtree(notes_dir)
        for relpath, text in vault.items():
            dest = notes_dir / relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
        print(f"regenerated {len(vault)} notes in {notes_dir}")
        for p in problems:
            print(f"WARN  {p}", file=sys.stderr)
        return 0

    if cmd == "build":
        from datetime import date

        from codex.build import BuildError, build

        try:
            res = build(manifest, ledger_root, join, profile=ns.profile,
                        today=date.today().isoformat())
        except BuildError as e:
            print(f"ath codex build: {e}", file=sys.stderr)
            return 2
        for p in res.problems:
            print(f"ERROR {p}")
        print(f"{res.notes} notes, {res.citations} citations resolved, "
              f"{res.rastered} rastered — profile {res.profile}")
        if res.certificate:
            print(f"certificate: {res.certificate.relative_to(manifest.root)}")
        return 0 if res.ok else 1

    if cmd == "check":
        from codex.notes import generate
        from codex.scope import materialize

        scoped, riding, problems = materialize(ledger_root, manifest)
        errors = list(problems)
        notes_dir = codex_root / "notes"
        if not notes_dir.is_dir():
            errors.append("no notes/ vault — run `ath codex … notes`")
        else:
            # currency: the vault must equal a fresh generation modulo the
            # `updated` stamp (notes are regenerable, never hand-drifted)
            import re

            def strip_updated(t: str) -> str:
                return re.sub(r"^updated: .*$", "updated:", t, flags=re.M)

            fresh = generate(scoped, riding, join, profile="private", today="")
            on_disk = {str(p.relative_to(notes_dir)): p.read_text(encoding="utf-8")
                       for p in notes_dir.rglob("*.md")}
            for rel in sorted(set(fresh) | set(on_disk)):
                if rel not in on_disk:
                    errors.append(f"notes/{rel}: missing — regenerate")
                elif rel not in fresh:
                    errors.append(f"notes/{rel}: no backing fact in scope")
                elif strip_updated(fresh[rel]) != strip_updated(on_disk[rel]):
                    errors.append(f"notes/{rel}: stale — regenerate")
        for e in errors:
            print(f"ERROR {e}")
        print(f"{len(scoped)} facts in scope, {len(riding)} riding — "
              f"{len(errors)} errors")
        return 0 if not errors else 1

    print(f"ath codex: unknown command {cmd!r}", file=sys.stderr)
    return 2
