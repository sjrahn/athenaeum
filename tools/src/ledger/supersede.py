"""`ath ledger supersede <old> <new>` — rewrite corpus citations when a record is re-captured.

A content-addressed record has no stable id across re-captures: a Claude Code session that
grew by a few turns bundles to a NEW blake3 (`corpus session capture`). When that happens,
every ledger citation `corpus://<old>?<addr>` must follow the content to `corpus://<new>` —
but ONLY where the cited content actually survived. This verb rewrites the safe citations
and reports the rest, gated by `corpus.continuity`:

- an address whose content is preserved in the new record (byte-identical, or contained as a
  prefix the new capture extends) → the citation is rewritten `old → new`, tail (`?params` /
  `#fragment`) verbatim;
- an address that DIVERGED (the content changed) → the citation is LEFT ALONE and reported;
  it needs a human/agent to re-anchor against the new record. No silent rewrite of a quote
  onto content it was never checked against — which is why no `dirty` flag is needed: a
  genuine break stays visibly on the old id, and `ath ledger check` / `verify` already error
  on it (dangling id, or broken anchor/quote).

`--retire` then reclaims the old record's bytes (`corpus rm`) — but only when no diverged
citation still points at it. This is the corpus-citation analogue of the ledger's own
concept-level lineage map (`facts/LINEAGE.json`, §4.1), one layer down.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from corpus import continuity as continuity_lib

from .corpora import CorpusJoin
from .model import CORPUS_URI_RE, next_source_key

# Continuity verdicts that mean "the cited content survived into the new record".
_PRESERVED = (continuity_lib.IDENTICAL, continuity_lib.CONTAINED)


@dataclass
class Rewrite:
    fact: str  # fact file name (relative)
    old_uri: str
    new_uri: str


@dataclass
class Divergence:
    fact: str
    uri: str  # the citation left untouched (its content did not survive into `new`)
    address: str  # the diverged address (`path=<member>`, or `(whole record)`)


@dataclass
class SupersedeResult:
    old: str
    new: str
    rewrites: list[Rewrite] = field(default_factory=list)
    divergences: list[Divergence] = field(default_factory=list)
    facts_touched: list[str] = field(default_factory=list)
    retired: bool = False
    note: str = ""

    @property
    def ok(self) -> bool:
        return not self.note.startswith("error")


class SupersedeError(RuntimeError):
    """The supersession could not proceed (records unresolvable, or in different corpora)."""


def _address_of(tail: str) -> str:
    """The continuity address a citation tail refers to — a `path=<member>` when the tail
    carries one, else `""` (a bare citation of the whole record). Accepts either a full
    URI tail (`?path=…`, from a roster/based_on string citation) or a bare sources-table
    `anchor` (`path=…`, no leading `?`, per §6.2's anchor grammar) — both address the
    same grammar, one just predates the `?`."""
    if not tail:
        return ""
    if tail[0] == "#":
        return ""  # a #fragment only — treat as whole-record
    if tail[0] == "?":
        tail = tail[1:]
    for chunk in tail.split("&"):
        key, _, value = chunk.partition("=")
        if key == "path" and value:
            return f"path={value}"
    return ""


def _preserved(cont: continuity_lib.Continuity, tail: str) -> tuple[bool, str]:
    """Whether the content a citation `tail` addresses survived into the new record, and the
    address label for reporting. A `path=<member>` citation is judged by that member's
    verdict; a bare citation by whole-record containment."""
    address = _address_of(tail)
    if address:
        return cont.status_for(address) in _PRESERVED, address
    return cont.contains_a, "(whole record)"


def supersede(
    ledger_root: Path, old: str, new: str, join: CorpusJoin, *, retire: bool = False
) -> SupersedeResult:
    """Rewrite every ledger citation of `old` to `new` where the cited content is preserved
    (proven by `corpus.continuity`); report the rest. Optionally retire `old`'s bytes."""
    result = SupersedeResult(old=old, new=new)
    if old == new:
        result.note = "error: old and new are the same record"
        return result

    old_holders = join.holders(old)
    new_holders = join.holders(new)
    if not new_holders:
        result.note = f"error: new record {new[:12]}… resolves in no registered corpus"
        return result
    if not old_holders:
        result.note = (
            f"error: old record {old[:12]}… resolves in no registered corpus — "
            "run supersede BEFORE retiring the old capture"
        )
        return result
    corpus_root = new_holders[0].root
    if old_holders[0].root != corpus_root:
        result.note = (
            "error: old and new live in different corpora — supersession is within one corpus"
        )
        return result

    cont = continuity_lib.continuity(corpus_root, old, new)

    for fact_file in sorted(ledger_root.glob("facts/*/*.json")):
        try:
            fact = json.loads(fact_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rel = f"{fact_file.parent.name}/{fact_file.name}"
        # sources-table citations (claim evidence, §13.3 sources-table amendment):
        # judged per referencing evidence entry's `anchor`, since one sources
        # entry may be shared by several evidence entries with different
        # anchors. Then the generic string walk, unchanged, for the citation
        # forms that stayed flat (roster `artifacts[].uri`) — it never matches
        # inside `sources`, whose values are bare hashes, not `corpus://` strings.
        changed_a, rewrites_a, divs_a = _rewrite_sources(fact, old, new, cont, rel)
        changed_b, rewrites_b, divs_b = _rewrite_tree(fact, old, new, cont, rel)
        changed = changed_a or changed_b
        result.rewrites.extend(rewrites_a + rewrites_b)
        result.divergences.extend(divs_a + divs_b)
        if changed:
            fact_file.write_text(
                json.dumps(fact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            result.facts_touched.append(rel)

    if retire:
        if result.divergences:
            result.note = (
                f"{len(result.divergences)} diverged citation(s) still reference "
                f"{old[:12]}… — not retiring; re-anchor them first."
            )
        else:
            from corpus import maintenance

            maintenance.remove_records(corpus_root, [old], force=True, execute=True)
            result.retired = True

    return result


def _rewrite_sources(fact: dict, old: str, new: str, cont, fact_rel: str):
    """Rewrite/split this fact's `sources` entries whose `record == old`, judged
    PER REFERENCING EVIDENCE ENTRY'S `anchor` — a sources entry may be shared
    by several evidence entries addressing different (or no) spans, so one
    entry's citations can diverge while another's are preserved:

    - every referencing entry preserved → the sources entry rewrites in place
      (one shared record change, no evidence entries need touching);
    - none preserved → left alone, all reported;
    - a mix → SPLIT: a fresh sources entry lands on `new`, the preserved
      entries repoint their `source` to it, the diverged entries stay on the
      old key (still citing `old`) and are reported.

    Returns `(changed, rewrites, divergences)`, mutating `fact` in place."""
    rewrites: list[Rewrite] = []
    divs: list[Divergence] = []
    changed = False
    sources = fact.get("sources")
    if not isinstance(sources, dict):
        return changed, rewrites, divs

    claims = [c for c in fact.get("claims") or [] if isinstance(c, dict)]

    for skey, entry in list(sources.items()):
        if not isinstance(entry, dict) or entry.get("record") != old:
            continue
        referrers = [
            e for c in claims for e in (c.get("evidence") or [])
            if isinstance(e, dict) and e.get("source") == skey
        ]

        def tail_of(e: dict) -> str:
            a = e.get("anchor")
            if not a:
                return ""
            return str(a) if str(a).startswith("#") else f"?{a}"

        if not referrers:
            # nothing addresses it specifically — judge by whole-record containment
            preserved, address = cont.contains_a, "(whole record)"
            if preserved:
                entry["record"] = new
                rewrites.append(Rewrite(fact=fact_rel, old_uri=f"corpus://{old}",
                                        new_uri=f"corpus://{new}"))
                changed = True
            else:
                divs.append(Divergence(fact=fact_rel, uri=f"corpus://{old}", address=address))
            continue

        verdicts = [(_preserved(cont, str(e.get("anchor") or "")), e) for e in referrers]
        if all(ok for (ok, _addr), _e in verdicts):
            entry["record"] = new
            for (_ok, _addr), e in verdicts:
                t = tail_of(e)
                rewrites.append(Rewrite(fact=fact_rel, old_uri=f"corpus://{old}{t}",
                                        new_uri=f"corpus://{new}{t}"))
            changed = True
        elif not any(ok for (ok, _addr), _e in verdicts):
            for (_ok, addr), e in verdicts:
                divs.append(Divergence(fact=fact_rel, uri=f"corpus://{old}{tail_of(e)}",
                                       address=addr))
        else:
            new_key = next_source_key(sources)
            sources[new_key] = {"record": new}
            for (ok, addr), e in verdicts:
                t = tail_of(e)
                if ok:
                    e["source"] = new_key
                    rewrites.append(Rewrite(fact=fact_rel, old_uri=f"corpus://{old}{t}",
                                            new_uri=f"corpus://{new}{t}"))
                else:
                    divs.append(Divergence(fact=fact_rel, uri=f"corpus://{old}{t}",
                                           address=addr))
            changed = True
    return changed, rewrites, divs


def _rewrite_tree(obj, old: str, new: str, cont, fact_rel: str):
    """Walk a fact's JSON, rewriting any standalone `corpus://<old>…` citation string whose
    addressed content is preserved in `new`. Returns `(changed, rewrites, divergences)` and
    mutates `obj` in place. A citation whose content diverged is left untouched + reported."""
    rewrites: list[Rewrite] = []
    divs: list[Divergence] = []
    changed = False

    def walk(node):
        nonlocal changed
        if isinstance(node, dict):
            for k, v in node.items():
                node[k] = walk(v)
            return node
        if isinstance(node, list):
            return [walk(x) for x in node]
        if isinstance(node, str):
            m = CORPUS_URI_RE.match(node)
            if m and m.group(1) == old:
                tail = m.group(2) or ""
                preserved, address = _preserved(cont, tail)
                if preserved:
                    new_uri = f"corpus://{new}{tail}"
                    rewrites.append(Rewrite(fact=fact_rel, old_uri=node, new_uri=new_uri))
                    changed = True
                    return new_uri
                divs.append(Divergence(fact=fact_rel, uri=node, address=address))
            return node
        return node

    walk(obj)
    return changed, rewrites, divs
