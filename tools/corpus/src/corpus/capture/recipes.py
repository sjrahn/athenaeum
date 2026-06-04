"""Per-origin capture recipes — read from the origin overlay's ``capture:`` section.

Capture is a retrieval concern of an origin, so its config lives **on the origin
overlay** (``schema/origin/web/<host>.yaml`` — origin overlays are namespaced by URI
scheme family, http(s) under ``web/``) rather than a separate namespace — one
host-keyed file describes both what a source is and how to capture it. The
``capture:`` block selects and parameterises the capturer for matching origins::

    # schema/origin/web/instagram.com.yaml
    applies_to:
      host_pattern: instagram.com        # or host_patterns: [a, b]; "*" = catch-all
      include_subdomains: true
    extended_fields: {}                   # origin-block field overlays (validation)
    capture:                              # capture-time behavior (read only at capture)
      capturer: browser                   # packaged or corpus-local name (default: browser)
      transport: headless                 # headless | headed | cdp
      fidelity: exact                     # exact | balanced | lean SingleFile snapshot tier
                                          #   (default balanced; exact preserves presentation,
                                          #   lean keeps only the info -- see FIDELITY_PRESETS)
      url_rewrite:                        # rewrite the NAV target before goto (regex sub,
        - pattern: '#/vehicle/(.+/nonstandard/.+)$'   #   in order). The original URL stays
          replacement: '#/article/\1'     #   the recorded origin; the rewritten form lands
                                          #   as final_url. For hosts whose link form cold-
                                          #   loads a stub but an alt form loads full content.
      url_equivalent:                     # IDENTITY-only normalization (never changes the
        query: drop                       #   fetch). Two URLs are the same resource iff their
        rules:                            #   identity keys match. `query: drop|keep` (keep =
          - pattern: '/page-1(?=[/?#]|$)' #   default) + ordered {pattern, replacement} rules;
            replacement: ''               #   on_rewritten: true folds identity on the rewrite
                                          #   output. Bare list form = rules only. See
                                          #   corpus.urls.identity_key. (g8board: /page-1==bare,
                                          #   nested_view/affiliate params == noise.)
      interactions:                       # see corpus.capture.interactions
        - scroll: full
        - click: {selector: "button[aria-label*=Next i]", repeat: 12}
      pagination: true                    # walk a paginated work's pages, merge them, ingest
                                          #   ONE record (bare true = auto-detect; a map
                                          #   {content_selector, next, max_pages, expect_count}
                                          #   gives control). See corpus.capture.pagination.
      viewport: 1280x900
      user_agent: "..."

Global defaults go on the universal ``schema/origin/origin.yaml`` ``capture:`` (it
deep-merges under every per-host overlay via the schema loader); per-host
``capture:`` overrides. The reference package ships **no** capture config — absent
any match, the browser capturer's built-in defaults apply (headless +
``interactions.DEFAULT_STEPS``). For the hard cases a corpus-local capturer (code;
see Phase C) is named by a recipe's ``capturer:``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .. import schemas
from .. import urls as urlcanon

log = logging.getLogger("corpus.capture.recipes")


def _patterns(overlay: dict[str, Any]) -> tuple[list[str], bool]:
    applies = overlay.get("applies_to") or {}
    pats: list[str] = []
    if "host_pattern" in applies:
        pats.append(str(applies["host_pattern"]))
    if "host_patterns" in applies:
        pats.extend(str(p) for p in applies["host_patterns"])
    return pats, bool(applies.get("include_subdomains", False))


def _overlay_section_for_url(
    corpus_root: Path, url: str, section: str
) -> dict[str, Any] | None:
    """Return the named top-level section (e.g. `capture` / `canonical`) of the
    most-specific origin overlay matching `url`'s host, or None.

    Match predicate mirrors `schemas.origin_overlays_for_uris` (the overlays are the
    same files): each overlay's `applies_to.host_pattern(s)` is tested with
    `urls.same_domain` (apex↔www aware) honoring `include_subdomains`.
    `host_pattern: "*"` is a catch-all (lowest priority). Ties break toward the
    longest pattern (most specific), then id — deterministic. The universal
    `origin.yaml`'s same section deep-merges under each per-host overlay (global
    defaults), so the returned dict already carries any global + per-host layering.
    """
    matches: list[tuple[int, str, dict[str, Any]]] = []
    for id_, overlay in schemas.load_origin_overlays(corpus_root):
        cfg = overlay.get(section)
        if not isinstance(cfg, dict):
            continue
        patterns, include_subdomains = _patterns(overlay)
        for pattern in patterns:
            if pattern == "*":
                matches.append((0, id_, cfg))
                break
            if urlcanon.same_domain(url, pattern, include_subdomains=include_subdomains):
                matches.append((len(pattern), id_, cfg))
                break
    if not matches:
        return None
    matches.sort(key=lambda m: (m[0], m[1]), reverse=True)
    return matches[0][2]


def capture_recipe_for_url(corpus_root: Path, url: str) -> dict[str, Any] | None:
    """Return the `capture:` config of the most-specific origin overlay matching `url`'s
    host, or None when no matching overlay declares one. See `_overlay_section_for_url`."""
    return _overlay_section_for_url(corpus_root, url, "capture")


def url_equivalent_for_url(corpus_root: Path, url: str) -> Any:
    """Return the per-host `capture.url_equivalent` config (a list of rules or a
    `{query, rules, on_rewritten}` map) for `url`'s host, or None.

    Identity-equivalence rules let a host declare which URL spellings denote the same
    resource (spec §7.2). Consumed by `urls.identity_key` at the capture short-circuit,
    crawl frontier dedup, and pagination uri-recording sites. Opt-in: absent the section,
    identity stays the conservative `urls.normalize` string match. See `identity_key_for_url`."""
    cap = _overlay_section_for_url(corpus_root, url, "capture")
    if not isinstance(cap, dict):
        return None
    eq = cap.get("url_equivalent")
    return eq if isinstance(eq, (dict, list)) else None


def identity_key_for_url(corpus_root: Path, url: str) -> str:
    """Compute `url`'s identity key, honoring the host's `url_equivalent` (+ `url_rewrite`
    for the `on_rewritten` hook). The single-URL entry point for the capture short-circuit /
    `find_by_uri` resolve site; equals `urls.normalize(url)` when the host declares no
    equivalence rules. Bulk sites (`build_uri_index`, crawl `_expand`) memoize the recipe
    by host and call `urls.identity_key` directly rather than re-resolving per URL."""
    recipe = capture_recipe_for_url(corpus_root, url) or {}
    return urlcanon.identity_key(
        url, recipe.get("url_equivalent"), url_rewrite=recipe.get("url_rewrite")
    )


def transcription_for_url(corpus_root: Path, url: str) -> dict[str, Any] | None:
    """Return the per-host `transcription:` section for `url`'s host, or None.

    A host declares whether/how its audio+video records transcribe at DRAFT time:
    `enabled: false` skips transcription (no warning); `adapter`/`base_url` override
    the global `[corpus.transcription]` backend. Absent the section, the global
    config applies. Mirrors `canonical_content_selector_for_url`; consumed by the
    audio/video drafters via `draft._hostcfg.resolve_transcription`."""
    return _overlay_section_for_url(corpus_root, url, "transcription")


def canonical_content_selector_for_url(
    corpus_root: Path, url: str
) -> str | list[str] | None:
    """Return the per-host `canonical.content_selector` (a CSS selector or list) for
    `url`'s host, or None. A host declares this to scope its canonical-content hash to the
    article-content region — excluding per-page framing (title, breadcrumb, entry-specific
    headings) — so the same article reached by different links collapses to one record via
    the existing content-dedup. Opt-in: absent the section, canonical stays whole-document.
    Consumed at draft time; see `content_hash._canonicalize_html`."""
    cfg = _overlay_section_for_url(corpus_root, url, "canonical")
    if not isinstance(cfg, dict):
        return None
    return cfg.get("content_selector") or None
