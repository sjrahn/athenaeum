"""`ath ledger remap-el-ordinal` — rewrite `el=` evidence anchors for the v35 addressing
remap (spec §6.1.1, CHANGELOG v35).

The corpus remap (`corpus remap-el-ordinal`) re-addresses every dotted/legacy HTML record
to its document-order ordinal. Ledger evidence anchors cite those axes directly —
`anchor: el=1.3.2`, `corpus://<hash>?el=5-8` — and an anchor is not limited to addresses
the record stores, so this pass maps every anchor through the SAME pure artifact
functions the corpus remap uses (`corpus.remap_el_ordinal.map_dotted_value_to_ordinal` /
`map_legacy_value_to_ordinal`): resolve the old grammar's element, read its ordinal,
verify by re-resolution. One engine, two layers, zero drift.

**Ordering is part of the contract — and stricter here than the 3.6 precedent.** For the
3.6 migration, the OLD (filtered-whitelist) enumeration was a frozen, timeless function of
the artifact bytes alone, recomputable at any time regardless of a record's current stamp
— so the ledger pass only needed an ELIGIBILITY set (which records the corpus remap
actually touched). For v35 the two SOURCE generations (dotted, legacy) are properties of a
record's OWN addressing history, not of its bytes: once the corpus remap flips a record's
stamp to `scheme: ordinal`, the fact that its addresses used to be DOTTED (as opposed to
LEGACY) is no longer recoverable by inspecting the record — the artifact never changes,
but which grammar a bare/dotted anchor value meant depends on that lost fact. So this pass
needs the corpus remap's run manifest (`--manifest`) not just as an eligibility set but as
the GENERATION record: `{record: "dotted"|"legacy"}` for every record it actually
rewrote — `load_migration_generations`, below. A record absent from the manifest (not yet
migrated, held, or skipped) is INELIGIBLE and its anchors are left exactly as stored,
which is correct either way: an un-migrated record still speaks its old grammar, so its
anchors already agree with it.

A flat/dotted range rewrites to the tightest §6.1.1 ordinal address CONTAINING it — a
subtree ordinal or a sibling range `[A-B]`, always one string — so crossing subtree
boundaries is ordinary here and not a hold. What still holds is the interval whose
endpoints' nearest common ancestor is the ordinal root itself: no §6.1.1 spelling exists
for it (the #65 pattern — re-scoping is a judgment, reported rather than guessed at).
Quotes never change; only the `anchor`/URI value does. Anchors on the EPUB axis
(`spine=N&el=K`) are untouched — that axis keeps its own frozen enumeration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from corpus import containment
from corpus import mime as mime_mod
from corpus import paths as corpus_paths
from corpus import records as corpus_records
from corpus.remap_el_ordinal import (
    ContainerPairing,
    RemapHold,
    map_dotted_value_to_ordinal,
    map_legacy_value_to_ordinal,
)
from corpus.transforms.html import EL_PARSER_ID, legacy_is_addressable, path_root

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
    skipped_not_migrated: int = 0  # anchors on records the corpus remap did not migrate


def load_migration_generations(manifest_paths: list[Path]) -> dict[str, str]:
    """The eligibility set AND generation record: `{record: "dotted"|"legacy"}` for every
    record `corpus remap-el-ordinal` actually rewrote, read from its run manifest(s) —
    one per hub. Held and skipped records are deliberately absent (see module docstring:
    for v35 the generation is not recoverable from an un-migrated or already-ordinal
    record any other way)."""
    generations: dict[str, str] = {}
    for path in manifest_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("changed") and row.get("record") and row.get("generation"):
                generations[str(row["record"])] = str(row["generation"])
    return generations


class _Pairing:
    """Per-record parse cache: the FORCED generation (from the manifest) + the artifact
    tree, or the reason the record cannot be paired. Unlike the 3.6 `_Pairing`, the
    generation is never read off the record's own (now possibly-ordinal) stamp — it is
    supplied by the caller from `load_migration_generations`, which is what makes the
    ordering-independence promise hold."""

    def __init__(self, join: CorpusJoin, generations: dict[str, str] | None = None) -> None:
        self._join = join
        self._generations = generations or {}
        self._cache: dict[str, ContainerPairing | str] = {}

    def get(self, record_hash: str) -> ContainerPairing | str:
        if record_hash in self._cache:
            return self._cache[record_hash]
        result: ContainerPairing | str
        generation = self._generations.get(record_hash)
        if generation is None:
            result = "NOT-MIGRATED"
        else:
            try:
                holders = self._join.holders(record_hash)
                if not holders:
                    result = "record resolves in no registered corpus"
                else:
                    root_dir = holders[0].root
                    _rid, rf = corpus_paths.resolve_record(root_dir, record_hash)
                    post = corpus_records.load(rf)
                    media_type = corpus_records.media_type_for(post)
                    if not media_type.startswith("text/html"):
                        result = f"non-HTML mime ({media_type or 'none'})"
                    else:
                        binary = containment.ensure_local_bytes(
                            root_dir, record_hash, mime_mod.extension_for(media_type)
                        )
                        soup_bytes = binary.read_bytes()
                        from bs4 import BeautifulSoup, Tag

                        soup = BeautifulSoup(soup_bytes, EL_PARSER_ID)
                        root = path_root(soup)
                        old_elements = (
                            [t for t in soup.find_all(legacy_is_addressable) if isinstance(t, Tag)]
                            if generation == "legacy" else []
                        )
                        result = ContainerPairing(
                            generation=generation, old_elements=old_elements, root=root
                        )
            except Exception as exc:  # parse tolerantly; the anchor is held with the reason
                result = f"pairing failed: {exc}"
        self._cache[record_hash] = result
        return result


def _map_anchor_value(value: str, pairing: ContainerPairing) -> tuple[str, str]:
    """Map one el VALUE from an anchor; a list-form result has no single-anchor
    spelling and raises `RemapHold`."""
    if pairing.generation == "dotted":
        new, form = map_dotted_value_to_ordinal(value, pairing.root)
    else:
        new, form = map_legacy_value_to_ordinal(value, pairing.old_elements, pairing.root)
    if isinstance(new, list):
        raise RemapHold(
            "maps to an address list (a region crossing subtree boundaries) — "
            "an anchor is one string; re-anchor interpretively"
        )
    return new, form


def _rewrite_params(params: str, pairing: ContainerPairing) -> tuple[str, str] | None:
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
    returning whether anything changed. Holds and not-migrated skips land on `result`."""
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


def remap_ledger_el_ordinal(
    ledger_root: Path,
    join: CorpusJoin,
    *,
    apply: bool = False,
    generations: dict[str, str] | None = None,
) -> LedgerRemapResult:
    """Sweep every fact/interpretation file, rewriting el-leading anchors and
    `corpus://…?el=…` citation strings through the v35 ordinal mapping. Dry-run unless
    `apply`. Every hold carries its reason; nothing is guessed. Quotes are never
    touched — only `anchor`/URI values."""
    result = LedgerRemapResult()
    pairings = _Pairing(join, generations)

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
