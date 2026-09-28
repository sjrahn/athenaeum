"""The fact/interpretation data model — shapes, grammars, tolerant loading.

Checks work on plain dicts (parse tolerantly, author strictly): this module
holds the key sets, vocabularies, and grammar regexes of `spec/ledger.md`
§4—§7, the canonical claim-state hash of §7.3, and the period calculus of
§5.2 used by temporal invariants.
"""

from __future__ import annotations

import calendar
import json
import re
from collections.abc import Mapping
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
# *(v17, §6.5)* group(1) dataset, group(2) optional pinned snapshot tag (None
# for a bare ref, which resolves/tracks the dataset's `latest`), group(3) the
# native id. `ref://{dataset}/{id}` bare tracks; `ref://{dataset}@{tag}/{id}`
# pins a registered snapshot permanently.
REF_URI_RE = re.compile(r"^ref://([a-z0-9][a-z0-9._-]*)(?:@([a-z0-9][a-z0-9._-]*))?/(.+)$")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")

# The per-fact sources table: a claim evidence entry cites a `source` key
# instead of an inline `uri`; the fact-level `sources` mapping resolves each
# key to exactly one `record` (a full 64-hex blake3) or `ref` (a bare
# `{dataset}/{id}` or pinned `{dataset}@{tag}/{id}`, the same grammar
# REF_URI_RE carries past its `ref://` prefix — group(1) dataset, group(2)
# optional tag, group(3) id). The derived citation URI is reconstructed at
# every point that used to read an inline `uri` (see `derived_uri`).
SOURCE_KEY_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
FULL_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_REF_RE = re.compile(r"^([a-z0-9][a-z0-9._-]*)(?:@([a-z0-9][a-z0-9._-]*))?/(.+)$")

PERIOD_RE = re.compile(
    r"^~?\d{4}(-\d{2}(-\d{2})?)?(T\d{2}:\d{2})?"
    r"(/(\.\.|~?\d{4}(-\d{2}(-\d{2})?)?(T\d{2}:\d{2})?))?$"
)
ASOF_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")

CONCEPT_KEYS = {
    "id", "type", "name", "aliases", "meta", "sensitivity", "period", "provenance",
    "artifacts", "claims", "sources", "domain", "ontology",
}
EDGE_KEYS = {
    "id", "type", "subject", "participants", "title", "period", "meta", "sensitivity",
    "provenance", "claims", "sources", "domain",
}
REDIRECT_KEYS = {"id", "type", "merged_into"}
CLAIM_KEYS = {
    "id", "predicate", "value", "object", "presence", "qualifiers", "period", "status",
    "asof", "reasoning", "sensitivity", "provenance", "evidence",
}
# Presence claims (§5.5): `presence` stands in place of `value`/`object`,
# asserting the shape of the predicate's extension rather than a value.
PRESENCE_VALUES = {"none", "some"}
# Claim evidence cites a `source` key (+ optional `anchor`) into the fact's own
# `sources` table (sibling of `claims`) rather than an inline `uri` — the
# per-fact sources table, replacing the old {uri, quote, note, kind, verified}
# shape. `verified` moves to the sources entry (one stamp per fact/source,
# not per evidence entry).
EVIDENCE_KEYS = {"source", "anchor", "quote", "note", "kind", "element"}
SOURCES_ENTRY_KEYS = {"record", "ref", "verified"}
ROSTER_KEYS = {"uri", "role", "note", "provenance",
               "modality", "expression", "derived_from", "derivation"}
# A hypothesis's `proposes` draft claim (§7.2) predates the fact it targets, so
# it has no sources table of its own to reference — its evidence stays in the
# pre-reforge inline-`uri` shape until `ath ledger promote` lands it on the
# target fact (hoisting into that fact's `sources`, minting/reusing entries).
# `source`/`anchor` don't belong here; neither does `verified` (nothing to
# stamp before the citation resolves against a real fact).
PROPOSES_EVIDENCE_KEYS = {"uri", "quote", "note", "kind", "element"}
# *(v47, §7.2)* a hypothesis that a thing the ledger has no fact for exists: the concept
# `ath ledger promote` mints (`facts/{type}/{id}.json`) and the draft claims it lands on it.
PROPOSES_NEW_KEYS = {"id", "type", "name", "claims"}

CLAIM_STATUSES = {"confirmed", "provisional", "inferred", "reported", "disputed", "conflicting"}
EVIDENCE_KINDS = {"authoritative", "direct", "incidental"}

INTERP_KEYS = {
    "id", "kind", "about", "statement", "confidence", "reasoning", "based_on",
    "would_resolve", "proposes", "proposes_new", "challenges", "needs", "status",
    "resolution", "asof",
}
INTERP_KINDS = {"hypothesis", "assessment", "correction"}
HYPOTHESIS_STATUSES = {"open", "promoted", "refuted"}
STANDING_STATUSES = {"standing", "retired"}
CONFIDENCES = {"speculative", "plausible", "likely"}
NEED_ACTIONS = {"enqueue", "search", "capture", "observe", "promote"}
# `demand:` names a demand rule (§14) this need blocks — a blocked demand's
# state is derived from this, never stored on the demand itself.
NEED_KEYS = {"action", "record", "why", "demand"}
CHALLENGE_KEYS = {"claim", "state"}
STATE_RE = re.compile(r"^blake3:[0-9a-f]{64}$")

# The lineage row `reason` vocabulary (§4.1) — closed, grown by amendment. A row's GRAIN
# picks its half: a file-grain key (`old-id`, a whole concept retired) is `merged`/`renamed`;
# a claim-grain key (`file-id:short`, one claim leaving a file that lives on, v49) is
# `split` (it became, or joined, another fact) or `rekeyed` (it moved to a sibling concept).
LINEAGE_REASONS = {"merged", "renamed"}
CLAIM_LINEAGE_REASONS = {"split", "rekeyed"}


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
    """Detects the RETIRED per-file tombstone shape (pre-1.7, `merged_into`).

    Lineage now lives in `facts/LINEAGE.json` (§4.1, `load_lineage`); a fact
    file still carrying this shape is a check ERROR ("fold into
    facts/LINEAGE.json"), never a live redirect — callers use this only to
    detect and skip/flag such legacy files.
    """
    return "merged_into" in fact


def _read_lineage(ledger_root: Path) -> tuple[dict[str, dict], dict[str, dict], list[str]]:
    """Tolerant read of `facts/LINEAGE.json` (§4.1) → (file-grain rows, claim-grain rows,
    errors). See `load_lineage_rows` for the contract; a key containing `:` is a claim-grain
    row (v49), keyed by the moved claim's full id, whose `to` is a fact id or a claim id."""
    path = ledger_root / "facts" / "LINEAGE.json"
    if not path.is_file():
        return {}, {}, []
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {}, {}, [f"facts/LINEAGE.json: invalid JSON — {e}"]
    if not isinstance(obj, dict):
        return {}, {}, ["facts/LINEAGE.json: top level must be a JSON object"]
    rows: dict[str, dict] = {}
    claim_rows: dict[str, dict] = {}
    errors: list[str] = []
    for k, v in obj.items():
        if not isinstance(k, str):
            errors.append(f"facts/LINEAGE.json: entry key {k!r} must be a string")
            continue
        claim_grain = ":" in k
        if claim_grain and not CLAIM_ID_RE.match(k):
            errors.append(f"facts/LINEAGE.json: claim-grain key {k!r} is not a claim id "
                          "`{file-id}:{short}`")
            continue
        if isinstance(v, str) and not claim_grain:
            errors.append(
                f"facts/LINEAGE.json: {k!r} -> {v!r}: lineage row not in v39 object "
                'form — {"to": …, "reason": …}'
            )
            rows[k] = {"to": v, "reason": None}
            continue
        if not isinstance(v, dict):
            errors.append(f"facts/LINEAGE.json: entry {k!r} -> {v!r} must be an object "
                          '{"to": …, "reason": …} (or a legacy string, migrated loudly)')
            continue
        unknown = set(v) - {"to", "reason"}
        if unknown:
            errors.append(f"facts/LINEAGE.json: entry {k!r} unknown keys {sorted(unknown)}")
        to = v.get("to")
        if not isinstance(to, str) or not to:
            errors.append(f"facts/LINEAGE.json: entry {k!r} missing string `to`")
            continue
        reason = v.get("reason")
        allowed = CLAIM_LINEAGE_REASONS if claim_grain else LINEAGE_REASONS
        if reason not in allowed:
            grain = "a claim-grain row" if claim_grain else "a file-grain row"
            errors.append(f"facts/LINEAGE.json: entry {k!r} reason {reason!r} not in "
                          f"{sorted(allowed)} ({grain})")
            continue
        if claim_grain and not (SLUG_RE.match(to) or CLAIM_ID_RE.match(to)):
            errors.append(f"facts/LINEAGE.json: claim-grain entry {k!r} `to` {to!r} is "
                          "neither a fact id nor a claim id")
            continue
        (claim_rows if claim_grain else rows)[k] = {"to": to, "reason": reason}
    return rows, claim_rows, errors


def load_lineage_rows(ledger_root: Path) -> tuple[dict[str, dict], list[str]]:
    """Tolerant read of `facts/LINEAGE.json`'s FILE-grain rows (§4.1) → ({old-id: {"to",
    "reason"}}, errors).

    v39 object-row form: `"old-id": {"to": "survivor-id", "reason": "merged"|"renamed"}`
    — `reason` is closed vocabulary (`LINEAGE_REASONS`), grown by amendment. This is
    the full per-row metadata behind `load_lineage`'s old->survivor resolution map:
    `reason` is what check's Graph block validates and what a future export projects
    as the deprecation pattern (§15.7). Claim-grain rows (`file-id:short`, v49) are
    `load_claim_lineage_rows`'s; their parse errors are reported here too, so a caller
    reading only the file grain still sees a malformed map.

    Missing file → empty map, no errors. A non-object top level is an error, whole
    file dropped. Per row: a legacy flat-string row (`"old": "survivor"`, pre-v39)
    still populates the map — as `{"to": survivor, "reason": None}` — so tooling
    stays operable while red, but is reported as an error naming the v39 shape it
    must migrate to. An object row missing a string `to`, carrying an unknown
    `reason`, or otherwise malformed, is reported as an error and the row is
    dropped from the map entirely — parse tolerantly, author strictly.
    """
    rows, _claim_rows, errors = _read_lineage(ledger_root)
    return rows, errors


def load_claim_lineage_rows(ledger_root: Path) -> dict[str, dict]:
    """`facts/LINEAGE.json`'s CLAIM-grain rows (§4.1, v49): `{"file-id:short": {"to":
    "fact-id[:short]", "reason": "split"|"rekeyed"}}` — one claim that left a file which
    lives on. Parse errors are `load_lineage_rows`'s to report."""
    return _read_lineage(ledger_root)[1]


def resolve_claim_ref(
    claim_id: str, claim_lineage: Mapping[str, str], lineage: Mapping[str, str]
) -> str:
    """Where a held claim id now lives (§4.1), one hop only: a claim-grain row for the id
    itself first (a claim that left its file — its `to` is a fact id, the claim having
    become that fact, or a claim id), else the file-grain row for its file with the short
    preserved (a merged/renamed concept). An id no row names is returned unchanged."""
    if claim_id in claim_lineage:
        return claim_lineage[claim_id]
    m = CLAIM_ID_RE.match(claim_id)
    if m and m.group(1) in lineage:
        return f"{lineage[m.group(1)]}:{m.group(2)}"
    return claim_id


def load_lineage(ledger_root: Path) -> tuple[dict[str, str], list[str]]:
    """Tolerant read of `facts/LINEAGE.json` (§4.1) → ({old-id: survivor-id}, errors).

    The old->survivor resolution map alone — see `load_lineage_rows` for the full
    per-row metadata (including `reason`) and the parsing/error contract, which
    this derives from unchanged so every existing caller keeps working untouched.
    """
    rows, errors = load_lineage_rows(ledger_root)
    return {k: v["to"] for k, v in rows.items()}, errors


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
        # `calendar.monthrange` range-checks the year internally and gives the true
        # per-month/leap-year day count — a hardcoded table (28/29/30/31) got February
        # wrong on every non-leap year.
        _, last_day = calendar.monthrange(y, mo)
        return (y, mo, 1), (y, mo, last_day)
    d = int(m.group(3))
    _, last_day = calendar.monthrange(y, mo)
    if not 1 <= d <= last_day:
        return None
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
