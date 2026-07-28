"""Evidence verification — the anti-hallucination gate (`spec/ledger.md` §13.2).

Beyond record existence: every span anchor must resolve against the cited
record, every quote must be found verbatim (modulo whitespace normalization)
in the content the URI resolves to, and passing entries are stamped with the
record's touch identity (snapshot binding) so a later authoring or migration
pass — anything that moves the touch — flags them for re-verification
instead of silently rotting.

Verification reads record *markdown* first — segment bodies are the faithful
text — so most of it works without artifact bytes. *(1.5)* An anchor the
stored markdown can't scope (a derivation-op axis: `?path=`, `time_range=`,
`row=`/`col=`, `prop=`, …) is now additionally resolved through the corpus
resolver itself (`corpus.resolver.resolve`, the same path `corpus resolve`
uses) before falling back to `unverifiable` — the honestly-unverifiable
residue narrows to ops the verifying environment genuinely can't run
(artifact bytes absent, an optional extra missing, a non-textual result).
`ref://` citations (resolver deferred post-reforge) still report
`unverifiable`, never failure.

A claim whose evidence FAILS is flagged at the severity of its status:
`confirmed` failing is an error; lower rungs warn.

*(1.4)* One gate ignores claim status entirely: a `segments`-surface record
(corpus §7.1 — raw/derived whole-record text that is presentation soup, e.g.
a captured HTML DOM) carrying zero persisted segments has no citable surface
at all, so claim evidence citing it is an ERROR at any status, before any
anchor/quote matching (§13.2.4). Interpretations are exempt from the error —
they may reference such a record freely — but draw a WARNING when they do so
without a matching `enqueue`/`promote` need naming the same hash.
"""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from corpus import functional_uri as furi
from ledger.corpora import CorpusJoin
from ledger.model import CORPUS_URI_RE, derived_uri

_SPAN_RE = re.compile(r"^(\d+)(?:-(\d+))?$")
_UNCHECKED_PARAMS = {"time_range", "frame", "bbox", "path", "region", "rotate"}


@dataclass
class RecordContent:
    """The addressable text of one record, parsed once."""

    spans: dict[str, list[tuple[int, int, str]]]  # axis -> [(lo, hi, text)]
    full_text: str
    touch: str  # the latest touch identity ("" when the record carries none)
    # (3.6, corpus §6.1.1) `el=` child-index paths, when the RECORD is stamped with
    # `addressing:` — [(path, text)]. Which grammar this record's el= values speak is
    # decided by the record, never by the value's shape: `el=5` is legal under both and
    # means different elements, so the stamp is the only honest discriminator. Integer
    # axes (page/msg/turn/part/…) and unstamped records keep `spans` untouched.
    el_paths: list[tuple[object, str]] = field(default_factory=list)
    el_stamped: bool = False
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
    # *(1.5)* quotes verified against a surface the corpus RESOLVER derived
    # mechanically (a derivation op the record markdown itself can't scope) —
    # verified, at full anchor precision, via a library call to `corpus.resolver`
    derived_resolved: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


_BLOCK_TAG_RE = re.compile(
    r"</?(?:td|th|tr|p|div|li|ul|ol|h[1-6]|table|thead|tbody|blockquote|section)[^<>]*>"
    r"|<br\s*/?>",
    re.I,
)
# `[^<>]+` — NOT `[^>]+` (1.5 defect): a negated class also matches newlines, so on
# arbitrary derived-surface text (raw JSON/chat member content, never HTML-authored)
# a single stray unmatched `<` — a Discord "<3" heart, a bare "x < y" — greedily
# consumed everything up to the NEXT unrelated `>` anywhere later in the document,
# silently deleting spans of a multi-MB derived surface (§13.2, 1.5) including
# whatever quote happened to fall inside. Requiring the run to stay bracket-free
# still matches every well-formed tag `_norm` is meant to strip (`<td>`, `<u>`,
# `<br>` never nest `<`/`>`) while leaving an unmatched stray bracket untouched.
_TAG_RE = re.compile(r"<[^<>]+>")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_ELLIPSIS_RE = re.compile(r"\s*(?:\.\.\.|…|\|)\s*")
_CHAR_FOLD = str.maketrans(  # the fold table IS the ambiguous chars — noqa: RUF001
    {"’": "'", "‘": "'", "“": '"', "”": '"', " ": " "})  # noqa: RUF001


def _norm(s: str, *, strip_markup: bool = True) -> str:
    """Markup-insensitive comparison form: entities decode, markdown links
    unwrap, markup becomes whitespace or vanishes (record bodies keep
    faithful HTML tables and inline markers; quotes cite the rendered text),
    typographic quotes fold to straight, whitespace collapses.

    *(1.5)* `strip_markup=False` for derived-surface text (a resolver op's
    output — raw JSON/CSV/vcard/chat-export bytes, never normalizer-authored
    markdown): a Discord export's literal `<3`, `>` blockquote prefixes, `*`
    emphasis, or `[x]` brackets in ordinary message text are NOT markup to
    strip — record bodies are the one surface where that assumption holds."""
    import html

    s = html.unescape(s).translate(_CHAR_FOLD)
    if strip_markup:
        # markdown links unwrap to their text; inline markers strip
        s = _MD_LINK_RE.sub(r"\1", s)
        s = s.replace("*", "").replace("`", "")
        # structural tags (cells, breaks) become whitespace; inline tags vanish
        # (an underline inside a word must not split it)
        s = _BLOCK_TAG_RE.sub(" ", s)
        s = _TAG_RE.sub("", s)
        s = s.replace("|", " ")
    s = " ".join(s.split())
    return re.sub(r"\s+(['.,;:!?])", r"\1", s)


_SEPARATORS_RE = re.compile(r"[\s\-]+")


def _quote_found(quote: str, haystack: str, *, strip_markup: bool = True) -> bool:
    """Verbatim modulo normalization. `...`/`…` inside a quote is elision, and
    `|` separates fragments across cell boundaries; every fragment must be
    found verbatim IN DOCUMENT ORDER — a quote is a reading of the record,
    never a bag of true substrings (order-free matching let "Head bolts |
    100 ft-lb" assemble from the wrong table rows). What order cannot prove
    — which column a table cell sits in — belongs in the evidence `note`,
    not the quote. A separator-squashed retry (whitespace and hyphens
    removed from both sides) absorbs list bullets, inline-markup word
    splits, and soft-wrap artifacts — the characters stay verbatim.

    `strip_markup=False` (§13.2, 1.5) for matching against a derived-surface
    resolver output — see `_norm`."""
    hay = _norm(haystack, strip_markup=strip_markup)
    parts = [p for p in _ELLIPSIS_RE.split(quote) if p.strip()]

    def scan(h: str, squash: bool) -> bool:
        pos = 0
        for part in parts:
            n = _norm(part, strip_markup=strip_markup)
            if squash:
                n = _SEPARATORS_RE.sub("", n)
            i = h.find(n, pos)
            if i < 0:
                return False
            pos = i + len(n)
        return True

    return scan(hay, squash=False) or scan(_SEPARATORS_RE.sub("", hay), squash=True)


def _parse_axis_values(
    addr: str | list[str], *, el_stamped: bool = False
) -> tuple[list[tuple[str, int, int]], list[object]]:
    """Address strings → `(integer spans, el paths)`. An address may carry several
    params (`el=5&bbox=0,0,2272,1234`); every int-span param registers its axis.

    On a record stamped with `addressing:` the `el` axis is a §6.1.1 child-index path
    and is returned separately — parsed, not regex-matched, so a malformed value is
    simply not registered rather than being mistaken for an integer span."""
    out: list[tuple[str, int, int]] = []
    paths: list[object] = []
    addrs = addr if isinstance(addr, list) else [addr]
    for a in addrs:
        if not isinstance(a, str) or "=" not in a:
            continue
        for part in a.split("&"):
            axis, _, value = part.partition("=")
            axis, value = axis.strip(), value.strip()
            if axis == "el" and el_stamped:
                with contextlib.suppress(ValueError):
                    paths.append(furi.parse_el_path(value))
                continue
            m = _SPAN_RE.match(value)
            if m:
                lo = int(m.group(1))
                hi = int(m.group(2)) if m.group(2) else lo
                out.append((axis, lo, hi))
    return out, paths


def _el_paths_overlap(a, b) -> bool:
    """Two §6.1.1 addresses intersect when either contains the other — a segment at
    `el=1.3` holds a quote anchored at `el=1.3.2`, and an anchored envelope
    `el=1.[2-9]` holds a segment at `el=1.4`."""
    return furi.el_path_contains(a, b) or furi.el_path_contains(b, a)


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
    el_stamped = records.el_addressing(post) is not None
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
        int_spans, paths = _parse_axis_values(addr, el_stamped=el_stamped)
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
        corpus_root=corpus_root, el_paths=el_paths, el_stamped=el_stamped,
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
        if key == "el" and content.el_stamped:
            # (3.6) The record speaks §6.1.1, so the anchor does too: scope by path
            # intersection rather than numeric interval. An anchor that names nothing
            # the record persists is a BAD anchor, exactly as on the integer axes —
            # falling back to a record-wide quote search would let a confabulated
            # address read as verified evidence.
            try:
                anchor_path = furi.parse_el_path((value or "").strip())
            except ValueError:
                return None, "unchecked"
            if not content.el_paths:
                return None, "unchecked"
            hit = [t for (p, t) in content.el_paths if _el_paths_overlap(anchor_path, p)]
            if not hit:
                return None, "bad-anchor"
            return "\n".join(hit), "ok"
        m = _SPAN_RE.match((value or "").strip())
        if not m:
            return None, "unchecked"
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        rows = content.spans.get(key)
        if not rows:
            # the record has no segments on this axis — page-cited PDFs whose
            # drafts aren't paginated, etc.
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
        result = (False, "", f"derived surface is not textual "
                             f"({out_path.suffix or 'no extension'})", {})
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
    datasets: set[str],
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
        referenced: set[str] = set()

        def bad(skey: str, _map: dict[str, bool] = source_ok) -> None:
            _map[skey] = False

        def ok(skey: str, _map: dict[str, bool] = source_ok) -> None:
            _map.setdefault(skey, True)

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
                    res.unverifiable += 1
                    res.notes.append(f"{where}: ref://{entry['ref']} unverifiable "
                                     "(mirror resolver lands post-reforge)")
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
                if content.citation_surface == "segments" and content.segment_count == 0:
                    # §13.2.4: a segments-surface record with no persisted segments has
                    # no citable surface at all — record-wide matching against its raw/
                    # derived whole-record text (nav chrome, script payloads, inlined
                    # framing) would be structurally misleading, not merely weak. This
                    # is an error regardless of claim status (unlike `sev` below), and
                    # it preempts anchor/quote matching entirely — no fallback applies.
                    res.errors.append(
                        f"{where}: evidence cites corpus://{h[:12]}… whose mime "
                        f"({content.media_type}) requires a rendered surface — no "
                        "persisted segments; enqueue for normalize, cite after (§13.2.4)"
                    )
                    bad(skey)
                    continue
                anchor = e.get("anchor")
                uri = derived_uri(sources, skey, anchor) or f"corpus://{h}"
                from corpus import functional_uri

                try:
                    parsed = functional_uri.parse(uri)
                    params = [(k, v or "") for k, v in parsed.params]
                except Exception:
                    params = []
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
                        if status == "ok" and text is not None and \
                                _quote_found(str(quote), content.full_text):
                            sev.append(f"{where}: quote exists in the record but NOT at "
                                       f"the cited anchor — re-anchor or widen the span")
                        else:
                            sev.append(f"{where}: quote not found verbatim in "
                                       f"corpus://{h[:12]}… — «{str(quote)[:60]}…»")
                        bad(skey)
                        continue
                if status == "unchecked" and not quote:
                    res.unverifiable += 1
                    bad(skey)
                    continue
                res.verified += 1
                if status == "unchecked" and quote:
                    res.record_scoped += 1
                ok(skey)
        if stamp:
            for skey in referenced:
                if not source_ok.get(skey, False):
                    continue
                entry = sources[skey]
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

    # §13.2.4 (interpretations exempt from the error): a segment-less
    # segments-surface record may be referenced freely — the pre-assertion
    # workspace exists precisely to hold discoveries the evidence bar can't
    # yet carry — but referencing one without a matching enqueue/promote
    # need (naming that same hash) draws a warning, so the normalize demand
    # rides along with the discovery instead of silently going missing.
    for f in sorted(ledger_root.glob("interpretations/*.json")):
        try:
            interp = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(interp, dict):
            continue
        where = f"interpretations/{f.name} :: {interp.get('id')}"
        need_hashes: set[str] = set()
        for n in interp.get("needs") or []:
            if not isinstance(n, dict) or n.get("action") not in ("enqueue", "promote"):
                continue
            nm = CORPUS_URI_RE.match(str(n.get("record", "")))
            if nm:
                need_hashes.add(nm.group(1))
        # corpus:// refs live in two homes on an interpretation: `based_on` (the
        # standard reference list) and — for a hypothesis's `proposes` — the
        # pre-reforge inline-`uri` evidence shape (proposes predates the fact it
        # targets, so it can't yet cite a sources-table key, check.py's
        # PROPOSES_EVIDENCE_KEYS handling). Both are references the discovery
        # rides on, so both draw the same warning under the same need-matching.
        refs: list[str] = list(interp.get("based_on") or [])
        proposes = interp.get("proposes")
        if isinstance(proposes, dict):
            for pe in proposes.get("evidence") or []:
                if isinstance(pe, dict):
                    refs.append(str(pe.get("uri", "")))
        warned: set[str] = set()
        for b in refs:
            m = CORPUS_URI_RE.match(str(b))
            if not m or m.group(1) in warned or m.group(1) in need_hashes:
                continue
            h = m.group(1)
            content = content_for(h)
            if content is None or content.citation_surface != "segments" \
                    or content.segment_count != 0:
                continue
            warned.add(h)
            res.warnings.append(
                f"{where}: references corpus://{h[:12]}… (segments-surface, none "
                "persisted) with no enqueue/promote need — type the demand beside "
                "the discovery"
            )
    return res
