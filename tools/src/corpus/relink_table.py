"""Restore a data-table's own hyperlinks from the artifact DOM (#164 → #118's table case) —
`corpus relink-table`.

The alldata TSB listing pages render their one table faithfully EXCEPT for links: every
bulletin number and title is an anchor in the DOM, and the retired draft pass emitted the
cells as plain text. `subject-link-flattened` now refuses those records at finalize — 141 of
the 145 otherwise gate-clean table pages in the queue fail on exactly that one rule and
nothing else (measured 2026-08-09).

The repair is surgical, deliberately: re-derive the BODY of each `text/data-table` segment
from the very element its address names, anchors preserved as `[text](href)`, and touch
nothing else. These records' crumbs and rails were homed by the #89 sweep — a whole-zone
re-author would have to reproduce that restoration byte-for-byte to avoid destroying it,
which is a much larger claim than "this table's links come from this table".

The gate layer is `reshape_index`'s, same order, same reasons: dumps-stability, round-trip,
lint-neutrality across the whole rule set, and #159's fidelity gate as the POSITIVE landing
check. Nothing here writes: `relink_table_record` computes `new_text` and the caller decides;
`corpus relink-table` is dry-run by default.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

from bs4 import NavigableString, Tag

from corpus import functional_uri as furi
from corpus import lint, records, segments
from corpus.fidelity import el_paths
from corpus.reshape_index import HOST, fidelity_hold
from corpus.shape.alldata_index import load_stamped_soup
from corpus.transforms.html import iter_element_children, path_root, resolve_element_path

#: The segment opener this verb rewrites — nothing else is touched.
_ATOM = "text/data-table"


@dataclass
class TableRelink:
    record_id: str
    relpath: str
    changed: bool = False
    skipped: str | None = None
    hold: str | None = None
    counts: Counter[str] = dataclass_field(default_factory=Counter)
    new_text: str | None = None


def _cell_md(cell: Tag) -> str:
    """One cell as markdown: text runs verbatim, each anchor as `[label](href)` in document
    order (an anchor with no href or no label renders as its text — there is no link to
    keep). Whitespace squashed, `|` escaped so the cell cannot break its row."""
    out: list[str] = []
    stack: list[object] = list(reversed(cell.contents))
    while stack:
        node = stack.pop()
        if isinstance(node, NavigableString):
            out.append(str(node))
        elif isinstance(node, Tag) and node.name == "a":
            label = " ".join(node.get_text(" ").split())
            href = node.get("href")
            out.append(f"[{label}]({href})" if href and label else label)
        elif isinstance(node, Tag):
            stack.extend(reversed(node.contents))
    return " ".join("".join(out).split()).replace("|", "\\|")


def _table_md(table: Tag) -> str:
    """The whole table as a markdown pipe table, first row the header (its cells `th` or
    `td` alike — the source decides what it calls a header, the shape is rows either way)."""
    rows = table.find_all("tr")
    if not rows:
        raise ValueError("addressed <table> contains no rows")
    lines: list[str] = []
    for i, row in enumerate(rows):
        cells = [c for c in iter_element_children(row) if c.name in ("td", "th")]
        lines.append("| " + " | ".join(_cell_md(c) for c in cells) + " |")
        if i == 0:
            lines.append("|" + "|".join(" --- " for _ in cells) + "|")
    return "\n".join(lines)


def _is_pipe_table(body: str) -> bool:
    """True when the existing body is a pure markdown pipe table — every non-blank line a
    `|` row. That is the ONLY shape this verb replaces: it is a RE-link, and the sweep that
    taught it so (2026-08-09, corpus `76b51383a` partially reverted) found two bodies it
    must never touch. A body carrying prose beyond its table loses that prose to the
    rewrite — and the gates BLESS the loss, because the dropped lines were the very lines
    failing fidelity under the table's address, so the finding disappears with the content.
    And a raw-HTML `<table>` body with colspan/rowspan holds structure a pipe table cannot
    express — replacing it is a degrade, not a repair. Both are re-segmentation or
    re-authoring: another pass's work."""
    lines = [line for line in body.split("\n") if line.strip()]
    return bool(lines) and all(line.lstrip().startswith("|") for line in lines)


def _addressed_table(soup: Tag, address: object) -> Tag | None:
    """The single `<table>` a segment's address names, or None when the address is not one
    point path resolving to a table (a range, a list, another element — not this verb's)."""
    paths = el_paths(address)
    if len(paths) != 1:
        return None
    parsed = furi.parse_el_path(paths[0][1])
    if parsed.sibling_range is not None:
        return None
    node = resolve_element_path(path_root(soup), parsed)
    return node if isinstance(node, Tag) and node.name == "table" else None


def relink_table_record(record_file: Path, corpus_root: Path) -> TableRelink:
    """Compute (never write) the link restoration for one record's data-table segments."""
    original = record_file.read_text(encoding="utf-8")
    post = records.load(record_file)
    rid = str(post.metadata.get("id") or record_file.stem)
    report = TableRelink(record_id=rid, relpath=str(record_file.relative_to(corpus_root)))

    if not any((b.get("id") or "") == HOST for b in records.iter_origin_blocks(post)):
        report.skipped = f"not a {HOST} record"
        return report

    try:
        blocks = segments.iter_blocks(post.content or "")
    except ValueError as exc:
        report.hold = f"content zone does not parse: {exc}"
        return report

    targets = [
        b
        for b in segments.leaf_segments(blocks)
        if b.atom == "text" and b.overlay == _ATOM and b.address
    ]
    if not targets:
        report.skipped = f"no addressed {_ATOM} segment"
        return report

    if records.dumps(post) != original:
        report.hold = "record is not dumps-stable; the serializer would introduce unrelated changes"
        return report

    try:
        soup = load_stamped_soup(corpus_root, post)
    except Exception as exc:
        report.hold = f"{type(exc).__name__}: {exc}"
        return report

    before = Counter(f.rule_id for f in lint.lint(post, blocks, corpus_root))

    rewritten = 0
    for seg in targets:
        try:
            table = _addressed_table(soup, seg.address)
        except ValueError as exc:
            report.hold = f"segment address does not resolve: {exc}"
            return report
        if table is None:
            continue
        if not _is_pipe_table(seg.body or ""):
            report.hold = (
                "a data-table segment's body is not a pure pipe table — replacing it would "
                "drop its non-table content or its spanned-table structure (re-segmentation, "
                "out of scope for a link restoration)"
            )
            return report
        body = _table_md(table)
        if body != (seg.body or "").strip("\n"):
            seg.body = body
            rewritten += 1
    if not rewritten:
        report.skipped = "every addressed table already renders as the DOM's own (links included)"
        return report

    post.content = segments.emit(blocks).rstrip("\n")
    from corpus import touches

    touches.record_touch(post, touches.script_identifier("relink.data-table"))
    new_text = records.dumps(post)

    try:
        reparsed = segments.iter_blocks(post.content or "")
    except ValueError as exc:
        report.hold = f"rewritten content zone does not parse: {exc}"
        return report
    if segments.emit(reparsed).rstrip("\n") != (post.content or "").rstrip("\n"):
        report.hold = "rewritten content zone does not survive an emit round-trip losslessly"
        return report

    after = Counter(f.rule_id for f in lint.lint(post, reparsed, corpus_root))
    worse = sorted(rule for rule in set(before) | set(after) if after[rule] > before.get(rule, 0))
    if worse:
        report.hold = (
            "rewrite would raise lint findings ("
            + ", ".join(f"{r}: {before.get(r, 0)}→{after[r]}" for r in worse)
            + ")"
        )
        return report

    held = fidelity_hold(post, reparsed, corpus_root, rid)
    if held is not None:
        report.hold = held
        return report

    report.counts["tables"] = rewritten
    report.counts["flattened_before"] = before.get("subject-link-flattened", 0)
    report.counts["flattened_after"] = after.get("subject-link-flattened", 0)
    report.changed = True
    report.new_text = new_text
    return report
