"""List outbound URLs from one or more records' HTML artifacts.

    corpus links <record-id-or-path> [<more>...]
    corpus links --include-subdomains <record>
    corpus links --all-domains <record>
    corpus links --show-captured <record>

The building block for crawl's per-level discovery and any tool that wants "what
does this page link out to that we haven't captured yet."

Default behaviour:
- Reads each input record's HTML artifact, extracts every `<a href>`, resolves
  relatives against the record's first origin URI.
- Normalizes via `corpus.urls.normalize` (lowercase host, sorted query, dropped
  fragment).
- Filters to same-domain (host-exact, against the first input record's host).
- Drops URLs already present in some record's origin URIs.
- Dedupes across all input records; prints one URL per line, sorted.

Stdout = candidate URLs (one per line). Stderr = progress logs.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from corpus import artifacts, mime, paths, records, urls
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

log = logging.getLogger("corpus.links")


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    corpus_root = resolved_corpus_root(args)
    record_paths = [paths.resolve_record(corpus_root, t)[1] for t in args.targets]

    # One pass to map every known origin URI → owning record, so the per-href
    # already-captured check doesn't walk records once per link.
    uri_index = records.build_uri_index(corpus_root)

    posts = [records.load(p) for p in record_paths]
    if not posts:
        log.error("no records resolved")
        return 1

    seed_uri = _first_uri(posts[0])
    if not seed_uri:
        log.error("first record has no origin URI; cannot derive seed host")
        return 1
    seed_host = urls.host_of(seed_uri)
    log.info("seed host: %s%s", seed_host, " (+ subdomains)" if args.include_subdomains else "")

    candidates: dict[str, set[str]] = {}  # normalized_url -> source record ids
    out_of_scope: dict[str, set[str]] = {}
    captured_already: dict[str, set[str]] = {}

    for record_path, post in zip(record_paths, posts, strict=True):
        record_id = str(post.metadata.get("id") or record_path.stem)
        base_uri = _first_uri(post)
        if not base_uri:
            log.warning("%s has no origin URI; skipping", record_id[:12])
            continue
        if records.media_type_for(post) != "text/html":
            log.info("%s: not text/html; no link extraction", record_id[:12])
            continue
        try:
            artifact = artifacts.ensure_local(corpus_root, record_id, mime.extension_for("text/html"))
        except artifacts.ArtifactMissing as exc:
            log.warning("%s: %s", record_id[:12], exc)
            continue

        for raw_href in _extract_hrefs(artifact):
            try:
                absolute = urljoin(base_uri, raw_href)
                normalized = urls.normalize(absolute)
            except ValueError:
                continue
            if not normalized.startswith(("http://", "https://")):
                continue

            in_scope = args.all_domains or urls.same_domain(
                normalized, seed_host, include_subdomains=args.include_subdomains
            )
            if not in_scope:
                out_of_scope.setdefault(normalized, set()).add(record_id)
                continue

            existing_id = uri_index.get(normalized)
            if existing_id and not args.show_captured:
                captured_already.setdefault(normalized, set()).add(record_id)
                continue

            candidates.setdefault(normalized, set()).add(record_id)

    for url in sorted(candidates):
        tag = " [captured]" if args.show_captured and uri_index.get(url) else ""
        print(f"{url}{tag}")

    if args.show_captured:
        for url in sorted(captured_already):
            print(f"{url} [captured]")

    if args.show_out_of_scope and not args.all_domains:
        for url in sorted(out_of_scope):
            print(f"{url} [out-of-scope]")

    log.info(
        "candidates: %d in-scope-new  %d already-captured  %d out-of-scope",
        len(candidates), len(captured_already), len(out_of_scope),
    )
    return 0


def _first_uri(post) -> str:
    """The record's primary origin URI (v1.0). Falls back to a legacy `uris[]`
    frontmatter key for records not yet on the block model."""
    uri = records.primary_origin_uri(post)
    if uri:
        return uri
    legacy = post.metadata.get("uris") or []
    return str(legacy[0]) if legacy else ""


def _extract_hrefs(artifact: Path) -> list[str]:
    html = artifact.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        out.append(href)
    return out


def configure(parser: argparse.ArgumentParser) -> None:
    p = parser
    p.add_argument("targets", nargs="+", help="record id (full or unambiguous prefix) or path to record .md")
    p.add_argument("--include-subdomains", action="store_true", help="widen same-domain to all subdomains of the seed host")
    p.add_argument("--all-domains", action="store_true", help="emit URLs from every domain (off-domain annotated [out-of-scope])")
    p.add_argument("--show-captured", action="store_true", help="also list URLs already captured (annotated [captured])")
    p.add_argument("--show-out-of-scope", action="store_true", help="also list out-of-scope URLs as a separate group")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging on stderr")
    add_corpus_root_arg(parser)
