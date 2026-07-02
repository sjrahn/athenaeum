"""Same-domain crawler.

A BFS frontier + politeness layer + same-domain filter on top of
`corpus.capture`: it walks links from a seed URL, captures each page in-process,
and never writes records or artifacts directly (capture → ingest does that).

    corpus crawl <seed-url>
    corpus crawl --depth 1 --count 25 <seed-url>
    corpus crawl --dry-run --depth 2 <seed-url>
    corpus crawl --resume <seed-url>
    corpus crawl --yes <seed-url>              # skip the confirmation gate
    corpus crawl --include-subdomains <seed-url>

State persists to `capture/crawl-<seed-hash>.json` so a Ctrl-C is resumable
(`--resume` picks up where it left off).

Stdout: nothing on success — all reporting is on stderr. Exit 0 on clean
completion (even with per-URL failures); non-zero only on catastrophic errors.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

import blake3
from bs4 import BeautifulSoup

from corpus import artifacts, mime, paths, records, urls
from corpus import capture as capture_lib
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root
from corpus.capture import recipes

log = logging.getLogger("corpus.crawl")

DEFAULT_USER_AGENT = "athenaeum-crawl/0.1"
DEFAULT_DEPTH = 2
DEFAULT_COUNT = 50
DEFAULT_DELAY = 1.0


@dataclass
class CrawlState:
    """Persistent crawl state. Serialized to capture/crawl-<seed-hash>.json."""

    seed: str
    normalized_seed: str
    seed_host: str
    depth_cap: int
    count_cap: int
    include_subdomains: bool
    visited: list[str] = field(default_factory=list)  # normalized URLs already captured
    frontier: list[tuple[str, int]] = field(default_factory=list)  # (normalized_url, depth)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (normalized_url, reason)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (normalized_url, reason)

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "normalized_seed": self.normalized_seed,
            "seed_host": self.seed_host,
            "depth_cap": self.depth_cap,
            "count_cap": self.count_cap,
            "include_subdomains": self.include_subdomains,
            "visited": list(self.visited),
            "frontier": [list(item) for item in self.frontier],
            "failed": [list(item) for item in self.failed],
            "skipped": [list(item) for item in self.skipped],
        }

    @classmethod
    def from_dict(cls, data: dict) -> CrawlState:
        return cls(
            seed=data["seed"],
            normalized_seed=data["normalized_seed"],
            seed_host=data["seed_host"],
            depth_cap=data["depth_cap"],
            count_cap=data["count_cap"],
            include_subdomains=data.get("include_subdomains", False),
            visited=list(data.get("visited", [])),
            frontier=[tuple(x) for x in data.get("frontier", [])],
            failed=[tuple(x) for x in data.get("failed", [])],
            skipped=[tuple(x) for x in data.get("skipped", [])],
        )


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    corpus_root = resolved_corpus_root(args)

    if args.references:
        return _run_references_mode(args, corpus_root)

    if not args.seed_url:
        log.error("a seed URL is required (omit it only with --references)")
        return 1

    capture_dir = corpus_root / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)

    normalized_seed = urls.normalize(args.seed_url)
    seed_host = urls.host_of(normalized_seed)
    if not seed_host:
        log.error("seed URL has no host: %s", args.seed_url)
        return 1

    sidecar = _sidecar_path(capture_dir, normalized_seed)

    if args.resume:
        if not sidecar.is_file():
            log.error("no sidecar to resume from: %s", sidecar)
            return 1
        state = CrawlState.from_dict(json.loads(sidecar.read_text(encoding="utf-8")))
        log.info(
            "resuming: visited=%d frontier=%d failed=%d sidecar=%s",
            len(state.visited), len(state.frontier), len(state.failed), sidecar,
        )
    else:
        state = CrawlState(
            seed=args.seed_url,
            normalized_seed=normalized_seed,
            seed_host=seed_host,
            depth_cap=args.depth,
            count_cap=args.count,
            include_subdomains=args.include_subdomains,
        )

    robots = _load_robots(seed_host, user_agent=args.user_agent) if not args.dry_run else None

    if not args.resume:
        seed_record = _capture_one(
            state.normalized_seed,
            corpus_root=corpus_root,
            user_agent=args.user_agent,
            dry_run=args.dry_run,
            robots=robots,
            fidelity=args.fidelity,
        )
        if seed_record is None and not args.dry_run:
            log.error("failed to capture seed; aborting")
            return 1
        state.visited.append(state.normalized_seed)
        if seed_record is not None:
            _expand(state, seed_record, current_depth=0, corpus_root=corpus_root)
        _save_sidecar(sidecar, state)

    if not args.yes and not args.dry_run:
        decision = _confirm(state, sidecar=sidecar, robots=robots)
        if decision == "abort":
            log.info("aborted by user")
            return 0
        if decision == "narrow":
            log.info("narrowed; re-run with adjusted --depth or --count")
            return 0

    if args.dry_run:
        _report_dry_run(state)
        return 0

    captured = 0
    while state.frontier and len(state.visited) < state.count_cap:
        url, depth = state.frontier.pop(0)
        if url in state.visited:
            continue
        if robots is not None and not robots.can_fetch(args.user_agent, url):
            log.info("robots-disallowed: %s", url)
            state.skipped.append((url, "robots-disallowed"))
            _save_sidecar(sidecar, state)
            continue
        time.sleep(args.delay)
        record_path = _capture_one(
            url,
            corpus_root=corpus_root,
            user_agent=args.user_agent,
            dry_run=False,
            robots=None,  # already checked above
            fidelity=args.fidelity,
        )
        if record_path is None:
            state.failed.append((url, "capture failed"))
            _save_sidecar(sidecar, state)
            continue
        state.visited.append(url)
        captured += 1
        if depth < state.depth_cap:
            _expand(state, record_path, current_depth=depth, corpus_root=corpus_root)
        _save_sidecar(sidecar, state)

    _report_final(state, captured=captured, sidecar=sidecar)
    return 0


def _reference_targets(corpus_root: Path, seed: str | None):
    """Resolve the records a `--references` sweep operates on: a single record when `seed`
    is given (a URL matched via `find_by_uri`, else a record id / path), or every record in
    the corpus when `seed` is None. Returns a list of `(path, post)`, or None on a bad seed."""
    if not seed:
        return list(records.load_all(corpus_root))
    rid = records.find_by_uri(seed, corpus_root=corpus_root)
    if rid is None:
        try:
            rid, path = paths.resolve_record(corpus_root, seed)
        except Exception:
            log.error("crawl --references: no record matches %r (URL, record id, or path)", seed)
            return None
        return [(path, records.load(path))]
    path = paths.record_path(corpus_root, rid)
    return [(path, records.load(path))]


def _run_references_mode(args: argparse.Namespace, corpus_root: Path) -> int:
    """`--references`: fetch overlay-declared dependent references (spec §7.2) at depth 1,
    the deferred counterpart to the inline `corpus capture --with-references` grab. Walks
    the target record(s), and for each HTML record whose host declares `capture.references`
    rules, fetches every declared-but-not-yet-captured target (content-hash deduped). The
    captured manuals become their own records; the citing record's tier-2 references advance
    to tier 3 on its next draft (draft resolves the tier by URI)."""
    from corpus import artifacts, mime, references

    pairs = _reference_targets(corpus_root, args.seed_url)
    if pairs is None:
        return 1
    opts = capture_lib.CaptureOptions(user_agent=args.user_agent, fidelity=args.fidelity)
    totals = {"records": 0, "selected": 0, "captured": 0, "existing": 0, "failed": 0}
    for path, post in pairs:
        if records.media_type_for(post) != "text/html":
            continue
        base = records.primary_origin_uri(post)
        if not base or not references.rules_for_url(corpus_root, base):
            continue
        rid = str(post.metadata.get("id") or path.stem)
        try:
            artifact = artifacts.ensure_local(corpus_root, rid, mime.extension_for("text/html"))
        except artifacts.ArtifactMissing as exc:
            log.warning("%s: %s", rid[:12], exc)
            continue
        html = artifact.read_text(encoding="utf-8", errors="replace")
        if not args.dry_run and args.delay:
            time.sleep(args.delay)
        res = references.fetch_references(
            corpus_root, post, html, force=True, opts=opts, dry_run=args.dry_run
        )
        if not res.selected:
            continue
        totals["records"] += 1
        totals["selected"] += len(res.selected)
        totals["captured"] += len(res.captured)
        totals["existing"] += len(res.existing)
        totals["failed"] += len(res.failed)
        for url, reason in res.failed:
            log.warning("reference capture failed: %s (%s)", url, reason)
        if args.dry_run:
            existing = set(res.existing)
            for url in res.selected:
                if url not in existing:
                    print(url)
    verb = "would fetch" if args.dry_run else "captured"
    log.info(
        "references: %d record(s) with rules; %d declared, %d %s, %d already present, %d failed",
        totals["records"], totals["selected"], totals["captured"], verb,
        totals["existing"], totals["failed"],
    )
    return 0


def _sidecar_path(capture_dir: Path, normalized_seed: str) -> Path:
    digest = blake3.blake3(normalized_seed.encode("utf-8")).hexdigest()[:16]
    return capture_dir / f"crawl-{digest}.json"


def _save_sidecar(sidecar: Path, state: CrawlState) -> None:
    sidecar.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


def _load_robots(host: str, *, user_agent: str) -> urllib.robotparser.RobotFileParser | None:
    """Fetch robots.txt for `host`. On any failure return None (permissive) —
    robots is policy, not a hard gate, and a missing/unreachable robots.txt
    traditionally means 'allowed'."""
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"https://{host}/robots.txt")
    try:
        rp.read()
    except Exception as exc:
        log.warning("robots.txt fetch failed for %s: %s (treating as permissive)", host, exc)
        return None
    return rp


def _capture_one(
    url: str,
    *,
    corpus_root: Path,
    user_agent: str,
    dry_run: bool,
    robots: urllib.robotparser.RobotFileParser | None,
    fidelity: str | None = None,
) -> Path | None:
    """Capture `url` in-process. Returns the resulting record path, or None on
    failure. In dry-run, returns the existing record path if the URL is already
    captured, else None (never launches a browser)."""
    if robots is not None and not robots.can_fetch(user_agent, url):
        log.info("robots-disallowed: %s", url)
        return None

    if dry_run:
        existing_id = records.find_by_uri(url, corpus_root=corpus_root)
        if existing_id is None:
            return None
        return paths.record_path(corpus_root, existing_id)

    log.info("capture %s", url)
    opts = capture_lib.CaptureOptions(user_agent=user_agent, fidelity=fidelity)
    try:
        return capture_lib.capture_and_ingest(url, corpus_root=corpus_root, opts=opts)
    except capture_lib.CaptureError as exc:
        log.error("capture failed for %s: %s", url, exc)
        return None


def _expand(
    state: CrawlState, record_path: Path, *, current_depth: int, corpus_root: Path
) -> None:
    """Read the record's HTML artifact, extract same-domain links, push unseen
    ones to the frontier at depth `current_depth + 1`. Non-HTML records are not
    expandable."""
    if current_depth + 1 > state.depth_cap:
        return
    post = records.load(record_path)
    media_type = records.media_type_for(post)
    if media_type != "text/html":
        log.debug("not expandable (%s): %s", media_type, record_path.name)
        return
    record_id = str(post.metadata.get("id") or "")
    if not record_id:
        return
    try:
        artifact = artifacts.ensure_local(corpus_root, record_id, mime.extension_for(media_type))
    except artifacts.ArtifactMissing as exc:
        log.warning("%s: %s", record_id[:12], exc)
        return

    base_url = records.primary_origin_uri(post)
    if not base_url:
        log.warning("no origin URI on record %s; skipping expansion", record_id[:12])
        return

    # Dedup the frontier by **identity key** (urls.identity_key via the host's opt-in
    # `url_equivalent` rules — spec §7.2), not the raw normalized string, so a paginated
    # record's `/page-N` + query-noise variants and any equivalent spelling of a visited /
    # frontier URL collapse to one key. The frontier still STORES the fetchable normalized URL
    # (it is fed back to capture); identity is the dedup key only — never the fetch target.
    # A record's own URIs are excluded so a crawl won't re-enqueue the pages page 1 already
    # absorbed. Absent any `url_equivalent`, the key is exactly `normalize` (today's behavior).
    recipe_by_host: dict[str, dict] = {}

    def _ident(u: str) -> str:
        host = urls.host_of(u)
        if host not in recipe_by_host:
            recipe_by_host[host] = recipes.capture_recipe_for_url(corpus_root, u) or {}
        r = recipe_by_host[host]
        return urls.identity_key(u, r.get("url_equivalent"), url_rewrite=r.get("url_rewrite"))

    own_keys = {_ident(u) for u in records.iter_origin_uris(post)}
    found = _extract_links(artifact, base_url)
    pushed = 0
    frontier_keys = {_ident(u) for u, _ in state.frontier}
    visited_keys = {_ident(u) for u in state.visited}
    for raw_link in found:
        try:
            absolute = urljoin(base_url, raw_link)
            normalized = urls.normalize(absolute)
        except ValueError:
            continue
        if not normalized.startswith(("http://", "https://")):
            continue
        key = _ident(normalized)
        if key in own_keys:
            continue
        if not urls.same_domain(
            normalized, state.seed_host, include_subdomains=state.include_subdomains
        ):
            continue
        if key in visited_keys or key in frontier_keys:
            continue
        if len(state.visited) + len(state.frontier) >= state.count_cap:
            break
        state.frontier.append((normalized, current_depth + 1))
        frontier_keys.add(key)
        pushed += 1
    log.info("expanded %s: %d link(s) added to frontier", record_id[:12], pushed)


def _extract_links(artifact: Path, base_url: str) -> list[str]:
    """Parse `<a href>` links from the HTML artifact. Keeps client-side routes
    (`#/…`, `#!/…`); drops bare anchors + js/mailto/tel via the shared
    `urls.is_crawlable_href` (same filter as `corpus links`)."""
    html = artifact.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        href = href.strip()
        if not urls.is_crawlable_href(href):
            continue
        out.append(href)
    return out


def _confirm(
    state: CrawlState, *, sidecar: Path, robots: urllib.robotparser.RobotFileParser | None
) -> str:
    """Print a frontier summary on stderr; prompt [y]es / [n]arrow / [a]bort."""
    w = sys.stderr.write
    w("\n=== Crawl plan ===\n")
    w(f"  seed:               {state.seed}\n")
    w(f"  normalized seed:    {state.normalized_seed}\n")
    w(f"  host:               {state.seed_host}")
    w(" (+ subdomains)\n" if state.include_subdomains else " (host-exact)\n")
    w(f"  depth cap:          {state.depth_cap}\n")
    w(f"  count cap:          {state.count_cap}\n")
    w(f"  visited so far:     {len(state.visited)}\n")
    w(f"  frontier:           {len(state.frontier)}\n")
    w(f"  sidecar:            {sidecar}\n")
    w(f"  robots.txt:         {'loaded' if robots is not None else 'permissive (unreachable)'}\n")

    by_depth: dict[int, list[str]] = {}
    for url, depth in state.frontier:
        by_depth.setdefault(depth, []).append(url)
    for depth in sorted(by_depth):
        urls_at = by_depth[depth]
        w(f"\n  depth {depth} ({len(urls_at)} URL{'s' if len(urls_at) != 1 else ''}):\n")
        for url in urls_at[:20]:
            w(f"    {url}\n")
        if len(urls_at) > 20:
            w(f"    ... ({len(urls_at) - 20} more)\n")

    w("\nProceed? [y]es / [n]arrow (abort and re-run with tighter caps) / [a]bort: ")
    sys.stderr.flush()
    try:
        answer = input().strip().lower()
    except EOFError:
        return "abort"
    if answer in ("y", "yes"):
        return "confirm"
    if answer in ("n", "narrow"):
        return "narrow"
    return "abort"


def _report_dry_run(state: CrawlState) -> None:
    w = sys.stderr.write
    w("\n=== Dry run ===\n")
    w(f"  seed:               {state.seed}\n")
    w(f"  visited (existing): {len(state.visited)}\n")
    w(f"  frontier:           {len(state.frontier)}\n")
    by_depth: dict[int, list[str]] = {}
    for url, depth in state.frontier:
        by_depth.setdefault(depth, []).append(url)
    for depth in sorted(by_depth):
        urls_at = by_depth[depth]
        w(f"\n  depth {depth} ({len(urls_at)}):\n")
        for url in urls_at:
            w(f"    {url}\n")


def _report_final(state: CrawlState, *, captured: int, sidecar: Path) -> None:
    w = sys.stderr.write
    w("\n=== Crawl complete ===\n")
    w(f"  captured this run:  {captured}\n")
    w(f"  total visited:      {len(state.visited)}\n")
    w(f"  remaining frontier: {len(state.frontier)}\n")
    w(f"  failed:             {len(state.failed)}\n")
    w(f"  skipped:            {len(state.skipped)}\n")
    w(f"  sidecar:            {sidecar}\n")
    if state.failed:
        w("\n  failures:\n")
        for url, reason in state.failed[:10]:
            w(f"    {url}  ({reason})\n")
        if len(state.failed) > 10:
            w(f"    ... ({len(state.failed) - 10} more)\n")


def configure(parser: argparse.ArgumentParser) -> None:
    p = parser
    p.add_argument("seed_url", nargs="?", help="seed URL to start crawling from (omit with --references to sweep the whole corpus)")
    p.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help=f"max BFS depth from seed (default: {DEFAULT_DEPTH})")
    p.add_argument("--count", type=int, default=DEFAULT_COUNT, help=f"max URLs to capture this run (default: {DEFAULT_COUNT})")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"inter-request sleep in seconds (default: {DEFAULT_DELAY})")
    p.add_argument("--include-subdomains", action="store_true", help="widen same-domain to all subdomains of the seed host")
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help=f"User-Agent for robots.txt + propagated to capture (default: {DEFAULT_USER_AGENT!r})")
    p.add_argument("--fidelity", choices=("exact", "balanced", "lean"), default=None, help="snapshot fidelity for every page (exact|balanced|lean); overrides recipe/config. Useful for a whole-site lean re-crawl without editing the overlay")
    p.add_argument("--yes", action="store_true", help="skip the confirmation gate")
    p.add_argument("--resume", action="store_true", help="resume from the sidecar JSON")
    p.add_argument("--dry-run", action="store_true", help="discovery only; never capture")
    p.add_argument("--references", action="store_true", help="don't BFS-crawl; instead fetch overlay-declared dependent references (capture.references, spec §7.2) at depth 1 — for the seed's record, or every record when no seed is given. --dry-run lists pending targets.")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging on stderr")
    add_corpus_root_arg(parser)
