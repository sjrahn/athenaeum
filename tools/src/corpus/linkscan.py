"""Anchor-vs-body link-flattening scan (spec #118, #52's third acceptance gate).

An artifact's inline `<a href>` anchor is *flattened* when a normalize pass keeps the
anchor's own TEXT in the record body but drops the link itself — the defect #118's census
found across every normalizer generation despite the html schema having said "keep
`<a href>` as `[text](url)`" since 43598b0 (2026-05-31). `scan_flattened` is that census's
own detector (`tools/scripts/accept_alldata.py`'s `check_links`), lifted into a module both
the script and `corpus.lint`'s `subject-link-flattened` rule import — so a fix to one is a
fix to both, and the two can never quietly drift apart (`home_crumb.py` follows the same
discipline for the breadcrumb detector, porting `accept_alldata.crumb_labels`).

Two judgments do the real work, and both cost the census real false positives before they
were pinned down:

- **flattened vs. omitted.** An anchor whose text never made it into the body at all is an
  OMISSION, not a flattening — conflating the two inflated an early attempt at this census.
  `flattened` requires the text to survive in the body while its `href` does not.
- **subject vs. framing.** `rmap.renders_at()` (spec §7.2's innermost-wins) is what keeps a
  rail or breadcrumb anchor out of this count — only an anchor inside a declared `subject`
  region is a candidate at all, which is #120's own correction to an earlier over-count.

Text comparison decodes HTML entities (`&amp;`, `&rsquo;`, …) before comparing — the
CORRECTED behavior; #118's published figure (16,883 anchors / 2,176 records) was produced
without decoding and is therefore an under-count by ~45%. Reproducing that historical number
is `accept_alldata.py --legacy-text`'s job and stays local to the script; this module only
ever implements the corrected (modern) text treatment.

**A self-edge anchor is never a candidate.** The nav contract (`form/nav`, #89) and the
host guidance both rule that an anchor pointing back at the page it sits on adds no
wayfinding and is OMITTED — so its dropped link is the *mandated* rendering, not a
flattening. Without the exclusion, a correctly-dropped self-edge whose label happens to
repeat elsewhere in the body (measured: a "Service Procedure" rail entry colliding with an
unrelated `<b>Service Procedure</b>` body heading, #52 wave 7) scores as flattened and
blocks finalize on a record the guidance itself required. Callers pass the record's own
origin URIs via `self_urls`; an anchor matches when its href equals one of them outright,
or — for the fragment/rooted relative hrefs a SPA emits — when an origin URI ends with the
href. No `self_urls` means no exclusion, which keeps the detector's historical behavior
for callers that cannot name the page's own address.

**The presence test excludes the trailing `form/nav` span.** #89's restoration renders each
page's own breadcrumb as plain text inside a trailing `<!--section nav-->` span, and a
breadcrumb label routinely repeats a subject-region anchor's own text (measured: ~12 false
positives on one record, samples like "Evaporator Core" arriving via the crumb line, not the
body prose). Scanning the WHOLE body for presence therefore scores an anchor as flattened
when it was in truth never placed at all — an omission wearing a flattening's clothes, the
same false-positive shape the omission-vs-flattening guard above exists to catch. `blocks`
(not a raw body string) is what lets this module tell the two apart: the link-collection pass
still reads the WHOLE body — a markdown link is a link wherever it renders, nav span or not —
but the presence test runs only against the body with the nav span's own rendering excluded.
"""

from __future__ import annotations

import html as _html
import re
from collections.abc import Iterable
from typing import Any

from . import segments as _segments

__all__ = ["ANCHOR", "CHROME_TEXT", "HREF", "MDLINK", "TAG", "plain", "scan_flattened"]

ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
HREF = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
TAG = re.compile(r"<[^>]+>")
MDLINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")

# Anchor texts that are the page's own UI, not the publisher naming a component — carried
# over verbatim from the census that produced #118's published figure (changing this set
# changes the number, so it is not a place to improvise).
CHROME_TEXT = {"open in new tab", "zoom/print", "click for full-size image", "print"}


def plain(fragment: str) -> str:
    """Tag-stripped, entity-decoded text — the modern (corrected) treatment only; see the
    module docstring for why the legacy no-decode variant stays in the script."""
    stripped = TAG.sub(" ", fragment)
    return " ".join(_html.unescape(stripped).replace("\xa0", " ").split())


def _is_self_edge(href: str, self_urls: tuple[str, ...]) -> bool:
    """Does this href point back at the page it sits on? Exact match against the record's
    own origin URIs, or — for the `#/route` / rooted relative forms a SPA emits — an origin
    URI ending with the href (a bare `#` never matches; it names no route)."""
    if href in self_urls:
        return True
    if len(href) > 1 and href.startswith(("#", "/")):
        return any(u.endswith(href) for u in self_urls)
    return False


def scan_flattened(
    html: str, blocks: list[Any], rmap: Any, self_urls: Iterable[str] = ()
) -> dict[str, Any]:
    """Anchors inside a SUBJECT region whose text survived into the body but whose link did
    not. `rmap.renders_at()` implements §7.2's innermost-wins, so a rail link nested inside
    a subject wrapper scores as framing (#120's correction) and never lands here.

    `blocks` is the record's parsed content-zone blocks (`segments.iter_blocks(...)`) — see
    the module docstring for why a raw body string isn't enough: the presence test needs to
    exclude the trailing `form/nav` span's own rendering (the breadcrumb), while the
    link-collection pass reads the whole body regardless.

    Returns `{subject_anchors, flattened, sample, pass}` — `sample` is up to 5 flattened
    texts, `pass` is `flattened == 0`.

    The linked-set counts BOTH markdown links and raw `<a href>` anchors in the body: the
    guidance mandates raw HTML for merged-cell (rowspan/colspan) tables, so a raw anchor
    there is the correct rendering, not a flattening (#52 wave 6's finding — the rule was
    refusing bodies it had itself required).

    `self_urls` — the record's own origin URIs — excludes self-edge anchors from candidacy
    entirely (module docstring): their mandated rendering is omission (#52 wave 7's
    finding, the same refusing-what-it-required shape as the raw-anchor case)."""
    own = tuple(self_urls)
    whole_body = _segments.emit(blocks)
    subject_blocks = [
        b for b in blocks if not (isinstance(b, _segments.Section) and b.form == "nav")
    ]
    subject_body = _segments.emit(subject_blocks)
    linked = {t for t, _u in MDLINK.findall(whole_body)}
    for bm in ANCHOR.finditer(whole_body):
        if HREF.search(bm.group(1)):
            body_text = plain(bm.group(2))
            if body_text:
                linked.add(body_text)
    flattened: list[str] = []
    total_subject = 0
    for m in ANCHOR.finditer(html):
        text = plain(m.group(2))
        if not text or text.lower() in CHROME_TEXT:
            continue
        hm = HREF.search(m.group(1))
        href = next((g for g in (hm.groups() if hm else ()) if g), "") if hm else ""
        if not href:
            continue
        if _is_self_edge(href, own):
            continue
        if rmap.renders_at(m.start()) != "subject":
            continue
        total_subject += 1
        # The text has to still BE there, OUTSIDE the nav span. An anchor whose whole
        # element was never placed is an omission judgment, not a flattening — conflating
        # them is what inflated an earlier pass at this census (module docstring) — and a
        # nav span's own breadcrumb text repeating a subject anchor's label is exactly that
        # conflation wearing a different disguise.
        if text not in linked and re.search(
            r"(?<!\w)" + re.escape(text) + r"(?!\w)", subject_body
        ):
            flattened.append(text)
    return {
        "subject_anchors": total_subject,
        "flattened": len(flattened),
        "sample": flattened[:5],
        "pass": not flattened,
    }
