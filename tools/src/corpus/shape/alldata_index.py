"""The `index` shaper — my.alldata.com's category/link-list template, authored from the DOM
(#164, spec §7.8, §12.5.0).

These pages are machine-generated: a title, a breadcrumb, and a list of links to the sibling
information types for one vehicle component. Nothing about rendering them is interpretive,
which is the ticket's whole argument — *deterministic before LLM*, applied to where the #52
drain actually spent its tokens. Measured over the queue's 136 index records, the template is
**exactly one shape, 136/136**:

```
div.view-content
├── h3.repair-page-title          the page's title            → structural byte-mark
├── ad-repair-breadcrumb          the path to here (framing)  → the trailing form/nav span
└── div.content
    ├── div.page-header-banner    the title, again            → omitted (see below)
    └── div.itype-container xN    one <a> each, 2 to 9        → the subject link list
```

Every one of those invariants was measured rather than assumed, and the shaper REFUSES a
record that does not present them (`_TemplateMismatch`) instead of authoring something
plausible over a page it does not recognise.

Three judgments the shape encodes, each of them the corpus's own already-stated law:

- **The title becomes a structural byte-mark** (§4.3.2.3/§12.32), not prose. It is the
  source's own declared boundary, and #159's `missing-h3` class is precisely this text going
  unrendered — mechanically, here, it cannot.
- **The banner is omitted.** `div.page-header-banner`'s text equals the `<h3>`'s on 136/136
  records; rendering both states the title twice at two addresses, and the second is not a
  second fact. (The ticket calls this "banner dedup is a text compare" — it is that literal.)
- **The breadcrumb goes to the trailing `form/nav` span, VERBATIM** — #89's law, and the
  overlay states it in full: the labels exactly as they read, never the vehicle name spliced
  in, never reformatted, never the leaf dropped. Its final crumb carries no `href` in the DOM
  (it is this page) and so renders as plain text; the ancestors keep their links.

Registered under the FORM id `index` rather than the origin id. The registry prefers an
origin-keyed shaper for EVERY form that origin declares (`shape_record`), so keying this on
`my.alldata.com` would hand it the host's article records too — pages it knows nothing about.
`index` is declared by exactly one overlay today (`my.alldata.com`'s route rules), and the
template guard is what keeps that honest if a second one ever adopts the id.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter
from bs4 import BeautifulSoup, Tag

from corpus import containment, mime, recordbuild, records
from corpus.shape import register_shaper
from corpus.transforms.html import EL_PARSER_ID, element_path, path_root, total_element_count

#: `<h3>` — the level a byte-mark records for this template's title (§4.3.2.3).
_TITLE_LEVEL = 3


class TemplateMismatch(ValueError):
    """This record's DOM is not the index template the shaper knows. Raised rather than
    guessed around: authoring a plausible rendering over an unrecognised page is exactly the
    fabrication the fidelity gate exists to catch."""


def _text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ").split())


def _mdlink(label: str, href: str | None) -> str:
    """One crumb or entry. A label with no `href` renders as plain text — the breadcrumb's
    leaf is this page itself and the DOM gives it no link, which is also the nav contract's
    no-self-edge rule arriving by itself."""
    return f"[{label}]({href})" if href else label


def load_stamped_soup(corpus_root: Path, post: frontmatter.Post) -> BeautifulSoup:
    """The record's artifact, parsed under the parser its `addressing:` stamp attests.

    The stamp is checked here, not left to the caller: every address this shaper writes is a
    walk over THIS tree, so a parse that disagrees with the attested one would author
    addresses that point at other elements entirely (§6.1.1)."""
    record_id = str(post.metadata.get("id") or "")
    stamp = records.el_addressing(post)
    if stamp is None:
        raise TemplateMismatch(
            "record carries no `addressing:` stamp — its el= addresses would speak the "
            "frozen pre-3.6 index (§12.28), which this shaper does not author"
        )
    parser = str(stamp.get("parser") or "")
    if parser and parser != EL_PARSER_ID:
        raise TemplateMismatch(
            f"record's addresses were computed under parser {parser!r}; this shaper walks "
            f"{EL_PARSER_ID!r} and the trees may disagree (§6.1.1)"
        )
    path = containment.ensure_local_bytes(
        corpus_root, record_id, mime.extension_for(records.media_type_for(post))
    )
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), EL_PARSER_ID)
    attested = stamp.get("elements")
    if attested is not None and int(attested) != total_element_count(soup):
        raise TemplateMismatch(
            f"element-count mismatch: the record attests {attested} elements, this parse "
            f"yields {total_element_count(soup)} — addresses would land on other elements"
        )
    return soup


def _entries(content: Tag) -> list[tuple[Tag, str, str | None]]:
    """Each `div.itype-container` and its single anchor's `(container, label, href)`, in
    source order. The container — not the anchor — is what an address names: it is the unit
    the template repeats, and addressing the run of them is one range instead of N points."""
    out: list[tuple[Tag, str, str | None]] = []
    for container in content.select("div.itype-container"):
        anchors = container.find_all("a")
        if len(anchors) != 1:
            raise TemplateMismatch(
                f"itype-container holds {len(anchors)} anchors, expected exactly 1"
            )
        href = anchors[0].get("href")
        out.append((container, _text(anchors[0]), str(href) if href else None))
    if not out:
        raise TemplateMismatch("no div.itype-container entries — this page lists nothing")
    return out


def _entry_address(root: Tag, content: Tag, entries: list[tuple[Tag, str, str | None]]) -> str:
    """The address of the entry run: a sibling range over the containers, or a point path
    when the template carries exactly one (§6.1.1 — a single child IS its own point path, and
    `[n-n]` is not a legal range).

    The run must be CONTIGUOUS. It is on all 136 measured records — the banner is child 1 and
    the containers follow — but a gap would make the range claim an element the entries do
    not include, so it is checked rather than trusted."""
    first, last = entries[0][0], entries[-1][0]
    base = element_path(content, root)
    lo = int(element_path(first, root).rsplit(".", 1)[-1])
    hi = int(element_path(last, root).rsplit(".", 1)[-1])
    if hi - lo + 1 != len(entries):
        raise TemplateMismatch(
            f"itype-containers are not a contiguous run (children {lo}..{hi} for "
            f"{len(entries)} entries) — a range address would over-claim"
        )
    return f"el={base}.{lo}" if lo == hi else f"el={base}.[{lo}-{hi}]"


def _crumb_line(crumb: Tag) -> str:
    """The breadcrumb as one verbatim line. Labels come from the anchors in document order —
    NOT from the `<li>`s: this host emits unclosed `<li>` tags, so `html.parser` nests each
    inside the last and every `<li>`'s text reads as the whole remaining trail."""
    parts = []
    for anchor in crumb.find_all("a"):
        label = _text(anchor)
        if label:
            href = anchor.get("href")
            parts.append(_mdlink(label, str(href) if href else None))
    if not parts:
        raise TemplateMismatch("breadcrumb carries no labelled anchors")
    return " > ".join(parts)


@register_shaper("index")
def shape_alldata_index(
    build: recordbuild.Build,
    post: frontmatter.Post,
    corpus_root: Path,
    mapping: dict[str, Any],
) -> None:
    """Author the whole content zone of one alldata index page from its DOM. `mapping` is
    unused — the template is the contract (§7.2: a `form:` declaration may carry no mapping
    when the shape needs none)."""
    soup = load_stamped_soup(corpus_root, post)
    root = path_root(soup)

    view = soup.select_one("div.view-content")
    if view is None:
        raise TemplateMismatch("no div.view-content — not the alldata page shell")
    title = view.select_one("h3.repair-page-title")
    crumb = view.select_one("ad-repair-breadcrumb")
    content = view.select_one("div.content")
    if title is None or crumb is None or content is None:
        missing = [
            name
            for name, tag in (
                ("h3.repair-page-title", title),
                ("ad-repair-breadcrumb", crumb),
                ("div.content", content),
            )
            if tag is None
        ]
        raise TemplateMismatch(f"index template is missing {', '.join(missing)}")

    entries = _entries(content)

    recordbuild.open_section(build, form="index")
    recordbuild.add_structural(
        build,
        address=f"el={element_path(title, root)}",
        level=_TITLE_LEVEL,
        mark=_text(title),
    )
    recordbuild.add_segment(
        build,
        atom="text",
        address=_entry_address(root, content, entries),
        body="\n".join(f"- {_mdlink(label, href)}" for _tag, label, href in entries),
    )

    recordbuild.open_section(build, form="nav")
    recordbuild.add_segment(
        build,
        atom="text",
        address=f"el={element_path(crumb, root)}",
        body=_crumb_line(crumb),
    )
