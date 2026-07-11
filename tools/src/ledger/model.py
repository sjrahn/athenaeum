"""The fact/interpretation data model — shapes, grammars, tolerant loading.

Checks work on plain dicts (parse tolerantly, author strictly): this module
holds the key sets, vocabularies, and grammar regexes of `spec/ledger.md`
§4—§7, the canonical claim-state hash of §7.3, and the period calculus of
§5.2 used by temporal invariants.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import blake3

# A double hyphen conventionally separates the two sides of a pair edge id
# (steven-rahn--greg-rahn), §4.1.
SLUG_RE = re.compile(r"^[a-z0-9]+(--?[a-z0-9]+)*$")
CLAIM_ID_RE = re.compile(r"^([a-z0-9]+(?:--?[a-z0-9]+)*):([a-z0-9]+(?:--?[a-z0-9]+)*)$")

# Evidence URIs (§6.2): bare corpus://{blake3} + optional span params, or
# ref://{dataset}/{id}. The 1.0 qualified corpus://{corpus}/{hash} form is a
# grammar error — resolution is content-addressed, never scoped.
CORPUS_URI_RE = re.compile(r"^corpus://([0-9a-f]{64})([?#].*)?$")
QUALIFIED_URI_RE = re.compile(r"^corpus://[a-z0-9-]+/[0-9a-f]{64}")
CORPUS_REF_RE = re.compile(r"corpus://([0-9a-f]{64})")
REF_URI_RE = re.compile(r"^ref://([a-z0-9][a-z0-9._-]*)/(.+)$")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")

# The per-fact sources table: a claim evidence entry cites a `source` key
# instead of an inline `uri`; the fact-level `sources` mapping resolves each
# key to exactly one `record` (a full 64-hex blake3) or `ref` (a bare
# `{dataset}/{id}`, the same grammar REF_URI_RE carries past its `ref://`
# prefix). The derived citation URI is reconstructed at every point that used
# to read an inline `uri` (see `derived_uri`).
SOURCE_KEY_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
FULL_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_REF_RE = re.compile(r"^([a-z0-9][a-z0-9._-]*)/(.+)$")

PERIOD_RE = re.compile(
    r"^~?\d{4}(-\d{2}(-\d{2})?)?(T\d{2}:\d{2})?"
    r"(/(\.\.|~?\d{4}(-\d{2}(-\d{2})?)?(T\d{2}:\d{2})?))?$"
)
ASOF_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")

CONCEPT_KEYS = {
    "id", "type", "name", "aliases", "meta", "sensitivity", "period", "provenance",
    "artifacts", "claims", "sources",
}
EDGE_KEYS = {
    "id", "type", "subject", "participants", "title", "period", "meta", "sensitivity",
    "provenance", "claims", "sources",
}
REDIRECT_KEYS = {"id", "type", "merged_into"}
CLAIM_KEYS = {
    "id", "predicate", "value", "object", "qualifiers", "period", "status",
    "asof", "reasoning", "sensitivity", "provenance", "evidence",
}
# Claim evidence cites a `source` key (+ optional `anchor`) into the fact's own
# `sources` table (sibling of `claims`) rather than an inline `uri` — the
# per-fact sources table, replacing the old {uri, quote, note, kind, verified}
# shape. `verified` moves to the sources entry (one stamp per fact/source,
# not per evidence entry).
EVIDENCE_KEYS = {"source", "anchor", "quote", "note", "kind"}
SOURCES_ENTRY_KEYS = {"record", "ref", "verified"}
ROSTER_KEYS = {"uri", "role", "note", "provenance"}
# A hypothesis's `proposes` draft claim (§7.2) predates the fact it targets, so
# it has no sources table of its own to reference — its evidence stays in the
# pre-reforge inline-`uri` shape until `ath ledger promote` lands it on the
# target fact (hoisting into that fact's `sources`, minting/reusing entries).
# `source`/`anchor` don't belong here; neither does `verified` (nothing to
# stamp before the citation resolves against a real fact).
PROPOSES_EVIDENCE_KEYS = {"uri", "quote", "note", "kind"}

CLAIM_STATUSES = {"confirmed", "provisional", "inferred", "reported", "disputed", "conflicting"}
EVIDENCE_KINDS = {"authoritative", "direct", "incidental"}

INTERP_KEYS = {
    "id", "kind", "about", "statement", "confidence", "reasoning", "based_on",
    "would_resolve", "proposes", "challenges", "needs", "status", "resolution", "asof",
}
INTERP_KINDS = {"hypothesis", "assessment", "correction"}
HYPOTHESIS_STATUSES = {"open", "promoted", "refuted"}
STANDING_STATUSES = {"standing", "retired"}
CONFIDENCES = {"speculative", "plausible", "likely"}
NEED_ACTIONS = {"enqueue", "search", "capture", "observe"}
NEED_KEYS = {"action", "record", "why"}
CHALLENGE_KEYS = {"claim", "state"}
STATE_RE = re.compile(r"^blake3:[0-9a-f]{64}$")


def load_json_dir(base: Path, pattern: str) -> tuple[dict[Path, dict], list[str]]:
    """All JSON files under *base* matching *pattern* → ({path: obj}, parse errors)."""
    out: dict[Path, dict] = {}
    errors: list[str] = []
    for f in sorted(base.glob(pattern)):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"{f.relative_to(base)}: invalid JSON — {e}")
            continue
        if not isinstance(obj, dict):
            errors.append(f"{f.relative_to(base)}: top level must be a JSON object")
            continue
        out[f] = obj
    return out, errors


def is_redirect(fact: dict) -> bool:
    return "merged_into" in fact


def is_edge(fact: dict) -> bool:
    return "subject" in fact or "participants" in fact


def source_target(entry: object) -> tuple[str, str] | None:
    """A sources-entry dict → ('record'|'ref', value), or None if malformed
    (neither or both of `record`/`ref` present)."""
    if not isinstance(entry, dict):
        return None
    has_record, has_ref = "record" in entry, "ref" in entry
    if has_record == has_ref:
        return None
    return ("record", str(entry["record"])) if has_record else ("ref", str(entry["ref"]))


def derived_uri(sources: dict, source_key: object, anchor: object = None) -> str | None:
    """The §6.2 citation a claim evidence entry resolves to: `corpus://{record}`
    (+ `?{anchor}` when present) or `ref://{ref}` — reconstructed from the
    fact's `sources` table, never stored inline. None when `source_key` doesn't
    resolve in `sources` or the entry is malformed."""
    if not isinstance(sources, dict) or not source_key:
        return None
    target = source_target(sources.get(str(source_key)))
    if target is None:
        return None
    kind, value = target
    if kind == "ref":
        return f"ref://{value}"
    if not anchor:
        tail = ""
    elif str(anchor).startswith("#"):
        tail = str(anchor)  # a body-anchor fragment — the '#' IS the separator
    else:
        tail = f"?{anchor}"
    return f"corpus://{value}{tail}"


def next_source_key(sources: dict) -> str:
    """The next free `s{n}` key, local to one fact's sources table."""
    i = 1
    while f"s{i}" in sources:
        i += 1
    return f"s{i}"


def ensure_source(fact: dict, *, record: str | None = None, ref: str | None = None) -> str:
    """Find an existing sources entry on *fact* targeting *record*/*ref*, or
    mint a fresh key — used wherever a citation lands on a fact for the first
    time (harvest minting, hypothesis promotion, migration). Mutates *fact*
    in place. Exactly one of record/ref must be given."""
    if (record is None) == (ref is None):
        raise ValueError("ensure_source: exactly one of record/ref is required")
    sources = fact.setdefault("sources", {})
    for key, entry in sources.items():
        target = source_target(entry)
        if target == ("record", record) or target == ("ref", ref):
            return key
    key = next_source_key(sources)
    sources[key] = {"record": record} if record is not None else {"ref": ref}
    return key


def canonical_claim_state(claim: dict, sources: dict | None = None) -> str:
    """The §7.3 challenge pin: blake3 of the claim's canonical JSON minus `status`.

    `status` is excluded because the dispute mechanism itself moves it — filing
    a challenge flips the claim to `disputed`, which must not read as an edit.
    Evidence entries canonicalize to their DERIVED uri (resolved through the
    fact's `sources` table, given by the caller) rather than their raw
    `source`/`anchor` keys — a source-key rename changes nothing citation-wise,
    so it must not move the pin. Evidence `verified` (now a sources-entry
    stamp, never carried on the entry itself) and any residual `verified` are
    tooling writes, not content edits, and are excluded for the same reason.
    """
    content = {k: v for k, v in claim.items() if k != "status"}
    if isinstance(content.get("evidence"), list):
        resolved = []
        for e in content["evidence"]:
            if not isinstance(e, dict):
                resolved.append(e)
                continue
            e2 = {k: v for k, v in e.items() if k not in ("source", "anchor", "verified")}
            uri = derived_uri(sources or {}, e.get("source"), e.get("anchor"))
            if uri is not None:
                e2["uri"] = uri
            resolved.append(e2)
        content["evidence"] = resolved
    payload = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "blake3:" + blake3.blake3(payload.encode("utf-8")).hexdigest()


Day = tuple[int, int, int]

_DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _token_bounds(tok: str) -> tuple[Day, Day] | None:
    """One period token (YYYY[-MM[-DD]], optional time ignored) → (first, last) day."""
    m = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", tok)
    if not m:
        return None
    y = int(m.group(1))
    if m.group(2) is None:
        return (y, 1, 1), (y, 12, 31)
    mo = int(m.group(2))
    if not 1 <= mo <= 12:
        return None
    if m.group(3) is None:
        return (y, mo, 1), (y, mo, _DAYS_IN_MONTH[mo - 1])
    d = int(m.group(3))
    return (y, mo, d), (y, mo, d)


def period_interval(period: object) -> tuple[Day, Day] | None:
    """A §5.2 period → a closed (start, end) interval at day resolution.

    Circa (`~`) is stripped; an open range `a/..` ends at the far horizon.
    Returns None for anything unparseable — callers skip, never fail.
    """
    s = str(period).strip().lstrip("~")
    if "/" in s:
        a, b = (part.strip() for part in s.split("/", 1))
        lo = _token_bounds(a.lstrip("~"))
        if lo is None:
            return None
        if b in ("..", ""):
            return lo[0], (9999, 12, 31)
        hi = _token_bounds(b.lstrip("~"))
        if hi is None:
            return None
        return lo[0], hi[1]
    bounds = _token_bounds(s)
    return bounds if bounds is None else (bounds[0], bounds[1])


def intervals_overlap(a: tuple[Day, Day], b: tuple[Day, Day]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]
