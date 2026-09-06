"""Address-fidelity scan (#159) — does a segment's body text actually come from the
element its address names?

The #52 drain's single biggest defect family was an address and a body that disagreed while
every existing gate looked elsewhere: lint checked the address's *grammar* (§6.1.1) and the
body's *shape*, `check_order` checked address *sequence*, the link gate checked *anchors* —
and none of them ever asked whether the text at `el=1.3.[2-9]` is the text the segment
renders. Four measured classes, one missing comparison:

- **missing-h3** — a sibling-range address silently swallows a heading whose text never
  reaches the body. The address covers it; the rendering drops it.
- **container fabrication / stale body** — a segment addressed at container X whose body
  text is in truth from a different region of the artifact entirely.
- **fused foreign banner** — text from elsewhere in the artifact fused into the body.
- **off-by-one siblings** — the address points at the wrong sibling and the body renders
  the neighbour's text.

All four fall out of two comparisons run per segment, in both directions:

- **forward** (body → element): every body line must be found in the addressed element's own
  text — or, the other way round, must be built AROUND one of that element's own units
  (`_renders_unit`, the index-entry convention). A line that is neither, but is present
  ELSEWHERE in the artifact, is `misplaced` — borrowed text, which is what fabrication and
  off-by-one both look like from here. A line found nowhere in the artifact at all is
  `unsourced` — weaker, because a normalizer legitimately renders a table caption or an
  `alt` the DOM text doesn't carry.
- **reverse** (element → record): every element child that has text of its own must have
  that text (or its first `_PROBE` characters) somewhere in what the RECORD renders — not
  merely in the judged segment's own body, which is `_rendered_body`'s subject. A miss is
  `dropped`, and the missing-h3 signature is exactly ONE short child missing while the
  forward direction is entirely clean — so the reverse check is deliberately NOT
  ratio-gated.

The comparison itself is `corpus.textnorm` — the same tolerant matcher `ath ledger verify`
uses for quotes, for the same reason: a body is markdown, an artifact is a DOM, and only a
normalized form can honestly say "the same text".

The treatments this module applies that the raw matcher does not were all learned from real
bodies rather than reasoned out, and each removes a family that scored on renderings the
corpus's own contracts require:

- A body line is stripped of its leading markdown BLOCK syntax (`#` heading hashes, `>`
  quote markers, `-`/`*`/`1.` list markers) before comparison. `textnorm.norm` strips
  inline markup only, so without this every heading and every ordered-list item in a
  faithful rendering scores as a defect against a DOM whose `<h2>`/`<li>` text carries no
  such characters.
- A line that is PURE markdown syntax — a `---` rule, a `|---|---|` table separator — is
  skipped in both directions, and skipped out of the body haystack the reverse check reads.
  The separator row has no source counterpart at all, and left in the haystack it sits in
  the middle of a table's text and breaks the contiguous match for the whole table.
- Comparison is case-insensitive and folds the trademark marks (`_cmp`) — a CSS-shouted
  `<th>TSB NUMBER</th>` against a body's "TSB Number" is the same content.
- The reverse direction ignores text carried inside `<a>` descendants
  (`_text_runs_outside_anchors`): whether link text survives is `subject-link-flattened`'s
  question (#118), already gated, and double-reporting it makes two rules claim one defect.
- The reverse direction judges only the SUBJECT: a region an overlay declares `never` or
  `framing` is not owed by a transcription (`_unowed_region_tags`, §7.2/#89).

None of these touch `corpus.textnorm`, whose behavior against the real ledger is a
regression baseline — they live here, where the question is "the same content", not the
ledger's stricter "verbatim".

**This module is pure**: callers hand it the artifact html, the parsed blocks, and the
record's `addressing:` stamp; it opens nothing. `corpus.lint`'s `segment-address-fidelity`
rule and `scripts/accept_alldata.py` both call it, which is the `linkscan` discipline —
one detector, so a fix to one caller's gate is a fix to the other's census.

**Stamped records only.** An unstamped record's `el=` values speak the frozen pre-3.6
filtered index (§12.28), where `el=5` names a different element entirely; judging those
addresses under the path grammar would compare a segment against the wrong element and
report the defect this module exists to find. Callers gate on `records.el_addressing`.
"""

from __future__ import annotations

import copy
import functools
import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from . import functional_uri as furi
from . import segments as _segments
from . import textnorm
from .transforms.html import (
    EL_PARSER_ID,
    iter_element_children,
    path_root,
    resolve_element_path,
    resolve_ordinal,
    total_element_count,
)

__all__ = ["KINDS", "check_fidelity", "el_paths"]

#: The four judgments, in severity order. `misplaced` and `dropped` are the defect classes
#: the drain measured; `unresolvable` is an address that names nothing; `unsourced` is the
#: honest residue — text the artifact's DOM does not carry anywhere (a caption, an `alt`,
#: a normalizer's own table header), which is weak evidence of anything on its own.
KINDS = ("misplaced", "dropped", "unresolvable", "unsourced")

#: A body line shorter than this many normalized characters is not evidence — bullets,
#: dashes, single cells, "Yes"/"N/A" table entries all match somewhere by accident.
_MIN_LINE = 4
#: How much of a long child's text has to be found in the body for it to count as rendered.
_PROBE = 120
#: Longest leaf text still usable as a "the line renders this unit" probe — past it the leaf
#: is a container's worth of text, not a unit a line could be built around.
_UNIT_MAX = 200
_MAX_SAMPLES = 5
_SAMPLE_CHARS = 160

# Leading markdown BLOCK syntax — heading hashes, blockquote markers, list bullets. Repeated
# so a nested `> - item` sheds both. Never applied to the artifact side: a DOM's text is not
# markdown, and a source line that genuinely opens with "1." keeps it there.
_LINE_PREFIX_RE = re.compile(r"^\s*(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)+")
# A word character that is not an underscore — its absence marks a line as pure syntax.
_WORD_RE = re.compile(r"[^\W_]", re.UNICODE)
# Connectives a RENDERING inserts between two texts the DOM carries adjacent — see `_fold`.
_JOINERS_RE = re.compile(r"[/|>\u00b7\u2022\u2023\u2013\u2014]+")
#: Elements that do not break a contiguous run of rendered text — see `_leaf_elements`.
#: Anything absent from this set, including an unrecognized custom element, counts as
#: structure, so the contiguity guarantee is assumed only where it is known to hold.
_INLINE_TAGS = frozenset({
    "a", "abbr", "b", "bdi", "bdo", "big", "br", "cite", "code", "dfn", "em", "font", "i",
    "kbd", "mark", "nobr", "q", "s", "samp", "small", "span", "strike", "strong", "sub",
    "sup", "time", "tt", "u", "var", "wbr",
})
#: What the reverse direction does NOT owe (§7.2) — see `_unowed_region_tags`.
_UNOWED_RENDERS = frozenset({"never", "framing"})
#: Stand-in an anchor leaves behind when its text is lifted out, so the two sides of it stay
#: separate runs instead of being joined into a sentence that was never written.
_ANCHOR_BREAK = "\x00"
#: Punctuation folded in the RETRY pass only (`_fold`), never in the direct one. A label's
#: trailing colon is the renderer's, not the source's: a `<b>Subject:</b>` whose body renders
#: the header as a markdown table (`| Subject | … |`) loses the colon on the way, and 32
#: records in the drained census led with exactly that as a dropped finding.
_FOLD_PUNCT_RE = re.compile(r"[:]+")
# Trademark marks, folded to the spelling a body may use for them — see `_cmp`.
_MARK_FOLD = str.maketrans({"\u00ae": "(r)", "\u2122": "(tm)"})


def el_paths(address: str | list[str] | None) -> list[tuple[str, str]]:
    """Every `el=` value an address names, as `(address string, el value)` pairs.

    An address is a single string or an ordered list (§4.3.2.2), and each may carry several
    axes (`el=1.3&region=0,0,1,1`) — the `el` component is picked out by axis name, not by
    position, so a value that trails another axis is still found. An address with no `el`
    axis contributes nothing: this gate judges element addresses and has nothing to say
    about `page=` or `time_range=`."""
    values = address if isinstance(address, list) else [address]
    out: list[tuple[str, str]] = []
    for addr in values:
        if not isinstance(addr, str):
            continue
        for part in addr.split("&"):
            axis, _, value = part.partition("=")
            if axis.strip() == "el" and value.strip():
                out.append((addr, value.strip()))
    return out


def _line_norm(line: str) -> str:
    """One body line in comparison form: leading block syntax shed, then `textnorm.norm`
    with markdown stripping (a record body IS markdown)."""
    return textnorm.norm(_LINE_PREFIX_RE.sub("", line))


def _body_lines(body: str) -> list[str]:
    """The body's comparable lines, normalized — empties, pure-syntax rules and separator
    rows, and lines too short to be evidence all dropped."""
    out: list[str] = []
    for raw in body.split("\n"):
        n = _line_norm(raw)
        if len(n) < _MIN_LINE or not _WORD_RE.search(n):
            continue
        out.append(n)
    return out


def _rendered_body(blocks: list[Any]) -> str:
    """Everything the RECORD renders, in comparison form — every text segment's body and
    every structural byte-mark's, in document order.

    The reverse (element → record) direction reads this, not the judged segment's own body,
    and the corpus is what settled it. A heading's text routinely lands in a **structural
    byte-mark's body** (§4.3.2.3/§12.32 — a mark's own text IS its body), and #89's
    restoration moves a page's breadcrumb into a trailing `form/nav` span of its own; in both
    cases the element's text is faithfully rendered by the record while sitting in a
    different segment than the one whose address covers it. Scored per-segment, those score
    as dropped — measured on drained records, and it is the record's neighbour segment doing
    exactly what the contracts require.

    The signal survives the widening: `dropped` asks whether the record renders the addressed
    element's text ANYWHERE, and a swallowed `<h3>` is absent from every segment. Text that
    is rendered but in the wrong PLACE is the forward direction's question, and `misplaced`
    is what answers it."""
    return " ".join(
        line
        for seg in _segments.leaf_segments(blocks)
        if seg.atom == "text" or seg.is_structural
        for line in _body_lines(seg.body or "")
    )


def _element_text(nodes: list[Any]) -> str:
    """The rendered text of an addressed region, in comparison form. Joining with `" "` keeps
    adjacent cells and inline spans from fusing into one word; markdown stripping is applied
    to BOTH sides (see `_contains`)."""
    return textnorm.norm(" ".join(_node_text(n) for n in nodes))


@functools.lru_cache(maxsize=16384)
def _cmp(s: str) -> str:
    """Comparison form for THIS module's matching: case folded, and the trademark marks
    spelled the long way (`®` → `(r)`, `™` → `(tm)`) so the two spellings compare equal.

    A source that shouts `<th>TSB NUMBER</th>` under a CSS text-transform and a body that
    renders the header as "TSB Number" carry the same content, and scoring the difference put
    a paired `dropped` + `unsourced` on every such table in the drained set. The trade is
    deliberate and one-directional: a fabrication that differs from the source ONLY in case
    now passes, which is a defect nobody has ever reported, while a faithful title-cased
    header failing at error severity is one the corpus produces by the hundred.

    Applied only inside the comparison helpers, never to the text carried in a finding's
    `sample` — a lower-cased sample is a worse thing to read in a report.

    Local to this module: `textnorm.norm` is `ath ledger verify`'s matcher too, where a quote
    is verified VERBATIM and case is content."""
    return s.translate(_MARK_FOLD).casefold()


@functools.lru_cache(maxsize=16384)
def _fold(s: str) -> str:
    """The retry form: `_cmp`, then `textnorm.squash`'s whitespace and hyphens, plus the
    JOINERS a rendering inserts between two texts the DOM carries adjacent.

    Measured on the live corpus: a rail entry whose DOM is `<a>Description and
    Operation</a><span>Components</span>` renders faithfully as "Description and Operation /
    Components", and the inserted `/` made every such line score as text the artifact carries
    nowhere. A breadcrumb's `>` and a table's `|` are the same insertion. The characters on
    either side stay verbatim — this only stops a connective the renderer supplied from
    being read as a difference in the content.

    Local to this module on purpose: `textnorm.squash` is the ledger's quote-verification
    retry, whose behavior against the real ledger is a regression baseline."""
    return textnorm.squash(_FOLD_PUNCT_RE.sub("", _JOINERS_RE.sub("", _cmp(s))))


def _contains(needle: str, haystack: str) -> bool:
    """Is this normalized text present in that normalized text? Both sides go through `_cmp`
    on the direct pass; the retry (`_fold`) additionally absorbs the word splits an inline
    `<b>`/`<wbr>` puts in the DOM, the ones a soft wrap puts in the body, and the connectives
    a rendering inserts between adjacent source texts."""
    return _cmp(needle) in _cmp(haystack) or _fold(needle) in _fold(haystack)


def _inside_anchor(tag: Any) -> bool:
    """Whether any ancestor of `tag` is an `<a>` — `find_parent("a")` without the filter cost."""
    parent = tag.parent
    while parent is not None:
        if parent.name == "a":
            return True
        parent = parent.parent
    return False


def _text_runs_outside_anchors(tag: Any) -> list[str]:
    """`tag`'s rendered text as the contiguous RUNS that lie outside its `<a>` descendants,
    in comparison form — what the REVERSE direction judges.

    Whether an anchor's text survives into the body is `subject-link-flattened`'s question
    and #118's ticket, gated already; fidelity counting the same omission a second time is
    two gates claiming one defect, and the operator fixing it reads two unrelated rule ids.
    It also removes a whole false-positive family at its root rather than by name: a figure
    viewer's chrome ("Open In New Tab", "Zoom/Print", "Click for full-size image") is
    anchors, and so is a rail cluster's `<li>` of links — both scored as dropped text on
    records whose renderings are correct, and neither needs a hardcoded string list now.

    RUNS, not the spliced remainder, and that distinction is the whole correctness of it.
    Deleting an anchor from the MIDDLE of a sentence and comparing what is left joins two
    halves that were never adjacent: `<p>See the <a>Torque Spec</a> for details.</p>` would
    be probed as "See the for details.", which appears in no faithful body ever written. Each
    side of the anchor is its own run, and each is asked for separately.

    An element that IS an anchor, or sits inside one, is link text through and through and
    yields nothing — without that a bare `<a>` reached as a leaf would smuggle its own text
    straight back into the direction this exclusion exists to keep it out of. A leaf left
    with no run at all (all chrome, an image, a spacer) is simply never judged.

    Anchors are replaced in a COPY (`copy.copy` on a bs4 `Tag` deep-copies): the real tree
    must not be mutated, since every `el=` path in the record indexes into it."""
    # Plain tree walks rather than `find_parent("a")` / `find("a")`: bs4's filter machinery
    # dominated a 77,000-leaf record's fidelity pass, and the question is only "is any
    # ancestor / descendant an `<a>`".
    if tag.name == "a" or _inside_anchor(tag):
        return []
    if not any(isinstance(d, Tag) and d.name == "a" for d in tag.descendants):
        text = textnorm.norm(tag.get_text(" "))
        return [text] if len(text) >= _MIN_LINE else []
    clone = copy.copy(tag)
    for anchor in clone.find_all("a"):
        anchor.replace_with(_ANCHOR_BREAK)
    runs = (textnorm.norm(part) for part in clone.get_text(" ").split(_ANCHOR_BREAK))
    return [run for run in runs if len(run) >= _MIN_LINE]


def _leaf_elements(tag: Any) -> list[Any]:
    """`tag`'s LEAF elements: the OUTERMOST descendants (or `tag` itself) whose element
    children are all inline, so their text renders as one contiguous run.

    The unit both directions measure against, and the reverse direction's in particular: a
    leaf is the largest element whose text is guaranteed to render contiguously, which is the
    largest thing a "does the record render this?" probe can honestly ask about. Probing a
    CONTAINER assumed its whole subtree rendered contiguously, and any body that puts other
    content between a heading and the paragraph after it — which is what a body faithfully
    rendering a section does — broke the match for the container as a whole.

    Inline children do NOT end a leaf (`_INLINE_TAGS`). Counting them as boundaries loses the
    text they sit in rather than tightening anything: `<h3>Torque <b>Values</b></h3>` would
    stop being a leaf and only "Values" would ever be probed, and a heading carrying an
    inline `<a>` — the shape #159's own missing-h3 class arrives in — would vanish from the
    reverse direction entirely. An unrecognized element (a custom `<ad-repair-*>`) counts as
    structure, which keeps the contiguity guarantee conservative rather than assuming it.

    Iterative, not recursive: this host emits unclosed `<li>` chains that `html.parser`
    nests ~1,000 elements deep, past Python's recursion limit."""
    out: list[Any] = []
    stack = [tag]
    while stack:
        node = stack.pop()
        children = iter_element_children(node)
        if all(child.name in _INLINE_TAGS for child in children):
            out.append(node)
        else:
            stack.extend(reversed(children))
    return out


def _leaf_texts(nodes: list[Any]) -> list[str]:
    """The addressed region's smallest text-bearing units, deduped and length bounded. The
    units `_renders_unit` measures a body line against. A region's bare text nodes are units
    in their own right — on a bulletin header they ARE the values."""
    out: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, Tag):
            text = textnorm.norm(str(node))
            if _MIN_LINE <= len(text) <= _UNIT_MAX and text not in seen:
                seen.add(text)
                out.append(text)
            continue
        for leaf in _leaf_elements(node):
            text = textnorm.norm(leaf.get_text(" "))
            if _MIN_LINE <= len(text) <= _UNIT_MAX and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def _renders_unit(line: str, units: list[str]) -> bool:
    """Does this body line RENDER one of the addressed region's own units, with context added
    around it? Containment the other way round from the ordinary forward test.

    The alldata index pages are what forced this, and the convention is deliberate rather
    than defective: the source nests an entry under a category heading, and the entry alone
    ("Components", "Connector Views") means nothing out of that tree, so a faithful rendering
    composes `- [Diagrams / Connector Views](…)`. The address names where the ENTRY is —
    correctly — while the category it needs comes from an ancestor, so a plain "is the line
    inside the addressed text" test reads every index entry in the corpus as borrowed text.

    Two ways to satisfy it, and the second is what the calibration set needed:

    - **containment with a length floor** — a unit that is a SUBSTANTIAL part of the line, a
      third of it, appears inside the line. Loose enough for a composed entry, and floored
      because with enough leaves under one address some four-character unit turns up inside
      any sentence you like — `misplaced` is an error-severity judgment.
    - **exact fragment** — the line, split on the same rendered JOINERS `_fold` removes, has
      a fragment that IS one of the units outright. This is the honest statement of the
      convention: the renderer built the line by joining a category to an entry, so the entry
      survives as a whole fragment. It carries no length floor because it needs none —
      equality to a real unit is the evidence, and the floor was rejecting entries only
      because their category happened to be the longer half ("Description and Operation /
      Components", where the entry is 10 characters against a 12-character floor).

    The target signal survives both: a prose line has no joiner to split on, so its only
    fragment is the whole line, which equals no unit; and a segment addressed at an `<h3>`
    whose body is 40 lines of a different section's prose contains no unit of that `<h3>` at
    any length. The stale-body and off-by-one classes still fire."""
    floor = max(_MIN_LINE, len(line) // 3)
    if any(len(unit) >= floor and _contains(unit, line) for unit in units):
        return True
    exact = {_cmp(unit) for unit in units}
    return any(
        len(fragment) >= _MIN_LINE and _cmp(fragment) in exact
        for fragment in (part.strip() for part in _JOINERS_RE.split(line))
    )


def _unowed_region_tags(soup: Any, regions: list[dict[str, Any]] | None) -> set[int]:
    """The `id()`s of every subtree the TRANSCRIPTION does not owe — an overlay region
    declared `renders: never` or `renders: framing` (§7.2).

    Both are excluded for one reason, and it is settled law rather than a fresh judgment.
    A `never` region is not rendered at all, so its text is nobody's to have dropped. A
    `framing` region IS rendered, but under its OWN named contract — #89's restoration homes
    the page's breadcrumb as a crumb line and the cross-link rail as grouped links in a
    trailing `form/nav` span, and it deliberately carries neither region's DOM verbatim: the
    rail's own "Related Information" label was never rendered, corpus-wide, under sjrahn's
    ruling. Transcription fidelity is a question about the SUBJECT — the region a rendering
    is a faithful transcription OF — so only subject-rendering (or entirely undeclared) DOM
    is owed here.

    Selected against the parsed tree rather than by byte offset the way `corpus.regionmap`
    does it: this module already holds the soup the stamp attests, and a leaf's membership is
    an ancestor question, not an interval one. The two agree on the selector forms overlays
    actually declare — a bare element name and `tag.class` are both valid CSS — and a
    selector neither can resolve simply selects nothing here, which is the same silence
    `origin_declaration_errors` reports on."""
    out: set[int] = set()
    for row in regions or []:
        if row.get("renders") not in _UNOWED_RENDERS:
            continue
        selector = str(row.get("selector") or "").strip()
        if not selector:
            continue
        try:
            matches = soup.select(selector)
        except Exception:
            continue  # a selector this parser cannot express selects nothing
        out.update(id(tag) for tag in matches)
    return out


def _inside_unowed(tag: Any, unowed: set[int]) -> bool:
    """Is this element inside a region the transcription does not owe? Walks ancestors, which
    is cheap at HTML depths and exact — no interval arithmetic to disagree with the DOM."""
    node = tag
    while node is not None:
        if id(node) in unowed:
            return True
        node = node.parent
    return False


def _resolve(root: Any, path: furi.ElPath) -> list[Any]:
    """The NODES an address names: one tag for a point path; for a sibling range, the
    parent's contiguous run of contents from the first named sibling through the last —
    interleaved text nodes included.

    Those bare text nodes are the correction that matters most here. `el=` components count
    ELEMENTS only (§6.1.1: text nodes are invisible to the walk), so a range's endpoints are
    elements — but the REGION a range names is everything between them, and on this corpus
    that is where the content lives. A service bulletin's header is a run of `<b>` labels and
    `<br>` breaks whose VALUES are bare text between them: `<b>Date</b>February 14, 2013<br>`.
    Collecting only the elements' own `get_text()` yields the labels and none of the values,
    so a body faithfully rendering "**Date** February 14, 2013" scores every value it carries
    as text borrowed from elsewhere. Measured: that one mistake produced most of the census's
    `misplaced` mass across the bulletin population.

    `resolve_element_path` walks to (and bounds-checks) the range's PARENT; the endpoints are
    that parent's element children at the 1-based, inclusive range, and the region is the
    slice of `parent.contents` spanning them. Slicing is by IDENTITY, never by `.index()` —
    two `<br/>` tags compare EQUAL under bs4's structural equality, and a run of them is
    exactly what these addresses are made of."""
    node = resolve_element_path(root, path)
    if path.sibling_range is None:
        return [node]
    lo, hi = path.sibling_range
    children = iter_element_children(node)
    first, last = children[lo - 1], children[hi - 1]
    contents = node.contents
    start = next(i for i, c in enumerate(contents) if c is first)
    end = next(i for i, c in enumerate(contents) if c is last)
    region = contents[start : end + 1]
    # Comments, doctypes and CDATA are NavigableString subclasses that render nothing.
    return [n for n in region if isinstance(n, Tag) or type(n) is NavigableString]


def _resolve_ordinal(root: Any, ordinal: furi.ElOrdinal) -> list[Any]:
    """The ORDINAL counterpart of `_resolve` (v35, §6.1.1) — same node-collection
    semantics (a point's own tag; a sibling range's parent-contiguous content run,
    interleaved text nodes included), resolved through the ordinal tree walk rather than
    dotted path algebra. Raises `ValueError` for an out-of-bounds ordinal or a range
    whose endpoints are not siblings — exactly the checks `extract_el` runs before
    materializing, applied here to the same question."""
    if ordinal.sibling_range is None:
        return [resolve_ordinal(root, ordinal.point)]
    a, b = ordinal.sibling_range
    first, last = resolve_ordinal(root, a), resolve_ordinal(root, b)
    if first.parent is None or first.parent is not last.parent:
        raise ValueError(
            f"el={furi.format_el_ordinal(ordinal)}: ordinals {a} and {b} are not siblings "
            f"(spec §6.1.1)"
        )
    contents = first.parent.contents
    start = next(i for i, c in enumerate(contents) if c is first)
    end = next(i for i, c in enumerate(contents) if c is last)
    region = contents[start : end + 1]
    return [n for n in region if isinstance(n, Tag) or type(n) is NavigableString]


def _node_text(node: Any) -> str:
    """A region node's raw rendered text — an element's whole subtree, or a bare text node's
    own characters."""
    return node.get_text(" ") if isinstance(node, Tag) else str(node)


def check_fidelity(
    html: str,
    blocks: list[Any],
    el_addressing: dict,
    regions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Scan one record's segments for address/body disagreement.

    `regions` is the holding origin overlay's declared `regions:` rows
    (`schemas.origin_regions`), and is OPTIONAL — a caller that cannot name the origin simply
    judges every region. Only the `renders: never` rows are read, and only by the REVERSE
    direction: a region §7.2 declares nobody renders is not owed by any rendering, so its
    text is nobody's to have dropped. The forward direction is untouched by it — a body line
    that came out of a never-region is still text this segment took from somewhere it does
    not address, and that judgment is the same either way.

    `html` is the artifact's bytes as text, `blocks` the record's parsed content zone
    (`segments.iter_blocks`), `el_addressing` the record's `addressing:` stamp
    (`records.el_addressing`) — required, and non-None, because this grammar is only legible
    on a stamped record (module docstring). The artifact is parsed ONCE, under the parser
    identity the stamp attests, so the tree walked here is the tree the addresses were
    computed against.

    Only `text`-atom content segments carrying a body and an `el=` address are judged.
    Structural byte-marks, placements, and the body-empty image/audio/video markers state no
    text and have nothing to compare; section envelopes are derived from their children
    (§12.29) and would judge the same text twice.

    Raises `ValueError` when the stamp's two attested facts disagree with this parse — a
    foreign parser identity or a diverging element count, `extract_el`'s check applied to the
    same question. A tree that is not the tree the addresses were computed against would make
    every comparison below a comparison against the wrong element, which is a defect this
    module would then report as the record's. Callers decide what that means: lint stays
    silent (the stamp is another gate's business), a census names it.

    Returns per-record totals, a `findings` list of
    `{segment_index, address, kind, detail, sample}` (one entry per kind per segment, samples
    capped), and `pass` — which is `misplaced`, `dropped` and `unresolvable` all being zero.
    An `unsourced` line does NOT fail the record: it is the honest residue class, not a
    measured defect."""
    parser = str(el_addressing.get("parser") or "")
    if parser and parser != EL_PARSER_ID:
        raise ValueError(
            f"record's el= addresses were computed under parser {parser!r}; this toolchain "
            f"parses with {EL_PARSER_ID!r} and their trees may disagree (§6.1.1)"
        )
    soup = BeautifulSoup(html, EL_PARSER_ID)
    stamped = el_addressing.get("elements")
    if stamped is not None and int(stamped) != total_element_count(soup):
        raise ValueError(
            f"element-count mismatch: the record attests {stamped} elements, this parse "
            f"yields {total_element_count(soup)} — the trees disagree, so el= addresses "
            f"resolve to the wrong elements (§6.1.1)"
        )
    root = path_root(soup)
    ordinal_scheme = el_addressing.get("scheme") == "ordinal"
    whole_text = textnorm.norm(soup.get_text(" "))
    rendered_text = _rendered_body(blocks)
    unowed = _unowed_region_tags(soup, regions)

    findings: list[dict[str, Any]] = []
    counts = dict.fromkeys(KINDS, 0)
    segments_checked = 0
    lines_checked = 0
    # Per-leaf memo for the reverse direction: `(runs, missing)` — the leaf's runs outside
    # anchors and the subset the body renders nowhere — or None for a leaf inside an unowed
    # region. Both are properties of the leaf and the body, not of the segment probing it, so
    # a leaf reached under several addresses (a malformed host nests every unclosed `<p>`
    # under the one before, so each address's subtree is the rest of the document) is walked
    # once; the per-segment `probed` set still decides what each segment reports.
    leaf_memo: dict[int, tuple[list[str], set[str]] | None] = {}

    for index, seg in enumerate(_segments.leaf_segments(blocks)):
        if not seg.is_content or seg.atom != "text" or not (seg.body or "").strip():
            continue
        addressed = el_paths(seg.address)
        if not addressed:
            continue

        resolved: list[tuple[str, list[Any]]] = []
        unresolvable: list[str] = []
        for addr, value in addressed:
            try:
                if ordinal_scheme:
                    tags = _resolve_ordinal(root, furi.parse_el_ordinal(value))
                else:
                    tags = _resolve(root, furi.parse_el_path(value))
            except ValueError as exc:
                unresolvable.append(f"el={value}: {exc}")
                continue
            resolved.append((addr, tags))
        if unresolvable:
            _record(findings, counts, index, seg, "unresolvable",
                    f"{len(unresolvable)} address(es) name no element", unresolvable)
        if not resolved:
            continue

        segments_checked += 1
        # A multi-address segment renders the UNION of its addresses (§4.3.2.2), so the
        # forward direction reads them as one text; the reverse direction still runs per
        # address, since a dropped child belongs to the address that claimed it.
        element_text = _element_text([t for _addr, tags in resolved for t in tags])
        body_lines = _body_lines(seg.body or "")
        lines_checked += len(body_lines)

        element_units = _leaf_texts([t for _addr, tags in resolved for t in tags])
        misplaced: list[str] = []
        unsourced: list[str] = []
        for line in body_lines:
            if _contains(line, element_text) or _renders_unit(line, element_units):
                continue
            (misplaced if _contains(line, whole_text) else unsourced).append(line)
        if misplaced:
            _record(findings, counts, index, seg, "misplaced",
                    f"{len(misplaced)} body line(s) come from elsewhere in the artifact, "
                    f"not from the addressed element", misplaced)
        if unsourced:
            _record(findings, counts, index, seg, "unsourced",
                    f"{len(unsourced)} body line(s) appear nowhere in the artifact",
                    unsourced)

        dropped: list[str] = []
        probed: set[str] = set()
        for addr, tags in resolved:
            for tag in tags:
                # Per LEAF, never per container: contiguity holds inside a leaf and nowhere
                # above it (`_leaf_elements`). Anchor text comes off BEFORE the floor, so a
                # child that is nothing but links falls out here rather than being judged.
                if not isinstance(tag, Tag):
                    continue  # a bare text node has no element identity to name in a finding
                for leaf in _leaf_elements(tag):
                    key = id(leaf)
                    if key not in leaf_memo:
                        if unowed and _inside_unowed(leaf, unowed):
                            leaf_memo[key] = None  # §7.2: the transcription owes only the subject
                        else:
                            runs = _text_runs_outside_anchors(leaf)
                            leaf_memo[key] = (
                                runs,
                                {run for run in runs if not _contains(run[:_PROBE], rendered_text)},
                            )
                    memo = leaf_memo[key]
                    if memo is None:
                        continue
                    runs, missing = memo
                    for run in runs:
                        if run in probed:
                            continue  # this segment already answered for identical text
                        probed.add(run)
                        if run in missing:
                            dropped.append(f"<{leaf.name}> in {addr}: {run}")
        if dropped:
            _record(findings, counts, index, seg, "dropped",
                    f"{len(dropped)} addressed element(s) whose text the record renders "
                    f"nowhere", dropped)

    return {
        "segments": segments_checked,
        "lines": lines_checked,
        **counts,
        "findings": findings,
        "pass": not (counts["misplaced"] or counts["dropped"] or counts["unresolvable"]),
    }


def _record(
    findings: list[dict[str, Any]],
    counts: dict[str, int],
    index: int,
    seg: Any,
    kind: str,
    detail: str,
    samples: list[str],
) -> None:
    """Append one finding — one per kind per segment, its samples capped both in count and
    in length so a scan over thousands of records stays readable and JSON-sized."""
    counts[kind] += len(samples)
    findings.append({
        "segment_index": index,
        "address": seg.address,
        "kind": kind,
        "detail": detail,
        "sample": [s[:_SAMPLE_CHARS] for s in samples[:_MAX_SAMPLES]],
    })
