"""Capture a URL into the corpus.

Three capture paths. Routing is **overlay-driven** — the origin overlay's
`capture.capturer:` field (resolved per host) names the capturer; the CLI
`--video` / `--no-video` flags are explicit overrides; absent both, the default
is the browser. There is no hardcoded host knowledge (no built-in video-host list).

    yt-dlp dispatch    → `capturer: video` (or `--video`). Downloads best-quality
                         video+audio via yt-dlp's Python API and writes a sibling
                         `.info.json` (metadata + top comments). yt-dlp options are
                         declared in the overlay's `capture.ytdlp:` block and merged
                         over library defaults. Requires the ``[media]`` extra.
    text/html (xhtml)  → Playwright renders the page; the SingleFile bundle — the
                         instance's registered `assets.singlefile` (spec/corpus.md
                         §12.3.6), never tooling-shipped — inlines CSS / images /
                         fonts as `data:` URIs for a self-contained snapshot. With
                         no asset registered (or its bytes not materialized here),
                         the rendered DOM (`page.content()`) is captured instead —
                         still valid HTML, just without inlined sub-resources — and
                         the degrade is disclosed loudly (a warning + a capture
                         issue), never silent. Requires the ``[capture]`` extra.
    anything else      → re-fetch the bytes via the browser's session (cookies
                         already set) and write the raw response.

For HTML snapshots two `<meta>` tags are injected into the snapshot `<head>` so a
drafter can recover capture provenance from the bytes alone::

    <meta name="corpus-capture-url" content="<final-url>">
    <meta name="corpus-fetched-at"  content="<ISO-8601 UTC timestamp>">
    <meta name="corpus-fidelity"    content="<exact|balanced|lean>">

The capture provenance is *also* written to a `<file>.capture.yaml` sidecar that
``corpus ingest`` reads to seed the record's first `<!--origin-->` block and to
replay any capture-stage issues as `<!--issue-->` blocks. A web capture's resolved
snapshot engine rides the same sidecar as `snapshot_engine:` (spec/corpus.md
§12.3.6), landing on that first origin block as an ordinary extended field.

This module is the importable library. `capture()` produces bytes under
`capture/` and returns a `CaptureResult`; `capture_and_ingest()` chains
capture → ingest in-process (the path `corpus crawl` drives). The thin
`_cli/capture.py` wrapper turns argv into a `CaptureOptions`.

Generalized from the reference `_cli/capture.py`: account/host/credential
specifics are gone, the SingleFile bundle is resolved (not hardcoded), the
capture-stage detector id is `corpus.capture@<version>` (a valid touch
identifier), and the issues it emits already conform to spec §4.3.3.1
(`severity: blocking|warning|info`, `detector: <touch>`).
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from .. import assets as corpus_assets
from .. import hashing, mime, paths, records, touches
from .. import urls as urlcanon

log = logging.getLogger("corpus.capture")


# ---------- configuration ---------- #

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_VIEWPORT = (1280, 900)
DEFAULT_TIMEOUT_S = 60

# Soft cap on `wait_for_load_state("networkidle")`. Tracker-heavy pages never
# reach networkidle within the navigation timeout because analytics keep the
# network "busy" indefinitely. Wait this long, then snapshot whatever's loaded
# (`domcontentloaded` has already fired, so the DOM is parsed).
NETWORKIDLE_BUDGET_MS = 10_000

# Default CDP autodetect endpoint. A Chrome launched with
# `--remote-debugging-port=9222` exposes /json/version; we probe it and, if
# reachable, connect to that browser (reusing its login/cookie state) instead
# of launching a fresh headless one.
CDP_AUTODETECT_URL = "http://localhost:9222"

# SingleFile options. Tuned for archival: scripts stripped, hidden DOM kept,
# styles minified, original resource URLs preserved alongside inlined data:
# URIs. Spellings verified against the upstream bundle.
SINGLEFILE_OPTIONS = {
    "removeHiddenElements": False,
    "removeUnusedStyles": False,
    "removeUnusedFonts": True,
    "removeFrames": False,
    "removeImports": False,
    "removeScripts": True,
    "blockScripts": True,
    "blockVideos": False,
    "compressHTML": True,
    "compressCSS": True,
    "groupDuplicateImages": True,
    "saveOriginalURLs": True,
    "loadDeferredImagesBeforeFrames": True,
    # We run our own Playwright-side scroll/hydrate before SingleFile; letting
    # SingleFile re-run its deferred-image pass has been observed to reset
    # already-hydrated images back to `data:,` placeholders on some sites.
    "loadDeferredImages": False,
    "insertSingleFileComment": False,  # we inject our own corpus-* meta tags
    "insertMetaCSP": False,
}

# Capture fidelity tiers, layered over SINGLEFILE_OPTIONS at snapshot time. A
# SingleFile snapshot inlines every asset for self-containment; on asset-heavy
# SPAs that boilerplate (web/icon fonts shipped in redundant eot+ttf+woff+woff2
# formats, app icon-sprite / illustration SVGs) dwarfs the content and is re-inlined
# fresh into *every* page, so content-addressed dedup can't share it (each page's
# whole-file hash differs). Fidelity trades snapshot completeness for size and is a
# per-host choice: some sites ARE their presentation (design / art / layout-sensitive
# pages) and want `exact`; others we keep only for the information and can run `lean`.
# None of these options touch the drafted record — the mechanical drafter reads DOM
# text/tables, not fonts/CSS — so records are identical across tiers; only the
# gitignored `artifacts/` shrink. Spellings verified against the registered bundle.
FIDELITY_PRESETS: dict[str, dict[str, bool]] = {
    "exact": {},  # byte-faithful; presentation IS content
    "balanced": {  # ~-76%, no rendering risk: drop redundant font / image / media alternates
        "removeAlternativeFonts": True,
        "removeAlternativeImages": True,
        "removeAlternativeMedias": True,
    },
    "lean": {  # ~-91%, information-faithful: also prune CSS rules with no matching element
        "removeAlternativeFonts": True,
        "removeAlternativeImages": True,
        "removeAlternativeMedias": True,
        "removeUnusedStyles": True,
    },
}
# Global default. `balanced` is a strict improvement for virtually every site with
# no rendering-fidelity risk; `exact` / `lean` are opt-in per host. Precedence:
# CLI --fidelity > overlay `capture.fidelity` > `origin/origin.yaml` > this default.
DEFAULT_FIDELITY = "balanced"


def _resolve_fidelity(cli: str | None, recipe: dict[str, Any]) -> str:
    """Resolve the capture fidelity tier by precedence: CLI override >
    per-host overlay / ``origin/origin.yaml`` ``capture.fidelity`` (already
    deep-merged into ``recipe`` by the schema loader, per-host winning) > the
    tooling default (``balanced``). Unknown spellings warn and fall through."""
    for source, val in (("--fidelity", cli), ("recipe", recipe.get("fidelity"))):
        if val:
            tier = str(val).strip().lower()
            if tier in FIDELITY_PRESETS:
                return tier
            log.warning(
                "ignoring unknown fidelity %r from %s (want exact|balanced|lean)", val, source
            )
    return DEFAULT_FIDELITY


def _singlefile_options(fidelity: str) -> dict[str, Any]:
    """``SINGLEFILE_OPTIONS`` with the fidelity preset merged over it."""
    return {**SINGLEFILE_OPTIONS, **FIDELITY_PRESETS.get(fidelity, {})}


class CaptureError(RuntimeError):
    """A capture could not be completed (extra missing, navigation failed, etc.)."""


@dataclass
class CaptureOptions:
    """Knobs for a single capture. All optional; defaults match the CLI."""

    timeout_s: int = DEFAULT_TIMEOUT_S
    viewport: tuple[int, int] = DEFAULT_VIEWPORT
    user_agent: str = DEFAULT_USER_AGENT
    cdp_url: str | None = None
    transport: str | None = None  # CLI override: headless | headed | cdp (else recipe/config)
    fidelity: str | None = None  # CLI override: exact | balanced | lean (else recipe/default)
    video: bool = False  # --video: force the video (yt-dlp) capturer
    no_video: bool = False  # --no-video: force the browser capturer
    no_comments: bool = False  # skip yt-dlp comment scrape
    force: bool = False  # re-capture even if the URL is already in the corpus


@dataclass
class CaptureResult:
    """Outcome of `capture()` — bytes staged under `capture/`, not yet ingested."""

    capture_path: Path
    used_video: bool
    issues: list[dict] = field(default_factory=list)
    # The resolved snapshot engine identity (spec/corpus.md §12.3.6), stamped onto the
    # capture sidecar as `snapshot_engine:` — `None` for a capturer that never touches
    # SingleFile (the video pathway, a non-HTML binary re-fetch).
    snapshot_engine: str | None = None


# ---------- pluggable capturer seam ---------- #


@runtime_checkable
class Capturer(Protocol):
    """A capture handler for a single URL.

    Packaged defaults are `browser` (Playwright) and `video` (yt-dlp), each self-registering
    via `@register("<name>")` at import time (routing lives in `get_capturer`). `shapers/` is
    the sole corpus-local code tier (spec §12.4.3) — a corpus routes a host to one of these
    two through the origin overlay's `capture.capturer:` field rather than registering a
    third. `recipe` is the resolved per-origin capture recipe (a later phase) or None.
    """

    def __call__(
        self,
        url: str,
        *,
        corpus_root: Path,
        capture_dir: Path,
        opts: CaptureOptions,
        recipe: dict[str, Any] | None,
    ) -> CaptureResult: ...


CapturerFn = Callable[..., CaptureResult]

# name → capturer. Populated at import time by the `@register` decorators below.
REGISTRY: dict[str, CapturerFn] = {}


def register(name: str) -> Callable[[CapturerFn], CapturerFn]:
    """Register a capturer under `name` (mirrors `draft.register` / `transforms.register`)."""

    def decorator(fn: CapturerFn) -> CapturerFn:
        if name in REGISTRY:
            raise ValueError(f"capturer already registered: {name!r}")
        REGISTRY[name] = fn
        return fn

    return decorator


def get_capturer(
    corpus_root: Path, url: str, *, opts: CaptureOptions
) -> tuple[CapturerFn, dict[str, Any] | None]:
    """Resolve `(capturer, recipe)` for `url`.

    Routing precedence — no hardcoded host knowledge:

      1. CLI override: `--video` → `video`, `--no-video` → `browser`.
      2. The origin overlay's `capture.capturer:` field (the recipe; resolved
         per host via `capture_recipe_for_url`).
      3. Default: `browser`.

    The chosen name resolves against `REGISTRY` (the packaged `browser`/`video` pair — no
    corpus-local capturer tier). The resolved recipe rides along so the capturer can apply
    its declared config (transport / interactions / ytdlp / …).
    """
    from .recipes import capture_recipe_for_url

    recipe = capture_recipe_for_url(corpus_root, url)

    if opts.video and opts.no_video:
        raise CaptureError("--video and --no-video are mutually exclusive")
    if opts.video:
        name = "video"
    elif opts.no_video:
        name = "browser"
    elif recipe and recipe.get("capturer"):
        name = str(recipe["capturer"])
    else:
        name = "browser"

    fn = REGISTRY.get(name)
    if fn is None:
        raise CaptureError(
            f"unknown capturer {name!r} (registered: {sorted(REGISTRY)})"
        )
    return fn, recipe


# ---------- public API ---------- #


def capture(url: str, *, corpus_root: Path, opts: CaptureOptions | None = None) -> CaptureResult:
    """Capture `url`'s bytes into `corpus_root/capture/`. Does not ingest.

    Returns a `CaptureResult`. Raises `CaptureError` when the required extra
    (`[capture]` for Playwright, `[media]` for yt-dlp) is not installed or the
    fetch fails outright.
    """
    opts = opts or CaptureOptions()
    canonical = _canonicalize(url)
    capture_dir = corpus_root / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)
    log.info("capturing %s", canonical)
    capturer, recipe = get_capturer(corpus_root, canonical, opts=opts)
    return capturer(
        canonical, corpus_root=corpus_root, capture_dir=capture_dir, opts=opts, recipe=recipe
    )


def capture_and_ingest(
    url: str, *, corpus_root: Path, opts: CaptureOptions | None = None
) -> Path | None:
    """Capture `url`, then ingest the bytes → a record stub. Returns the record
    path (or None if ingest failed).

    Short-circuit (two-stage, unless `opts.force`):

      1. Cheap string identity — a URL already present in some record's origin URIs
         (by identity key: `normalize` + the host's `url_equivalent`) returns that
         record without launching a browser, so re-running a crawl doesn't re-fetch.
      2. Redirect-aware identity — when (1) misses AND `url` looks like an opaque
         short link (`redirects.is_probably_short_link`), follow its HTTP redirects to
         the final URL (a body-less HEAD/GET — the artifact is NOT downloaded) and
         re-check identity. This catches a *fresh* short link that points at an
         already-captured canonical (two `vt.tiktok.com/XXXX` links → one video)
         BEFORE the expensive (esp. video) download — not only after the byte-level
         re-encounter on ingest. Gated by the short-link heuristic so a normal
         canonical URL never pays the network round-trip.

    Either short-circuit folds the requested URL into the matched record's origin URI
    list as an alias (the spec §7.2 "shortlinks/redirects collapse to one origin"
    behavior), so the new spelling is recorded without re-downloading.
    """
    opts = opts or CaptureOptions()
    canonical = _canonicalize(url)

    if not opts.force:
        existing = records.find_by_uri(canonical, corpus_root=corpus_root)
        if existing:
            log.info("already captured: %s -> %s", canonical, existing)
            return paths.record_path(corpus_root, existing)
        if hit := _redirect_dedup(canonical, corpus_root=corpus_root):
            return hit

    # Paginated work (thread / multi-page article / gallery): walk the pages and ingest ONE
    # merged artifact. Only for the browser capturer (HTML) and only when the overlay opts in
    # via `capture.pagination`. Every other host / capturer takes the single-page path below.
    from . import pagination
    from .recipes import capture_recipe_for_url

    recipe = capture_recipe_for_url(corpus_root, canonical)
    pag = pagination.normalize_config((recipe or {}).get("pagination")) if recipe else None
    if pag is not None and not opts.video and (recipe.get("capturer") or "browser") == "browser":
        return _reconcile_pagination(
            canonical, corpus_root=corpus_root, opts=opts, recipe=recipe, cfg=pag
        )

    result = capture(canonical, corpus_root=corpus_root, opts=opts)
    return _ingest_capture(result, original_url=canonical, corpus_root=corpus_root)


# ---------- from-save (replay a manual SingleFile save) ---------- #


@dataclass
class FromSaveProvenance:
    """The URL + moment a manual SingleFile save records — its honest provenance."""

    url: str
    saved_at: str
    source: str  # "banner" | "sidecar"


def resolve_from_save_provenance(src: Path) -> FromSaveProvenance:
    """Resolve `(url, saved_at)` for a manual save. The SingleFile banner (§12.3.4) is
    the primary source — the URL the human was on and the moment they saved it; absent a
    banner, a `<file>.capture.yaml` sidecar's `source_url` / `fetched_at`. Raises
    `CaptureError` when neither yields a URL: from-save must know WHAT was saved (to look
    up the host recipe) and WHEN (to snapshot-stamp the origin)."""
    from .. import singlefile

    if banner := singlefile.banner_origin(src):
        url, saved_at = banner
        return FromSaveProvenance(url=url, saved_at=saved_at, source="banner")

    sidecar_path = src.with_suffix(src.suffix + ".capture.yaml")
    if sidecar_path.is_file():
        import yaml

        try:
            data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        url = str((data or {}).get("source_url") or "").strip()
        if url:
            raw_at = data.get("fetched_at")
            # PyYAML coerces an unquoted ISO timestamp to a datetime; keep the `T`-form.
            saved_at = (
                raw_at.isoformat()
                if hasattr(raw_at, "isoformat")
                else str(raw_at or "").strip()
            ) or touches.now_iso()
            return FromSaveProvenance(url=url, saved_at=saved_at, source="sidecar")

    raise CaptureError(
        f"from-save: {src.name} carries no SingleFile banner and no "
        f"'{src.name}.capture.yaml' sidecar with a source_url — cannot determine the "
        f"saved page's URL. A from-save capture needs the origin URL; a SingleFile save "
        f"supplies it automatically in its banner comment."
    )


def capture_from_save(
    path: Path, *, corpus_root: Path, opts: CaptureOptions | None = None
) -> CaptureResult:
    """Stage a from-save capture (no ingest). Replays the saved DOM through the browser
    (see `_capture_from_save`) and returns a `CaptureResult` under `capture/`."""
    opts = opts or CaptureOptions()
    src = Path(path).resolve()
    prov = resolve_from_save_provenance(src)
    canonical = _canonicalize(prov.url)
    capture_dir = corpus_root / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)
    from .recipes import capture_recipe_for_url

    recipe = capture_recipe_for_url(corpus_root, canonical)
    cap_path, issues, snapshot_engine = _capture_from_save(
        src,
        url=canonical,
        saved_at=prov.saved_at,
        capture_dir=capture_dir,
        opts=opts,
        recipe=recipe,
        corpus_root=corpus_root,
    )
    return CaptureResult(
        capture_path=cap_path, used_video=False, issues=issues, snapshot_engine=snapshot_engine
    )


def capture_from_save_and_ingest(
    path: Path, *, corpus_root: Path, opts: CaptureOptions | None = None
) -> Path | None:
    """From-save capture → ingest. Replay a manual SingleFile save through the browser to
    run the host overlay's `capture.interactions` against the saved DOM, re-snapshot, and
    ingest — so the record's first origin is `uri:` = the banner URL, `snapshot:` = the
    saved date (the fetch happened when the human saved it, not now).

    Mirrors `capture_and_ingest`'s already-captured short-circuit (`--force` skips it).
    The source file is **retained** — a manual save can be irreplaceable, so from-save
    never unlinks it (only the re-snapshot staging file is consumed by ingest)."""
    opts = opts or CaptureOptions()
    src = Path(path).resolve()
    prov = resolve_from_save_provenance(src)
    canonical = _canonicalize(prov.url)

    if not opts.force:
        existing = records.find_by_uri(canonical, corpus_root=corpus_root)
        if existing:
            log.info("already captured: %s -> %s", canonical, existing)
            return paths.record_path(corpus_root, existing)

    capture_dir = corpus_root / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)
    from .recipes import capture_recipe_for_url

    recipe = capture_recipe_for_url(corpus_root, canonical)
    log.info(
        "from-save: %s -> %s (saved %s, provenance=%s)",
        src.name,
        canonical,
        prov.saved_at,
        prov.source,
    )
    cap_path, issues, snapshot_engine = _capture_from_save(
        src,
        url=canonical,
        saved_at=prov.saved_at,
        capture_dir=capture_dir,
        opts=opts,
        recipe=recipe,
        corpus_root=corpus_root,
    )
    result = CaptureResult(
        capture_path=cap_path, used_video=False, issues=issues, snapshot_engine=snapshot_engine
    )
    return _ingest_capture(
        result, original_url=canonical, corpus_root=corpus_root, fetched_at=prov.saved_at
    )


def _capture_from_save(
    src: Path,
    *,
    url: str,
    saved_at: str,
    capture_dir: Path,
    opts: CaptureOptions,
    recipe: dict[str, Any] | None,
    corpus_root: Path,
) -> tuple[Path, list[dict], str]:
    """Replay a manual SingleFile save through a headless browser and re-snapshot it.

    The saved bytes are self-contained (SingleFile inlined every asset as `data:` URIs),
    so the save IS the honest state — nothing may be fetched live. We load it via
    `file://` with CSP bypassed (a save can carry a CSP `<meta>`) and **every http/https
    route aborted**, run the host overlay's `capture.interactions` (DEFAULT_STEPS when the
    recipe declares none — the same pass live capture runs; steps are best-effort so a
    click/lazy-load step degrades to a no-op on a dead-script DOM), then re-snapshot with
    the same SingleFile fidelity machinery. The corpus-* metas record the BANNER url and
    saved date, never the `file://` path or the re-snapshot moment.

    Returns `(capture_path, issues, snapshot_engine)`. No capture-stage detectors run —
    there was no live navigation to drift, and a save's inlined images are neither
    re-fetched nor scored — except the snapshot-engine degrade check (spec §12.3.6),
    which applies here exactly as it does to a live browser capture.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise CaptureError(
            "from-save capture requires the `[capture]` extra. Install with: "
            "uv pip install 'athenaeum[capture]' && playwright install chromium"
        ) from e

    from . import interactions

    timeout_ms = opts.timeout_s * 1000
    recipe = recipe or {}
    fidelity = _resolve_fidelity(opts.fidelity, recipe)
    interaction_steps = recipe.get("interactions")
    viewport = _recipe_viewport(recipe) or opts.viewport
    user_agent = str(recipe.get("user_agent") or "") or opts.user_agent
    resolved_bundle = _resolve_singlefile_bundle(corpus_root)
    bundle = resolved_bundle.path if resolved_bundle else None
    snapshot_engine = resolved_bundle.engine if resolved_bundle else SNAPSHOT_ENGINE_DEGRADED
    issues: list[dict] = []
    if issue := _snapshot_engine_issue(snapshot_engine):
        issues.append(issue)
    base = _sanitize_filename(url)
    file_uri = src.as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = None
        try:
            ctx = browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                user_agent=user_agent,
                bypass_csp=True,
            )
            # Abort every live http/https fetch — a dead-script DOM must never reach the
            # network; file:/data:/about: (the save itself + its inlined assets) pass.
            ctx.route(
                "**/*",
                lambda route: route.abort()
                if route.request.url.startswith(("http://", "https://"))
                else route.continue_(),
            )
            page = ctx.new_page()
            log.info("from-save: loading %s (headless, network aborted)", src.name)
            page.goto(file_uri, wait_until="domcontentloaded", timeout=timeout_ms)
            interactions.run(page, interaction_steps)
            snapshot = _snapshot_html(
                page=page,
                fetched_at=saved_at,
                bundle=bundle,
                fidelity=fidelity,
                capture_url=url,
            )
            capture_path = capture_dir / f"{base}.html"
            capture_path.write_text(snapshot, encoding="utf-8")
            log.info(
                "from-save: re-snapshot %d bytes (fidelity=%s) -> %s",
                len(snapshot.encode()),
                fidelity,
                capture_path.name,
            )
            return capture_path, issues, snapshot_engine
        finally:
            if page is not None:
                with contextlib.suppress(Exception):
                    page.close()
            browser.close()


def _redirect_dedup(canonical: str, *, corpus_root: Path) -> Path | None:
    """Second-stage capture dedup: follow `canonical`'s redirects (only when it looks like
    an opaque short link) and re-check `find_by_uri` against the resolved final URL — so a
    fresh short link pointing at an already-captured canonical is detected BEFORE the
    download. Returns the matched record path (with the short link folded in as an origin
    alias), or None to proceed with a normal capture.

    Best-effort + parse-tolerant: any failure resolving / recording leaves None so capture
    continues — the byte-level re-encounter on ingest remains the backstop."""
    from .recipes import resolve_identity_for_url

    try:
        final_url, key = resolve_identity_for_url(corpus_root, canonical)
    except Exception as exc:  # never let a probe break capture
        log.debug("redirect dedup probe failed for %s: %s", canonical, exc)
        return None
    if final_url == canonical:
        return None  # not a short link, or unresolved — nothing new to match on
    existing = records.find_by_uri(key, corpus_root=corpus_root, _prekeyed=True)
    if not existing:
        return None
    log.info("already captured (via redirect): %s -> %s -> %s", canonical, final_url, existing)
    record_path = paths.record_path(corpus_root, existing)
    # Fold the short link in as an origin alias so the new spelling is recorded without a
    # re-download (spec §7.2). Identity-key dedup keeps it minimal if already present.
    try:
        post = records.load(record_path)
        if records.add_origin_uri_alias(post, canonical, corpus_root=corpus_root):
            records.dump(post, record_path)
    except Exception as exc:
        log.debug("could not record short-link alias on %s: %s", existing, exc)
    return record_path


def _reconcile_pagination(
    canonical: str,
    *,
    corpus_root: Path,
    opts: CaptureOptions,
    recipe: dict[str, Any],
    cfg: Any,
) -> Path | None:
    """Walk a paginated work's pages, merge them into one HTML, ingest exactly ONE artifact.

    Per the pagination-reconcile invariant (`capture.pagination`): each page is
    captured via the staging-only `capture()`
    path, read into memory, and its staging file unlinked — per-page bytes are **never**
    content-addressed (the INVARIANT). Only the merged document is ingested. The clean seed
    (`canonical`) is the recorded origin URI; every constituent page URL — both the bare site
    form and the pinned `url_rewrite` nav form — is folded in as an origin alias, so a later
    crawl that discovers `/page-N` short-circuits to this record instead of re-capturing it.
    """
    from . import pagination
    from .recipes import canonical_content_selector_for_url

    capture_dir = corpus_root / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)

    # Identity-equivalence config (spec §7.2) — dedup the walk by identity key, not raw URL,
    # so a host's view/affiliate query variants of the same page don't get re-walked.
    eq = recipe.get("url_equivalent")
    rw = recipe.get("url_rewrite")

    def _ident(u: str) -> str:
        return urlcanon.identity_key(u, eq, url_rewrite=rw)

    htmls: list[str] = []
    page_forms: list[tuple[str, str]] = []  # (bare site form, pinned nav form) per page
    seen_keys = {_ident(canonical)}
    cap_hit = False

    url = canonical
    while True:
        result = capture(url, corpus_root=corpus_root, opts=opts)
        html = result.capture_path.read_text(encoding="utf-8")
        with contextlib.suppress(OSError):
            result.capture_path.unlink()  # INVARIANT: per-page bytes are never content-addressed
        htmls.append(html)
        page_forms.append((url, _apply_url_rewrite(url, recipe)))

        nxt = pagination.extract_next_url(html, base_url=url, cfg=cfg)
        if len(htmls) >= cfg.max_pages:
            cap_hit = nxt is not None
            if cap_hit:
                log.warning("pagination: max_pages=%d hit with more pages remaining", cfg.max_pages)
            break
        # `nxt` stays the fetchable form (we capture it); identity is only the dedup key.
        if not nxt or _ident(nxt) in seen_keys:
            break
        seen_keys.add(_ident(nxt))
        url = nxt

    merged_path = capture_dir / f"{_sanitize_filename(canonical)}.html"

    def _ingest(text: str) -> Path | None:
        merged_path.write_text(text, encoding="utf-8")
        return _ingest_capture(
            CaptureResult(capture_path=merged_path, used_video=False, issues=[]),
            original_url=canonical,
            corpus_root=corpus_root,
        )

    # Single page (no next link): behave exactly like a non-paginated capture — write the
    # original snapshot bytes verbatim (no BeautifulSoup round-trip), so the record id is
    # byte-identical and no pagination provenance is attached.
    if len(htmls) == 1:
        return _ingest(htmls[0])

    try:
        merged_html, posts = pagination.merge_pages(
            htmls,
            content_selector=cfg.content_selector,
            canonical_selector=canonical_content_selector_for_url(corpus_root, canonical),
        )
    except pagination.RegionUnresolved as exc:
        # Don't silently ship a lossy merge: ingest page 1 only and flag it loudly.
        log.warning("pagination: %s — ingesting page 1 only", exc)
        record_path = _ingest(htmls[0])
        if record_path is not None:
            post = records.load(record_path)
            records.append_issue_block(
                post,
                id="pagination-incomplete",
                subtype="region-unresolved",
                severity="warning",
                detector=touches.script_identifier("capture"),
                fields={"pages_captured": len(htmls)},
            )
            records.dump(post, record_path)
        return record_path

    record_path = _ingest(merged_html)
    if record_path is None:
        return None

    expected = pagination.expected_count(htmls[0], cfg=cfg)
    incomplete = (expected is not None and posts < expected) or cap_hit

    post = records.load(record_path)
    for bare, pinned in page_forms:
        records.add_origin_uri_alias(post, bare, corpus_root=corpus_root)
        records.add_origin_uri_alias(post, pinned, corpus_root=corpus_root)
    records.merge_origin_fields(
        post,
        {
            "pagination": {
                "pages": len(htmls),
                "form": _apply_url_rewrite(canonical, recipe),
                "posts": posts,
            }
        },
    )
    if incomplete:
        records.append_issue_block(
            post,
            id="pagination-incomplete",
            severity="warning",
            detector=touches.script_identifier("capture"),
            fields={
                "pages": len(htmls),
                "posts": posts,
                "expected": expected,
                "max_pages_hit": cap_hit,
            },
        )
    records.dump(post, record_path)
    log.info(
        "pagination: merged %d page(s) -> %d item(s)%s",
        len(htmls),
        posts,
        " [INCOMPLETE]" if incomplete else "",
    )
    return record_path


# ---------- video (yt-dlp) ---------- #


def _capture_video_with_cookies(
    url: str, *, capture_dir: Path, opts: CaptureOptions, recipe: dict[str, Any] | None
) -> Path:
    """yt-dlp dispatch with optional CDP-derived cookies; cleans the cookie file."""
    recipe = recipe or {}
    cookiefile: Path | None = None
    cdp_url = _resolve_cdp_endpoint(opts.cdp_url)
    if cdp_url:
        if recipe.get("cdp_prime"):
            _prime_cdp_session(cdp_url, url=url, timeout_ms=opts.timeout_s * 1000)
        cookiefile = _extract_cdp_cookies_for_ytdlp(cdp_url, capture_dir, url=url, recipe=recipe)
    try:
        return _capture_video(
            url=url,
            capture_dir=capture_dir,
            include_comments=not opts.no_comments,
            cookiefile=cookiefile,
            ytdlp_opts=recipe.get("ytdlp"),
        )
    finally:
        if cookiefile is not None:
            with contextlib.suppress(OSError):
                cookiefile.unlink()


@register("video")
def _capture_with_video(
    url: str,
    *,
    corpus_root: Path,
    capture_dir: Path,
    opts: CaptureOptions,
    recipe: dict[str, Any] | None,
) -> CaptureResult:
    """Packaged yt-dlp capturer. yt-dlp options come from the overlay's
    `capture.ytdlp:` block (full passthrough over library defaults)."""
    path = _capture_video_with_cookies(url, capture_dir=capture_dir, opts=opts, recipe=recipe)
    return CaptureResult(capture_path=path, used_video=True, issues=[])


# yt-dlp options the library owns — an overlay's `ytdlp:` block cannot clobber them
# (output path, logger, and the resolved cookie file are forced after the merge).
_YTDLP_FORCED_KEYS = ("outtmpl", "logger", "cookiefile")


def _build_ydl_opts(
    *,
    outtmpl: str,
    include_comments: bool,
    cookiefile: Path | None,
    ytdlp_opts: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge library yt-dlp DEFAULTS ← overlay `capture.ytdlp:` passthrough ← FORCED
    library-owned keys (`_YTDLP_FORCED_KEYS`). `include_comments=False` (CLI
    `--no-comments`) force-disables `getcomments` (CLI > overlay > default)."""
    # Library defaults — every one overridable by the overlay's `ytdlp:` block.
    defaults: dict[str, Any] = {
        "format": "bv*+ba/b",
        "writeinfojson": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "noplaylist": True,
        "getcomments": True,
        "quiet": False,
        "no_warnings": False,
        # `--embed-chapters` equivalent (spec §12.20 item 2(a)): new video captures carry
        # chapter marks in-band, in the artifact's own bytes, going forward — the
        # `FFmpegMetadataPP` postprocessor is what the yt-dlp CLI flag itself builds
        # (`add_chapters=True`), with `add_metadata`/`add_infojson` left off so this adds
        # nothing beyond chapters. Requires ffmpeg on PATH (already a system dependency here).
        # An overlay declaring its own `postprocessors:` replaces this list entirely, same as
        # every other default key — that's an explicit host-level opt-out, not a bug.
        "postprocessors": [
            {"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": False,
             "add_infojson": False},
        ],
        # YouTube needs an external JS runtime to decode signature/n challenges.
        # Register node (any Node 18+ on PATH) + fetch the per-player EJS solver.
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
    }
    opts: dict[str, Any] = {**defaults, **(ytdlp_opts or {})}
    if not include_comments:
        opts["getcomments"] = False
    # `impersonate` is a CLI-style string in the overlay (e.g. `chrome` or
    # `chrome-110:windows-10`); the Python API wants an ImpersonateTarget, which
    # the CLI builds via from_str. Normalise here so the overlay stays string-based.
    impersonate = opts.get("impersonate")
    if isinstance(impersonate, str):
        from yt_dlp.networking.impersonate import (  # type: ignore[import-untyped]
            ImpersonateTarget,
        )

        opts["impersonate"] = ImpersonateTarget.from_str(impersonate)
    # FORCED: the overlay must not break output paths, logging, or auth.
    opts["outtmpl"] = outtmpl
    opts["logger"] = _YtDlpLogger()
    if cookiefile is not None:
        opts["cookiefile"] = str(cookiefile)
    return opts


def _capture_video(
    *,
    url: str,
    capture_dir: Path,
    include_comments: bool,
    cookiefile: Path | None,
    ytdlp_opts: dict[str, Any] | None = None,
) -> Path:
    """Drive yt-dlp via its Python API; write video + `.info.json` sidecar.

    Library DEFAULTS are merged under the overlay's `capture.ytdlp:` block
    (``ytdlp_opts``, full passthrough into ``YoutubeDL``); then library-owned keys
    (`_YTDLP_FORCED_KEYS`) are forced so the overlay can't break output paths,
    logging, or auth. The CLI ``--no-comments`` flag force-disables ``getcomments``
    (CLI > overlay > default).

    Subtitles are skipped (transcription is the canonical transcript source). When
    `cookiefile` is set, yt-dlp authenticates with it (typically extracted from a
    running CDP browser's login state).
    """
    try:
        from yt_dlp import YoutubeDL  # type: ignore[import-untyped]
    except ImportError as e:
        raise CaptureError(
            "video capture requires the `[media]` extra. Install with: "
            "uv pip install 'athenaeum[media]'"
        ) from e

    base = _sanitize_filename(url)
    outtmpl = str(capture_dir / f"{base}.%(ext)s")
    ydl_opts = _build_ydl_opts(
        outtmpl=outtmpl,
        include_comments=include_comments,
        cookiefile=cookiefile,
        ytdlp_opts=ytdlp_opts,
    )
    if cookiefile is not None:
        log.info("yt-dlp cookies: %s", cookiefile)
    log.info(
        "yt-dlp: format=%s comments=%s impersonate=%s",
        ydl_opts.get("format"),
        ydl_opts.get("getcomments"),
        ydl_opts.get("impersonate"),
    )
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_path = Path(ydl.prepare_filename(info))

    if not video_path.is_file():
        # prepare_filename returns the pre-merge name; the merged file lands at
        # .mp4 (or whatever the merger produced). Find the real artifact.
        candidates = sorted(
            p for p in capture_dir.glob(f"{base}.*") if p.suffix not in {".json", ".part", ".vtt"}
        )
        if not candidates:
            raise CaptureError(f"yt-dlp produced no video file for base {base!r}")
        video_path = candidates[0]

    log.info("yt-dlp wrote %s", video_path)
    return video_path


def _cookie_scope_urls(url: str, recipe: dict[str, Any]) -> list[str]:
    """Cookie URL scopes to pull from the CDP session for a video capture.

    Host-generic (no hardcoded list): the default scope is the capture URL's own
    origin (e.g. `https://www.tiktok.com/`). The overlay's `cookies_from_host`
    disables it (`false`) or extends it (a list of extra origin URLs — e.g. a
    separate login/CDN host)."""
    setting = recipe.get("cookies_from_host", True)
    if setting is False:
        return []
    scopes: list[str] = []
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        scopes.append(f"{parsed.scheme}://{parsed.netloc}/")
    if isinstance(setting, (list, tuple)):
        scopes += [str(s).strip() for s in setting if str(s).strip()]
    return scopes


def _prime_cdp_session(cdp_url: str, *, url: str, timeout_ms: int) -> None:
    """Warm the CDP browser's cookie jar by navigating it to `url` before we read
    cookies for yt-dlp.

    yt-dlp never tunnels through CDP — it borrows the jar's cookies and makes its own
    (impersonated) requests. A logged-in, trusted browser session passes the
    interstitials / anti-bot challenges that yt-dlp's request can trip; the
    challenge-passed cookies it leaves behind (e.g. TikTok's `msToken` / `ttwid`) then
    let yt-dlp's own fetch be served the real page instead of a block page. Opt-in via
    the overlay's `capture.cdp_prime: true`. Best-effort: any failure is logged and
    ignored — we still read whatever cookies already exist.
    """
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        return
    log.info("priming CDP session: navigating browser to %s", url)
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url)
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    with contextlib.suppress(PlaywrightTimeout):
                        page.wait_for_load_state("networkidle", timeout=NETWORKIDLE_BUDGET_MS)
                finally:
                    page.close()
            finally:
                browser.close()
    except Exception as exc:
        log.warning("CDP session priming failed: %s — continuing with existing cookies", exc)


def _extract_cdp_cookies_for_ytdlp(
    cdp_url: str, scratch_dir: Path, *, url: str, recipe: dict[str, Any]
) -> Path | None:
    """Pull the capture host's cookies from the CDP browser into a Netscape cookies
    file for yt-dlp. Scope = the capture URL's own origin (+ overlay extras; see
    `_cookie_scope_urls`). Returns the file path, or None on any failure / no
    cookies / disabled — yt-dlp then runs cookieless.
    """
    scope_urls = _cookie_scope_urls(url, recipe)
    if not scope_urls:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    log.info("extracting cookies for %s from CDP browser at %s", scope_urls, cdp_url)
    cookies_path = scratch_dir / ".cdp-cookies.txt"
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url)
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                raw = ctx.cookies(scope_urls)
            finally:
                browser.close()
    except Exception as exc:
        log.warning("CDP cookie extraction failed: %s — yt-dlp will run cookieless", exc)
        return None

    if not raw:
        log.info("no cookies for %s in the CDP session — yt-dlp will run cookieless", scope_urls)
        return None

    lines = [
        "# Netscape HTTP Cookie File",
        "# Exported by corpus.capture from a CDP browser session",
    ]
    for c in raw:
        domain = c.get("domain", "")
        if not domain:
            continue
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path") or "/"
        secure = "TRUE" if c.get("secure") else "FALSE"
        expires = c.get("expires")
        expires_int = int(expires) if isinstance(expires, (int, float)) and expires > 0 else 0
        name = c.get("name") or ""
        value = c.get("value") or ""
        if not name:
            continue
        domain_field = f"#HttpOnly_{domain}" if c.get("httpOnly") else domain
        lines.append(
            f"{domain_field}\t{include_subdomains}\t{path}\t{secure}\t{expires_int}\t{name}\t{value}"
        )

    cookies_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("wrote %d cookies to %s", len(raw), cookies_path)
    return cookies_path


class _YtDlpLogger:
    """Route yt-dlp's chatty output to our logger."""

    def debug(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def info(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        log.warning("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.error("yt-dlp: %s", msg)


# ---------- HTML / binary (Playwright) ---------- #


def _capture_via_playwright(
    *,
    url: str,
    capture_dir: Path,
    opts: CaptureOptions,
    cdp_url: str | None,
    recipe: dict[str, Any] | None = None,
    corpus_root: Path,
) -> tuple[Path, list[dict], str | None]:
    """Drive Playwright; branch on response content-type.

    HTML → a snapshot (the registered SingleFile asset if resolved, else the
    rendered DOM, disclosed as a degrade — spec §12.3.6) with corpus-* meta
    injection and capture-stage detectors. Anything else → raw bytes re-fetched
    via the browser session, written with a MIME-derived extension. Returns
    `(capture_path, issues, snapshot_engine)` — `snapshot_engine` is `None` for
    the binary branch, which never touches SingleFile.

    A `recipe` (resolved per-origin) may override the transport (`headless` |
    `headed` | `cdp`), the viewport / user-agent, and the pre-snapshot
    `interactions:` pass. Absent a recipe the historical defaults apply (headless
    or autodetected CDP; `interactions.DEFAULT_STEPS`).
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise CaptureError(
            "HTML/binary capture requires the `[capture]` extra. Install with: "
            "uv pip install 'athenaeum[capture]' && playwright install chromium"
        ) from e

    from . import interactions

    timeout_ms = opts.timeout_s * 1000
    fetched_at = touches.now_iso()
    base = _sanitize_filename(url)
    resolved_bundle = _resolve_singlefile_bundle(corpus_root)
    bundle = resolved_bundle.path if resolved_bundle else None
    snapshot_engine = resolved_bundle.engine if resolved_bundle else SNAPSHOT_ENGINE_DEGRADED

    recipe = recipe or {}
    transport = (str(recipe.get("transport") or "").strip().lower()) or None
    if (recipe.get("auth") or {}).get("cdp"):
        transport = "cdp"
    viewport = _recipe_viewport(recipe) or opts.viewport
    user_agent = str(recipe.get("user_agent") or "") or opts.user_agent
    fidelity = _resolve_fidelity(opts.fidelity, recipe)
    interaction_steps = recipe.get("interactions")
    # Per-host nav-URL rewrite: some hosts link to a route form that cold-loads a stub
    # while an equivalent form cold-loads the full content (ALLDATA's #/vehicle/.../
    # nonstandard/ vs #/article/.../nonstandard/). Rewrite only the navigation target; the
    # original URL stays the recorded origin and the rewritten form lands as `final_url`.
    nav_url = _apply_url_rewrite(url, recipe)

    with sync_playwright() as p:
        # `transport` (recipe) wins; absent a recipe, preserve the historical
        # behaviour of using an autodetected CDP endpoint when one is reachable.
        using_cdp = transport == "cdp" or (transport is None and bool(cdp_url))
        if using_cdp:
            if not cdp_url:
                raise CaptureError(
                    "capture recipe requested `transport: cdp` but no CDP endpoint is "
                    "reachable — start Chrome with --remote-debugging-port=9222, or set "
                    "--cdp-url / CAPTURE_CDP_URL"
                )
            log.info("connecting to CDP browser at %s", cdp_url)
            browser = p.chromium.connect_over_cdp(cdp_url)
        else:
            headed = transport == "headed"
            browser = p.chromium.launch(headless=not headed)
            if headed:
                log.info("launched headed browser (recipe transport: headed)")
        page = None
        try:
            if using_cdp:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            else:
                ctx = browser.new_context(
                    viewport={"width": viewport[0], "height": viewport[1]},
                    user_agent=user_agent,
                    accept_downloads=True,
                )
            page = ctx.new_page()

            # Relax CSP for the snapshot, BEFORE goto. CSP-strict sites (Instagram / all
            # Meta properties, and many modern sites use nonce-based `script-src` with no
            # `unsafe-inline`) block the SingleFile bundle that `_snapshot_html` injects via
            # `add_script_tag` — a real, CSP-subject inline <script>. `Page.setBypassCSP` is
            # what Playwright's `bypass_csp` context option does under the hood; we can't set
            # that option here because the CDP transport attaches to a reused context, so we
            # issue the CDP command directly. It must precede goto so the document commits
            # with CSP relaxed. Safe: we snapshot the rendered DOM, not preserve runtime
            # behaviour. Best-effort — a non-Chromium / unsupported transport just skips it.
            try:
                page.context.new_cdp_session(page).send(
                    "Page.setBypassCSP", {"enabled": True}
                )
            except Exception as exc:
                log.debug("Page.setBypassCSP unavailable: %s", exc)

            log.debug("navigating: %s", url)
            response = None
            binary_fallback = False
            try:
                response = page.goto(nav_url, wait_until="domcontentloaded", timeout=timeout_ms)
            except PlaywrightTimeout:
                log.info("goto timed out (likely inline binary) — fetching via request API")
                binary_fallback = True
            except PlaywrightError as e:
                if "Download is starting" not in str(e):
                    raise
                log.info("server triggered download — fetching binary via request API")
                binary_fallback = True

            content_type = _content_type(response)
            response_status = response.status if response is not None else None
            log.info(
                "settled: %s (status=%s, content-type=%s%s)",
                page.url if not binary_fallback else url,
                response_status if response_status is not None else "?",
                content_type or "?",
                ", binary fallback" if binary_fallback else "",
            )

            if not binary_fallback and _is_html(content_type):
                try:
                    page.wait_for_load_state("networkidle", timeout=NETWORKIDLE_BUDGET_MS)
                except PlaywrightTimeout:
                    log.warning(
                        "networkidle did not settle within %dms — snapshotting anyway",
                        NETWORKIDLE_BUDGET_MS,
                    )
                interactions.run(
                    page,
                    interaction_steps,
                    carousel_handler=lambda pg, a: _walk_carousel(
                        page=pg, request_api=ctx.request, arg=a
                    ),
                )
                image_stats = _inline_image_srcs(page=page, request_api=ctx.request)
                final_url = page.url
                snapshot = _snapshot_html(
                    page=page, fetched_at=fetched_at, bundle=bundle, fidelity=fidelity
                )
                issues = _run_capture_detectors(
                    snapshot=snapshot,
                    # Drift is measured against where we INTENDED to navigate (the rewritten
                    # nav target), not the pre-rewrite URL — else any `url_rewrite` that
                    # changes host (e.g. www.reddit → old.reddit) self-reports a false
                    # hostname-change drift. The original `url` remains the recorded origin.
                    request_url=nav_url,
                    final_url=final_url,
                    response_status=response_status,
                    image_stats=image_stats,
                    snapshot_engine=snapshot_engine,
                )
                capture_path = capture_dir / f"{base}.html"
                capture_path.write_text(snapshot, encoding="utf-8")
                return capture_path, issues, snapshot_engine

            api = ctx.request.get(url, timeout=timeout_ms)
            raw = api.body()
            ct = (
                api.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                or content_type
                or ""
            )
            if _looks_like_bot_challenge(raw, ct):
                log.info(
                    "binary fetch returned a bot challenge (%d bytes, ct=%s) — retrying via urllib",
                    len(raw),
                    ct,
                )
                raw, ct = _plain_http_get(url, user_agent=user_agent, timeout_s=opts.timeout_s)
                log.info("urllib fallback: %d bytes, ct=%s", len(raw), ct)
            ext = mime.extension_for(ct, fallback="bin")
            capture_path = capture_dir / f"{base}.{ext}"
            capture_path.write_bytes(raw)
            log.info("non-HTML response: saved %d bytes as .%s", len(raw), ext)
            return capture_path, [], None
        finally:
            if page is not None:
                with contextlib.suppress(Exception):
                    page.close()
            browser.close()


@register("browser")
def _capture_with_browser(
    url: str,
    *,
    corpus_root: Path,
    capture_dir: Path,
    opts: CaptureOptions,
    recipe: dict[str, Any] | None,
) -> CaptureResult:
    """Packaged Playwright capturer: HTML snapshot (SingleFile or rendered DOM) +
    binary re-fetch + the capture-stage detector suite."""
    from corpus.config import load_config

    # Transport precedence: CLI `--transport` > recipe `transport:` > config default.
    eff_recipe = dict(recipe or {})
    chosen = opts.transport or eff_recipe.get("transport") or load_config(
        corpus_root
    ).capture.get("default_transport")
    if chosen:
        eff_recipe["transport"] = chosen
    cdp_url = _resolve_cdp_endpoint(opts.cdp_url)
    path, issues, snapshot_engine = _capture_via_playwright(
        url=url,
        capture_dir=capture_dir,
        opts=opts,
        cdp_url=cdp_url,
        recipe=eff_recipe,
        corpus_root=corpus_root,
    )
    if issues:
        log.info(
            "capture-stage detectors fired: %s",
            ", ".join(
                f"{i['id']}" + (f"/{i['subtype']}" if i.get("subtype") else "") for i in issues
            ),
        )
    return CaptureResult(
        capture_path=path, used_video=False, issues=issues, snapshot_engine=snapshot_engine
    )


def _recipe_viewport(recipe: dict[str, Any]) -> tuple[int, int] | None:
    """Parse a recipe's `viewport: WxH`, or None when absent/invalid."""
    spec = recipe.get("viewport")
    if not spec:
        return None
    try:
        return parse_viewport(str(spec))
    except ValueError:
        log.warning("ignoring invalid recipe viewport %r", spec)
        return None


def _inline_image_srcs(*, page: Any, request_api: Any, quiet: bool = False) -> tuple[int, int]:
    """Pre-fetch each external `<img src>` via Playwright's request API (no CORS)
    and swap it to a base64 `data:` URI in the live DOM.

    Works for both snapshot paths: SingleFile picks up the inlined srcs, and a
    plain `page.content()` serializes them too. The original URL is preserved as
    `data-corpus-original-src` for downstream dedup. Returns `(inlined, failed)`.

    `quiet` logs the per-call counts at debug rather than info — used by the
    carousel walk, which calls this once per slide and would otherwise be noisy.
    """
    _log = log.debug if quiet else log.info
    items = page.evaluate(
        """() => {
            const out = [];
            document.querySelectorAll('img').forEach((img, idx) => {
                const src = img.src || '';
                if (src && (src.startsWith('http://') || src.startsWith('https://'))) {
                    out.push({idx, src});
                }
            });
            return out;
        }"""
    )
    if not items:
        return (0, 0)
    _log("pre-fetching %d external <img> srcs for inline embedding", len(items))
    # Hotlink-protecting hosts (photobucket &c.) serve a watermarked/degraded image to a
    # FOREIGN Referer but the clean original to a same-origin one. When a browser loads a
    # cross-origin <img>, its Referer is the embedding page — exactly the watermark trigger.
    # Our inline fetch goes through Playwright's request API, so for a cross-origin image we
    # set Referer to the image's OWN origin: the host sees a self-referer and serves the
    # un-degraded file. (Verified: photobucket returns the un-watermarked original to a
    # photobucket referer; a foreign / empty referer gets the "Groupsy" watermark overlay.)
    try:
        _pg = urlparse(page.url or "")
        page_key = (_pg.scheme, _pg.netloc) if _pg.netloc else None
    except Exception:
        page_key = None
    inlined = 0
    failed = 0
    for item in items:
        img_url = item["src"]
        idx = item["idx"]
        try:
            _iu = urlparse(img_url)
            headers = {}
            if page_key and _iu.scheme and _iu.netloc and (_iu.scheme, _iu.netloc) != page_key:
                headers["referer"] = f"{_iu.scheme}://{_iu.netloc}/"
            resp = request_api.get(img_url, headers=headers, timeout=15_000)
            if resp.status >= 400:
                failed += 1
                continue
            raw = resp.body()
            if not raw:
                failed += 1
                continue
            ct = (
                resp.headers.get("content-type") or "application/octet-stream"
            ).split(";", 1)[0].strip()
            data_uri = f"data:{ct};base64,{base64.b64encode(raw).decode('ascii')}"
            page.evaluate(
                "([idx, dataUri, originalSrc]) => {"
                " const img = document.querySelectorAll('img')[idx];"
                " if (img) {"
                "  img.setAttribute('data-corpus-original-src', originalSrc);"
                "  img.src = dataUri;"
                " } }",
                [idx, data_uri, img_url],
            )
            inlined += 1
        except Exception as exc:
            failed += 1
            log.debug("inline fetch %s: %s", img_url, exc)
    _log("inlined %d / failed %d external <img> srcs", inlined, failed)
    return (inlined, failed)


# Per-slide carousel walk. A virtualized carousel (Instagram: only the visible slide ±1
# is in the DOM, and each slide's image is lazy-fetched via XHR only when it becomes
# active) defeats a plain `click: Next` + the single end-of-run `_inline_image_srcs`:
# off-screen slides are evicted before that one inline pass runs, so it keeps only the two
# left in the DOM. The walk below force-inlines each slide AS the trusted click reaches it
# and clones the inlined image into a persistent hidden stash that survives eviction.

_CAROUSEL_STASH_JS = """
() => {
  let stash = document.getElementById('__corpus_carousel_stash');
  if (!stash) {
    stash = document.createElement('div');
    stash.id = '__corpus_carousel_stash';
    stash.style.display = 'none';
    document.body.appendChild(stash);
  }
  const have = new Set([...stash.querySelectorAll('img')]
    .map((i) => i.getAttribute('data-corpus-original-src') || i.src));
  let added = 0;
  document.querySelectorAll('img[data-corpus-original-src]').forEach((img) => {
    const key = img.getAttribute('data-corpus-original-src') || img.src;
    if (img.naturalWidth >= 600 && !have.has(key)) {
      stash.appendChild(img.cloneNode(true));
      have.add(key);
      added += 1;
    }
  });
  return added;
}
"""

# After a Next click, wait (network-aware) for the new slide's large image to load — the
# prior inline made every earlier <img> a data: URI, so a fresh http(s) src on a >=600px
# image is the slide that just became active. Bounded so a missing slide never hangs.
_CAROUSEL_WAIT_JS = """
() => new Promise((resolve) => {
  const t0 = Date.now();
  const tick = () => {
    const ready = [...document.querySelectorAll('img')].some(
      (i) => /^https?:/.test(i.src || '') && i.complete && i.naturalWidth >= 600);
    if (ready || Date.now() - t0 > 6000) resolve();
    else setTimeout(tick, 150);
  };
  tick();
})
"""


def _walk_carousel(*, page: Any, request_api: Any, arg: Any) -> None:
    """Service a `carousel` interaction: walk a virtualized image carousel slide by
    slide, force-inlining each slide's media as the walk reaches it.

    `arg` is `{next: <selector>, max: <int>}` (or a bare selector string). Per step:
    inline the currently-loaded externals (`_inline_image_srcs` force-fetches the
    visible slide's image) and clone the large inlined ones into a persistent hidden
    stash, then trusted-click `next` and wait (network-aware) for the new slide's image
    to load. The stash survives the carousel's DOM eviction, so the final snapshot
    carries every slide. The stash images dedup by `data-corpus-original-src`.
    """
    if isinstance(arg, dict):
        next_sel = arg.get("next") or arg.get("selector")
        max_clicks = int(arg.get("max", 12))
    else:
        next_sel, max_clicks = (str(arg) if arg else ""), 12
    if not next_sel:
        log.debug("carousel: no `next` selector — skipping")
        return

    def inline_and_stash() -> int:
        _inline_image_srcs(page=page, request_api=request_api, quiet=True)
        try:
            return int(page.evaluate(_CAROUSEL_STASH_JS) or 0)
        except Exception as exc:
            log.debug("carousel stash eval failed: %s", exc)
            return 0

    total = inline_and_stash()  # the slide we land on
    for _ in range(max(1, max_clicks)):
        loc = page.locator(str(next_sel))
        try:
            if loc.count() == 0:
                break
            loc.first.click(timeout=3000)
        except Exception as exc:  # ran out of "next" / control vanished — done
            log.debug("carousel: next click stopped: %s", exc)
            break
        with contextlib.suppress(Exception):
            page.evaluate(_CAROUSEL_WAIT_JS)
        total += inline_and_stash()
    log.info("carousel: captured %d slide image(s) across the walk", total)


def _snapshot_html(
    *,
    page: Any,
    fetched_at: str,
    bundle: Path | None,
    fidelity: str = DEFAULT_FIDELITY,
    capture_url: str | None = None,
) -> str:
    """Produce the HTML snapshot string with corpus-* meta tags injected.

    With a SingleFile bundle, run `singlefile.getPageData()` for a self-contained
    snapshot, with the `fidelity` preset merged over `SINGLEFILE_OPTIONS` (see
    `FIDELITY_PRESETS`). Without one, fall back to the rendered DOM
    (`page.content()`); the image srcs already inlined by `_inline_image_srcs`
    are preserved, only CSS / fonts are left external. The resolved `fidelity` is
    stamped into a `corpus-fidelity` meta tag regardless, so the artifact records
    how it was captured.

    `capture_url` overrides the recorded `corpus-capture-url` meta — used by from-save
    capture, where the navigation target is a `file://` path but the provenance URL is
    the SingleFile banner's; absent it, `page.url` (the live final URL) is recorded.
    """
    final_url = capture_url or page.url
    if bundle is not None:
        log.info("snapshotting via SingleFile bundle: %s (fidelity=%s)", bundle, fidelity)
        page.add_script_tag(content=_unwrap_bundle_source(bundle.read_text(encoding="utf-8")))
        data = page.evaluate(
            "async (opts) => { const d = await singlefile.getPageData(opts); "
            "return { content: d.content, title: d.title }; }",
            _singlefile_options(fidelity),
        )
        snapshot = data["content"]
        log.info("snapshot %d bytes, title %r", len(snapshot.encode()), data["title"])
    else:
        log.warning(
            "no SingleFile bundle resolved (registered `assets.singlefile`, or set "
            "CORPUS_SINGLEFILE_BUNDLE for local dev) — capturing rendered DOM without "
            "inlined CSS/fonts"
        )
        snapshot = page.content()
        log.info("rendered-DOM snapshot %d bytes, title %r", len(snapshot.encode()), page.title())
    return _inject_corpus_metadata(
        snapshot, capture_url=final_url, fetched_at=fetched_at, fidelity=fidelity
    )


# The upstream `single-file-cli` distribution ships the bundle as a JS module
# exporting the minified source as a string constant (`const script = "...";
# const ...` / `...; export ...`). A registered/env asset may be that verbatim
# upstream file OR an already-injectable IIFE — format knowledge for telling them
# apart, and unwrapping the former, lives in the loader (spec/corpus.md §12.3.6) so
# registering a build needs no manual pre-processing step.
_BUNDLE_MODULE_RE = re.compile(
    r"^\s*const\s+script\s*=\s*(\".*?\");(?:\s*const|\s*export)", re.DOTALL
)


def _unwrap_bundle_source(raw: str) -> str:
    """Injectable JS for a SingleFile bundle: unwrap the upstream `script`
    string-constant module form into its decoded JS text, or pass a direct IIFE
    through unchanged."""
    m = _BUNDLE_MODULE_RE.match(raw)
    if not m:
        return raw
    return json.loads(m.group(1))


@dataclass(frozen=True)
class ResolvedBundle:
    """A located SingleFile bundle plus the engine identity to stamp on the capture
    sidecar as `snapshot_engine:` (spec/corpus.md §12.3.6)."""

    path: Path
    engine: str


# Stamped when no bundle resolves at all — capture degrades to the rendered-DOM
# snapshot, and this is the honest, undisguised record of that (spec §12.3.6:
# "degraded fidelity is never silent").
SNAPSHOT_ENGINE_DEGRADED = "rendered-dom"


def _resolve_singlefile_bundle(corpus_root: Path) -> ResolvedBundle | None:
    """Locate the SingleFile JS bundle (spec/corpus.md §12.3.6).

    Resolution order:

    1. `CORPUS_SINGLEFILE_BUNDLE` env — the dev escape hatch, checked first. A set-
       but-missing path is a hard miss (no fallthrough to the registered asset): the
       operator asked for THIS file. Stamped `singlefile@env` + the blake3 of the
       loaded file's bytes.
    2. The instance's registered `assets.singlefile` (`athenaeum.yaml`, Part I §2.3):
       its `latest` tag resolved to an artifact blake3, materialized through the
       corpus's own artifact/custody routes (`corpus.assets.materialize`). Stamped
       `singlefile@{tag}` + the artifact blake3.
    3. Neither resolves (no asset registered, or its bytes aren't materialized in
       this environment) → `None`. The caller degrades to the rendered-DOM snapshot
       and discloses it loudly — a warning here, plus a capture issue at the call
       site (`_snapshot_engine_issue`), never silent.
    """
    env = os.environ.get("CORPUS_SINGLEFILE_BUNDLE")
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            digest = hashing.hash_file(p, also=())["blake3"]
            engine = f"singlefile@env {records.format_hash('blake3', digest)}"
            return ResolvedBundle(path=p, engine=engine)
        log.warning("CORPUS_SINGLEFILE_BUNDLE points at a missing file: %s", p)
        return None

    asset = corpus_assets.load_asset(corpus_root, "singlefile")
    if asset is None:
        log.warning(
            "no `singlefile` asset registered (assets: in athenaeum.yaml) and no "
            "CORPUS_SINGLEFILE_BUNDLE override — capturing rendered DOM without inlined "
            "CSS/fonts/images"
        )
        return None
    snapshot = asset.snapshots[asset.latest]
    path = corpus_assets.materialize(corpus_root, snapshot.artifact)
    if path is None:
        log.warning(
            "registered singlefile asset @%s (artifact %s) is not materialized in this "
            "environment — capturing rendered DOM without inlined CSS/fonts/images",
            asset.latest,
            snapshot.artifact[:12],
        )
        return None
    return ResolvedBundle(
        path=path,
        engine=f"singlefile@{asset.latest} {records.format_hash('blake3', snapshot.artifact)}",
    )


# ---------- CDP endpoint resolution ---------- #


def _resolve_cdp_endpoint(cli_arg: str | None) -> str | None:
    """Decide whether to connect to an existing CDP browser, and where.

    Order: explicit `cli_arg` → `CAPTURE_CDP_URL` env → `CAPTURE_NO_CDP=1` skips
    autodetect → probe `CDP_AUTODETECT_URL`/json/version (sub-second). None means
    "launch a fresh headless browser".
    """
    if cli_arg:
        return cli_arg
    env = os.environ.get("CAPTURE_CDP_URL")
    if env:
        return env
    if os.environ.get("CAPTURE_NO_CDP") == "1":
        return None
    probe = f"{CDP_AUTODETECT_URL.rstrip('/')}/json/version"
    try:
        with urllib.request.urlopen(probe, timeout=0.5):
            return CDP_AUTODETECT_URL
    except OSError:
        return None


# ---------- capture-stage detectors (spec §4.3.3.1 issue shape) ---------- #


def _run_capture_detectors(
    *,
    snapshot: str,
    request_url: str,
    final_url: str,
    response_status: int | None,
    image_stats: tuple[int, int],
    snapshot_engine: str | None = None,
) -> list[dict]:
    """Run capture-stage detectors against the snapshot + orchestration context.

    Detectors are independent — each adds 0 or 1 issues. No short-circuit: one
    captured page can exhibit several problems (e.g. redirect-drift to a paywall
    fires both). Returns issue dicts in the shape `ingest` replays as
    `<!--issue-->` blocks.
    """
    detector_id = touches.script_identifier("capture")
    issues: list[dict] = []
    for detector in (
        _detect_http_error_with_200_body,
        _detect_final_url_drift,
        _detect_login_wall,
        _detect_paywall,
        _detect_captcha,
    ):
        if issue := detector(
            snapshot=snapshot,
            request_url=request_url,
            final_url=final_url,
            response_status=response_status,
            detector_id=detector_id,
        ):
            issues.append(issue)
    if issue := _detect_inline_image_failure(image_stats=image_stats, detector_id=detector_id):
        issues.append(issue)
    if issue := _snapshot_engine_issue(snapshot_engine, detector_id=detector_id):
        issues.append(issue)
    return issues


def _snapshot_engine_issue(
    snapshot_engine: str | None, *, detector_id: str | None = None
) -> dict | None:
    """A `snapshot-engine-degraded` issue when `snapshot_engine` is the rendered-DOM
    degrade stamp (spec §12.3.6: "discloses it loudly") — the loud, on-record half
    of the disclosure; `_resolve_singlefile_bundle`'s `log.warning` is the other.
    `None` for a resolved engine (registered asset or env override), never emitted."""
    if snapshot_engine != SNAPSHOT_ENGINE_DEGRADED:
        return None
    return {
        "id": "snapshot-engine-degraded",
        "subtype": None,
        "severity": "warning",
        "detector": detector_id or touches.script_identifier("capture"),
        "fields": {"snapshot_engine": SNAPSHOT_ENGINE_DEGRADED},
    }


def _detect_http_error_with_200_body(
    *, snapshot: str, response_status: int | None, detector_id: str, **_: Any
) -> dict | None:
    """HTTP 200 but the body is a known error template (Apache/nginx/IIS/404)."""
    from corpus.quality.signatures import HTTP_ERROR_BODY_SIGNATURES

    if response_status != 200:
        return None
    for name, body_re in HTTP_ERROR_BODY_SIGNATURES:
        if body_re.search(snapshot):
            return {
                "id": "partial-content",
                "subtype": "http-error",
                "severity": "blocking",
                        "detector": detector_id,
                "fields": {"http_status": 200, "signature": name},
            }
    return None


def _detect_final_url_drift(
    *, request_url: str, final_url: str, detector_id: str, **_: Any
) -> dict | None:
    """Final settled URL drifted to a login/cookie/error/root landing surface.

    Hostname change OR path matches a drift pattern. Same-host same-path
    canonical redirects (trailing slash, www) are ignored.
    """
    from corpus.quality.signatures import REDIRECT_DRIFT_PATH_PATTERNS

    try:
        req = urlparse(request_url)
        fin = urlparse(final_url)
    except Exception:
        return None
    req_host = (req.hostname or "").lower().lstrip(".")
    fin_host = (fin.hostname or "").lower().lstrip(".")

    if req_host and fin_host and req_host.removeprefix("www.") != fin_host.removeprefix("www."):
        return {
            "id": "partial-content",
            "subtype": "redirect-drift",
            "severity": "warning",
                "detector": detector_id,
            "fields": {
                "drift": "hostname-change",
                "request_url": request_url,
                "final_url": final_url,
            },
        }

    req_path = req.path.rstrip("/")
    if not req_path:
        return None
    for name, path_re in REDIRECT_DRIFT_PATH_PATTERNS:
        if path_re.match(fin.path):
            return {
                "id": "partial-content",
                "subtype": "redirect-drift",
                "severity": "warning",
                        "detector": detector_id,
                "fields": {"drift": name, "request_url": request_url, "final_url": final_url},
            }
    return None


def _detect_login_wall(*, snapshot: str, detector_id: str, **_: Any) -> dict | None:
    """Page served a sign-in/login wall instead of the requested content."""
    from corpus.quality.signatures import LOGIN_WALL_SIGNATURES

    title_text = _extract_title_text(snapshot)
    body_text = _extract_visible_text(snapshot)
    for (sig_name, title_re), body_re in LOGIN_WALL_SIGNATURES:
        if title_re is not None and title_text and title_re.search(title_text):
            if body_re is None or body_re.search(body_text):
                return {
                    "id": "partial-content",
                    "subtype": "login-wall",
                    "severity": "warning",
                                "detector": detector_id,
                    "fields": {"signature": sig_name},
                }
        elif body_re is not None and body_re.search(body_text):
            return {
                "id": "partial-content",
                "subtype": "login-wall",
                "severity": "warning",
                        "detector": detector_id,
                "fields": {"signature": sig_name},
            }
    return None


def _detect_paywall(*, snapshot: str, detector_id: str, **_: Any) -> dict | None:
    """Content served behind a 'subscribe' wall."""
    from corpus.quality.signatures import PAYWALL_SIGNATURES

    body_text = _extract_visible_text(snapshot)
    for name, _title_re, body_re, severity in PAYWALL_SIGNATURES:
        target = snapshot if name == "paywall-marker" else body_text
        if body_re.search(target):
            return {
                "id": "partial-content",
                "subtype": "paywall",
                "severity": severity,
                        "detector": detector_id,
                "fields": {"signature": name},
            }
    return None


def _detect_captcha(*, snapshot: str, detector_id: str, **_: Any) -> dict | None:
    """Page is a captcha / human-verification challenge."""
    from corpus.quality.signatures import CAPTCHA_SIGNATURES

    body_text = _extract_visible_text(snapshot)
    for name, regex in CAPTCHA_SIGNATURES:
        target = snapshot if name in ("hcaptcha", "recaptcha") else body_text
        if regex.search(target):
            return {
                "id": "partial-content",
                "subtype": "captcha",
                "severity": "blocking",
                        "detector": detector_id,
                "fields": {"signature": name},
            }
    return None


def _detect_inline_image_failure(
    *, image_stats: tuple[int, int], detector_id: str
) -> dict | None:
    """Emit `info` if external-image inline failure > 10%, `warning` if > 50%."""
    inlined, failed = image_stats
    total = inlined + failed
    if total == 0:
        return None
    rate = failed / total
    if rate <= 0.10:
        return None
    return {
        "id": "inline-image-failure",
        "subtype": None,
        "severity": "warning" if rate > 0.50 else "info",
        "detector": detector_id,
        "fields": {
            "inlined_count": inlined,
            "failed_count": failed,
            "failure_rate": round(rate, 3),
        },
    }


# ---------- text extraction (lazy regex, good enough for signature scans) ---------- #


def _extract_title_text(snapshot: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", snapshot, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_visible_text(snapshot: str) -> str:
    """Strip tags → rough visible text for prose-pattern matching. Caps input so
    a megabyte of inlined-image data: URIs doesn't slow detectors down."""
    text = re.sub(
        r"<script\b[^>]*>.*?</script>", " ", snapshot[:200_000], flags=re.IGNORECASE | re.DOTALL
    )
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return text[:50_000]


# ---------- bot-challenge fallback ---------- #


_BOT_CHALLENGE_MARKERS = (
    b"_Incapsula_Resource",  # Imperva / Incapsula
    b"_pxAppId",  # PerimeterX
    b"<title>Just a moment",  # Cloudflare interstitial
    b"akamai-bot-manager",  # Akamai
)


def _looks_like_bot_challenge(body: bytes, content_type: str) -> bool:
    # Challenge interstitials (Cloudflare/PerimeterX/Akamai) are typically 20-60 KB of
    # markup + inline JS; cap well above that so real challenges are scanned, while a large
    # body still short-circuits as genuine content (the CDN markers also appear in legit
    # pages that merely use those services).
    if len(body) > 128 * 1024:
        return False
    if content_type and not content_type.startswith(("text/html", "application/xhtml")):
        return False
    return any(marker in body for marker in _BOT_CHALLENGE_MARKERS)


def _plain_http_get(url: str, *, user_agent: str, timeout_s: float) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read()
        ct = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    return body, ct


# ---------- corpus-* meta injection ---------- #


_HEAD_OPEN = re.compile(r"<head\b[^>]*>", re.IGNORECASE)


def _inject_corpus_metadata(
    html: str, *, capture_url: str, fetched_at: str, fidelity: str = DEFAULT_FIDELITY
) -> str:
    """Inject corpus-capture-url / corpus-fetched-at / corpus-fidelity meta tags after `<head>`."""
    block = (
        f'<meta name="corpus-capture-url" content="{_attr_escape(capture_url)}">'
        f'<meta name="corpus-fetched-at" content="{_attr_escape(fetched_at)}">'
        f'<meta name="corpus-fidelity" content="{_attr_escape(fidelity)}">'
    )
    if m := _HEAD_OPEN.search(html):
        idx = m.end()
        return html[:idx] + block + html[idx:]
    # No <head> (common under SingleFile's compressHTML — HTML5 makes the tag
    # optional and the minifier drops it). Prepend a synthetic head wrapping our
    # tags; the page's original head content remains inside <html>.
    log.debug("no <head> tag in snapshot; prepending one for corpus metadata")
    return f"<head>{block}</head>{html}"


def _attr_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


# ---------- ingest seam ---------- #


def _ingest_capture(
    result: CaptureResult,
    *,
    original_url: str,
    corpus_root: Path,
    fetched_at: str | None = None,
) -> Path | None:
    """Write the `.capture.yaml` sidecar (source_url / fetched_at / snapshot_engine /
    issues) and dispatch `ingest` in-process. Returns the resulting record path, or
    None on a non-zero ingest exit.

    `fetched_at` overrides the recorded snapshot timestamp — used by from-save capture
    to seed the origin `snapshot:` with the SingleFile saved date (when the human saved
    the page), not the moment we re-snapshotted it; absent it, capture time (now).

    A yt-dlp `.info.json` companion (enrichment metadata) is left in `capture/` and
    renamed to `<hash>.info.json` by `ingest` itself — it stays in staging, is read at
    draft, then deleted. The artifact is the only `<hash>`-named file under `artifacts/`.
    """
    import yaml

    from corpus._cli import dispatch

    capture_path = result.capture_path
    record_id = hashing.hash_file(capture_path, also=())["blake3"]

    sidecar = capture_path.with_suffix(capture_path.suffix + ".capture.yaml")
    payload: dict[str, Any] = {
        "source_url": original_url,
        "fetched_at": fetched_at or touches.now_iso(),
    }
    if result.snapshot_engine:
        payload["snapshot_engine"] = result.snapshot_engine
    if result.issues:
        payload["capture_issues"] = result.issues
    sidecar.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    log.debug("dispatch: ingest %s", capture_path)
    rc = dispatch(["ingest", str(capture_path), "--corpus-root", str(corpus_root)])
    if rc != 0:
        return None

    return paths.record_path(corpus_root, record_id)


# ---------- small pure helpers ---------- #


def _apply_url_rewrite(url: str, recipe: dict[str, Any]) -> str:
    """Apply the recipe's per-host `url_rewrite` regex rules to the navigation URL and
    return the result (unchanged when no rule matches). Each rule is `{pattern, replacement}`
    applied in order via `re.sub`. Use when a host's link form differs from the form that
    cold-loads full content — e.g. ALLDATA links to `#/vehicle/<v>/.../nonstandard/<id>`
    (a cold-load stub) but the equivalent `#/article/<v>/.../nonstandard/<id>` cold-loads
    the full article. Only the navigation target is rewritten; the original URL remains the
    recorded origin URI and the rewritten form is captured as `final_url` (an origin alias)."""
    out = urlcanon.apply_rewrite_rules(url, recipe.get("url_rewrite"))
    if out != url:
        log.info("url_rewrite: %s -> %s", url, out)
    return out


def _sanitize_filename(url: str) -> str:
    """Readable, filesystem-safe name from a URL. Only the name a human sees if
    they peek at `capture/` — ingest renames to `artifacts/<hash>.<ext>`."""
    parsed = urlparse(url)
    raw = (parsed.netloc + parsed.path).strip("/") or "page"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-")
    return safe[:120] or "page"


def parse_viewport(spec: str) -> tuple[int, int]:
    """Parse a `WxH` viewport spec (e.g. `1280x900`). Raises ValueError on junk."""
    if m := re.fullmatch(r"\s*(\d+)\s*x\s*(\d+)\s*", spec):
        return (int(m.group(1)), int(m.group(2)))
    raise ValueError(f"invalid viewport {spec!r}: expected WxH (e.g. 1280x900)")


def _content_type(response: Any) -> str:
    if response is None:
        return ""
    raw = response.headers.get("content-type", "") if response.headers else ""
    return raw.split(";", 1)[0].strip().lower()


def _is_html(content_type: str) -> bool:
    return content_type in {"text/html", "application/xhtml+xml"}


def _canonicalize(url: str) -> str:
    try:
        canonical = urlcanon.normalize(url)
    except Exception:
        return url
    if canonical != url:
        log.debug("canonicalized URL: %s -> %s", url, canonical)
    return canonical


