"""Stream a record's body to stdout.

The stored content zone when the record has one (a normalized record's authored body, or a
2.x draft's grandfathered mechanical body); otherwise the **derived** body — the `body` op
(§6.2), which re-runs the mime drafter over the artifact on demand — so a 3.0 stub whose
content zone is empty (bytes not stored as a body) is still readable. `--derived` forces the
derivation even when a stored body exists.

`--anchor <axis>=<N>` renders ONLY the segment addressed by an integer-span axis (`el=`,
`turn=`, `prop=`, ...) — the same scoping `ath ledger verify` applies when it checks an
evidence anchor against a cited record, so this is the read-only, span-check equivalent: an
investigator can confirm one quote's anchor without dumping the whole body by hand."""

from __future__ import annotations

import argparse
import sys

from corpus import paths, records
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "--derived",
        action="store_true",
        help="Always derive the body from the artifact (ignore any stored content zone).",
    )
    parser.add_argument(
        "--anchor",
        metavar="AXIS=N",
        default=None,
        help="Render only the segment(s) at this integer-span axis (e.g. --anchor turn=4, "
             "--anchor el=12, --anchor prop=5, or a range --anchor page=2-3) — the same "
             "scoping `ath ledger verify` applies to an evidence anchor. Axes are discovered "
             "from the record itself; an unknown axis or out-of-range N errors naming what "
             "the record actually carries.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    _, record_file = paths.resolve_record(root, args.target)
    post = records.load(record_file)

    anchor = getattr(args, "anchor", None)
    if anchor:
        if getattr(args, "derived", False):
            sys.exit(
                "--anchor and --derived are mutually exclusive: --anchor scopes the record's "
                "stored, segmented body; --derived bypasses that body entirely"
            )
        return _run_anchor(post, anchor)

    stored = post.content or ""
    if stored.strip() and not args.derived:
        text = stored
    else:
        from corpus.derive import DeriveError, derive_body
        from corpus.store import ArtifactMissing

        try:
            text = derive_body(post, root)
        except (DeriveError, ArtifactMissing) as exc:
            sys.exit(f"cannot derive body: {exc}")

    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def _run_anchor(post, anchor: str) -> int:
    from corpus import segments

    axis, sep, value = anchor.partition("=")
    axis = axis.strip()
    if not sep or not axis:
        sys.exit(f"--anchor must be AXIS=N (e.g. --anchor turn=4); got {anchor!r}")
    span = segments.parse_axis_span(value)
    if span is None:
        sys.exit(
            f"--anchor value must be an integer or an integer range (e.g. turn=4 or "
            f"turn=4-6); got {anchor!r}"
        )
    lo, hi = span

    stored = post.content or ""
    if not stored.strip():
        sys.exit(
            "record carries no stored content zone to anchor into (its body would be "
            "derived from the artifact, not segmented — --anchor needs a formed body)"
        )
    try:
        blocks = segments.iter_blocks(stored)
    except ValueError as exc:
        sys.exit(f"cannot parse record content zone: {exc}")

    by_axis: dict[str, list[tuple[int, int, segments.Segment]]] = {}
    for seg in segments.leaf_segments(blocks):
        for a, slo, shi in segments.address_axis_spans(seg.address):
            by_axis.setdefault(a, []).append((slo, shi, seg))

    if axis not in by_axis:
        if not by_axis:
            sys.exit(
                "record carries no integer-addressable segment axes — nothing to anchor into"
            )
        known = ", ".join(
            f"{a}={min(r[0] for r in rows)}-{max(r[1] for r in rows)}"
            for a, rows in sorted(by_axis.items())
        )
        sys.exit(f"unknown anchor axis {axis!r} for this record; it addresses: {known}")

    rows = by_axis[axis]
    hits = [seg for slo, shi, seg in rows if slo <= hi and lo <= shi]
    if not hits:
        lo_all = min(r[0] for r in rows)
        hi_all = max(r[1] for r in rows)
        sys.exit(
            f"{axis}={value} matches no segment; this record's `{axis}` axis spans "
            f"{lo_all}-{hi_all}"
        )

    out = "\n".join(segments.render_segment(seg) for seg in hits)
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    return 0
