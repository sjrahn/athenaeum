"""Evidence verification — the anti-hallucination gate (`spec/ledger.md` §13.2).

Beyond record existence: every span anchor must resolve against the cited
record, every quote must be found verbatim (modulo whitespace normalization)
in the content the URI resolves to, and passing entries are stamped with the
record's touch identity (snapshot binding) so a later authoring or migration
pass — anything that moves the touch — flags them for re-verification
instead of silently rotting.

Verification reads record *markdown* only — segment bodies are the faithful
text — so it works without artifact bytes. Anchor forms with no checkable
text (time_range, frame, bbox, path, #fragment) and `ref://` citations
(resolver deferred post-reforge) report `unverifiable`, never failure.

A claim whose evidence FAILS is flagged at the severity of its status:
`confirmed` failing is an error; lower rungs warn.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ledger.corpora import CorpusJoin
from ledger.model import derived_uri

_SPAN_RE = re.compile(r"^(\d+)(?:-(\d+))?$")
_UNCHECKED_PARAMS = {"time_range", "frame", "bbox", "path", "region", "rotate"}


@dataclass
class RecordContent:
    """The addressable text of one record, parsed once."""

    spans: dict[str, list[tuple[int, int, str]]]  # axis -> [(lo, hi, text)]
    full_text: str
    touch: str  # the latest touch identity ("" when the record carries none)


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

    @property
    def ok(self) -> bool:
        return not self.errors


_BLOCK_TAG_RE = re.compile(
    r"</?(?:td|th|tr|p|div|li|ul|ol|h[1-6]|table|thead|tbody|blockquote|section)[^>]*>"
    r"|<br\s*/?>",
    re.I,
)
_TAG_RE = re.compile(r"<[^>]+>")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_ELLIPSIS_RE = re.compile(r"\s*(?:\.\.\.|…|\|)\s*")
_CHAR_FOLD = str.maketrans(  # the fold table IS the ambiguous chars — noqa: RUF001
    {"’": "'", "‘": "'", "“": '"', "”": '"', " ": " "})  # noqa: RUF001


def _norm(s: str) -> str:
    """Markup-insensitive comparison form: entities decode, markdown links
    unwrap, markup becomes whitespace or vanishes (record bodies keep
    faithful HTML tables and inline markers; quotes cite the rendered text),
    typographic quotes fold to straight, whitespace collapses."""
    import html

    s = html.unescape(s).translate(_CHAR_FOLD)
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


def _quote_found(quote: str, haystack: str) -> bool:
    """Verbatim modulo normalization. `...`/`…` inside a quote is elision, and
    `|` separates fragments across cell boundaries; every fragment must be
    found verbatim IN DOCUMENT ORDER — a quote is a reading of the record,
    never a bag of true substrings (order-free matching let "Head bolts |
    100 ft-lb" assemble from the wrong table rows). What order cannot prove
    — which column a table cell sits in — belongs in the evidence `note`,
    not the quote. A separator-squashed retry (whitespace and hyphens
    removed from both sides) absorbs list bullets, inline-markup word
    splits, and soft-wrap artifacts — the characters stay verbatim."""
    hay = _norm(haystack)
    parts = [p for p in _ELLIPSIS_RE.split(quote) if p.strip()]

    def scan(h: str, squash: bool) -> bool:
        pos = 0
        for part in parts:
            n = _norm(part)
            if squash:
                n = _SEPARATORS_RE.sub("", n)
            i = h.find(n, pos)
            if i < 0:
                return False
            pos = i + len(n)
        return True

    return scan(hay, squash=False) or scan(_SEPARATORS_RE.sub("", hay), squash=True)


def _parse_axis_values(addr: str | list[str]) -> list[tuple[str, int, int]]:
    """Address strings → [(axis, lo, hi)] for integer-span axes. An address
    may carry several params (`el=5&bbox=0,0,2272,1234`); every int-span
    param registers its axis."""
    out = []
    addrs = addr if isinstance(addr, list) else [addr]
    for a in addrs:
        if not isinstance(a, str) or "=" not in a:
            continue
        for part in a.split("&"):
            axis, _, value = part.partition("=")
            m = _SPAN_RE.match(value.strip())
            if m:
                lo = int(m.group(1))
                hi = int(m.group(2)) if m.group(2) else lo
                out.append((axis.strip(), lo, hi))
    return out


def load_record_content(join: CorpusJoin, hash_: str) -> RecordContent | None:
    """Parse the first holding corpus's record into addressable spans."""
    holders = join.holders(hash_)
    if not holders:
        return None
    from corpus import records, segments  # heavy import, deferred

    path = join.record_path(holders[0].root, hash_)
    try:
        post = records.load(path)
        blocks = segments.iter_blocks(post.content)
    except Exception:  # tolerant by contract: unparseable → no content
        return None
    spans: dict[str, list[tuple[int, int, str]]] = {}
    texts: list[str] = []

    def add(addr, *parts):
        text = "\n".join(p for p in parts if p)
        if text:
            texts.append(text)
        for axis, lo, hi in _parse_axis_values(addr):
            spans.setdefault(axis, []).append((lo, hi, text))

    def block_texts(b) -> tuple[str, ...]:
        # a block's citable text: body + normalizer-written prose (descriptions,
        # TOC entries) — all of it is record content a quote may cite
        return (getattr(b, "body", ""), getattr(b, "description", None) or "",
                getattr(b, "entry", None) or "")

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
    # frontmatter prose and origin-block field values are record content too —
    # a quote may cite the title, the description, or stored provenance (a
    # chat's group name lives only in its origin fields)
    for key in ("title", "description"):
        add(None, str(post.metadata.get(key) or ""))
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
    return RecordContent(spans=spans, full_text="\n".join(texts), touch=touch)


def scoped_text(content: RecordContent, params: list[tuple[str, str]]) -> tuple[str | None, str]:
    """(text the URI resolves to, status) — status: ok | bad-anchor | unchecked.

    A span param scopes to the segments it intersects; a cited span touching
    nothing addressable is a bad anchor. Params with no checkable text mark
    the citation `unchecked` (falls back to whole-record for quote search).
    """
    for key, value in params:
        if key in _UNCHECKED_PARAMS:
            return None, "unchecked"
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
                        # the anchor addresses content the record markdown does
                        # not carry (a zip member via ?path=, a time range) —
                        # absence there is unverifiable, never refuted
                        res.unverifiable += 1
                        res.notes.append(f"{where}: quote lives behind an anchor the "
                                         f"record markdown cannot resolve "
                                         f"(corpus://{h[:12]}…) — unverifiable")
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
                prev = entry.get("verified")
                # re-stamp only when the snapshot identity moved — the `at`
                # date alone must not rewrite the tree on every run
                if isinstance(prev, dict) and prev.get("touch") == touch:
                    continue
                # OPEN (1.1, spec/ledger.md §13.2; spec/corpus.md §12.19 open
                # question 2): for evidence resolved through a derivation op
                # rather than the stored record body, the binding also pins
                # the op's version label here — format unsettled until the
                # first derived-surface citation lands. Touch-keyed binding
                # below is unaffected and needs no change for that case.
                stamped: dict[str, str] = {"touch": touch}
                if today:
                    stamped["at"] = today
                entry["verified"] = stamped
                res.stamped += 1
                dirty = True
        if dirty:
            f.write_text(json.dumps(fact, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    return res
