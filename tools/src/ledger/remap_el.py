"""`ath ledger remap-el` — rewrite `el=` evidence anchors for the §12.28 addressing remap.

ATH-CORPUS 3.6 (spec §6.1.1) re-addresses every HTML record from the filtered-index
`el=<N>` to the total child-index path. Ledger evidence anchors cite those axes directly
— `anchor: el=5`, `corpus://<hash>?el=6-8` — and an anchor is NOT limited to addresses
the record stores, so this pass maps every anchor through the SAME pure artifact
function the corpus remap uses (`corpus.remap_el.map_el_value`): walk the frozen legacy
enumeration and the total tree over the same bytes, pair positionally, verify by
identity. One engine, two layers, zero drift.

**Ordering is part of the contract.** This pass runs AFTER `corpus remap-el --apply` and
is driven by its run manifest (`--manifest`, one per hub), because only that manifest
knows which records actually migrated: the corpus remap holds the records whose legacy
addresses alias under §6.1.1, and a held record keeps the legacy grammar forever until
someone re-addresses it deliberately. So the manifest is the eligibility set, and a
record absent from it — held, skipped, or in no corpus — keeps its legacy anchors, which
is exactly right, since its stored addresses are legacy too. Run in the other order (or
with no manifest) and the two layers can disagree about which grammar a record speaks,
which is the one way this migration silently breaks a citation.

A flat range rewrites to the tightest §6.1.1 address CONTAINING it — a subtree path or a
sibling range, always one string — so crossing subtree boundaries is ordinary here and
not a hold. What still holds is the interval whose endpoints' nearest common ancestor is
the path root itself: it covers the whole body, and §6.1.1 spells a sibling range
`el=<parent>.[a-b]`, so there is no address for it. Re-scoping such an anchor (usually to
a whole-record citation, which is the same extent) is a judgment, so it is reported
rather than guessed at — the #65 pattern. Span precision is unchanged either way: a
legacy flat range and a 3.6 sibling range are both unmaterializable, so `verify` treated
these anchors as record-scoped before the migration and treats them the same after.

Anchors on the EPUB axis (`spine=N&el=K`) are untouched — that axis keeps its own
enumeration (zero exist today, measured 2026-07-27). `ref://` citations are untouched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from corpus import containment
from corpus import mime as mime_mod
from corpus import records as corpus_records
from corpus.remap_el import RemapHold, map_el_value
from corpus.transforms.html import legacy_is_addressable, path_root

from .corpora import CorpusJoin
from .model import CORPUS_URI_RE


@dataclass
class AnchorRewrite:
    fact: str
    old: str
    new: str


@dataclass
class AnchorHold:
    fact: str
    record: str
    anchor: str
    reason: str


@dataclass
class LedgerRemapResult:
    rewrites: list[AnchorRewrite] = field(default_factory=list)
    holds: list[AnchorHold] = field(default_factory=list)
    facts_touched: list[str] = field(default_factory=list)
    forms: dict[str, int] = field(default_factory=dict)
    skipped_not_migrated: int = 0  # anchors on records the corpus remap did not rewrite


class _Pairing:
    """Per-record parse cache: the frozen legacy enumeration + the path root, or the
    reason the record cannot be paired (missing bytes, non-HTML, not migrated).

    `migrated` is the eligibility set — the record ids the corpus remap actually
    rewrote, read from its run manifest. It is what keeps the two layers consistent:
    the corpus remap HOLDS the records whose legacy addresses alias under §6.1.1, those
    records keep the legacy grammar (their `addressing:` stamp is never written, so the
    resolver still reads their integers the old way), and their anchors must therefore
    keep the legacy spelling too. Rewriting an anchor on a held record would point a
    path at a record that reads integers — the one way this migration can silently
    break a citation. Without a manifest, no record is eligible: there is no safe
    default, because the stamp alone cannot distinguish "migrated" from "was never in
    scope"."""

    def __init__(self, join: CorpusJoin, migrated: set[str] | None = None) -> None:
        self._join = join
        self._migrated = migrated or set()
        self._cache: dict[str, tuple[list[Tag], Tag] | str] = {}

    def get(self, record_hash: str) -> tuple[list[Tag], Tag] | str:
        if record_hash in self._cache:
            return self._cache[record_hash]
        result: tuple[list[Tag], Tag] | str
        try:
            holders = self._join.holders(record_hash)
            if not holders:
                result = "record resolves in no registered corpus"
            elif record_hash not in self._migrated:
                result = "NOT-MIGRATED"
            else:
                root_dir = holders[0].root
                from corpus import paths as corpus_paths

                _rid, rf = corpus_paths.resolve_record(root_dir, record_hash)
                post = corpus_records.load(rf)
                media_type = corpus_records.media_type_for(post)
                if not media_type.startswith("text/html"):
                    result = f"non-HTML mime ({media_type or 'none'})"
                else:
                    binary = containment.ensure_local_bytes(
                        root_dir, record_hash, mime_mod.extension_for(media_type)
                    )
                    soup = BeautifulSoup(binary.read_bytes(), "html.parser")
                    elements = [
                        t for t in soup.find_all(legacy_is_addressable) if isinstance(t, Tag)
                    ]
                    result = (elements, path_root(soup))
        except Exception as exc:  # parse tolerantly; the anchor is held with the reason
            result = f"pairing failed: {exc}"
        self._cache[record_hash] = result
        return result


def _map_anchor_value(
    value: str, pairing: tuple[list[Tag], Tag]
) -> tuple[str, str]:
    """Map one el VALUE from an anchor; a list-form result has no single-anchor
    spelling and raises `RemapHold`."""
    new, form = map_el_value(value, pairing[0], pairing[1])
    if isinstance(new, list):
        raise RemapHold(
            "maps to an address list (a region crossing subtree boundaries) — "
            "an anchor is one string; re-anchor interpretively"
        )
    return new, form


def _rewrite_params(params: str, pairing: tuple[list[Tag], Tag]) -> tuple[str, str] | None:
    """Rewrite the `el=` LEAD param of an `&`-joined param string (an anchor, or a URI
    query). Returns `(new_params, form)`, or None when the string is not el-leading
    (another axis, or EPUB's `spine=…&el=…` — both stay untouched)."""
    chunks = params.split("&")
    key, _, value = chunks[0].partition("=")
    if key != "el" or not value:
        return None
    new_value, form = _map_anchor_value(value, pairing)
    return "&".join([f"el={new_value}", *chunks[1:]]), form


def _walk_uris(node, rel: str, pairings: _Pairing, result: LedgerRemapResult, tally) -> bool:
    """Rewrite every flat `corpus://<hash>?el=…` citation string under `node` in place,
    returning whether anything changed. Holds and stamped-skips land on `result`."""
    changed = False
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                new_v, ch = _rewrite_uri_string(v, rel, pairings, result, tally)
                node[k] = new_v
                changed = changed or ch
            else:
                changed = _walk_uris(v, rel, pairings, result, tally) or changed
        return changed
    if isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                new_v, ch = _rewrite_uri_string(v, rel, pairings, result, tally)
                node[i] = new_v
                changed = changed or ch
            else:
                changed = _walk_uris(v, rel, pairings, result, tally) or changed
        return changed
    return changed


def _rewrite_uri_string(
    value: str, rel: str, pairings: _Pairing, result: LedgerRemapResult, tally
) -> tuple[str, bool]:
    m = CORPUS_URI_RE.match(value)
    if not (m and (m.group(2) or "").startswith("?el=")):
        return value, False
    record_hash = m.group(1)
    tail = m.group(2)[1:]  # drop the `?`
    fragment = ""
    if "#" in tail:
        tail, frag = tail.split("#", 1)
        fragment = f"#{frag}"
    pairing = pairings.get(record_hash)
    if pairing == "NOT-MIGRATED":
        result.skipped_not_migrated += 1
        return value, False
    if isinstance(pairing, str):
        result.holds.append(AnchorHold(rel, record_hash, value, pairing))
        return value, False
    try:
        rewritten = _rewrite_params(tail, pairing)
    except RemapHold as exc:
        result.holds.append(AnchorHold(rel, record_hash, value, str(exc)))
        return value, False
    if rewritten is None:
        return value, False
    new_tail, form = rewritten
    new_uri = f"corpus://{record_hash}?{new_tail}{fragment}"
    if new_uri == value:
        return value, False
    result.rewrites.append(AnchorRewrite(rel, value, new_uri))
    tally(form)
    return new_uri, True


def load_migrated_ids(manifest_paths: list[Path]) -> set[str]:
    """The eligibility set: record ids the corpus remap actually REWROTE, read from its
    run manifest(s) — one per hub. Held and skipped records are deliberately absent."""
    migrated: set[str] = set()
    for path in manifest_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("changed") and row.get("record"):
                migrated.add(str(row["record"]))
    return migrated


def remap_ledger_el(
    ledger_root: Path,
    join: CorpusJoin,
    *,
    apply: bool = False,
    migrated: set[str] | None = None,
) -> LedgerRemapResult:
    """Sweep every fact/interpretation file, rewriting el-leading anchors and
    `corpus://…?el=…` citation strings through the §12.28 mapping. Dry-run unless
    `apply`. Every hold carries its reason; nothing is guessed."""
    result = LedgerRemapResult()
    pairings = _Pairing(join, migrated)

    def tally(form: str) -> None:
        result.forms[form] = result.forms.get(form, 0) + 1

    files = sorted(ledger_root.glob("facts/*/*.json")) + sorted(
        ledger_root.glob("interpretations/*.json")
    )
    for fact_file in files:
        try:
            fact = json.loads(fact_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rel = str(fact_file.relative_to(ledger_root))
        changed = False

        # 1. Evidence anchors (sources-table indirection): the anchor addresses the
        #    record named by its evidence entry's `source` key.
        sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
        for claim in fact.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            for ev in claim.get("evidence") or []:
                if not isinstance(ev, dict):
                    continue
                anchor = ev.get("anchor")
                if not isinstance(anchor, str) or not anchor.startswith("el="):
                    continue
                entry = sources.get(str(ev.get("source") or ""))
                record_hash = (entry or {}).get("record") if isinstance(entry, dict) else None
                if not record_hash:
                    continue
                pairing = pairings.get(str(record_hash))
                if pairing == "NOT-MIGRATED":
                    result.skipped_not_migrated += 1
                    continue
                if isinstance(pairing, str):
                    result.holds.append(AnchorHold(rel, str(record_hash), anchor, pairing))
                    continue
                try:
                    rewritten = _rewrite_params(anchor, pairing)
                except RemapHold as exc:
                    result.holds.append(AnchorHold(rel, str(record_hash), anchor, str(exc)))
                    continue
                if rewritten is None:
                    continue
                new_anchor, form = rewritten
                if new_anchor != anchor:
                    ev["anchor"] = new_anchor
                    result.rewrites.append(AnchorRewrite(rel, anchor, new_anchor))
                    tally(form)
                    changed = True

        # 2. Flat `corpus://<hash>?el=…` citation strings anywhere in the tree
        #    (roster `artifacts[].uri`, `based_on`, prose-adjacent citation fields).
        if _walk_uris(fact, rel, pairings, result, tally):
            changed = True

        if changed:
            result.facts_touched.append(rel)
            if apply:
                fact_file.write_text(
                    json.dumps(fact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )

    return result
