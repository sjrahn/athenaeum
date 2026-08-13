"""`ath ledger worklist <ref>` — the revision workflow made first-class.

Every edit to the durable layer deterministically yields the dependents to
revisit: a record → the claims and rosters citing it; a fact → the claims,
edges, wikilinks, and interpretations referencing it; an invariant → the
claims violating it. (The fact → dependent-notes direction lands with the
codex build at 5e — notes carry their `generated_from` there.)
"""

from __future__ import annotations

import re
from pathlib import Path

from ledger import invariants as invariants_mod
from ledger.model import derived_uri, load_json_dir, load_lineage


def worklist(ledger_root: Path, ref: str) -> list[str]:
    facts, _ = load_json_dir(ledger_root, "facts/*/*.json")
    interps, _ = load_json_dir(ledger_root, "interpretations/*.json")
    out: list[str] = []

    hash_ = None
    m = re.fullmatch(r"(?:corpus://)?([0-9a-f]{12,64})", ref)
    if m:
        hash_ = m.group(1)

    if hash_:  # record → citers
        for path, o in {**facts, **interps}.items():
            text = path.read_text(encoding="utf-8")
            if hash_ not in text:
                continue
            where = str(path.relative_to(ledger_root))
            sources = o.get("sources") if isinstance(o.get("sources"), dict) else {}
            for c in o.get("claims") or []:
                for e in c.get("evidence") or []:
                    if isinstance(e, dict) and hash_ in (
                            derived_uri(sources, e.get("source"), e.get("anchor")) or ""):
                        out.append(f"claim   {c.get('id')} ({where})")
                        break
            for e in o.get("artifacts") or []:
                if isinstance(e, dict) and hash_ in str(e.get("uri", "")):
                    out.append(f"roster  {o.get('id')} role={e.get('role')} ({where})")
            if any(hash_ in str(b) for b in o.get("based_on") or []):
                out.append(f"interp  {o.get('id')} based_on ({where})")
            for n in o.get("needs") or []:
                if isinstance(n, dict) and hash_ in str(n.get("record", "")):
                    out.append(f"need    {o.get('id')} ({n.get('action')}) ({where})")
        return out

    inv = next((i for i in invariants_mod.load_invariants(ledger_root)[0]
                if i.get("id") == ref), None)
    if inv:  # invariant → violators
        return [f"{sev.upper():7} {msg}" for sev, msg in
                invariants_mod.evaluate([inv], facts)]

    # fact id → dependents
    link = re.compile(rf"\[\[{re.escape(ref)}(?:[\]|#])")
    lineage, _ = load_lineage(ledger_root)
    for key, target in sorted(lineage.items()):
        if target == ref:
            out.append(f"lineage {key} → {ref} (facts/LINEAGE.json)")
    for path, o in facts.items():
        where = str(path.relative_to(ledger_root))
        if o.get("subject") == ref or ref in (o.get("participants") or []):
            out.append(f"edge    {o.get('id')} ({where})")
        for c in o.get("claims") or []:
            if c.get("object") == ref:
                out.append(f"claim   {c.get('id')} object ({where})")
            elif link.search(str(c.get("value", "")) + str(c.get("reasoning", ""))):
                out.append(f"claim   {c.get('id')} wikilink ({where})")
    for path, o in interps.items():
        where = str(path.relative_to(ledger_root))
        if ref in (o.get("about") or []):
            out.append(f"interp  {o.get('id')} about ({where})")
        if any(str(b).startswith(f"{ref}:") for b in o.get("based_on") or []):
            out.append(f"interp  {o.get('id')} based_on ({where})")
        ch = o.get("challenges") or {}
        if isinstance(ch, dict) and str(ch.get("claim", "")).startswith(f"{ref}:"):
            out.append(f"interp  {o.get('id')} challenges ({where})")
    return out
