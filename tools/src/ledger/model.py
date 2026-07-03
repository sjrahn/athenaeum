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

PERIOD_RE = re.compile(
    r"^~?\d{4}(-\d{2}(-\d{2})?)?(T\d{2}:\d{2})?"
    r"(/(\.\.|~?\d{4}(-\d{2}(-\d{2})?)?(T\d{2}:\d{2})?))?$"
)
ASOF_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")

CONCEPT_KEYS = {
    "id", "type", "name", "aliases", "meta", "sensitivity", "provenance", "artifacts", "claims"
}
EDGE_KEYS = {
    "id", "type", "subject", "participants", "title", "period", "meta", "sensitivity",
    "provenance", "claims",
}
REDIRECT_KEYS = {"id", "type", "merged_into"}
CLAIM_KEYS = {
    "id", "predicate", "value", "object", "qualifiers", "period", "status",
    "asof", "reasoning", "sensitivity", "provenance", "evidence",
}
EVIDENCE_KEYS = {"uri", "quote", "note", "kind", "verified"}
ROSTER_KEYS = {"uri", "role", "note", "provenance"}

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


def canonical_claim_state(claim: dict) -> str:
    """The §7.3 challenge pin: blake3 of the claim's canonical JSON minus `status`.

    `status` is excluded because the dispute mechanism itself moves it — filing
    a challenge flips the claim to `disputed`, which must not read as an edit.
    Evidence `verified` stamps (§13.2 snapshot binding) are tooling writes, not
    content edits, and are excluded for the same reason.
    """
    content = {k: v for k, v in claim.items() if k != "status"}
    if isinstance(content.get("evidence"), list):
        content["evidence"] = [
            {k: v for k, v in e.items() if k != "verified"} if isinstance(e, dict) else e
            for e in content["evidence"]
        ]
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
