"""The uncommitted derived index — entity resolution before minting.

`spec/ledger.md` (state derived, never stored) + ticket #174: one pass over
`facts/*/*.json` + `interpretations/*.json` builds lookup structures — by id,
by name/alias, and by cited corpus hash — that `ath ledger resolve` (and
future minting/harvest passes) query instead of re-scanning the fact tree.
Rebuildable at any time from the fact files; cached under `.cache/` for
speed, never committed.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path

from ledger.model import CORPUS_REF_RE, is_edge, is_redirect, load_json_dir, source_target

INDEX_VERSION = 1
CACHE_REL = Path(".cache") / "ledger-index.json"

_WORD_RE = re.compile(r"[a-z0-9]+")

_BASIS_RANK = {
    "id": 0,
    "redirect": 1,
    "name": 2,
    "alias": 2,
    "id-prefix": 3,
    "substring": 4,
    "tokens": 5,
}


def tokenize(s: object) -> list[str]:
    return _WORD_RE.findall(str(s).lower())


def normalize_text(s: object) -> str:
    return " ".join(tokenize(s))


def slugify(s: object) -> str:
    return "-".join(tokenize(s))


def build_index(ledger_root: Path) -> dict:
    facts, fact_errors = load_json_dir(ledger_root, "facts/*/*.json")
    interps, interp_errors = load_json_dir(ledger_root, "interpretations/*.json")
    skipped: list[str] = [*fact_errors, *interp_errors]

    entries: dict[str, dict] = {}
    names: dict[str, list[str]] = {}
    citations: dict[str, dict[str, list[str]]] = {}

    def add_name(key: str, fid: str) -> None:
        if not key:
            return
        bucket = names.setdefault(key, [])
        if fid not in bucket:
            bucket.append(fid)

    def cite(h: str, *, claim: str | None = None, roster: str | None = None,
             based_on: str | None = None) -> None:
        bucket = citations.setdefault(h, {"claims": [], "rosters": [], "based_on": []})
        for field, val in (("claims", claim), ("rosters", roster), ("based_on", based_on)):
            if val is not None and val not in bucket[field]:
                bucket[field].append(val)

    for path, fact in facts.items():
        fid = fact.get("id")
        if not isinstance(fid, str) or not fid:
            skipped.append(f"{path.relative_to(ledger_root)}: missing id")
            continue
        rel = str(path.relative_to(ledger_root))
        # type == parent directory name (facts/{type}/{slug}.json), not the
        # fact's own `type` field — tolerant of a field that disagrees.
        ftype = path.parent.name

        if is_redirect(fact):
            entries[fid] = {
                "file": rel, "kind": "redirect", "type": ftype, "name": "",
                "aliases": [], "merged_into": fact.get("merged_into"),
            }
            continue

        kind = "edge" if is_edge(fact) else "concept"
        aliases = [a for a in (fact.get("aliases") or []) if isinstance(a, str)]
        name = fact.get("name") or fact.get("title") or ""
        entries[fid] = {
            "file": rel, "kind": kind, "type": ftype, "name": name, "aliases": aliases,
        }
        add_name(normalize_text(name), fid)
        for a in aliases:
            add_name(normalize_text(a), fid)

        sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
        for claim in fact.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            cid = claim.get("id")
            if not isinstance(cid, str):
                continue
            for ev in claim.get("evidence") or []:
                if not isinstance(ev, dict):
                    continue
                target = source_target(sources.get(str(ev.get("source"))))
                if target is not None and target[0] == "record":
                    cite(target[1], claim=cid)
        for art in fact.get("artifacts") or []:
            if not isinstance(art, dict):
                continue
            m = CORPUS_REF_RE.search(str(art.get("uri", "")))
            if m:
                cite(m.group(1), roster=fid)

    for path, interp in interps.items():
        iid = interp.get("id")
        if not isinstance(iid, str) or not iid:
            skipped.append(f"{path.relative_to(ledger_root)}: missing id")
            continue
        entries[iid] = {
            "file": str(path.relative_to(ledger_root)), "kind": "interpretation",
            "type": interp.get("kind") or "", "name": "", "aliases": [],
        }
        for b in interp.get("based_on") or []:
            m = CORPUS_REF_RE.search(str(b))
            if m:
                cite(m.group(1), based_on=iid)

    n_files, max_mtime = _stat_pass(ledger_root)
    return {
        "version": INDEX_VERSION,
        "stamp": {"files": n_files, "max_mtime": max_mtime},
        "entries": entries,
        "names": names,
        "citations": citations,
        "skipped": skipped,
    }


def _stat_pass(ledger_root: Path) -> tuple[int, float]:
    """File count + max mtime over the two glob sets — a cheap stat pass, no
    parsing — the staleness signal `load_or_build`/`is_fresh` compare against
    the cached stamp."""
    n = 0
    max_mtime = 0.0
    for pattern in ("facts/*/*.json", "interpretations/*.json"):
        for p in ledger_root.glob(pattern):
            n += 1
            with contextlib.suppress(OSError):
                max_mtime = max(max_mtime, p.stat().st_mtime)
    return n, max_mtime


def _cache_path(ledger_root: Path) -> Path:
    return ledger_root / CACHE_REL


def _read_cache(ledger_root: Path) -> dict | None:
    p = _cache_path(ledger_root)
    if not p.is_file():
        return None
    try:
        cached = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return cached if isinstance(cached, dict) else None


def is_fresh(ledger_root: Path, cached: dict | None = None) -> bool:
    """Whether the on-disk cache (or *cached*, to skip a re-read) matches the
    ledger's current stat-pass stamp."""
    if cached is None:
        cached = _read_cache(ledger_root)
    if cached is None or cached.get("version") != INDEX_VERSION:
        return False
    n, max_mtime = _stat_pass(ledger_root)
    return cached.get("stamp") == {"files": n, "max_mtime": max_mtime}


def write_cache(ledger_root: Path, index: dict) -> bool:
    """Persist *index* atomically. Returns False (never raises) when
    `.cache/` can't be written — index building degrades to in-memory-only."""
    cache_path = _cache_path(ledger_root)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_name(cache_path.name + ".tmp")
        tmp.write_text(json.dumps(index), encoding="utf-8")
        os.replace(tmp, cache_path)
        return True
    except OSError:
        return False


def load_or_build(ledger_root: Path) -> dict:
    cached = _read_cache(ledger_root)
    if is_fresh(ledger_root, cached):
        return cached
    index = build_index(ledger_root)
    write_cache(ledger_root, index)
    return index


def resolve_query(
    index: dict,
    query: str,
    *,
    type_filter: str | None = None,
    include_interpretations: bool = False,
    limit: int = 15,
) -> list[dict]:
    entries: dict[str, dict] = index.get("entries") or {}
    names: dict[str, list[str]] = index.get("names") or {}
    q = str(query)
    q_norm = normalize_text(q)
    q_slug = slugify(q)
    q_tokens = set(tokenize(q))

    def allowed(e: dict) -> bool:
        if e.get("kind") == "interpretation" and not include_interpretations:
            return False
        return not (type_filter and e.get("type") != type_filter)

    def survivor(entry_id: str) -> tuple[str, dict] | None:
        """Chase ONE redirect hop; None if the survivor is missing or is
        itself a redirect (a chain, which `ath ledger check` disallows)."""
        e = entries.get(entry_id)
        if e is None or e.get("kind") != "redirect":
            return None
        target = e.get("merged_into")
        se = entries.get(target) if isinstance(target, str) else None
        if se is None or se.get("kind") == "redirect":
            return None
        return target, se

    best: dict[str, dict] = {}

    def consider(cid: str, entry: dict, basis: str, note: str | None = None) -> None:
        if not allowed(entry):
            return
        cur = best.get(cid)
        if cur is not None and _BASIS_RANK[cur["basis"]] <= _BASIS_RANK[basis]:
            return
        cand = {"id": cid, "type": entry.get("type", ""), "kind": entry.get("kind", ""),
                "name": entry.get("name", ""), "basis": basis}
        if note:
            cand["note"] = note
        best[cid] = cand

    # 1 (id) + 2 (redirect): exact id match, also the slugified query as id
    for candidate_id in {q, q_slug} - {""}:
        e = entries.get(candidate_id)
        if e is None:
            continue
        if e.get("kind") == "redirect":
            res = survivor(candidate_id)
            if res is not None:
                sid, se = res
                consider(sid, se, "redirect", note=f"via redirect {candidate_id}")
        else:
            consider(candidate_id, e, "id")

    # 3: name/alias exact
    if q_norm:
        for nid in names.get(q_norm, []):
            e = entries.get(nid)
            if e is None:
                continue
            basis = "name" if normalize_text(e.get("name", "")) == q_norm else "alias"
            consider(nid, e, basis)

    # 4: id-prefix (redirects chase to survivor, same as rule 1/2)
    if q_slug:
        for eid, e in entries.items():
            if not eid.startswith(q_slug):
                continue
            if e.get("kind") == "redirect":
                res = survivor(eid)
                if res is not None:
                    sid, se = res
                    consider(sid, se, "id-prefix")
            else:
                consider(eid, e, "id-prefix")

    # 5 (substring) + 6 (tokens): text match against name+aliases; redirects
    # carry no name/aliases of their own and are excluded here (only ever
    # surfaced via the id-based rules above, always as their survivor).
    if q_norm or q_tokens:
        for eid, e in entries.items():
            if e.get("kind") == "redirect":
                continue
            alias_list = e.get("aliases") or []
            if q_norm:
                haystacks = [h for h in
                             [normalize_text(e.get("name", "")), *(normalize_text(a) for a in
                                                                    alias_list)] if h]
                if any(q_norm in h for h in haystacks):
                    consider(eid, e, "substring")
                    continue
            if q_tokens:
                ent_tokens = set(tokenize(e.get("name", "")))
                for a in alias_list:
                    ent_tokens |= set(tokenize(a))
                if q_tokens.issubset(ent_tokens):
                    consider(eid, e, "tokens")

    ranked = sorted(best.values(), key=lambda c: (_BASIS_RANK[c["basis"]], c["id"]))
    return ranked[:limit]
