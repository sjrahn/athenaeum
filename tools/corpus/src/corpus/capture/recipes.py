"""Per-origin capture recipes — read from the origin overlay's ``capture:`` section.

Capture is a retrieval concern of an origin, so its config lives **on the origin
overlay** (``schema/origin/<host>.yaml``) rather than a separate namespace — one
host-keyed file describes both what a source is and how to capture it. The
``capture:`` block selects and parameterises the capturer for matching origins::

    # schema/origin/instagram.com.yaml
    applies_to:
      host_pattern: instagram.com        # or host_patterns: [a, b]; "*" = catch-all
      include_subdomains: true
    extended_fields: {}                   # origin-block field overlays (validation)
    capture:                              # capture-time behavior (read only at capture)
      capturer: browser                   # packaged or corpus-local name (default: browser)
      transport: headless                 # headless | headed | cdp
      url_rewrite:                        # rewrite the NAV target before goto (regex sub,
        - pattern: '#/vehicle/(.+/nonstandard/.+)$'   #   in order). The original URL stays
          replacement: '#/article/\1'     #   the recorded origin; the rewritten form lands
                                          #   as final_url. For hosts whose link form cold-
                                          #   loads a stub but an alt form loads full content.
      interactions:                       # see corpus.capture.interactions
        - scroll: full
        - click: {selector: "button[aria-label*=Next i]", repeat: 12}
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


def capture_recipe_for_url(corpus_root: Path, url: str) -> dict[str, Any] | None:
    """Return the `capture:` config of the most-specific origin overlay matching
    `url`'s host, or None when no matching overlay declares one.

    Match predicate mirrors `schemas.origin_overlays_for_uris` (the overlays are the
    same files): each overlay's `applies_to.host_pattern(s)` is tested with
    `urls.same_domain` (apex↔www aware) honoring `include_subdomains`.
    `host_pattern: "*"` is a catch-all (lowest priority). Ties break toward the
    longest pattern (most specific), then id — deterministic. The universal
    `origin.yaml`'s `capture:` deep-merges under each per-host overlay (global
    defaults), so the returned dict already carries any global + per-host layering.
    """
    matches: list[tuple[int, str, dict[str, Any]]] = []
    for id_, overlay in schemas.load_origin_overlays(corpus_root):
        capture_cfg = overlay.get("capture")
        if not isinstance(capture_cfg, dict):
            continue
        patterns, include_subdomains = _patterns(overlay)
        for pattern in patterns:
            if pattern == "*":
                matches.append((0, id_, capture_cfg))
                break
            if urlcanon.same_domain(url, pattern, include_subdomains=include_subdomains):
                matches.append((len(pattern), id_, capture_cfg))
                break
    if not matches:
        return None
    matches.sort(key=lambda m: (m[0], m[1]), reverse=True)
    return matches[0][2]
