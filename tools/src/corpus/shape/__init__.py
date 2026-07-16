"""Shapers — the deterministic half of the normalize pass (spec §12.5.0, §8.1, 3.0).

A **shaper** reads the origin overlay's `form:` mapping (§7.2) and the form overlay's
decomposition contract (§7.8), consumes derivation ops, and emits the authored content zone
through `recordbuild` — the mechanical case where a declared form makes the shape deterministic
(a conversation's envelopes from a producer's JSON), leaving the agent only the editorial work
(title, description, per-asset descriptions). The `corpus.shape` REGISTRY is the successor of
the 2.x draft `STRATEGY_REGISTRY`; corpus-local shapers load from `<root>/shapers/*.py` via the
same `local_code` loader (the iMessage sub-drafter re-registers here), keyed by form or origin
id so a corpus specializes the shaping of its own content without editing this package.

`shape_record` is the dispatch: it finds the record's declared form (its origin overlay's
`form:` key), looks up the shaper, builds the content zone, and appends the
`<pkg>.shape.<form-id>@<v>` touch.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import frontmatter

from corpus import recordbuild, records, schemas, touches

# A shaper: (build, post, corpus_root, mapping) → None. It populates `build` (the content zone)
# through the recordbuild ops; the caller `finish`es it and stamps the touch.
ShaperFn = Callable[[recordbuild.Build, frontmatter.Post, Path, dict[str, Any]], None]

REGISTRY: dict[str, ShaperFn] = {}


def register_shaper(key: str) -> Callable[[ShaperFn], ShaperFn]:
    """Register a shaper keyed on a form id (`conversation`) or an origin id. Form-id keys
    serve every origin that maps onto the form via its `form.mapping`; origin-id keys let a
    corpus specialize one producer's shaping."""

    def decorator(fn: ShaperFn) -> ShaperFn:
        if key in REGISTRY:
            raise ValueError(f"shaper already registered for {key!r}")
        REGISTRY[key] = fn
        return fn

    return decorator


def get_shaper(key: str) -> ShaperFn | None:
    """Look up the shaper for a form id or origin id."""
    return REGISTRY.get(key)


def form_for_record(
    post: frontmatter.Post, corpus_root: Path
) -> tuple[str, str, dict[str, Any]] | None:
    """The `(origin_id, form_id, mapping)` the record's origin overlay declares via its `form:`
    key (§7.2), or None. Walks the record's qualified origin blocks, loading each overlay, and
    returns the first that declares a form. The origin id is returned so an origin-keyed shaper
    can be preferred over the generic form-keyed one."""
    for origin in records.iter_origin_blocks(post):
        oid = str(origin.get("id") or "")
        if not oid:
            continue
        overlay = schemas.load_origin_overlay_by_id(corpus_root, oid)
        form = (overlay or {}).get("form")
        if isinstance(form, dict) and form.get("id"):
            mapping = form.get("mapping") if isinstance(form.get("mapping"), dict) else {}
            return oid, str(form["id"]), dict(mapping)
    return None


def declared_form_unmet(post: frontmatter.Post, corpus_root: Path) -> str | None:
    """The "formed where declared" half of the pass gate (spec §8.5, §4.4.6): when the
    record's origin overlay declares a form (`form_for_record`) but no section in the
    content zone carries that form id, return the declared form id — the gate's refusal
    detail. Returns None when either no form is declared, or the declared form IS present
    (nothing to refuse on this half; form-coherence lint separately checks that a STAMPED
    section actually conforms — this only checks that a DECLARED one was stamped at all)."""
    resolved = form_for_record(post, corpus_root)
    if resolved is None:
        return None
    _, form_id, _ = resolved
    from corpus import segments as _segments

    blocks = _segments.iter_blocks(post.content or "")
    if any(isinstance(b, _segments.Section) and b.form == form_id for b in blocks):
        return None
    return form_id


def shape_record(post: frontmatter.Post, corpus_root: Path) -> bool:
    """Shape `post`'s content zone in place if a declared form + registered shaper apply;
    return True when shaped. Loads corpus-local shapers first, resolves the record's form,
    prefers an origin-id-keyed shaper over the form-id-keyed one, builds the content zone via
    `recordbuild`, grammar-validates it, and appends the `shape.<form-id>` touch. Shaping is
    only half the normalize pass (§8.1) — it does NOT author the vouch (the editorial fields
    are the interpretive agent's remaining work; the queue's `finalize` gates on both, §8.5)."""
    from corpus import local_code

    local_code.load_corpus_modules(corpus_root, "shapers")
    resolved = form_for_record(post, corpus_root)
    if resolved is None:
        return False
    origin_id, form_id, mapping = resolved
    shaper = get_shaper(origin_id) or get_shaper(form_id)
    if shaper is None:
        return False

    build = recordbuild.begin_from_post(post, corpus_root)
    shaper(build, post, corpus_root, mapping)
    recordbuild.finish(build)
    touches.record_touch(post, touches.script_identifier(f"shape.{form_id}"))
    return True


# Import the bundled shapers so they self-register.
from corpus.shape import conversation as _conversation  # noqa: E402, F401
