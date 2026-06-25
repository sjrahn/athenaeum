"""Capture a URL into capture/, then ingest it to a record stub.

Thin wrapper over `corpus.capture`: turns argv into a `CaptureOptions`, then
calls `capture()` (with `--no-ingest`) or `capture_and_ingest()`.

Stdout (default):       absolute path of the resulting record.
Stdout (--no-ingest):   absolute path of the captured file.
Stderr:                 progress logs.
"""

from __future__ import annotations

import argparse
import logging
import sys

from corpus import capture as capture_lib
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    p = parser
    p.add_argument("url", help="the URL to capture")
    p.add_argument(
        "--no-ingest",
        action="store_true",
        help="stop after writing capture/<sanitized>.<ext>; do not call ingest",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="capture even if the URL already appears in a record's origin URIs",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=capture_lib.DEFAULT_TIMEOUT_S,
        help=f"navigation / network-idle timeout in seconds (default: {capture_lib.DEFAULT_TIMEOUT_S})",
    )
    p.add_argument(
        "--viewport",
        default=f"{capture_lib.DEFAULT_VIEWPORT[0]}x{capture_lib.DEFAULT_VIEWPORT[1]}",
        help=f"browser viewport WxH (default: {capture_lib.DEFAULT_VIEWPORT[0]}x{capture_lib.DEFAULT_VIEWPORT[1]})",
    )
    p.add_argument(
        "--user-agent",
        default=capture_lib.DEFAULT_USER_AGENT,
        help="User-Agent header (default: a recent Chrome string). Ignored in CDP mode.",
    )
    p.add_argument(
        "--cdp-url",
        default=None,
        help=(
            "Connect to an existing Chrome via CDP instead of launching headless "
            "(e.g. http://localhost:9222). Reuses the running browser's default "
            "context so cookies / login state persist. Falls back to env var "
            "CAPTURE_CDP_URL, then auto-detect on http://localhost:9222 (suppress "
            "with CAPTURE_NO_CDP=1)."
        ),
    )
    p.add_argument(
        "--transport",
        choices=("headless", "headed", "cdp"),
        default=None,
        help=(
            "browser transport for HTML capture; overrides any recipe / config default. "
            "headed needs a display (xvfb-run on a headless box); cdp attaches to a running "
            "Chrome (see --cdp-url) to reuse login state."
        ),
    )
    p.add_argument(
        "--fidelity",
        choices=("exact", "balanced", "lean"),
        default=None,
        help=(
            "snapshot fidelity for HTML capture; overrides any recipe / config default. "
            "exact = byte-faithful (presentation is content); balanced = drop redundant "
            "font/image/media alternates (~-76%%, the default); lean = also prune unused "
            "CSS (~-91%%, information-faithful). Records are identical across tiers."
        ),
    )
    p.add_argument(
        "--video",
        action="store_true",
        help="force the video (yt-dlp) capturer, overriding the overlay's capturer",
    )
    p.add_argument(
        "--no-video",
        action="store_true",
        help="force the browser capturer, overriding the overlay's capturer",
    )
    p.add_argument(
        "--no-comments",
        action="store_true",
        help="when using yt-dlp, skip the comment scrape (faster for high-traffic videos)",
    )
    p.add_argument(
        "--with-references",
        action="store_true",
        help=(
            "after capturing an HTML page, also grab its overlay-declared dependent "
            "references (capture.references, spec §7.2) at depth 1 — every declared match, "
            "overriding each rule's `capture:` flag. Default: honor per-rule `capture: true`. "
            "Preview with `corpus links --references`."
        ),
    )
    p.add_argument(
        "--no-references",
        action="store_true",
        help="suppress the dependent-reference grab even for rules that set `capture: true`",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="enable DEBUG logging")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    corpus_root = resolved_corpus_root(args)
    if args.with_references and args.no_references:
        sys.exit("--with-references and --no-references are mutually exclusive")
    try:
        viewport = capture_lib.parse_viewport(args.viewport)
    except ValueError as e:
        sys.exit(str(e))

    opts = capture_lib.CaptureOptions(
        timeout_s=args.timeout,
        viewport=viewport,
        user_agent=args.user_agent,
        cdp_url=args.cdp_url,
        transport=args.transport,
        fidelity=args.fidelity,
        video=args.video,
        no_video=args.no_video,
        no_comments=args.no_comments,
        force=args.force,
    )

    try:
        if args.no_ingest:
            result = capture_lib.capture(args.url, corpus_root=corpus_root, opts=opts)
            print(result.capture_path)
            return 0
        record_path = capture_lib.capture_and_ingest(args.url, corpus_root=corpus_root, opts=opts)
    except capture_lib.CaptureError as e:
        sys.exit(str(e))

    if record_path is None:
        sys.exit("capture: ingest failed")

    _maybe_grab_references(args, corpus_root, record_path, opts)
    print(record_path)
    return 0


def _maybe_grab_references(args, corpus_root, record_path, opts) -> None:
    """Depth-1 grab of the just-captured page's declared dependent references (spec §7.2).
    Honors per-rule `capture: true` by default; `--with-references` forces all, and
    `--no-references` suppresses it. HTML-only; silent when the host declares no rules."""
    from corpus import artifacts, mime, records, references

    force = True if args.with_references else (False if args.no_references else None)
    if force is False:
        return
    post = records.load(record_path)
    if records.media_type_for(post) != "text/html":
        if force is True:
            logging.getLogger("corpus.capture").info(
                "--with-references: primary is not text/html; nothing to grab"
            )
        return
    record_id = str(post.metadata.get("id") or "")
    try:
        artifact = artifacts.ensure_local(
            corpus_root, record_id, mime.extension_for("text/html")
        )
    except artifacts.ArtifactMissing:
        return
    html = artifact.read_text(encoding="utf-8", errors="replace")
    result = references.fetch_references(corpus_root, post, html, force=force, opts=opts)
    if not result.selected:
        return
    log = logging.getLogger("corpus.capture")
    log.info(
        "references: %d selected, %d captured, %d already present, %d failed",
        len(result.selected),
        len(result.captured),
        len(result.existing),
        len(result.failed),
    )
    for url, reason in result.failed:
        log.warning("reference capture failed: %s (%s)", url, reason)
