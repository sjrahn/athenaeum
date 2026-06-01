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
    p.add_argument("--video", action="store_true", help="force yt-dlp dispatch (override the host check)")
    p.add_argument(
        "--no-video",
        action="store_true",
        help="force Playwright (skip the yt-dlp host check, even for youtube.com etc.)",
    )
    p.add_argument(
        "--no-comments",
        action="store_true",
        help="when using yt-dlp, skip the comment scrape (faster for high-traffic videos)",
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
    print(record_path)
    return 0
