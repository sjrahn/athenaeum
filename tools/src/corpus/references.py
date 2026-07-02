"""Overlay-declared dependent references (spec §7.2 `capture.references`, §4.3.3.3).

A host's origin overlay can declare which of a captured page's outbound links are
*dependent reference material* — the few links that are part of the thing being captured
far more than the rest (a product-detail page's product manual, a spec sheet). This
module is the single home for that declaration:

- `parse_rules` / `rules_for_url` — read the overlay's `capture.references` list into
  typed `ReferenceRule`s (the reader half of spec §7.2).
- `match` — apply the rules to a captured HTML document, yielding the dependent links
  (resolved + normalized, deduped) the rest of the pipeline acts on.
- `emit_overlay_references` — the draft-stage emission: turn the matches into
  `provenance: auto` `reference` context blocks on the record (spec §4.3.3.3) at tier 2
  (`source_url`). It reads no corpus state and never writes tier-3 `source_uri`: whether
  a target is itself a record is a read-time edge (`derived_views.references`), so `draft`
  stays a pure function of the artifact.

The *fetch* of a dependent target (`capture: true` / `corpus capture --with-references`
/ `corpus crawl --references`) is a capture-side concern and lives there; this module
only declares, matches, and emits. Tolerant throughout: a malformed rule or a bad regex
is skipped, never fatal (spec design principle — parse tolerantly).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import records, urls

log = logging.getLogger("corpus.references")

# Match keys a rule may carry; at least one is required for the rule to be usable.
_MATCH_KEYS = ("selector", "href_pattern", "text_pattern", "rel")
_CROSS_HOST = ("allow", "same")


@dataclass(frozen=True)
class ReferenceRule:
    """One `capture.references` rule. The `match` keys present are ANDed; rules are ORed
    across the list. `role` labels the emitted reference; `capture` opts the target into
    the capture-side depth-1 auto-grab; `cross_host` bounds which hosts a match may reach
    (`allow` — the default, since manuals are off-host — vs `same`, host-restricted)."""

    selector: str | None = None
    href_pattern: str | None = None
    text_pattern: str | None = None
    rel: str | None = None
    role: str | None = None
    capture: bool = False
    cross_host: str = "allow"


@dataclass(frozen=True)
class MatchedReference:
    """A declared dependent link found in a document: the resolved + normalized `url`,
    the `text` of the anchor (tier-1 `attribution_text`), and the originating rule's
    `role` / `capture`."""

    url: str
    text: str
    role: str | None
    capture: bool


def parse_rules(cfg: Any) -> list[ReferenceRule]:
    """Parse an overlay's `capture.references` value into `ReferenceRule`s.

    Accepts the list-of-mappings form. Tolerant: a non-list, a non-mapping entry, an
    entry with no recognized match key, or a bad `cross_host` value is skipped with a
    debug log rather than raising — a typo in one host's overlay must not break drafting
    the whole corpus.
    """
    if not isinstance(cfg, list):
        if cfg is not None:
            log.debug("capture.references is not a list, ignoring: %r", type(cfg).__name__)
        return []
    rules: list[ReferenceRule] = []
    for raw in cfg:
        if not isinstance(raw, dict):
            log.debug("skipping non-mapping references rule: %r", raw)
            continue
        match = raw.get("match")
        match = match if isinstance(match, dict) else raw  # allow flat rules too
        keys = {k: match.get(k) for k in _MATCH_KEYS if match.get(k)}
        if not keys:
            log.debug("skipping references rule with no match key: %r", raw)
            continue
        cross_host = str(raw.get("cross_host", "allow")).strip().lower() or "allow"
        if cross_host not in _CROSS_HOST:
            log.debug("invalid cross_host %r, defaulting to allow", cross_host)
            cross_host = "allow"
        rules.append(
            ReferenceRule(
                selector=keys.get("selector"),
                href_pattern=keys.get("href_pattern"),
                text_pattern=keys.get("text_pattern"),
                rel=keys.get("rel"),
                role=(str(raw["role"]).strip() if raw.get("role") else None),
                capture=bool(raw.get("capture", False)),
                cross_host=cross_host,
            )
        )
    return rules


def rules_for_url(corpus_root: Path, url: str) -> list[ReferenceRule]:
    """Load the `capture.references` rules for `url`'s host from its origin overlay, or
    `[]`. Mirrors the other per-host overlay accessors (`recipes.*_for_url`)."""
    from .capture import recipes

    cap = recipes.capture_recipe_for_url(corpus_root, url) or {}
    return parse_rules(cap.get("references"))


def _compile(pattern: str | None) -> re.Pattern[str] | None:
    if not pattern:
        return None
    try:
        return re.compile(pattern)
    except re.error as exc:
        log.debug("bad reference regex %r: %s", pattern, exc)
        return None


def _rel_tokens(anchor: Any) -> set[str]:
    rel = anchor.get("rel")
    if isinstance(rel, list):
        return {str(t).lower() for t in rel}
    if rel:
        return {t.lower() for t in str(rel).split()}
    return set()


def _rule_anchors(soup: BeautifulSoup, rule: ReferenceRule) -> list[Any]:
    """Candidate anchors for a rule: the CSS-selected elements that carry an `href`
    (the selector is expected to target the `<a>`), else every `<a href>`."""
    if rule.selector:
        try:
            selected = soup.select(rule.selector)
        except Exception as exc:  # invalid selector — skip the rule, don't crash drafting
            log.debug("bad reference selector %r: %s", rule.selector, exc)
            return []
        return [el for el in selected if el.has_attr("href")]
    return list(soup.find_all("a", href=True))


def match(
    html: str,
    base_url: str,
    rules: list[ReferenceRule],
    *,
    primary_host: str | None = None,
) -> list[MatchedReference]:
    """Apply `rules` to `html`, returning the matched dependent links — resolved against
    `base_url`, normalized (`urls.normalize`), and **deduped by URL** (DOM order, first
    rule wins for `role`/`capture`/`cross_host`).

    Within a rule the present match keys are ANDed (`href_pattern`/`text_pattern` are
    `re.search`; `rel` is token membership; `selector` scopes the candidate anchors);
    rules are ORed. A rule's `cross_host: same` drops matches whose host is not
    `primary_host` (apex↔www aware); `allow` keeps them.
    """
    if not rules:
        return []
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[MatchedReference] = []
    for rule in rules:
        href_re = _compile(rule.href_pattern)
        text_re = _compile(rule.text_pattern)
        if rule.href_pattern and href_re is None:
            continue  # an unusable pattern can't match — skip the whole rule
        if rule.text_pattern and text_re is None:
            continue
        rel_want = rule.rel.lower() if rule.rel else None
        for anchor in _rule_anchors(soup, rule):
            href = (anchor.get("href") or "").strip()
            if not href or not urls.is_crawlable_href(href):
                continue
            resolved = urljoin(base_url, href)
            if href_re is not None and not href_re.search(resolved):
                continue
            text = anchor.get_text(" ", strip=True)
            if text_re is not None and not text_re.search(text):
                continue
            if rel_want is not None and rel_want not in _rel_tokens(anchor):
                continue
            url = urls.normalize(resolved)
            if (
                rule.cross_host == "same"
                and primary_host
                and not urls.same_domain(url, primary_host)
            ):
                continue
            if url in seen:
                continue
            seen.add(url)
            out.append(
                MatchedReference(
                    url=url,
                    text=text,
                    role=rule.role,
                    capture=rule.capture,
                )
            )
    return out


def matches_for_record(
    corpus_root: Path,
    post: Any,
    html: str,
) -> list[MatchedReference]:
    """The declared dependent links for a record: its host's rules applied to `html`,
    resolved against the record's primary origin URI, excluding self-links (the record's
    own origin URIs). The shared entry point for draft emission, `corpus links
    --references`, and the capture-side auto-grab."""
    base_url = records.primary_origin_uri(post)
    if not base_url:
        return []
    rules = rules_for_url(corpus_root, base_url)
    if not rules:
        return []
    found = match(html, base_url, rules, primary_host=urls.host_of(base_url))
    if not found:
        return []
    own = {urls.normalize(u) for u in records.iter_origin_uris(post)}
    return [m for m in found if m.url not in own]


def _reference_fields(m: MatchedReference) -> dict[str, Any]:
    """Assemble a mechanical `reference` context block's fields (spec §4.3.3.3): the
    `provenance: auto` marker, the rule's `role`, and the citation ladder up to tier 2 —
    tier-1 `attribution_text` (the link text) + tier-2 `source_url` (the resolved href).

    The mechanical drafter stops here. It NEVER writes tier-3 `source_uri`: "which record,
    if any, that URL is" is a read-time resolution of `source_url` (derived_views.references),
    not draft output — so `draft` stays a pure function of the artifact (it reads no corpus
    state) and the edge self-heals as the corpus changes instead of dangling under removal."""
    fields: dict[str, Any] = {"provenance": "auto"}
    if m.role:
        fields["role"] = m.role
    if m.text:
        fields["attribution_text"] = m.text
    fields["source_url"] = m.url
    return fields


def emit_overlay_references(post: Any, corpus_root: Path, html_path: Path) -> int:
    """Emit one `provenance: auto` `reference` context block per declared dependent link
    onto `post` (spec §4.3.3.3). Draft-stage only and HTML-only — the caller guards on
    media type. Each reference is record-scoped (no segment anchor in v1; the link's
    containing region is often un-segmented chrome) and stops at tier 2 (`source_url`).
    Returns the number emitted.

    **Pure.** Draft reads no corpus state — no `find_by_uri`, no tier-3 `source_uri` baked
    in. Whether a target URL is itself a record is a read-time derived edge over the durable
    `source_url` (`derived_views.references` / `corpus links --references`), so the same
    artifact always drafts to the same bytes regardless of what else the corpus holds (the
    line `draft` must not cross — spec §4.3.3.3, §8.2). The own-URI exclusion is already
    applied during matching (`matches_for_record`).

    Idempotent by construction: `corpus draft` runs only on a clean stub (and `redraft`
    re-stubs first, clearing context blocks), so this appends to a record that holds no
    prior reference blocks — there is nothing to overwrite, and an asserted (normalizer)
    reference added in a later normalize pass is untouched until the next re-stub.
    """
    try:
        html = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.debug("cannot read artifact for references: %s", exc)
        return 0
    found = matches_for_record(corpus_root, post, html)
    if not found:
        return 0
    for m in found:
        records.append_context_block(
            post,
            namespace="reference",
            id="reference",
            fields=_reference_fields(m),
        )
    return len(found)


# ---------- capture-side depth-1 auto-grab (spec §7.2 `capture: true`) ---------- #


def select_for_capture(
    matches: list[MatchedReference], *, force: bool | None
) -> list[MatchedReference]:
    """Which matched references to fetch. `force=True` (`--with-references`) grabs all;
    `force=False` (`--no-references`) grabs none; `force=None` (default) honors each
    rule's own `capture:` flag."""
    if force is True:
        return list(matches)
    if force is False:
        return []
    return [m for m in matches if m.capture]


@dataclass
class GrabResult:
    """Outcome of a depth-1 reference grab: which targets were `selected`, newly
    `captured` (url → new record id), already `existing` (deduped, not refetched),
    `failed` (url → reason), and whether this was a `dry_run`."""

    selected: list[str]
    captured: list[tuple[str, str]]
    existing: list[str]
    failed: list[tuple[str, str]]
    dry_run: bool


def fetch_references(
    corpus_root: Path,
    post: Any,
    html: str,
    *,
    force: bool | None = None,
    opts: Any = None,
    dry_run: bool = False,
) -> GrabResult:
    """Capture-side **depth-1** auto-grab of a record's declared dependent references
    (spec §7.2): fetch each selected target once as its own record, content-hash deduped.

    Depth is fixed at 1 — a grabbed target is ingested as a stub and never expanded;
    multi-hop following is `corpus crawl`'s job (spec §11). Already-captured targets are
    skipped via `find_by_uri` (so a re-capture of the page never refetches an unchanged
    manual). `cross_host` is already enforced during matching. Best-effort: a per-target
    capture failure is recorded, not raised.
    """
    from .capture import CaptureError, capture_and_ingest

    selected = select_for_capture(matches_for_record(corpus_root, post, html), force=force)
    # Build the URI index once for the whole grab, not once per target's dedup check.
    index = records.build_uri_index(corpus_root) if selected else None
    captured: list[tuple[str, str]] = []
    existing: list[str] = []
    failed: list[tuple[str, str]] = []
    for m in selected:
        if records.find_by_uri(m.url, corpus_root=corpus_root, index=index):
            existing.append(m.url)
            continue
        if dry_run:
            continue
        try:
            path = capture_and_ingest(m.url, corpus_root=corpus_root, opts=opts)
        except CaptureError as exc:
            failed.append((m.url, str(exc)))
            continue
        if path is None:
            failed.append((m.url, "ingest failed"))
            continue
        captured.append((m.url, path.stem))
    return GrabResult(
        selected=[m.url for m in selected],
        captured=captured,
        existing=existing,
        failed=failed,
        dry_run=dry_run,
    )
