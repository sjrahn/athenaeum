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

import re
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


def _origin_primary_uri(origin: dict[str, Any]) -> str | None:
    """The block's PRIMARY `uri:` value — the first entry, the capture's identity URI.
    Dedup-folded aliases are deliberately not exposed to route matching (§7.2): aliases
    are not gate-grade route evidence."""
    uri = (origin.get("fields") or {}).get("uri")
    uris = uri if isinstance(uri, list) else ([uri] if uri else [])
    for u in uris:
        if u:
            return str(u).strip()
    return None


def _route_rule_matches(rule: dict[str, Any], primary_uri: str | None) -> bool:
    """A route rule matches when its `match` regex (unanchored `re.search`) hits the
    block's primary URI; a rule with no `match` key matches everything (terminal
    fallback). A malformed regex is treated as non-matching rather than raised (§7.2,
    parse tolerantly)."""
    pattern = rule.get("match")
    if pattern is None:
        return True
    if primary_uri is None:
        return False
    try:
        compiled = re.compile(str(pattern))
    except re.error:
        return False
    return compiled.search(primary_uri) is not None


def form_for_record(
    post: frontmatter.Post, corpus_root: Path
) -> tuple[str, str, dict[str, Any]] | None:
    """The `(origin_id, form_id, mapping)` the record's origin overlay declares via its `form:`
    key (§7.2), or None. Walks the record's qualified origin blocks, loading each overlay, and
    returns the first that declares a form. The origin id is returned so an origin-keyed shaper
    can be preferred over the generic form-keyed one.

    `form:` is either the single declaration `{id, mapping?}` or, for a multi-shape origin
    (3.2 additive), a **list of route rules** `{match?, id, mapping?}` tried in declaration
    order — the first rule whose `match` regex hits the block's PRIMARY `uri:` value (the
    first entry; alias URIs are not gate-grade evidence, §7.2) is the declaration (a rule
    missing `match` matches everything). A rule missing `id` is skipped. A block matching
    no rule stands as if `form:` were absent — the walk continues to the record's next
    qualified origin block rather than returning None early. A `form:` value that is
    neither a dict nor a list is ignored (treated as absent)."""
    for origin in records.iter_origin_blocks(post):
        oid = str(origin.get("id") or "")
        if not oid:
            continue
        overlay = schemas.load_origin_overlay_by_id(corpus_root, oid)
        form = (overlay or {}).get("form")
        if isinstance(form, dict) and form.get("id"):
            mapping = form.get("mapping") if isinstance(form.get("mapping"), dict) else {}
            return oid, str(form["id"]), dict(mapping)
        if isinstance(form, list):
            primary_uri = _origin_primary_uri(origin)
            for rule in form:
                if not isinstance(rule, dict) or not rule.get("id"):
                    continue
                if _route_rule_matches(rule, primary_uri):
                    mapping = rule.get("mapping") if isinstance(rule.get("mapping"), dict) else {}
                    return oid, str(rule["id"]), dict(mapping)
            # No rule matched: this block stands as if `form:` were absent — fall through
            # to the record's next qualified origin block rather than returning None here.
    return None


def declared_form_unmet(post: frontmatter.Post, corpus_root: Path) -> str | None:
    """The "formed where declared" half of the pass gate (spec §8.5, §4.4.6): when the
    record's origin overlay declares a form (`form_for_record`) but no section in the
    content zone carries that form id, return the declared form id — the gate's refusal
    detail. Returns None when either no form is declared, or the declared form IS present
    (nothing to refuse on this half; form-coherence lint separately checks that a STAMPED
    section actually conforms — this only checks that a DECLARED one was stamped at all).

    *(3.3)* A declared TERMINAL contract (`schemas.is_terminal_form`) satisfies this half
    trivially and unconditionally — it prescribes the ABSENCE of a stored rendering, so
    "no section carries it" is the contract's normal, correct state, never a refusal
    (§7.8, §8.5: a terminal record's pass gate is trivially met)."""
    resolved = form_for_record(post, corpus_root)
    if resolved is None:
        return None
    _, form_id, _ = resolved
    if schemas.is_terminal_form(corpus_root, form_id):
        return None
    from corpus import segments as _segments

    blocks = _segments.iter_blocks(post.content or "")
    if any(isinstance(b, _segments.Section) and b.form == form_id for b in blocks):
        return None
    return form_id


def _whole_record_form(post: frontmatter.Post) -> str | None:
    """The form id of the record's whole-record section (spec §4.3.2.1: a qualified section
    with no `address`), or None. A local re-derivation of `records._whole_record_section`'s
    predicate (kept local rather than reaching into that private helper) so this module's
    governing-contract resolution stays a pure function of `segments.iter_blocks`."""
    from corpus import segments as _segments

    try:
        blocks = _segments.iter_blocks(post.content or "")
    except Exception:
        return None
    for blk in blocks:
        if isinstance(blk, _segments.Section) and blk.form and blk.address is None:
            return blk.form
    return None


def governing_form(
    post: frontmatter.Post, corpus_root: Path
) -> tuple[str, bool] | None:
    """Resolve the record's GOVERNING CONTRACT (spec §7.8, §4.1, 3.3) — `(form_id,
    is_terminal)` — or None when the record stands under the zeroth form (genuinely
    formless, no contract governs it). Precedence, most specific first:

    (a) the origin overlay's `form:` declaration (`form_for_record`, §7.2) — may name a
        rendering contract or a terminal one — a producer-level policy decision, so it
        outranks even the record's own asserted content;
    (b) *(fix, 3.3)* the record's own ASSERTED whole-record section (§4.3.2.1,
        §4.4.6) — whether terminal or a rendering contract, and regardless of what a
        class-level mime default would otherwise say. This step is not in the dispatch's
        original (a)(b)(c)(d) reading (which put the asserted-section check LAST and
        terminal-only) — moving it here and widening it to any form id is a correction
        this implementation made after real corpus-private data surfaced the collision:
        a promoted `video/h264` track already carries an asserted whole-record
        `slide-deck` section (72 real segments, the §12.20 presentation-video pilot).
        Declaring a mime-level `form: {id: passthrough}}` default on `video/h264` (as this
        addendum does) would otherwise make step (c) below win for EVERY h264 track,
        silently ignoring that one record's genuine `slide-deck` shape and making the new
        `terminal-stored-rendering` lint rule fire a false error against it. A record's
        own already-stamped judgment is more specific than a format-wide class default
        and must win over it, exactly as (a) already wins over (c)/(d);
    (c) the mime schema's `form:` default (§7.1) — terminal contracts only
        (`schemas.resolve_mime_terminal_form` tolerantly rejects a rendering-contract id);
    (d) the derivation: a resolved `disposition: manifest` (§1.2,
        `schemas.resolved_disposition_for_record`) with no rendering contract declared by
        (a)/(b)/(c) AND at least one attested member embed stands under `form/manifest` —
        the disposition already IS the terminal judgment (§7.8), no overlay edit required.
        The embed requirement matters: a mime schema's disposition is a class-level default
        (§1.2 — "always stamped ... never sniffed per record"), but a bare promoted-member
        stub (`corpus promote`, §8.1) shares that same mime WITHOUT ever having run the
        member-manifest attestation over its own bytes — it has no roster yet (`form/manifest`
        conformance binds "the attested member embeds," and there are none to bind). Such a
        stub stands formless-for-now (`proxy`), correctly, until it earns its own rendering
        contract — not swept into `terminal` by a class default it hasn't actually attested
        (concretely: a `text/vcard` mime schema's manifest disposition would otherwise sweep
        every promoted single-card stub into `terminal`, though real corpus measurement
        against the private hub is what surfaced this — §12.23's own inventory calls out
        "promoted vcard cards" as a population that stays `proxy`).

    *(fix, 3.3)* Neither class-level default — (c) nor (d) — applies to a record that
    ALREADY carries a stored rendering (`records.has_stored_rendering`), even top-level,
    formless, pre-form-axis content with no form-section wrapper (the ordinary `rendered`
    state, §4.1/§12.19). A class default asserts "no markdown shape will ever render these
    bytes more faithfully" — a judgment such a record visibly contradicts by already
    carrying one. Real corpus-private data forced this too: several `image/jpeg`/`image/png`
    records already carry top-level OCR/document segments (image.yaml's own "primarily a
    document" guidance) with no wrapping section — declaring a mime-level passthrough
    default on stills must not retroactively turn their genuine rendered content into a
    `terminal-stored-rendering` lint violation. (a) and (b) are unaffected by this guard —
    an explicit declaration or the record's own asserted judgment always wins regardless of
    existing content; only the two class-level fallbacks defer to demonstrated reality.

    Terminality is read off the `terminal: true` overlay marker (`schemas.is_terminal_form`)
    at every step — never a hardcoded form id, so a corpus's own terminal contract
    participates identically."""
    declared = form_for_record(post, corpus_root)
    if declared is not None:
        _, form_id, _ = declared
        return form_id, schemas.is_terminal_form(corpus_root, form_id)

    whole_record_form = _whole_record_form(post)
    if whole_record_form:
        return whole_record_form, schemas.is_terminal_form(corpus_root, whole_record_form)

    if records.has_stored_rendering(post):
        return None

    mime = records.media_type_for(post)
    if mime:
        mime_form = schemas.resolve_mime_terminal_form(corpus_root, mime)
        if mime_form is not None:
            return mime_form, True

    if schemas.resolved_disposition_for_record(corpus_root, post) == "manifest" and any(
        True for _ in records.iter_embed_blocks(post)
    ):
        return "manifest", True

    return None


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
from corpus.shape import contact_card as _contact_card  # noqa: E402, F401
from corpus.shape import conversation as _conversation  # noqa: E402, F401
