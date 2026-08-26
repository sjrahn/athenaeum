"""Audit a record's `page=N&bbox=` bands against the rendered pixels.

Complements `corpus resolve '...?page=N&words'`, which reads the PDF text layer.
Where that layer is broken — Mathematical-Italic equation pages are the usual
culprit — the text-layer view silently degrades and reports nothing wrong. This
renders each page and measures ink directly, so it stays honest on exactly the
pages that matter most.

    corpus bands <record>              audit every bbox band in the record
    corpus bands <record> --page 19    audit one page
    corpus bands <record> --rows 19    print the page's measured rows and gaps

`cuts` findings are hard defects: a band edge slicing through a line of text, so
neither crop renders a readable sentence. `drift` findings mean the band carries
whitespace well beyond its ink — usually a band that includes running chrome, or
one that has slid off its content.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

log = logging.getLogger(__name__)

_BBOX_RE = re.compile(r"page=(\d+)&bbox=([\d.]+),([\d.]+),([\d.]+),([\d.]+)")


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("record", help="record id (hash prefix) or path")
    parser.add_argument(
        "--page", type=int, default=None,
        help="restrict the audit to this 1-indexed page",
    )
    parser.add_argument(
        "--rows", type=int, default=None, metavar="PAGE",
        help="print measured ink rows for PAGE instead of auditing",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    from corpus import bands as _bands
    from corpus import paths, resolver

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.stderr
    )
    corpus_root = resolved_corpus_root(args)
    record_id, record_file = paths.resolve_record(corpus_root, args.record)
    text = Path(record_file).read_text(encoding="utf-8")

    cache: dict[int, list] = {}

    def rows_for_page(page: int) -> list:
        if page not in cache:
            try:
                # No fit=: native resolution measures ink boundaries more precisely
                # than a downscaled preview would.
                rendered = resolver.resolve(f"corpus://{record_id}?page={page}", corpus_root)
                cache[page] = _bands.ink_rows(rendered)
            except Exception as exc:
                log.warning("page %d did not render (%s); skipping", page, exc)
                cache[page] = []
        return cache[page]

    if args.rows is not None:
        rows = rows_for_page(args.rows)
        print(f"page {args.rows}: {len(rows)} ink row(s)")
        prev = None
        for row in rows:
            gap = f"   gap {round(row.top - prev, 4)}" if prev is not None else ""
            print(f"  {row.top:.4f} - {row.bottom:.4f}  (h={row.height:.4f}){gap}")
            prev = row.bottom
        return 0

    found: list[tuple[int, float, float, int]] = []
    all_pages: set[int] = set()
    for m in _BBOX_RE.finditer(text):
        page = int(m.group(1))
        all_pages.add(page)
        if args.page is not None and page != args.page:
            continue
        top = float(m.group(3))
        found.append((page, round(top, 4), round(top + float(m.group(5)), 4),
                      text[: m.start()].count("\n") + 1))
    if not found:
        print("no bbox bands to audit.")
        return 0

    # Chrome detection needs several pages to find what recurs, so it reads
    # every addressed page — not just the ones under audit. `--page N` used to
    # narrow this set too, which left `detect_chrome` one page to work with; it
    # bails below three and returned nothing, so every running header and footer
    # on that page reported as uncovered *content*. `--page 5` on a clean record
    # claimed three uncovered rows that were the header's two lines and the page
    # number. The comment here already promised whole-document rendering; only
    # the code disagreed.
    chrome_pages = {p: rows_for_page(p) for p in sorted(all_pages)}
    chrome = _bands.detect_chrome(chrome_pages)
    rows_by_page = {p: chrome_pages[p] for p, _, _, _ in found}

    findings = _bands.audit_bands(found, rows_for_page, chrome=chrome)
    missing = _bands.uncovered(found, rows_by_page, chrome)

    cuts = [f for f in findings if f.kind == "cuts"]
    swallowed = [f for f in findings if f.kind == "chrome"]
    drifts = [f for f in findings if f.kind == "drift"]
    print(f"{record_id[:12]}  {len(found)} band(s), "
          f"{len(cuts)} cutting a text row, {len(swallowed)} swallowing chrome, "
          f"{len(drifts)} drifted, {len(missing)} content row(s) uncovered")
    scope = (
        f"{len(chrome_pages)} rendered page(s)"
        if args.page is None
        else f"{len(chrome_pages)} rendered page(s), auditing p{args.page} only"
    )
    print(f"  ({len(chrome)} chrome row(s) detected across {scope})\n")
    for finding in findings:
        print(f"  {finding.kind:<6} p{finding.page:<4} L{finding.line:<6} {finding.detail}")
    for page, row in missing:
        # A row carrying a running-footer's exact height at a shifted y is
        # almost always that footer on a page whose layout differs (front
        # matter, landscape insert). Say so rather than let it read as content
        # loss — banding it would trade a phantom gap for a real chrome swallow.
        note = (
            "  — matches chrome profile at a shifted y; likely running "
            "furniture, crop before banding it"
            if _bands.matches_chrome_profile(row, chrome)
            else ""
        )
        print(f"  gap    p{page:<4} {'':<7} content row [{row.top}, {row.bottom}] "
              f"is covered by no band{note}")
    # Only `cuts` fails the exit code. An uncovered row is often a SANCTIONED
    # drop rather than a defect — the `Decision Class:` / `Document Type:` /
    # `Keywords:` metadata rows of a trailing "Document information" block are
    # dropped on purpose per the pacm/cdm schemas, so they are correctly covered
    # by no band. Read the gaps; don't gate on them.
    return 1 if cuts else 0
