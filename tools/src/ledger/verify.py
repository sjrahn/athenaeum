"""Evidence verification — the anti-hallucination gate (`spec/ledger.md` §13.2).

Beyond record existence: every span anchor must resolve against the cited
record, every quote must be found verbatim (modulo whitespace normalization)
in the content the URI resolves to, and passing entries are stamped with the
record's touch identity (snapshot binding) so a later authoring or migration
pass — anything that moves the touch — flags them for re-verification
instead of silently rotting.

Verification reads record *markdown* first — segment bodies are the faithful
text — so most of it works without artifact bytes. *(1.5)* An anchor the
stored markdown can't scope (a derivation-op axis: `?path=`, `row=`/`col=`,
`prop=`, …) is now additionally resolved through the corpus resolver itself
(`corpus.resolver.resolve`, the same path `corpus resolve` uses) before
falling back to `unverifiable` — the honestly-unverifiable residue narrows to
ops the verifying environment genuinely can't run (artifact bytes absent, an
optional extra missing, a non-textual result).

`time_range=` scopes directly against stored transcript segments, exactly
like the integer axes below — numerically (`9:59` < `10:00`, never
lexicographically), and a cited range spans every segment it overlaps. A
record whose transcript isn't stored (a promoted media leaf, derived-only)
carries no `time_range` spans to scope against, so its citations still fall
through to the resolver path above — which can only mux a media clip there,
not text, so that gap surfaces as its own honest, actionable note rather than
`unverifiable`'s generic "not textual" reason.

*(v17, §6.5/§13.2.3)* `ref://` citations resolve against the manifest's
registered datasets — a bare citation tracks `latest`, a pinned citation
freezes its tag — and the resolved `(tag, mirror-artifact blake3)` pair
stamps onto the source as a snapshot binding, drift-checked every run
exactly like the derivation-op pin above. Resolution is a mechanical
manifest lookup and stamps regardless of content — an environment gap (no
adapter registered for the dataset, or the mirror's bytes not locally
materialized) stays honestly `unverifiable` and still stamps, the binding
recording that the citation *resolves* even when its content couldn't be
checked here. *(Phase 1, §13.2.2)* Where the adapter is available and the
mirror is local, content verification is now real: `refdata.resolve`
renders the cited native id through the dataset's adapter, and a `quote`
checks against the rendered entry exactly as it would against a record's
text. An entry the mirror doesn't carry is a FAILURE (graded at the
citing claim's status severity, same as any other evidence failure) that
withdraws the stamp for that source; a quote that isn't found does the
same. The unverifiable residue narrows to genuine environment gaps — no
adapter, no locally materialized mirror. An unregistered dataset or a
dangling pin resolves to nothing (check's own finding, §13.1) —
unverifiable, no stamp, no crash.

A claim whose evidence FAILS is flagged at the severity of its status:
`confirmed` failing is an error; lower rungs warn.

*(1.4, regraded 1.8)* A `segments`-surface record (corpus §7.1 — raw/derived
whole-record text that is presentation soup, e.g. a captured HTML DOM)
carrying zero persisted segments is a DEFERRED surface (§13.2.4): evidence
citing it is neither failed nor warned — its quotes are held unmatched
(record-wide matching against soup would mislead), it stamps no binding, and
it is excluded from the §5.4 bar (check's side of the contract). What such a
record already attests mechanically still verifies now: a quote found on an
attested byte-fact surface, or an anchor resolving through a derivation op,
verifies exactly as on any record — and a quote that FAILS against a
mechanically derived surface is still a failure; deferral never shields a
wrong quote. Deferred citations aggregate per record — claim evidence and
interpretation references alike — into `VerifyResult.demand`, the standing
normalize-demand signal (cite-then-pressure; the 1.4 needs-warning retired).
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import refdata
from corpus import functional_uri as furi
from corpus import textnorm as _textnorm
from ledger.corpora import CorpusJoin
from ledger.model import CORPUS_URI_RE, SOURCE_REF_RE, derived_uri

if TYPE_CHECKING:
    from ath.manifest import Reference

_SPAN_RE = re.compile(r"^(\d+)(?:-(\d+))?$")
_UNCHECKED_PARAMS = {"frame", "bbox", "path", "region", "rotate"}


@dataclass
class RecordContent:
    """The addressable text of one record, parsed once."""

    spans: dict[str, list[tuple[float, float, str]]]  # axis -> [(lo, hi, text)]
    # (int for the integer axes; `time_range` stores fractional seconds)
    full_text: str
    touch: str  # the latest touch identity ("" when the record carries none)
    # `el=` claims, when the RECORD is stamped with `addressing:` (corpus §6.1.1) —
    # [(claim, text)], `claim` a `furi.ElOrdinal` (v35) or a `furi.ElPath` (the frozen 3.6
    # dotted path), per `el_scheme`. Which grammar this record's el= values speak is
    # decided by the record, never by the value's shape: `el=5` is legal under any of the
    # three generations and means a different element under each, so the stamp is the
    # only honest discriminator. Integer axes (page/msg/turn/part/…) and unstamped
    # records keep `spans` untouched.
    el_paths: list[tuple[object, str]] = field(default_factory=list)
    #: None (unstamped — the frozen pre-3.6 whitelist), "dotted" (frozen 3.6 path), or
    #: "ordinal" (v35, §6.1.1) — read off `records.el_addressing`.
    el_scheme: str | None = None
    media_type: str = ""
    # the format's honest citation-surface class (corpus §7.1, ledger.md §6.3/§13.2.4):
    # "segments" — citable only once persisted segments exist; "raw" — the default,
    # record-wide verbatim quotes are honest even on a formless record
    citation_surface: str = "raw"
    segment_count: int = 0  # addressable leaf segments the record actually persists
    corpus_root: Path | None = None  # the holding corpus root — for resolver calls (1.5)


@dataclass
class VerifyResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    verified: int = 0
    unverifiable: int = 0
    stamped: int = 0
    # quotes verified against the WHOLE record because their anchor addresses
    # content the markdown can't scope (time_range, path, bbox …) — verified,
    # but honestly weaker than anchor-scoped
    record_scoped: int = 0
    # *(1.8)* claim evidence entries held on DEFERRED surfaces (§13.2.4) —
    # admissible, unverified, bar-excluded; resolved by forming, never failed
    deferred: int = 0
    # *(1.8)* the demand aggregate: {record hash: count of deferred citations},
    # claim evidence and interpretation references together — the standing
    # normalize-demand signal the deferral principle runs on
    demand: dict[str, int] = field(default_factory=dict)
    # *(1.5)* quotes verified against a surface the corpus RESOLVER derived
    # mechanically (a derivation op the record markdown itself can't scope) —
    # verified, at full anchor precision, via a library call to `corpus.resolver`
    derived_resolved: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


# The tolerant matcher lives in `corpus.textnorm` — one definition shared with the corpus
# address-fidelity gate (#159), which asks the same "is this text found there, modulo
# markup and whitespace" question in the other direction. These names are the historical
# spellings verify's own call sites (and its tests) use; the semantics are unchanged.
_norm = _textnorm.norm
_quote_found = _textnorm.quote_found


def _parse_axis_values(
    addr: str | list[str], *, el_scheme: str | None = None
) -> tuple[list[tuple[str, float, float]], list[object]]:
    """Address strings → `(spans, el claims)`. An address may carry several params
    (`el=5&bbox=0,0,2272,1234`); every span-checkable param registers its axis —
    integer axes as ints, `time_range=` as fractional seconds (`corpus.segments.
    parse_time_range` — numeric, never lexicographic: `9:59` < `10:00`).

    On a record stamped with `addressing:` the `el` axis is parsed, not regex-matched,
    under the RECORD's own grammar (`el_scheme` — `"ordinal"` v35, else the frozen 3.6
    dotted path) and returned separately, so a malformed value is simply not registered
    rather than being mistaken for an integer span."""
    from corpus.segments import parse_time_range

    out: list[tuple[str, float, float]] = []
    paths: list[object] = []
    addrs = addr if isinstance(addr, list) else [addr]
    for a in addrs:
        if not isinstance(a, str) or "=" not in a:
            continue
        for part in a.split("&"):
            axis, _, value = part.partition("=")
            axis, value = axis.strip(), value.strip()
            if axis == "el" and el_scheme:
                with contextlib.suppress(ValueError):
                    if el_scheme == "ordinal":
                        paths.append(furi.parse_el_ordinal(value))
                    else:
                        paths.append(furi.parse_el_path(value))
                continue
            if axis == "time_range":
                span = parse_time_range(value)
                if span is not None:
                    out.append((axis, *span))
                continue
            m = _SPAN_RE.match(value)
            if m:
                lo = int(m.group(1))
                hi = int(m.group(2)) if m.group(2) else lo
                out.append((axis, lo, hi))
    return out, paths


def _el_paths_overlap(a, b) -> bool:
    """Two §6.1.1 el= claims intersect when either contains the other. Dispatched by
    TYPE — both are always parsed under the same record's single grammar, so this reads
    which class the parser produced, never sniffs a value: `furi.ElPath` (frozen 3.6
    dotted, exact prefix-test containment) or `furi.ElOrdinal` (v35 — `ordinal_overlaps`,
    the conservative NUMERIC proxy, since containment genuinely isn't decidable from two
    addresses alone without the parse this module doesn't have, §6.1.1)."""
    if isinstance(a, furi.ElOrdinal) and isinstance(b, furi.ElOrdinal):
        return furi.ordinal_overlaps(a, b)
    if isinstance(a, furi.ElPath) and isinstance(b, furi.ElPath):
        return furi.el_path_contains(a, b) or furi.el_path_contains(b, a)
    return False  # unreachable in practice — a record's claims share one grammar


def load_record_content(join: CorpusJoin, hash_: str) -> RecordContent | None:
    """Parse the first holding corpus's record into addressable spans."""
    holders = join.holders(hash_)
    if not holders:
        return None
    from corpus import records, segments  # heavy import, deferred

    corpus_root = holders[0].root
    path = join.record_path(corpus_root, hash_)
    try:
        post = records.load(path)
        blocks = segments.iter_blocks(post.content)
    except Exception:  # tolerant by contract: unparseable → no content
        return None
    spans: dict[str, list[tuple[int, int, str]]] = {}
    el_paths: list[tuple[object, str]] = []
    _addressing = records.el_addressing(post)
    el_scheme = (
        None if _addressing is None
        else "ordinal" if _addressing.get("scheme") == "ordinal"
        else "dotted"
    )
    texts: list[str] = []

    def add(addr, *parts):
        text = "\n".join(p for p in parts if p)
        if not text:
            # *(3.7)* A block with no citable text of its own registers no span. This used to
            # be unreachable for an ADDRESSED block, and it stopped being so when the section
            # header lost its last content-bearing fields: 3.5 retired `title`/`description`/
            # `entry`, and 3.7 made the envelope derived (§12.29), so a section now contributes
            # an address and no text. Registering that as a span put an empty string into every
            # hit list its envelope overlapped, and `"\n".join` turned it into a leading
            # newline on the resolved evidence — a quote that had matched exactly then would
            # not. Nothing citable is lost: the section's children carry the text and their own
            # addresses.
            return
        texts.append(text)
        int_spans, paths = _parse_axis_values(addr, el_scheme=el_scheme)
        for axis, lo, hi in int_spans:
            spans.setdefault(axis, []).append((lo, hi, text))
        for p in paths:
            el_paths.append((p, text))

    def block_texts(b) -> tuple[str, ...]:
        # A block's citable text: its body, plus any of the retired prose fields a
        # not-yet-swept record still carries (`description`, `entry`, a section's `title:` on
        # `.extra`) — legacy content a standing quote may still cite, read tolerantly until
        # the sweep reaches it. *(3.5/3.7: a CONFORMANT section contributes none of these, so
        # for a swept record this returns nothing and the block registers no span at all.)*
        parts = (getattr(b, "body", ""), getattr(b, "description", None) or "",
                 getattr(b, "entry", None) or "")
        if isinstance(b, segments.Section):
            parts += (str((b.extra or {}).get("title") or ""),)
        return parts

    for b in blocks:
        add(getattr(b, "address", None), *block_texts(b))
        for seg in getattr(b, "segments", []) or []:
            add(seg.address, *block_texts(seg))
    try:
        for embed in records.iter_embed_blocks(post):
            # embed extras (description, title) ride under `fields` in the
            # parsed block — read both homes, or descriptions silently vanish
            # from the citable text (the 2026-07-03 extraction pass hit this)
            flds = embed.get("fields") if isinstance(embed.get("fields"), dict) else {}
            add(embed.get("address"),
                str(embed.get("description") or flds.get("description") or ""),
                str(embed.get("title") or flds.get("title") or ""))
    except Exception:
        pass
    # the derived display title/description (corpus §4.2.3) are a pure function
    # of the record's own stored blocks — machine-checkable and citable exactly
    # like any attested field, so a quote of the display title still verifies
    # post-3.2 even though the frontmatter pair itself is no longer a
    # verifiable surface in its own right (ledger.md §6.3, 1.2): the derived
    # value it resolves to IS body content, routed through the frontmatter
    # override when one is present (§4.2.1). Origin-block field values are
    # record content too — a quote may cite stored provenance (a chat's group
    # name lives only in its origin fields)
    try:
        title, description = records.derived_editorial(post, corpus_root)
    except Exception:  # tolerant by contract: a schema config error is not a quote failure
        title, description = "", ""
    add(None, title)
    add(None, description)
    try:
        for origin in records.iter_origin_blocks(post):
            for v in (origin.get("fields") or {}).values():
                for item in v if isinstance(v, list) else [v]:
                    if isinstance(item, str):
                        add(None, item)
    except Exception:
        pass
    touches = post.metadata.get("touch") or []
    touch = str(touches[-1]) if isinstance(touches, list) and touches else ""
    from corpus.mime import citation_surface as _citation_surface_for

    media_type = records.media_type_for(post)
    surface = _citation_surface_for(media_type, corpus_root=corpus_root)
    segment_count = sum(1 for _ in segments.leaf_segments(blocks))
    return RecordContent(
        spans=spans, full_text="\n".join(texts), touch=touch,
        media_type=media_type, citation_surface=surface, segment_count=segment_count,
        corpus_root=corpus_root, el_paths=el_paths, el_scheme=el_scheme,
    )


def scoped_text(content: RecordContent, params: list[tuple[str, str]]) -> tuple[str | None, str]:
    """(text the URI resolves to, status) — status: ok | bad-anchor | unchecked.

    A span param scopes to the segments it intersects; a cited span touching
    nothing addressable is a bad anchor. Params with no checkable text mark
    the citation `unchecked` (falls back to whole-record for quote search).
    """
    for key, value in params:
        if key in _UNCHECKED_PARAMS:
            return None, "unchecked"
        if key == "el" and content.el_scheme:
            # (§6.1.1) The record speaks a claim grammar, so the anchor does too — parsed
            # under the SAME scheme the record's own el_paths were (`content.el_scheme`,
            # never sniffed): scope by containment (dotted, exact) or numeric overlap
            # (ordinal, v35 — the conservative proxy, `_el_paths_overlap`) rather than a
            # flat integer interval. An anchor that names nothing the record persists is
            # a BAD anchor, exactly as on the integer axes — falling back to a
            # record-wide quote search would let a confabulated address read as verified
            # evidence.
            try:
                anchor = (
                    furi.parse_el_ordinal((value or "").strip())
                    if content.el_scheme == "ordinal"
                    else furi.parse_el_path((value or "").strip())
                )
            except ValueError:
                return None, "unchecked"
            if not content.el_paths:
                return None, "unchecked"
            hit = [t for (p, t) in content.el_paths if _el_paths_overlap(anchor, p)]
            if not hit:
                return None, "bad-anchor"
            return "\n".join(hit), "ok"
        if key == "time_range":
            from corpus.segments import parse_time_range

            span = parse_time_range((value or "").strip())
            if span is None:
                return None, "unchecked"
            lo, hi = span
        else:
            m = _SPAN_RE.match((value or "").strip())
            if not m:
                return None, "unchecked"
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else lo
        rows = content.spans.get(key)
        if not rows:
            # the record has no segments on this axis — page-cited PDFs whose
            # drafts aren't paginated, an UNSTORED transcript on a media leaf, etc.
            return None, "unchecked"
        hit = [text for (slo, shi, text) in rows if slo <= hi and lo <= shi]
        if not hit:
            return None, "bad-anchor"
        return "\n".join(hit), "ok"
    return content.full_text, "ok"


def _op_engine_map(corpus_root: Path, media_type: str) -> dict[str, str]:
    """`{axis-param: engine-pin}` for every derivation-op axis reachable for
    `media_type`'s resolver pipeline that carries a STATIC engine pin
    (`ResolverOp.engine_version`) — read live off the resolver's own registry
    introspection, never hand-written (§13.2, 1.5). An axis with no static pin
    (an unpinned deterministic op, or a runtime-determined engine like
    `transcribe`'s adapter or the ffmpeg muxing family) carries no entry — there
    is nothing to pin against drift for it."""
    from corpus.resolver import ops_for_media_type

    return {op.param: op.engine_version
            for op in ops_for_media_type(corpus_root, media_type)
            if op.engine_version}


def _derived_resolution(
    corpus_root: Path,
    uri: str,
    media_type: str,
    params: list[tuple[str, str]],
    cache: dict[str, tuple[bool, str, str, dict[str, str]]],
) -> tuple[bool, str, str, dict[str, str]]:
    """Attempt to resolve `uri` (the record's evidence anchor) through the corpus
    resolver — a library call to `corpus.resolver.resolve`, the same path
    `corpus resolve` uses (§6.2) — before an anchor the record's own stored
    markdown can't scope is declared unverifiable (§13.2, 1.5).

    Returns `(resolved, text, reason, pins)`:
    - `resolved=True`: the resolver produced a TEXTUAL surface. `text` holds it;
      `pins` carries `{axis-param: engine-pin}` for every derivation-op axis in
      `params` that carries a static pin — the binding this citation's source
      earns at `--stamp`.
    - `resolved=False`: the honest-unverifiable path applies. `reason` explains
      why — no derivation-op axis in the anchor (never attempted), missing
      artifact bytes, a missing optional extra, a non-textual result, or any
      other resolver error. `text`/`pins` are empty.

    Cached per URI within the run — resolver calls may be slow (container
    extraction) — so the same (hash, anchor) pair is never resolved twice.
    """
    if uri in cache:
        return cache[uri]
    from corpus.resolver import ops_for_media_type

    op_params = {op.param for op in ops_for_media_type(corpus_root, media_type)}
    if not any(k in op_params for k, _ in params):
        # never attempted for an anchor with no derivation-op axis at all — a
        # plain `el=` against a record that already carries stored segments for
        # that axis never reaches this path (it resolves or bad-anchors above);
        # this guards the remaining honest gaps (unregistered/no-op params).
        result = (False, "", "no derivation-op axis in the anchor", {})
        cache[uri] = result
        return result
    op_engine = _op_engine_map(corpus_root, media_type)
    from corpus import resolver as corpus_resolver

    try:
        out_path = corpus_resolver.resolve(uri, corpus_root)
    except Exception as exc:  # tolerant by contract: the op genuinely can't run
        # here (artifact bytes absent, an optional extra not installed, a
        # malformed chain) — that stays honestly unverifiable, never a failure
        result = (False, "", f"{exc.__class__.__name__}: {exc}", {})
        cache[uri] = result
        return result
    if out_path.suffix not in (".txt", ".json"):
        if any(k == "time_range" for k, _ in params):
            # A `time_range=` anchor reaches this path only when the record carries no
            # stored transcript segments to scope against directly (`scoped_text`
            # resolves those without ever calling the resolver). With no `?transcribe`
            # op in the URI, `time_range=` on audio/video mux a media CLIP (§6.2
            # ffmpeg), never text — so "not textual" here always means the transcript
            # itself was never drafted onto the record, not a resolver limitation.
            reason = ("the transcript must be stored on the record before a "
                       "time_range anchor can be cited")
        else:
            reason = (f"derived surface is not textual "
                      f"({out_path.suffix or 'no extension'})")
        result = (False, "", reason, {})
        cache[uri] = result
        return result
    try:
        text = out_path.read_text(encoding="utf-8")
    except OSError as exc:
        result = (False, "", f"could not read derived output ({exc})", {})
        cache[uri] = result
        return result
    used_pins = {k: op_engine[k] for k, _ in params if k in op_engine}
    result = (True, text, "", used_pins)
    cache[uri] = result
    return result


def verify_ledger(
    ledger_root: Path,
    join: CorpusJoin,
    datasets: Mapping[str, Reference],
    *,
    stamp: bool = False,
    only_ids: set[str] | None = None,
    today: str | None = None,
) -> VerifyResult:
    res = VerifyResult()
    if not join.complete:
        res.notes.append(
            f"corpora missing on disk ({', '.join(join.missing)}) — verification skipped"
        )
        return res
    cache: dict[str, RecordContent | None] = {}
    # (1.5) derivation-op resolutions are cached per URI (hash + anchor params)
    # for the whole run — resolver calls may be slow (container extraction) —
    # shared across every fact/source that cites the same (hash, anchor) pair
    derived_cache: dict[str, tuple[bool, str, str, dict[str, str]]] = {}
    # (Phase 1, §6.5) every registered corpus's root — `refdata.resolve`'s
    # fallback for a snapshot with no `path:` override (the mirror lives in
    # the corpus artifact store like any other terminal-contract record)
    corpora_roots = tuple(c.root for c in join.corpora)

    def content_for(h: str) -> RecordContent | None:
        if h not in cache:
            cache[h] = load_record_content(join, h)
        return cache[h]

    for f in sorted(ledger_root.glob("facts/*/*.json")):
        try:
            fact = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if only_ids and fact.get("id") not in only_ids:
            continue
        sources = fact.get("sources")
        if not isinstance(sources, dict):
            sources = {}
        dirty = False
        # verification stays per EVIDENCE entry (an anchor/quote is checked
        # against its own citation); the touch stamp lives per SOURCE (§13.2 —
        # one per fact/source, not one per citing evidence entry). A source is
        # only stamped when every evidence entry that cited it this run
        # reached the verified tail — a genuine failure on one citation must
        # not certify the record as freshly checked for the others.
        source_ok: dict[str, bool] = {}
        source_touch: dict[str, str] = {}
        # (1.5) {skey: {axis-param: engine-pin}} — accumulated from every
        # evidence entry this run that resolved through a derivation op;
        # written into the source's `verified.ops` binding at --stamp
        source_ops: dict[str, dict[str, str]] = {}
        ops_drift_warned: set[str] = set()
        # *(v17, §6.5/§13.2.3)* {skey: (resolved tag, resolved mirror-artifact
        # blake3)} — every `ref` source resolved against `datasets` this run,
        # independent of `source_ok`/`bad`/`ok`: the binding records
        # RESOLUTION, not quote verification, so a resolved ref is stampable
        # even while its content stays unverifiable (no adapter exists yet).
        ref_resolved: dict[str, tuple[str, str]] = {}
        ref_drift_warned: set[str] = set()
        referenced: set[str] = set()

        def bad(skey: str, _map: dict[str, bool] = source_ok) -> None:
            _map[skey] = False

        def ok(skey: str, _map: dict[str, bool] = source_ok) -> None:
            _map.setdefault(skey, True)

        def defer(skey: str, h: str) -> None:
            # *(1.8, §13.2.4)* held on a deferred surface: admissible, unverified,
            # bar-excluded. Blocks the source's stamp (an unchecked citation must
            # not read as freshly verified) and aggregates into the demand signal.
            res.deferred += 1
            res.demand[h] = res.demand.get(h, 0) + 1
            bad(skey)

        for claim in fact.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            sev = res.errors if claim.get("status") == "confirmed" else res.warnings
            where = f"{f.parent.name}/{f.name} :: {claim.get('id')}"
            for e in claim.get("evidence") or []:
                if not isinstance(e, dict):
                    continue
                skey = e.get("source")
                if not isinstance(skey, str):
                    continue  # grammar errors are check's findings, not verify's
                entry = sources.get(skey)
                if not isinstance(entry, dict):
                    continue
                if "ref" in entry:
                    # *(v17, §6.5/§13.2.3)* resolution is a pure manifest
                    # lookup — dataset registration, then tag → mirror-artifact
                    # — tracked in `referenced` the same as a record source so
                    # unreferenced-entry accounting stays coherent.
                    referenced.add(skey)
                    ref_str = str(entry["ref"])
                    rm = SOURCE_REF_RE.match(ref_str)
                    reference = datasets.get(rm.group(1)) if rm else None
                    if rm is None or reference is None:
                        # unregistered dataset (or unparseable grammar) — a
                        # check finding (§13.1), not a verify crash; nothing
                        # to resolve or stamp
                        res.unverifiable += 1
                        res.notes.append(
                            f"{where}: ref://{ref_str} unverifiable (dataset not "
                            "registered in the manifest's references:)")
                        continue
                    tag = rm.group(2)
                    if tag is not None:
                        snap = reference.snapshots.get(tag)
                        if snap is None:
                            # dangling pin (§13.1, 17) — check errors it;
                            # verify stays honestly unverifiable, no stamp
                            res.unverifiable += 1
                            res.notes.append(
                                f"{where}: ref://{ref_str} unverifiable (pinned tag "
                                f"{tag!r} is not a registered snapshot of "
                                f"{rm.group(1)!r})")
                            continue
                        resolved_tag = tag
                        artifact = snap.artifact
                    else:
                        resolved_tag = reference.latest
                        snap = reference.snapshots.get(resolved_tag)
                        if snap is None:
                            res.unverifiable += 1
                            res.notes.append(
                                f"{where}: ref://{ref_str} unverifiable "
                                f"({rm.group(1)!r}'s latest tag {resolved_tag!r} is "
                                "not a registered snapshot)")
                            continue
                        artifact = snap.artifact
                    # drift (§13.2.3, always-on — not gated on --stamp): a bare
                    # cite's resolved (tag, artifact) moving off the stamped
                    # binding, or a pinned cite's artifact moving under its
                    # frozen tag, means the dataset changed under the citation
                    # since it was last bound — flagged once per (fact,
                    # source), mirroring the derivation-op pin-drift warning
                    # above.
                    verified_block = entry.get("verified")
                    if isinstance(verified_block, dict) and skey not in ref_drift_warned:
                        old_tag = verified_block.get("snapshot")
                        old_artifact = verified_block.get("artifact")
                        if old_tag is not None and \
                                (old_tag, old_artifact) != (resolved_tag, artifact):
                            ref_drift_warned.add(skey)
                            res.warnings.append(
                                f"{where}: snapshot binding drifted for "
                                f"ref://{ref_str} ({old_tag}@"
                                f"{str(old_artifact)[:12]}… → {resolved_tag}@"
                                f"{artifact[:12]}…) — re-verification needed")
                    ref_resolved[skey] = (resolved_tag, artifact)
                    # *(Phase 1, §6.5/§13.2.2)* content verification: a real
                    # attempt through refdata now that the adapter foundation
                    # exists. The manifest resolution above is mechanically
                    # true and stamps regardless of what follows; only an
                    # ENTRY-level failure (the mirror doesn't carry the cited
                    # native id) or a FAILING quote withdraws the stamp for
                    # this source — an environment gap (no adapter, no local
                    # mirror bytes) stays honestly unverifiable and never
                    # touches the binding, exactly like the dangling-pin case
                    # above.
                    quote = e.get("quote")
                    try:
                        resolved_entry = refdata.resolve(
                            reference, rm.group(3), tag=tag, corpora_roots=corpora_roots)
                    except (refdata.AdapterUnavailable, refdata.MirrorUnavailable) as exc:
                        res.unverifiable += 1
                        res.notes.append(
                            f"{where}: ref://{ref_str} content unverifiable ({exc})")
                        continue
                    except refdata.EntryNotFound:
                        # the mirror opened and the adapter ran, but the cited
                        # native id names no entry in it — an entry-level
                        # failure exactly like a bad anchor into a record: the
                        # dataset/tag resolved, what's cited inside it does
                        # not, so the stamp is withdrawn for this source
                        sev.append(f"{where}: ref://{ref_str} names no entry in "
                                   f"{rm.group(1)!r}@{resolved_tag!r}")
                        ref_resolved.pop(skey, None)
                        continue
                    except refdata.RefdataError as exc:
                        # defensive: the manifest/tag guards above make this
                        # unreachable in practice — an unexpected resolver
                        # failure must never crash a verify run
                        res.unverifiable += 1
                        res.notes.append(
                            f"{where}: ref://{ref_str} content unverifiable "
                            f"({exc.__class__.__name__}: {exc})")
                        continue
                    if quote:
                        if resolved_entry.text is None:
                            # no text projection (an image entry, e.g.) — the
                            # quote is held, not wrong
                            res.unverifiable += 1
                            res.notes.append(
                                f"{where}: ref://{ref_str} carries no text projection "
                                "— quote unverifiable")
                        # strip_markup=False: adapter-rendered text is external
                        # database content, never normalizer-authored markdown
                        # (the same convention the derivation-op path above uses)
                        elif _quote_found(str(quote), resolved_entry.text,
                                          strip_markup=False):
                            res.verified += 1
                        else:
                            sev.append(f"{where}: quote not found verbatim in "
                                       f"ref://{ref_str} — «{str(quote)[:60]}…»")
                            ref_resolved.pop(skey, None)
                    else:
                        # no quote: a bare existence citation — the entry
                        # resolving at all is what it asserts, and it does
                        res.verified += 1
                    continue
                h = str(entry.get("record", ""))
                if not h:
                    continue
                referenced.add(skey)
                content = content_for(h)
                if content is None:
                    res.unverifiable += 1
                    res.notes.append(f"{where}: corpus://{h[:12]}… has no parseable "
                                     "record content")
                    bad(skey)
                    continue
                source_touch[skey] = content.touch
                # (1.5) a pinned derivation-op engine that has moved since the last
                # stamp is a drift signal the anchor/quote re-check below can't see
                # by itself (the resolver call below always runs the CURRENT engine,
                # so a passing quote doesn't prove the pin is still accurate) —
                # flag it explicitly, once per source per fact.
                verified_block = entry.get("verified")
                stored_ops = verified_block.get("ops") if isinstance(verified_block, dict) \
                    else None
                if isinstance(stored_ops, dict) and stored_ops and skey not in ops_drift_warned \
                        and content.corpus_root is not None:
                    live_ops = _op_engine_map(content.corpus_root, content.media_type)
                    drifted = {p: (pin, live_ops[p]) for p, pin in stored_ops.items()
                              if p in live_ops and live_ops[p] != pin}
                    if drifted:
                        ops_drift_warned.add(skey)
                        detail = ", ".join(f"{p}: {old}→{new}"
                                          for p, (old, new) in drifted.items())
                        res.warnings.append(
                            f"{where}: derivation-op pin drifted for corpus://{h[:12]}… "
                            f"({detail}) — re-verification needed")
                # *(1.4, regraded 1.8, §13.2.4)* a segments-surface record with no
                # persisted segments is a DEFERRED surface: what its byte-facts and
                # derivation ops can still verify below verifies now; everything
                # that would fall back to record-wide soup matching is held as
                # `deferred` instead of failing — resolved by forming.
                surface_deferred = (content.citation_surface == "segments"
                                    and content.segment_count == 0)
                anchor = e.get("anchor")
                uri = derived_uri(sources, skey, anchor) or f"corpus://{h}"
                from corpus import functional_uri

                try:
                    parsed = functional_uri.parse(uri)
                    params = [(k, v or "") for k, v in parsed.params]
                except Exception:
                    params = []
                # (v43, corpus §6.2 op classes) an anchor is address-class ops, optionally
                # ending in one reading. A view (`mark=`, `fit=`), an instrument (`probe`,
                # `geometry`, `scenes=`), or an engine (`transcribe`) in an anchor cites a
                # TOOL, not the source — a citation defect at the claim's severity, never
                # the honest-unverifiable path (which is for surfaces this environment
                # cannot run, not for anchors that should not exist).
                from corpus.transforms import anchor_class_defects

                defects = anchor_class_defects(params)
                if defects:
                    listed = ", ".join(f"`{k}` ({cls})" for k, cls in defects)
                    hint = (" — an engine's output is citable only as stored transcript "
                            "segments (corpus §6.4)"
                            if any(cls == "engine" for _, cls in defects) else "")
                    sev.append(f"{where}: anchor `{anchor}` carries {listed}: anchors name "
                               f"places and readings, never tools (corpus §6.2 op "
                               f"classes){hint}")
                    bad(skey)
                    continue
                text, status = scoped_text(content, params)
                if status == "bad-anchor":
                    sev.append(f"{where}: anchor does not resolve — {anchor} "
                               f"matches no segment of corpus://{h[:12]}…")
                    bad(skey)
                    continue
                quote = e.get("quote")
                if quote:
                    haystack = text if (status == "ok" and text is not None) \
                        else content.full_text
                    if not haystack.strip() and not content.full_text.strip():
                        if surface_deferred:
                            defer(skey, h)
                            continue
                        # a text-less record (an image-only scan not yet OCR'd):
                        # the quote is unverifiable, not wrong
                        res.unverifiable += 1
                        res.notes.append(f"{where}: corpus://{h[:12]}… carries no "
                                         "segment text — quote unverifiable")
                        bad(skey)
                        continue
                    if status == "unchecked" and not _quote_found(str(quote),
                                                                  content.full_text):
                        # (1.5) the anchor addresses content the record's own
                        # markdown doesn't carry (a zip member via ?path=, a
                        # time range, a `prop=`/`row=` derivation …) — before
                        # calling that unverifiable, resolve it through the
                        # corpus resolver itself (the same path `corpus
                        # resolve` uses): a derivation-op axis in the anchor
                        # may mechanically produce the cited text even though
                        # the record's stored body never carries it.
                        resolved, derived_text, reason, pins = False, "", "", {}
                        if content.corpus_root is not None:
                            resolved, derived_text, reason, pins = _derived_resolution(
                                content.corpus_root, uri, content.media_type,
                                params, derived_cache,
                            )
                        if resolved:
                            # strip_markup=False: derived_text is raw resolver
                            # output (JSON/CSV/vcard/chat-export bytes), never
                            # normalizer-authored markdown — its literal `<3`,
                            # `>`, `*`, `|` must compare verbatim, not as markup
                            if _quote_found(str(quote), derived_text, strip_markup=False):
                                res.verified += 1
                                res.derived_resolved += 1
                                if pins:
                                    source_ops.setdefault(skey, {}).update(pins)
                                ok(skey)
                            else:
                                sev.append(
                                    f"{where}: quote not found verbatim in the "
                                    f"derived surface resolved from "
                                    f"corpus://{h[:12]}… ({anchor}) — "
                                    f"«{str(quote)[:60]}…»")
                                bad(skey)
                            continue
                        if surface_deferred:
                            # (1.8) the anchor's surface hasn't formed and no op
                            # could derive it — held, not unverifiable: forming
                            # the record is exactly what resolves it
                            defer(skey, h)
                            continue
                        # unresolvable through the record markdown OR the
                        # resolver — the honest gap the resolver call narrows
                        # (§13.2, 1.5): artifact bytes absent, an optional
                        # extra missing, a non-textual result, no derivation-op
                        # axis in the anchor at all
                        res.unverifiable += 1
                        note = (f"{where}: quote lives behind an anchor the "
                               f"record markdown cannot resolve "
                               f"(corpus://{h[:12]}…)")
                        if reason:
                            note += f" — resolver: {reason}"
                        note += " — unverifiable"
                        res.notes.append(note)
                        bad(skey)
                        continue
                    if not _quote_found(str(quote), haystack):
                        if surface_deferred:
                            # (1.8) the quote isn't on the record's byte-fact
                            # surfaces and its real surface hasn't formed —
                            # held, never soup-matched, never failed
                            defer(skey, h)
                            continue
                        if status == "ok" and text is not None and \
                                _quote_found(str(quote), content.full_text):
                            sev.append(f"{where}: quote exists in the record but NOT at "
                                       f"the cited anchor — re-anchor or widen the span")
                        else:
                            sev.append(f"{where}: quote not found verbatim in "
                                       f"corpus://{h[:12]}… — «{str(quote)[:60]}…»")
                        bad(skey)
                        continue
                if not quote and (status == "unchecked" or surface_deferred):
                    if surface_deferred:
                        # (1.8) a bare cite of a deferred surface attests nothing
                        # checkable yet — held as demand, not counted verified
                        defer(skey, h)
                    else:
                        res.unverifiable += 1
                        bad(skey)
                    continue
                res.verified += 1
                if status == "unchecked" and quote:
                    res.record_scoped += 1
                ok(skey)
        if stamp:
            for skey in referenced:
                entry = sources[skey]
                if skey in ref_resolved:
                    # *(v17, §13.2.3)* resolution-keyed re-stamping: an
                    # unchanged (tag, artifact) never rewrites the binding —
                    # the same discipline as the record path's touch-keyed
                    # re-stamp. Unlike the record path this never gates on
                    # `source_ok` — a resolved ref stamps even though its
                    # content is (and stays) unverifiable.
                    tag, artifact = ref_resolved[skey]
                    prev = entry.get("verified")
                    prev_tag = prev.get("snapshot") if isinstance(prev, dict) else None
                    prev_artifact = prev.get("artifact") if isinstance(prev, dict) else None
                    if prev_tag == tag and prev_artifact == artifact:
                        continue
                    ref_stamped: dict[str, str] = {"snapshot": tag, "artifact": artifact}
                    if today:
                        ref_stamped["at"] = today
                    entry["verified"] = ref_stamped
                    res.stamped += 1
                    dirty = True
                    continue
                if not source_ok.get(skey, False):
                    continue
                touch = source_touch.get(skey, "")
                # (1.5) the ops binding: one entry per derivation-op axis any of
                # this source's evidence resolved through this run, pinned to the
                # engine current at stamp time — {} when every citation resolved
                # from the record's own stored body (nothing to pin)
                current_ops = source_ops.get(skey) or {}
                prev = entry.get("verified")
                prev_touch = prev.get("touch") if isinstance(prev, dict) else None
                prev_ops = (prev.get("ops") or {}) if isinstance(prev, dict) else {}
                # re-stamp only when the snapshot identity OR the op pins moved —
                # both touch- and pin-keyed (§13.2, 1.5): the `at` date alone
                # must not rewrite the tree on every run
                if prev_touch == touch and prev_ops == current_ops:
                    continue
                stamped: dict[str, str | dict[str, str]] = {"touch": touch}
                if today:
                    stamped["at"] = today
                if current_ops:
                    stamped["ops"] = current_ops
                entry["verified"] = stamped
                res.stamped += 1
                dirty = True
        if dirty:
            f.write_text(json.dumps(fact, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")

    # §13.2.4 *(1.8)*: interpretation references to deferred surfaces join the
    # demand aggregate — the citation is itself the pressure signal, so the 1.4
    # needs-warning (enqueue/promote typed beside the discovery) retires. The
    # pre-assertion workspace references such records freely, as ever.
    for f in sorted(ledger_root.glob("interpretations/*.json")):
        try:
            interp = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(interp, dict):
            continue
        # corpus:// refs live in two homes on an interpretation: `based_on` (the
        # standard reference list) and — for a hypothesis's `proposes` — the
        # pre-reforge inline-`uri` evidence shape (proposes predates the fact it
        # targets, so it can't yet cite a sources-table key). Both are references
        # the discovery rides on, so both feed the same demand aggregate.
        refs: list[str] = list(interp.get("based_on") or [])
        proposes = interp.get("proposes")
        if isinstance(proposes, dict):
            for pe in proposes.get("evidence") or []:
                if isinstance(pe, dict):
                    refs.append(str(pe.get("uri", "")))
        counted: set[str] = set()
        for b in refs:
            m = CORPUS_URI_RE.match(str(b))
            if not m or m.group(1) in counted:
                continue
            h = m.group(1)
            content = content_for(h)
            if content is None or content.citation_surface != "segments" \
                    or content.segment_count != 0:
                continue
            counted.add(h)
            res.demand[h] = res.demand.get(h, 0) + 1
    return res
