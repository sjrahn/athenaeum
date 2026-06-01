"""Per-origin capture recipes — the capture-time analog of origin overlays.

A recipe is a YAML file at ``schema/capture/<name>.yaml``, resolved corpus-local
first by the schema loader (exactly like ``schema/origin/<host>.yaml``). It
selects and parameterises the capturer for matching origins::

    applies_to:
      host_pattern: instagram.com      # or host_patterns: [a, b]; "*" = catch-all
      include_subdomains: true
    capturer: browser                  # packaged or corpus-local name (default: browser)
    transport: headless                # headless | headed | cdp
    interactions:                      # see corpus.capture.interactions
      - scroll: full
      - click: {selector: "button[aria-label*=Next i]", repeat: 12}
    viewport: 1280x900
    user_agent: "..."

The reference package ships **no** base recipe — absent a match, the browser
capturer's built-in defaults apply (headless + ``interactions.DEFAULT_STEPS``).
A corpus adds per-origin recipes (data) or, for the hard cases, a corpus-local
capturer (code; see Phase C) that a recipe's ``capturer:`` names.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .. import schemas
from .. import urls as urlcanon

log = logging.getLogger("corpus.capture.recipes")

# schema/capture/<name>.yaml
_RECIPE_DIR = "capture"


def _load_all(corpus_root: Path) -> list[tuple[str, dict[str, Any]]]:
    """Every capture recipe visible to `corpus_root` (corpus-local first), as
    `(relpath, recipe)`. Reuses the schema loader so resolution/caching match
    origin overlays."""
    sources = schemas._sources(corpus_root)
    out: list[tuple[str, dict[str, Any]]] = []
    for relpath in schemas._discover_yaml(sources, _RECIPE_DIR):
        data = schemas._read_yaml_first(sources, relpath)
        if isinstance(data, dict):
            out.append((relpath, data))
    return out


def _patterns(recipe: dict[str, Any]) -> tuple[list[str], bool]:
    applies = recipe.get("applies_to") or {}
    pats: list[str] = []
    if "host_pattern" in applies:
        pats.append(str(applies["host_pattern"]))
    if "host_patterns" in applies:
        pats.extend(str(p) for p in applies["host_patterns"])
    return pats, bool(applies.get("include_subdomains", False))


def capture_recipe_for_url(corpus_root: Path, url: str) -> dict[str, Any] | None:
    """Return the most-specific recipe matching `url`'s origin, or None.

    Match predicate mirrors `schemas.origin_overlays_for_uris`: each recipe's
    `applies_to.host_pattern(s)` is tested with `urls.same_domain` (apex↔www
    aware) honoring `include_subdomains`. `host_pattern: "*"` is a catch-all
    (lowest priority). Ties break toward the longest pattern (most specific),
    then path order — deterministic.
    """
    matches: list[tuple[int, str, dict[str, Any]]] = []
    for relpath, recipe in _load_all(corpus_root):
        patterns, include_subdomains = _patterns(recipe)
        for pattern in patterns:
            if pattern == "*":
                matches.append((0, relpath, recipe))
                break
            if urlcanon.same_domain(url, pattern, include_subdomains=include_subdomains):
                matches.append((len(pattern), relpath, recipe))
                break
    if not matches:
        return None
    matches.sort(key=lambda m: (m[0], m[1]), reverse=True)
    return matches[0][2]
