"""Deterministic classification-candidate matcher.

Walks every interpretive overlay declared by the corpus (composite namespaces),
evaluates each against a record on two axes — MIME and body cues — and returns a
ranked list of candidates labelled by match basis. The normalizer consumes this list
(via `corpus diagnose`) as its authoritative discovery, removing the need to
enumerate the schema directory or read overlay yamls before deciding which to apply.

See spec/corpus.md §7 for the overlay structure (`applies_to` / `cues` /
`content_types` / subclasses).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import frontmatter

from . import records, schemas

# Match basis labels — also serve as sort keys (mime+cue first, then cue-only, then
# mime-only, then no-axes/shape-based).
Basis = Literal["mime+cue", "cue-only", "mime-only", "shape-based"]
_BASIS_ORDER: dict[str, int] = {
    "mime+cue": 0,
    "cue-only": 1,
    "mime-only": 2,
    "shape-based": 3,
}


@dataclass
class Candidate:
    """One classification overlay that plausibly applies to a record.

    `overlay_id` is the namespaced classification id ready to pass to
    `corpus classify` (e.g. `4c/methodology` or bare `article`).
    """

    overlay_id: str
    basis: Basis
    matched_cues: list[str] = field(default_factory=list)
    matched_mime: str | None = None
    declared_cues: int = 0
    declared_mime_patterns: int = 0
    extended_fields: list[str] = field(default_factory=list)


def candidates(post: frontmatter.Post, corpus_root: Path) -> list[Candidate]:
    """Return classification candidates for a record, sorted strong→weak.

    Discovery scope: every overlay returned by
    `schemas.interpretive_classifications_for(corpus_root)`, plus each declared
    subclass. Match axes:

    - **cues**: `applies_to.cues.body_contains` — case-insensitive substring match
      against the record's combined segment-text body.
    - **mime**: `applies_to.content_types` — exact or family-prefix match against
      `records.media_type_for(post)`.

    Bucket assignment:

    - `mime+cue` — both axes declared AND both matched.
    - `cue-only` — cues declared and matched; mime either undeclared or didn't.
    - `mime-only` — mime declared and matched; cues either undeclared or didn't.

    Overlays where neither axis matched (regardless of what was declared) are not
    returned. Subclasses surface as separate candidates; when a subclass matches,
    the bare namespace is not separately surfaced.
    """
    body_text = _record_body_text(post)
    record_mime = records.media_type_for(post)
    title = records.title_for(post) or ""

    found: list[Candidate] = []
    for namespace_id, schema in schemas.interpretive_classifications_for(corpus_root):
        ns_applies = (schema.get("applies_to") or {}) if isinstance(schema, dict) else {}
        ns_fields = list((schema.get("extended_fields") or {}).keys())

        ns_cue_decl, ns_cue_hits = _eval_cues(ns_applies, body_text)
        ns_mime_decl, ns_mime_match = _eval_mime(ns_applies, record_mime)

        subclasses = schemas.iter_classification_subclasses(corpus_root, namespace_id)
        emitted_any_subclass = False
        for sub_id, sub_schema in subclasses:
            sub_applies = (
                (sub_schema.get("applies_to") or {}) if isinstance(sub_schema, dict) else {}
            )
            # `cues.excludes` (the subclass's own OR the namespace's, inherited) suppresses
            # the candidate entirely — lets a sibling genre that shares vocabulary disqualify
            # the wrong overlay (spec §7.4 cues). Checked before scoring the axes.
            if _excluded(sub_applies, body_text, title) or _excluded(ns_applies, body_text, title):
                continue
            sub_cue_decl, sub_cue_hits = _eval_cues(sub_applies, body_text)
            sub_mime_decl, sub_mime_match = _eval_mime(sub_applies, record_mime)

            # Subclass inherits from namespace when its own axis isn't declared.
            cue_decl = sub_cue_decl or ns_cue_decl
            cue_hits = sub_cue_hits if sub_cue_decl else ns_cue_hits
            mime_decl = sub_mime_decl or ns_mime_decl
            mime_match = sub_mime_match if sub_mime_decl else ns_mime_match

            basis = _basis_for(cue_decl, cue_hits, mime_decl, mime_match)
            if basis is None:
                continue
            sub_fields = (
                list((sub_schema.get("extended_fields") or {}).keys())
                if isinstance(sub_schema, dict)
                else []
            )
            found.append(
                Candidate(
                    overlay_id=f"{namespace_id}/{sub_id}",
                    basis=basis,
                    matched_cues=cue_hits,
                    matched_mime=mime_match,
                    declared_cues=cue_decl,
                    declared_mime_patterns=mime_decl,
                    extended_fields=ns_fields + sub_fields,
                )
            )
            emitted_any_subclass = True

        if not emitted_any_subclass:
            if _excluded(ns_applies, body_text, title):
                continue
            basis = _basis_for(ns_cue_decl, ns_cue_hits, ns_mime_decl, ns_mime_match)
            if basis is None:
                continue
            found.append(
                Candidate(
                    overlay_id=namespace_id,
                    basis=basis,
                    matched_cues=ns_cue_hits,
                    matched_mime=ns_mime_match,
                    declared_cues=ns_cue_decl,
                    declared_mime_patterns=ns_mime_decl,
                    extended_fields=ns_fields,
                )
            )

    found.sort(key=lambda c: (_BASIS_ORDER[c.basis], -len(c.matched_cues), c.overlay_id))
    return found


# ---------- axis evaluators ---------- #


def _eval_cues(applies_to: dict[str, Any], body_text: str) -> tuple[int, list[str]]:
    """Return `(declared_count, matched_cues)` for the cues axis."""
    cues = applies_to.get("cues") or {}
    if not isinstance(cues, dict):
        return 0, []
    declared = cues.get("body_contains") or []
    if not isinstance(declared, list):
        return 0, []
    body_l = body_text.lower()
    hits = [
        str(phrase)
        for phrase in declared
        if isinstance(phrase, str) and phrase.lower() in body_l
    ]
    return len(declared), hits


def _eval_mime(applies_to: dict[str, Any], record_mime: str) -> tuple[int, str | None]:
    """Return `(declared_count, matched_pattern_or_None)` for the mime axis."""
    patterns = applies_to.get("content_types") or []
    if not isinstance(patterns, list) or not patterns:
        return 0, None
    rm = (record_mime or "").lower()
    for pat in patterns:
        if not isinstance(pat, str):
            continue
        pat_l = pat.lower()
        if pat_l == rm:
            return len(patterns), pat
        # Family wildcard: "text/*" matches "text/html".
        if pat_l.endswith("/*") and rm.startswith(pat_l[:-1]):
            return len(patterns), pat
    return len(patterns), None


def _excluded(applies_to: dict[str, Any], body_text: str, title: str) -> bool:
    """True if the overlay's `cues.excludes` fire — suppress the candidate.

    A `title_pattern` regex match on the record title, or any `body_contains` substring
    hit, disqualifies the overlay (mirrors the drafter's cue-exclude handling). Lets sibling
    genres that share vocabulary (e.g. a verification report that also contains "VALIDATION
    REPORT") suppress the wrong candidate. A malformed exclude pattern is treated as a
    non-match rather than breaking candidate generation for every record.
    """
    cues = applies_to.get("cues") or {}
    if not isinstance(cues, dict):
        return False
    excl = cues.get("excludes") or {}
    if not isinstance(excl, dict):
        return False
    pat = excl.get("title_pattern")
    if pat and title:
        try:
            if re.search(str(pat), title):
                return True
        except re.error:
            pass
    body_l = body_text.lower()
    for needle in excl.get("body_contains") or []:
        if isinstance(needle, str) and needle.lower() in body_l:
            return True
    return False


def _basis_for(
    cue_decl: int, cue_hits: list[str], mime_decl: int, mime_match: str | None
) -> Basis | None:
    """Categorize an overlay's match result. Returns None if axes declared but no match.

    Treats "axis undeclared" as a free pass — the other axis can carry candidacy on
    its own. Many interpretive overlays declare only one axis.

    `shape-based` covers overlays that declare neither axis (or declare empty axes).
    """
    cue_matched = bool(cue_hits)
    mime_matched = mime_match is not None
    if cue_matched and mime_matched:
        return "mime+cue"
    if cue_matched and not mime_matched:
        return "cue-only"
    if mime_matched and not cue_matched:
        return "mime-only"
    if cue_decl == 0 and mime_decl == 0:
        return "shape-based"
    return None


# ---------- body-text extraction ---------- #


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_BLOCK_RE = re.compile(
    r"<!--(segment|section|embed|artifact|origin|classify|issue)\b[^>]*?-->",
    re.DOTALL,
)
_BODY_TEXT_CAP = 200_000  # ~200 KB of plain text is plenty for cue matching


def _record_body_text(post: frontmatter.Post) -> str:
    """Return the record's combined body text for cue matching.

    Concatenates the text content of every segment block, with HTML tags stripped.
    Caps at ~200KB so very large records (rare) stay cheap to match against.
    """
    body = post.content or ""
    if not body:
        return ""

    pieces: list[str] = []
    total = 0
    last_end = 0
    in_segment = False
    for match in _BLOCK_RE.finditer(body):
        if in_segment:
            chunk = body[last_end : match.start()]
            pieces.append(chunk)
            total += len(chunk)
            if total >= _BODY_TEXT_CAP:
                break
        kind = match.group(1)
        in_segment = kind == "segment"
        last_end = match.end()
    if in_segment and total < _BODY_TEXT_CAP:
        pieces.append(body[last_end:])

    text = "".join(pieces)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text[:_BODY_TEXT_CAP]
