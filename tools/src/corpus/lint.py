"""Record validator — pure inspector that surfaces conformance findings.

Every rule reads the in-memory record and yields zero or more `Finding`s. Rules
never mutate the record. The CLI surfaces them to the operator (or the normalizer
agent); persistence of unresolved findings as `<!--issue-->` blocks is the agent's
responsibility, not lint's.

P1 scope — the essential conformance rules. P2/P3 will add the long tail (the
reference has ~30 rules; we ship the load-bearing subset now and grow as needed).

Reconciliations applied:
- #1 — embed rules read embeds from `post.metadata["_embeds"]` (metadata zone), NOT
  off the content `blocks` list.
- #5 — touch regex keeps the `corpus.` prefix (we kept the import package as `corpus`,
  so the reference's regex is correct).
- #6 — segment `perceptual:` is NOT flagged as present-equals-error; the rule instead
  validates the `<algo>:<hex>` shape per spec §7.7 (our spec makes per-atom
  fingerprints normative, where the reference suspended them).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter

from corpus import records as _records
from corpus import schemas as _schemas
from corpus import segments as _segments

VERSION = "0.1.0"


# ---------- Finding ---------- #


@dataclass(frozen=True)
class Finding:
    """One linter result. Frozen so callers can de-dup by identity."""

    rule_id: str
    severity: str  # "error" | "warning" | "info"
    message: str
    subtype: str | None = None
    address: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)


# ---------- regex / constants ---------- #


# Touch identifier shapes (spec §4.2.2):
#   script    corpus.<module>@<version>         e.g. corpus.draft.mime/text/html@0.1.0
#   model     <model-id>[<modifier>]            e.g. claude-opus-4-8[1m]
#   combined  corpus.<module>@<ver>+<model-id>  e.g. corpus.compile@0.1.0+claude-opus-4-8[1m]
#   generic   <tool>@<version>                  third-party tooling
# Each form may carry a trailing `_<N>` dedup counter (consecutive identical passes
# coalesce: ...@0.1.0 → ...@0.1.0_2).
# §4.2.2: an LLM-model touch is the model id "with any context modifier in brackets" —
# the `[<modifier>]` is OPTIONAL, so a bare id (`gpt-4o`, `claude-opus-4-8`) is valid both
# standalone and in the combined `…@<ver>+<model-id>` form.
_TOUCH_MODEL = r"[a-z][\w.\-]*(?:\[\w+\])?"
_TOUCH_SCRIPT = r"corpus\.[a-z0-9_./\-]+@[\w.\-]+"
_TOUCH_GENERIC = r"[\w\-]+@[\w.\-]+"
_TOUCH_RE = re.compile(
    rf"^({_TOUCH_SCRIPT}(\+{_TOUCH_MODEL})?|{_TOUCH_MODEL}|{_TOUCH_GENERIC})(_\d+)?$"
)

_HASH_RE = re.compile(r"^[a-z][a-z0-9_-]*:[0-9a-f]{32,128}$", re.IGNORECASE)
# Perceptual fingerprints (§7.7) are narrower than byte hashes: pHash and simhash are
# 64-bit (16 hex). `transport`/`canonical` are byte hashes (blake3/sha256, ≥128-bit) and
# keep `_HASH_RE`; perceptual values get this 64-bit-floor variant.
_PERCEPTUAL_RE = re.compile(r"^[a-z][a-z0-9_-]*:[0-9a-f]{16,128}$", re.IGNORECASE)
_BLAKE3_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_VALID_ATOMS = {"text", "image", "audio", "video"}
_VALID_VISIBILITIES = {"visible", "deranked", "hidden"}
# Universal FALLBACK vocab for issue severity/resolution. The authoritative set is the
# `enum:` declared on the layered `context/issue` schema (a corpus may extend it); these
# constants apply only when the schema declares no enum. See `_issue_vocab`.
_VALID_SEVERITIES = {"blocking", "warning", "info"}
_VALID_RESOLUTIONS = {"open", "fixed", "wontfix", "superseded"}


# ---------- frontmatter rules ---------- #


def _rule_id_format(post, blocks, root) -> Iterator[Finding]:
    """`id` is exactly a 64-char lowercase blake3 hex (spec §4.2)."""
    rid = post.metadata.get("id")
    if not rid:
        yield Finding(
            rule_id="id-missing",
            severity="error",
            message="frontmatter `id` is missing (spec §4.2).",
        )
        return
    if not isinstance(rid, str) or not _BLAKE3_HEX_RE.match(rid):
        yield Finding(
            rule_id="id-format",
            severity="error",
            message=f"`id` must be 64-char lowercase blake3 hex; got {rid!r}.",
        )


def _rule_legacy_status(post, blocks, root) -> Iterator[Finding]:
    """A record still carrying a frontmatter `status:` key (spec §4.1, §12.19 — retired 3.1).
    Read-tolerant on parse (the key survives in `post.metadata` for exactly this rule to see)
    but never re-emitted: `records.dumps` drops it on the record's next write, so a stray
    is transitional — the migration sweep clears the fleet; after it, this rule catches any
    record that missed the sweep or was hand-edited back in."""
    if "status" not in post.metadata:
        return
    yield Finding(
        rule_id="frontmatter-legacy-status",
        severity="info",
        message=(
            f"frontmatter carries a legacy `status: {post.metadata.get('status')!r}` key "
            f"(spec §4.1) — a 3.0 field, ignored and dropped on the record's next write."
        ),
    )


def _rule_editorial_override_shape(post, blocks, root) -> Iterator[Finding]:
    """*(3.2)* Frontmatter `title:`/`description:` are OPTIONAL overrides of the derived
    editorial pair (spec §4.2.1, §4.2.3), not a required together-vouch — the retired
    `is_authored` strict-AND is gone, and a record carrying exactly one is a legal, lone
    editorial assertion, not a defect. What's still worth flagging: an explicit empty-string
    `''` value, a 3.1-era placeholder (the old required-vouch shape) that `dumps()` now
    drops on the record's next write (spec §12.21) — info, mirroring the
    `frontmatter-legacy-status` precedent. `description` is separately capped at ~600 chars
    (1–3 sentences) when present."""
    for key in ("title", "description"):
        raw = post.metadata.get(key)
        if isinstance(raw, str) and raw == "":
            yield Finding(
                rule_id="editorial-override-placeholder",
                severity="info",
                message=(
                    f"frontmatter `{key}: ''` is a 3.1-era placeholder (spec §12.21) — "
                    f"`dumps()` drops it on the record's next write; safe to ignore or strip."
                ),
            )
    desc = str(post.metadata.get("description") or "").strip()
    if len(desc) > 600:
        yield Finding(
            rule_id="description-too-long",
            severity="warning",
            message=f"`description` is {len(desc)} chars; aim ≤600 (1–3 sentences).",
        )


def _rule_editorial_override_redundant(post, blocks, root) -> Iterator[Finding]:
    """*(3.2, §12.21 step 1)* A frontmatter override whose value EQUALS the record's
    derived value computed WITHOUT the override is noise, not an assertion (spec §4.2.1)."""
    for role in ("title", "description"):
        override = str(post.metadata.get(role) or "").strip()
        if not override:
            continue
        beneath = _records.derived_editorial_field(post, root, role, include_override=False)
        if beneath.value and beneath.value == override:
            yield Finding(
                rule_id="editorial-override-redundant",
                severity="warning",
                message=(
                    f"frontmatter `{role}` override equals the record's derived {role} "
                    f"(layer: {beneath.layer}) — noise, not an assertion (spec §4.2.1); "
                    f"drop the override."
                ),
            )


def _rule_transport_format(post, blocks, root) -> Iterator[Finding]:
    """`transport:` is `<algo>:<hex>` or list thereof (spec §4.2)."""
    raw = post.metadata.get("transport")
    if raw is None:
        return
    values = raw if isinstance(raw, list) else [raw]
    for v in values:
        if not isinstance(v, str) or not _HASH_RE.match(v):
            yield Finding(
                rule_id="transport-format",
                severity="error",
                message=(
                    f"`transport` entry {v!r} is not `<algo>:<hex>` "
                    f"(e.g. `sha256:abc…`, spec §4.2)."
                ),
            )


def _rule_canonical_format(post, blocks, root) -> Iterator[Finding]:
    """`canonical:` is `<algo>:<hex>` or list thereof (spec §4.2)."""
    raw = post.metadata.get("canonical")
    if raw is None:
        return
    values = raw if isinstance(raw, list) else [raw]
    for v in values:
        if not isinstance(v, str) or not _HASH_RE.match(v):
            yield Finding(
                rule_id="canonical-format",
                severity="error",
                message=f"`canonical` entry {v!r} is not `<algo>:<hex>`.",
            )


def _rule_perceptual_format(post, blocks, root) -> Iterator[Finding]:
    """Record-scope `perceptual:` is `<algo>:<hex>` (spec §7.7)."""
    raw = post.metadata.get("perceptual")
    if raw is None:
        return
    values = raw if isinstance(raw, list) else [raw]
    for v in values:
        if not isinstance(v, str) or not _PERCEPTUAL_RE.match(v):
            yield Finding(
                rule_id="perceptual-format",
                severity="error",
                message=f"frontmatter `perceptual` entry {v!r} is not `<algo>:<hex>`.",
            )


def _rule_visibility_invalid(post, blocks, root) -> Iterator[Finding]:
    v = post.metadata.get("visibility")
    if v is None:
        return
    if v not in _VALID_VISIBILITIES:
        yield Finding(
            rule_id="visibility-invalid",
            severity="warning",
            message=(
                f"`visibility` is {v!r}; expected one of {sorted(_VALID_VISIBILITIES)}."
            ),
        )


def _rule_touch_format(post, blocks, root) -> Iterator[Finding]:
    """`touch[]` non-empty and each entry matches the spec §4.2.2 grammar.

    Reconciliation #5: the regex keeps the `corpus.` package prefix — applies because
    the import package is named `corpus`.
    """
    raw = post.metadata.get("touch")
    chain: list[str]
    if raw is None:
        chain = []
    elif isinstance(raw, str):
        chain = [raw]
    elif isinstance(raw, list):
        chain = [str(x) for x in raw]
    else:
        chain = []
    if not chain:
        yield Finding(
            rule_id="touch-empty",
            severity="error",
            message="`touch[]` is empty; every record carries at least an ingest touch.",
        )
        return
    for entry in chain:
        if not _TOUCH_RE.match(entry):
            yield Finding(
                rule_id="touch-format",
                severity="error",
                message=(
                    f"touch entry {entry!r} does not match the grammar "
                    f"`corpus.<module>@<ver>[+<model-id>][_<N>]` or `<model-id>[<mod>]` "
                    f"(spec §4.2.2)."
                ),
            )


# ---------- metadata-zone block rules ---------- #


def _rule_artifact_block_missing(post, blocks, root) -> Iterator[Finding]:
    """Exactly one `<!--artifact-->` block, with a MIME on the opener (spec §4.3.1.1)."""
    artifact = _records.artifact_block(post)
    if not artifact:
        yield Finding(
            rule_id="artifact-block-missing",
            severity="error",
            message="metadata zone is missing the `<!--artifact <mime>-->` block.",
        )
        return
    mime = (artifact.get("mime") or "").strip()
    if not mime or "/" not in mime:
        yield Finding(
            rule_id="artifact-mime-missing",
            severity="error",
            message=(
                f"`<!--artifact-->` opener MIME is {mime!r}; expected `type/subtype` "
                f"(spec §4.3.1.1)."
            ),
        )


def _rule_origins_empty(post, blocks, root) -> Iterator[Finding]:
    """At least one `<!--origin-->` block (spec §4.3.1.2; §8.1 — origin count ≥ 1)."""
    if not list(_records.iter_origin_blocks(post)):
        yield Finding(
            rule_id="origins-empty",
            severity="error",
            message="metadata zone has no `<!--origin-->` blocks (spec §4.3.1.2: ≥1).",
        )


def _rule_origin_uri_shape(post, blocks, root) -> Iterator[Finding]:
    """Each origin block carries a `snapshot:` and a source identity: either a `uri:`
    (a retrieval origin) or local-file metadata (`filename`/`source_modified` — a dropped-in
    file has no retrievable source, spec §7.2). An origin with neither is malformed."""
    for idx, origin in enumerate(_records.iter_origin_blocks(post)):
        fields = origin.get("fields") or {}
        uri = fields.get("uri")
        has_uri = not (
            uri is None
            or (isinstance(uri, list) and not uri)
            or (isinstance(uri, str) and not uri.strip())
        )
        has_local = bool(fields.get("filename") or fields.get("source_modified"))
        if not has_uri and not has_local:
            yield Finding(
                rule_id="origin-without-source",
                severity="error",
                message=(
                    f"origin block #{idx + 1} has neither a `uri:` nor local-file metadata "
                    f"(`filename`/`source_modified`)."
                ),
            )
        if not fields.get("snapshot"):
            yield Finding(
                rule_id="origin-snapshot-missing",
                severity="error",
                message=f"origin block #{idx + 1} missing required `snapshot:`.",
            )


# ---------- embed rules (reconciliation #1 — read from metadata zone) ---------- #


def _rule_embed_format(post, blocks, root) -> Iterator[Finding]:
    """Each `<!--embed-->` block carries `media_type`, `address`, `transport: <algo>:<hex>`.

    Reads embeds via `_records.iter_embed_blocks(post)` — the metadata-zone source —
    NOT off the content `blocks` list. Reconciliation #1.
    """
    for idx, embed in enumerate(_records.iter_embed_blocks(post)):
        mt = (embed.get("media_type") or "").strip()
        if "/" not in mt:
            yield Finding(
                rule_id="embed-mime-missing",
                severity="error",
                message=f"embed #{idx + 1} opener MIME is {mt!r}; expected `type/subtype`.",
            )
        addr = embed.get("address")
        if addr is None or (isinstance(addr, list) and not addr) or (isinstance(addr, str) and not addr.strip()):
            yield Finding(
                rule_id="embed-address-missing",
                severity="error",
                message=f"embed #{idx + 1} missing required `address:`.",
            )
        transport = (embed.get("transport") or "").strip()
        if not _HASH_RE.match(transport):
            yield Finding(
                rule_id="embed-transport-format",
                severity="error",
                message=(
                    f"embed #{idx + 1} `transport: {transport!r}` is not `<algo>:<hex>` "
                    f"(spec §4.3.1.4)."
                ),
            )


# ---------- content-zone (sections/segments) rules ---------- #


def _rule_atom_invalid(post, blocks, root) -> Iterator[Finding]:
    """Every segment's atom is one of {text, image, audio, video} (spec §1.3)."""
    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for seg in blk.segments:
                yield from _check_atom(seg)
        elif isinstance(blk, _segments.Segment):
            yield from _check_atom(blk)


def _check_atom(seg: _segments.Segment) -> Iterator[Finding]:
    if seg.is_structural:  # the fifth kind — a byte-mark, not an atom (§4.3.2.3)
        return
    if seg.atom not in _VALID_ATOMS:
        yield Finding(
            rule_id="atom-invalid",
            severity="error",
            message=(
                f"segment atom is {seg.atom!r}; must be one of {sorted(_VALID_ATOMS)}."
            ),
            address=_addr_str(seg.address),
        )


def _rule_segment_non_text_with_body(post, blocks, root) -> Iterator[Finding]:
    """image/audio/video segments are body-empty positioning markers (spec §4.3.2.2)."""
    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for seg in blk.segments:
                yield from _check_non_text_body(seg)
        elif isinstance(blk, _segments.Segment):
            yield from _check_non_text_body(blk)


def _check_non_text_body(seg: _segments.Segment) -> Iterator[Finding]:
    if seg.atom in ("image", "audio", "video") and seg.body.strip():
        yield Finding(
            rule_id="segment-non-text-with-body",
            severity="error",
            message=(
                f"{seg.atom} segment carries body content; image/audio/video segments "
                f"are body-empty positioning markers (spec §4.3.2.2)."
            ),
            address=_addr_str(seg.address),
        )


def _rule_segment_perceptual_format(post, blocks, root) -> Iterator[Finding]:
    """Reconciliation #6: validate the `<algo>:<hex>` shape per spec §7.7.

    The reference's rule flagged ANY presence of `perceptual:` as an error to remove;
    our spec makes per-atom fingerprints normative. Here we validate the encoding
    when present rather than rejecting presence.
    """
    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for seg in blk.segments:
                yield from _check_perceptual_shape(seg)
        elif isinstance(blk, _segments.Segment):
            yield from _check_perceptual_shape(blk)


def _check_perceptual_shape(seg: _segments.Segment) -> Iterator[Finding]:
    if seg.perceptual is None:
        return
    # §7.6: a perceptual field is `str` OR `list[str]` (multi-region segments). Validate
    # each entry, mirroring the record-scope `_rule_perceptual_format`.
    values = seg.perceptual if isinstance(seg.perceptual, list) else [seg.perceptual]
    for v in values:
        if not isinstance(v, str) or not _PERCEPTUAL_RE.match(v):
            yield Finding(
                rule_id="segment-perceptual-format",
                severity="error",
                message=(
                    f"segment `perceptual: {v!r}` is not `<algo>:<hex>` (spec §7.7)."
                ),
                address=_addr_str(seg.address),
            )


def _rule_section_empty(post, blocks, root) -> Iterator[Finding]:
    for blk in blocks:
        if isinstance(blk, _segments.Section) and not blk.segments:
            yield Finding(
                rule_id="section-empty",
                severity="warning",
                message="section has no child segments.",
                address=_addr_str(blk.address),
            )


def _rule_section_address_span(post, blocks, root) -> Iterator[Finding]:
    """A section's address is the envelope (min-max span) of its child segments' addresses,
    in their discrete-index scheme (spec §4.3.2.1) — the same value `Section.spanning`
    derives at draft time. Skips sections whose scheme has no span strategy: temporal
    (`time_range=`) sections are structurally bounded intervals, not content envelopes."""
    for blk in blocks:
        if not isinstance(blk, _segments.Section) or not blk.segments:
            continue
        if blk.address is None:  # whole-record form section — envelope deliberately omitted
            continue
        expected = _segments.section_address(blk.segments)
        if expected is None or expected == blk.address:
            continue
        yield Finding(
            rule_id="section-address-span",
            severity="warning",
            message=(
                f"section address `{_addr_str(blk.address)}` is not the span of its "
                f"segments (expected `{_addr_str(expected)}`)."
            ),
            address=_addr_str(blk.address),
        )


def _rule_segment_address_duplicate(post, blocks, root) -> Iterator[Finding]:
    """No two segments may claim the same (opener-id, address) pair (spec §4.3.2.2)."""
    seen: dict[tuple[str, str], _segments.Segment] = {}
    for blk in blocks:
        segs = blk.segments if isinstance(blk, _segments.Section) else [blk] if isinstance(blk, _segments.Segment) else []
        for seg in segs:
            opener_id = seg.overlay or seg.atom
            for addr in _addresses(seg.address):
                key = (opener_id, addr)
                if key in seen:
                    yield Finding(
                        rule_id="segment-address-duplicate",
                        severity="error",
                        message=(
                            f"duplicate (opener-id, address) — `{opener_id}` at "
                            f"`{addr}` claimed by two segments."
                        ),
                        address=addr,
                    )
                else:
                    seen[key] = seg


# ---------- annotation-zone (issue) rules ---------- #


def _issue_vocab(root, id_: str) -> tuple[set[str], set[str]]:
    """Allowed (severity, resolution) value sets for an issue id, read from the layered
    `context/issue` schema's `enum:` declarations (spec §4.3.3.1: the vocab is
    schema-declared and corpus-local). Falls back to the universal constants when the
    schema declares no enum."""
    schema = _schemas.load_issue_schema(root, id_) or {}
    ext = schema.get("extended_fields") or {}
    sev = set((ext.get("severity") or {}).get("enum") or ()) or _VALID_SEVERITIES
    res = set((ext.get("resolution") or {}).get("enum") or ()) or _VALID_RESOLUTIONS
    return sev, res


def _rule_issue_shape(post, blocks, root) -> Iterator[Finding]:
    """Reconciliation #2: every `<!--issue-->` block carries the spec §4.3.3.1 shape.

    Required: severity + resolution drawn from the schema-declared vocab (universal default
    {blocking, warning, info} / {open, fixed, wontfix, superseded}, extensible per corpus);
    detector (a touch identifier).
    """
    for idx, issue in enumerate(_records.iter_issue_blocks(post)):
        fields = issue.get("fields") or {}
        valid_sev, valid_res = _issue_vocab(root, str(issue.get("id") or ""))
        sev = fields.get("severity")
        if sev not in valid_sev:
            yield Finding(
                rule_id="issue-severity-invalid",
                severity="error",
                message=(
                    f"issue #{idx + 1} `severity: {sev!r}`; expected one of "
                    f"{sorted(valid_sev)}."
                ),
            )
        res = fields.get("resolution")
        if res not in valid_res:
            yield Finding(
                rule_id="issue-resolution-invalid",
                severity="error",
                message=(
                    f"issue #{idx + 1} `resolution: {res!r}`; expected one of "
                    f"{sorted(valid_res)}."
                ),
            )
        det = fields.get("detector")
        if not isinstance(det, str) or not _TOUCH_RE.match(det):
            yield Finding(
                rule_id="issue-detector-format",
                severity="error",
                message=(
                    f"issue #{idx + 1} `detector: {det!r}` is not a valid touch "
                    f"identifier (spec §4.3.3.1)."
                ),
            )


def _rule_context_shape(post, blocks, root) -> Iterator[Finding]:
    """Every `<!--context <ns>/<id>-->` block's namespace must resolve to a live
    `context/<ns>` overlay (spec §4.3.3), and its `address`/`quote` anchor must be a string."""
    for idx, ctx in enumerate(_records.iter_context_blocks(post)):
        ns = str(ctx.get("namespace") or "")
        fields = ctx.get("fields") or {}
        if not ns or _schemas.load_context_schema(root, ns) is None:
            yield Finding(
                rule_id="context-namespace-unknown",
                severity="warning",
                message=(
                    f"context #{idx + 1} namespace `{ns}` has no `context/{ns}` overlay; "
                    f"declare it under schema/context/{ns}/."
                ),
            )
        for key in ("address", "quote"):
            if key in fields and not isinstance(fields[key], str):
                yield Finding(
                    rule_id="context-anchor-format",
                    severity="warning",
                    message=f"context #{idx + 1} `{key}` must be a string.",
                )


def _rule_classify_retired(post, blocks, root) -> Iterator[Finding]:
    """The classify block was removed in ATH-CORPUS 2.0: what content means is ledger
    knowledge (harvest rules / claims, `ledger.md` §10), never a record assertion. A
    surviving block is a 1.0-era record awaiting migration — flagged, not failed (parse
    stays tolerant; `load`/`dump` round-trip it losslessly).

    A **qualified section opener** is NOT a returning composite: in 3.0 it binds the form
    axis (`form/<id>`, §4.4.1), a structural-shape judgment checkable against the bytes —
    validated by the form-coherence rules, never flagged here."""
    for blk in _records.iter_classify_blocks(post):
        ns = blk.get("namespace") or ""
        cid = blk.get("id") or ""
        qualified = f"{ns}/{cid}" if cid and cid != ns else ns
        yield Finding(
            rule_id="classify-block-retired",
            severity="warning",
            message=(
                f"classify block `{qualified}` is retired (ATH-CORPUS 2.0 §4.3.1.3): "
                f"interpretive classification moved to the ledger. Strip the block; "
                f"assert the knowledge as a ledger concept/claim citing this record."
            ),
            subtype=qualified,
        )


# ---------- normalizer-support rules (luklacloud-intent parity) ---------- #


def _rule_description_too_long(post, blocks, root) -> Iterator[Finding]:
    """An over-long description usually signals interpretation leaking into the summary."""
    desc = (post.metadata.get("description") or "").strip()
    if not desc:
        return
    words = len(desc.split())
    if words > 800:
        yield Finding(
            rule_id="description-too-long",
            severity="warning",
            message=(
                f"description is {words} words; consider tightening (>800 is usually a "
                f"signal of over-detail)."
            ),
            fields={"word_count": words},
        )


def _rule_mime_extension_mismatch(post, blocks, root) -> Iterator[Finding]:
    """The local artifact's extension should match the artifact-block MIME. Only flags when a
    sibling binary of a *different* extension is present (an unhydrated artifact is silent)."""
    from corpus import mime as _mime
    from corpus import paths as _paths
    from corpus import records as _records

    media_type = _records.media_type_for(post)
    record_id = post.metadata.get("id") or ""
    if not media_type or not record_id:
        return
    try:
        ext = _mime.extension_for(media_type)
    except Exception:
        return
    if not ext or ext == "bin":
        return
    expected = _paths.artifact_path(root, record_id, ext)
    if expected.is_file():
        return
    shard_dir = expected.parent
    if not shard_dir.is_dir():
        return
    siblings = list(shard_dir.glob(f"{record_id}.*"))
    found_exts = sorted({s.suffix.lstrip(".") for s in siblings if s.suffix})
    if not siblings or ext in found_exts:
        return
    yield Finding(
        rule_id="mime-extension-mismatch",
        severity="warning",
        message=(
            f"artifact MIME `{media_type}` implies `.{ext}` but the stored artifact is "
            f"`{', '.join('.' + e for e in found_exts)}`."
        ),
        fields={"expected": ext, "found": found_exts},
    )


def _rule_entry_missing(post, blocks, root) -> Iterator[Finding]:
    """PARTIAL authored labeling only (3.0). `entry` on a top-level block is an OPTIONAL
    authored leaf label (§4.3.2.2), and a uniformly bare flat content zone is the default,
    well-formed state (§4.3.2.1) — never flagged. What IS a defect worth surfacing: a
    half-built authored TOC, where some top-level content blocks carry an `entry` and
    others do not — warning, never error. Structural segments are excluded from the count:
    their `entry:` is the source's own mark text, optional by §4.3.2.3, not an authored
    label. A single-content-block record is exempt as before (its own TOC line)."""
    content = [
        (i + 1, blk)
        for i, blk in enumerate(blocks)
        if getattr(blk, "atom", None) != _segments._STRUCTURAL
    ]
    if len(content) <= 1:
        return
    missing = [o for o, blk in content if not (getattr(blk, "entry", None) or "").strip()]
    if not missing or len(missing) == len(content):
        return  # fully labeled, or the uniformly-bare default state — both well-formed
    ords = ", ".join(str(o) for o in missing[:20])
    more = f" (+{len(missing) - 20} more)" if len(missing) > 20 else ""
    yield Finding(
        rule_id="entry-missing",
        severity="warning",
        message=(
            f"{len(missing)} of {len(content)} top-level content blocks are missing `entry` "
            f"while others carry one — a half-built authored TOC. Backfill or clear: "
            f"{ords}{more}."
        ),
        fields={"missing_ordinals": missing[:20]},
    )


def _iter_segments_labelled(blocks):
    for top_i, blk in enumerate(blocks, 1):
        if isinstance(blk, _segments.Section):
            for sub_i, child in enumerate(blk.segments, 1):
                yield f"section {top_i}/segment {sub_i}", child
        elif isinstance(blk, _segments.Segment):
            yield f"segment {top_i}", blk


def _rule_segment_body_lossless_contract(post, blocks, root) -> Iterator[Finding]:
    """Body ⟺ lossless (spec §4.3.2.3). A `text` segment whose atomic overlay opts out of
    lossless (`enables_lossless: false`, e.g. `text/data-table-dynamic`) is a body-empty
    marker — it must carry a `description`, not a transcribed body."""
    # *(3.2, re-keyed off `is_authored`'s retirement)* `is_formed` (not `has_stored_rendering`)
    # is the honest severity signal here: by the time this loop reaches a segment at all, the
    # record necessarily has a stored rendering (the segment IS one) — `has_stored_rendering`
    # would be tautologically true and collapse the info/warning distinction. Under 3.2 the
    # vouch rides the form (§4.1), so a record under a named form contract is the one that
    # shouldn't have gaps (warning); a record still rendering formless/grandfathered content
    # with no governing contract yet is expected to (info).
    formed = _records.is_formed(post)
    for label, seg in _iter_segments_labelled(blocks):
        if seg.atom != "text" or not seg.overlay:
            continue
        atom, _, sub = str(seg.overlay).partition("/")
        overlay = _schemas.load_atomic_overlay(root, atom, sub or atom)
        if not isinstance(overlay, dict) or overlay.get("enables_lossless") is not False:
            continue
        body = (seg.body or "").strip()
        desc = (seg.description or "").strip()
        if body:
            snippet = body if len(body) <= 80 else body[:77] + "…"
            yield Finding(
                rule_id="segment-body-requires-lossless",
                severity="error",
                message=(
                    f"{label} (`{seg.overlay}`) carries a body, but its overlay is non-lossless "
                    f"(`enables_lossless: false`) — it must be a body-empty marker with what the "
                    f"region is in the segment `description`, not a transcription. "
                    f"Body preview: {snippet!r}"
                ),
                address=_addr_str(seg.address),
                fields={"overlay": seg.overlay, "body_chars": len(body)},
            )
        elif not desc:
            yield Finding(
                rule_id="segment-description-required",
                severity="warning" if formed else "info",
                message=(
                    f"{label} (`{seg.overlay}`) is a non-lossless body-empty marker with no "
                    f"`description` — describe what the region is/computes on the segment header."
                ),
                address=_addr_str(seg.address),
                fields={"overlay": seg.overlay},
            )


def _rule_section_description_redundant(post, blocks, root) -> Iterator[Finding]:
    """A SPAN-scope section whose every child segment is lossless does not need a
    `description` — the segments already hold the content faithfully (advisory, info).
    *(3.2)* A WHOLE-RECORD section (no `address`) is exempt: its `description:` header
    field is the record's editorial vouch (spec §4.2.3, §4.3.2.1 — the vouch's home),
    summarizing the whole artifact, never a restatement of what its lossless children
    already hold."""

    def _is_lossless(seg: _segments.Segment) -> bool:
        if seg.atom != "text":
            return False
        if not seg.overlay:
            return True
        atom, _, sub = str(seg.overlay).partition("/")
        overlay = _schemas.load_atomic_overlay(root, atom, sub or atom)
        if not isinstance(overlay, dict):
            return True
        return overlay.get("enables_lossless") is not False

    for top_i, blk in enumerate(blocks, 1):
        if not isinstance(blk, _segments.Section):
            continue
        if blk.address is None:  # whole-record section: the vouch's home (§4.2.3)
            continue
        if not (blk.description or "").strip() or not blk.segments:
            continue
        if all(_is_lossless(child) for child in blk.segments):
            yield Finding(
                rule_id="section-description-redundant",
                severity="info",
                message=(
                    f"section {top_i} (`{_addr_str(blk.address)}`) carries a `description` but "
                    f"every child segment is lossless — the segments already hold the content. A "
                    f"section `description` is for lossy/interpretive sections; drop it here."
                ),
                address=_addr_str(blk.address),
                fields={"segment_count": len(blk.segments)},
            )


def _rule_segment_mode_deprecated(post, blocks, root) -> Iterator[Finding]:
    """v0.3 segments carried a `mode:` header; v1.0 removed it. Re-scan the raw body to
    surface any legacy record that still carries it (inert on a freshly-drafted corpus)."""
    lines = (post.content or "").splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].lstrip()
        if not (stripped.startswith("<!--segment ") or stripped == "<!--segment"):
            i += 1
            continue
        j = i + 1
        while j < len(lines) and lines[j].rstrip() != "-->":
            if re.match(r"\s*mode\s*:", lines[j]):
                yield Finding(
                    rule_id="segment-mode-deprecated",
                    severity="warning",
                    message=(
                        f"segment opener at line {i + 1} carries legacy `{lines[j].strip()}` — "
                        f"the `mode:` field was removed in v1.0; re-draft to drop it."
                    ),
                    fields={"line": i + 1, "raw": lines[j].strip()},
                )
                break
            j += 1
        i = j + 1


# ---------- embeds (metadata zone) ---------- #

_EMBED_ADDRESS_KEYS = {"el", "time", "page", "frame", "time_range"}


def _rule_embed_description_empty_on_normalized(post, blocks, root) -> Iterator[Finding]:
    """An embed carried by a record past the attested-only baseline — carrying a deliberate
    editorial override (spec §4.2.1 — the 3.2 analog of "the vouch is written" for a record
    with no content zone to hold a form-section vouch) or already rendering stored content —
    whose image/audio/video embed has no `description` is missing the normalizer's
    whole-asset summary (info — persist an issue if intentionally undescribed). Unlike the
    3.0 `status == "normalized"` gate (which implied BOTH halves), either half alone is
    enough signal that this embed should have been looked at by now."""
    if not (_records.has_editorial_override(post) or _records.has_stored_rendering(post)):
        return
    for i, eb in enumerate(_records.iter_embed_blocks(post), 1):
        top_type = str(eb.get("media_type") or "").split("/", 1)[0]
        if top_type not in ("image", "audio", "video"):
            continue
        desc = (eb.get("fields") or {}).get("description")
        if isinstance(desc, str) and desc.strip():
            continue
        yield Finding(
            rule_id="embed-description-empty-on-normalized",
            severity="info",
            message=(
                f"embed {i} (`{eb.get('media_type')}` at `{_addr_str(eb.get('address'))}`) carries "
                f"no `description` on a record past the attested-only baseline. Populate the "
                f"whole-asset summary, or persist an issue if the asset is intentionally "
                f"undescribed (chrome, logo)."
            ),
            address=_addr_str(eb.get("address")),
            fields={"media_type": eb.get("media_type")},
        )


def _embed_address_set(post) -> set[str]:
    out: set[str] = set()
    for eb in _records.iter_embed_blocks(post):
        out.update(_addresses(eb.get("address")))
    return out


def _wikilink_addresses(post) -> set[str]:
    from corpus import embeds as _embeds
    from corpus import functional_uri as _furi

    record_id = post.metadata.get("id") or ""
    out: set[str] = set()
    for wk in _embeds.find_wiki_embeds(post.content or ""):
        try:
            parsed = _furi.parse(wk.uri)
        except Exception:
            continue
        if parsed.hash != record_id:
            continue
        for k, v in parsed.params:
            if v is not None:
                out.add(f"{k}={v}")
    return out


def _rule_embed_unreferenced(post, blocks, root) -> Iterator[Finding]:
    """A metadata-zone embed whose address is referenced by no segment and no body wikilink.

    Skipped for a **manifest** record — one with no content-zone segments at all (e.g. a
    self_contained archive recorded as embeds, where each member is an embedded transport).
    There is no content flow to position the embeds within, so they ARE the content, not
    flow-assets, and "unreferenced" is not a defect.

    Also skipped for a **message/rfc822** record: its `part=<N>` embeds are the email's MIME
    members (attachments, inline images, nested messages) declared for promotion, not
    body-flow assets a mechanical draft can position — the normalizer links an inline image
    into the body when it belongs there (spec §12.11)."""
    if _records.media_type_for(post) == "message/rfc822":
        return
    has_segment = any(
        isinstance(b, _segments.Segment)
        or (isinstance(b, _segments.Section) and b.segments)
        for b in blocks
    )
    if not has_segment:
        return
    referenced: set[str] = _wikilink_addresses(post)
    # Only SEGMENT addresses reference embeds (§4.3.1.4 — address membership on segments).
    # A section's span address does not: a 3.0 section is a form span, not an
    # embed-referencing grouping, and the 2.x leniency that counted it masked latent orphans.
    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for child in blk.segments:
                referenced.update(_addresses(getattr(child, "address", None)))
        elif isinstance(blk, _segments.Segment):
            referenced.update(_addresses(getattr(blk, "address", None)))
    for i, eb in enumerate(_records.iter_embed_blocks(post), 1):
        addrs = _addresses(eb.get("address"))
        if addrs and not any(a in referenced for a in addrs):
            yield Finding(
                rule_id="embed-unreferenced",
                severity="warning",
                message=(
                    f"embed {i} (`{eb.get('media_type')}` at `{','.join(addrs)}`) is not "
                    f"referenced by any segment or body wikilink."
                ),
                address=",".join(addrs),
                fields={"media_type": eb.get("media_type")},
            )


def _rule_embed_missing_target(post, blocks, root) -> Iterator[Finding]:
    """An image segment (or body wikilink) at an address that no embed in this record carries.
    Artifact-self-slices (`frame=`/`page=`/`bbox=` rendered from the artifact) and
    lineage-chained references (`turn=N&att=M`, §4.3.1.4) need no embed — the resolver
    materializes them on demand."""
    from corpus import embeds as _embeds
    from corpus import functional_uri as _furi

    record_id = post.metadata.get("id") or ""
    artifact_mime = _records.media_type_for(post)
    known = _embed_address_set(post)

    def _self_slice(addr: str) -> bool:
        # A lineage-chained reference (a unit's declared attachment, `…&att=<M>`) is
        # resolver-materializable through containment lineage — no embed required (§4.3.1.4).
        if "att=" in addr:
            return True
        if artifact_mime.startswith("video/"):
            return addr.startswith(("frame=", "time=", "time_range="))
        if artifact_mime == "application/pdf":
            return addr.startswith("page=")
        if artifact_mime.startswith("image/"):
            return addr.startswith("bbox=")
        return False

    for top_i, blk in enumerate(blocks, 1):
        segs = (
            [(f"section {top_i}/segment {j}", s) for j, s in enumerate(blk.segments, 1)]
            if isinstance(blk, _segments.Section)
            else ([(f"segment {top_i}", blk)] if isinstance(blk, _segments.Segment) else [])
        )
        for label, seg in segs:
            if seg.atom != "image":
                continue
            ext = [a for a in _addresses(seg.address) if not _self_slice(a)]
            if ext and not any(a in known for a in ext):
                yield Finding(
                    rule_id="embed-missing-target",
                    severity="error",
                    message=(
                        f"{label} is an image segment at `{','.join(ext)}` but no embed in this "
                        f"record carries that address."
                    ),
                    address=",".join(ext),
                )
    for wk in _embeds.find_wiki_embeds(post.content or ""):
        try:
            parsed = _furi.parse(wk.uri)
        except Exception:
            continue
        if parsed.hash != record_id:
            continue
        addr_params = [
            f"{k}={v}" for k, v in parsed.params if v is not None and k in _EMBED_ADDRESS_KEYS
        ]
        ext = [a for a in addr_params if not _self_slice(a)]
        if ext and not any(a in known for a in ext):
            yield Finding(
                rule_id="embed-missing-target",
                severity="error",
                message=(
                    f"wikilink `{wk.uri}` references address `{','.join(ext)}` but no embed in "
                    f"this record carries that address."
                ),
                address=",".join(ext),
            )


# ---------- body sanity (markdown) ---------- #

_HTML_RESIDUE_RE = re.compile(r"<\s*(script|style|iframe)\b", re.IGNORECASE)
_WIKILINK_WELLFORMED_RE = re.compile(r"!?\[\[(?:(?!\[\[|\]\]).)*?\]\]", re.DOTALL)
_WIKILINK_OPEN_RE = re.compile(r"\[\[")
_FENCE_RE = re.compile(r"^```", re.MULTILINE)
# Verbatim-transcript atoms (§12.18 step 4): a chat user genuinely typing an unpaired ``` is
# faithful content, not a truncation artifact, so those bodies are exempt from fence-balance
# counting — the heuristic only makes sense for extracted document bodies.
_VERBATIM_BODY_OVERLAYS = frozenset({"text/message", "text/metadata"})
_HTML_COMMENT_OPENER_RE = re.compile(r"<!--\s*(/?[A-Za-z]+)")
# Closed block vocabulary (spec §4.3). `context` is the annotations family; `issue` is kept
# for the tolerant read of not-yet-upgraded legacy records.
_KNOWN_COMMENT_KEYWORDS = frozenset(
    {"artifact", "origin", "classify", "embed", "section", "segment", "context", "issue"}
)


def _rule_body_empty_normalized(post, blocks, root) -> Iterator[Finding]:
    # The 3.0 gate was `status == "normalized"` (formed + authored). `has_stored_rendering`
    # collapses out of its 3.1 successor: it can never be true in the same breath as an empty
    # content zone. *(3.2)* `is_authored` retires with the layer it named — the only way a
    # record can carry a written vouch AND an empty content zone now is a frontmatter
    # OVERRIDE (a form-section vouch requires the section, which requires content), so
    # `has_editorial_override` is the honest, narrower gate. A hit here is not necessarily
    # wrong — a formless-permanently record may legitimately carry an override and no
    # content — just worth a look; severity stays "warning", not "error", and the pass gate
    # (§8.5) doesn't block on it.
    if not _records.has_editorial_override(post) or (post.content or "").strip():
        return
    # A manifest record (a self_contained container recorded as embeds — e.g. a kept-whole
    # zip) legitimately has an empty content zone: the members are verbatim, resolvable
    # transports carried as embeds, so the metadata zone IS the content. Only flag a record
    # that is empty of content AND embeds (a genuinely empty normalize).
    if list(_records.iter_embed_blocks(post)):
        return
    yield Finding(
        rule_id="body-empty-normalized",
        severity="warning",
        message="content zone is empty on an authored record with no embeds.",
    )


def _rule_body_html_residue(post, blocks, root) -> Iterator[Finding]:
    matches = _HTML_RESIDUE_RE.findall(post.content or "")
    if matches:
        kinds = sorted({m.lower() for m in matches})
        yield Finding(
            rule_id="body-html-residue",
            severity="warning",
            message=f"body contains {len(matches)} stripped-but-surviving tag(s): {', '.join(kinds)}.",
            fields={"tags": kinds, "count": len(matches)},
        )


def _rule_body_wikilink_malformed(post, blocks, root) -> Iterator[Finding]:
    residual = _WIKILINK_WELLFORMED_RE.sub("", post.content or "")
    dangling = len(_WIKILINK_OPEN_RE.findall(residual))
    if dangling:
        yield Finding(
            rule_id="body-wikilink-malformed",
            severity="warning",
            message=(
                f"body has {dangling} unclosed `[[` wikilink opener(s) after removing "
                f"well-formed links."
            ),
            fields={"dangling_openers": dangling},
        )


def _rule_body_codefence_unbalanced(post, blocks, root) -> Iterator[Finding]:
    count = len(_FENCE_RE.findall(post.content or ""))
    # Exempt verbatim-transcript bodies: subtract their fences from the balance count (rather
    # than the whole body), so a genuine imbalance in an extracted document body elsewhere in
    # the same record still surfaces. An unpaired ``` a chat user typed is content, not a
    # truncation signal (§12.18 step 4).
    for seg in _iter_all_segments(blocks):
        if getattr(seg, "overlay", None) in _VERBATIM_BODY_OVERLAYS:
            count -= len(_FENCE_RE.findall(seg.body or ""))
    if count % 2:
        yield Finding(
            rule_id="body-codefence-unbalanced",
            severity="warning",
            message=f"body has {count} ``` code-fence markers (odd count → unbalanced).",
            fields={"count": count},
        )


def _rule_body_unknown_comment(post, blocks, root) -> Iterator[Finding]:
    """Any HTML comment whose opener isn't one of the closed block keywords (spec §4.3) is
    noise — drafters never emit them; flag every occurrence."""
    unknown: dict[str, int] = {}
    for match in _HTML_COMMENT_OPENER_RE.finditer(post.content or ""):
        head = match.group(1)
        if head not in _KNOWN_COMMENT_KEYWORDS:
            unknown[head] = unknown.get(head, 0) + 1
    for kind, count in sorted(unknown.items()):
        yield Finding(
            rule_id="body-unknown-comment",
            severity="error",
            message=(
                f"body contains {count} HTML comment(s) with unrecognized opener `<!--{kind}-->`. "
                f"Allowed block keywords: artifact, origin, embed, section, segment, context."
            ),
            fields={"opener": kind, "count": count},
        )


# ---------- 3.0 byte-mark + form-coherence rules (§4.3.2.1, §4.3.2.3, §7.8) ---------- #


def _iter_all_segments(blocks):
    """Yield every segment (top-level and in-section), in reading order."""
    for blk in blocks:
        if isinstance(blk, _segments.Section):
            yield from blk.segments
        elif isinstance(blk, _segments.Segment):
            yield blk


def _rule_structural_byte_mark(post, blocks, root) -> Iterator[Finding]:
    """A structural byte-mark (§4.3.2.3) carries a positive `level` and no body. The parser
    normalizes most of the shape (address required, level cast to int, body dropped); this
    guards the residue the grammar admits — a non-positive level."""
    for seg in _iter_all_segments(blocks):
        if not seg.is_structural:
            continue
        if not isinstance(seg.level, int) or seg.level < 1:
            yield Finding(
                rule_id="structural-level-invalid",
                severity="error",
                message=(
                    f"structural byte-mark `level` is {seg.level!r}; must be a positive "
                    f"integer (the source's own hierarchy depth, else 1) (spec §4.3.2.3)."
                ),
                address=_addr_str(seg.address),
            )


def _leading_axis(addr: Any) -> tuple[str, str]:
    """`(param, value)` of an address's leading `<param>=<value>` (`page=5&bbox=…` →
    `("page","5")`). For a list address, the first element's leading param."""
    if isinstance(addr, list):
        addr = addr[0] if addr else ""
    head = str(addr).split("&", 1)[0]
    param, _eq, value = head.partition("=")
    return param.strip(), value.strip()


def _axis_low(value: str) -> int | None:
    """The low integer of an axis value (`3` → 3, `2-6` → 2), or None when non-numeric."""
    try:
        return int(str(value).split("-", 1)[0])
    except (TypeError, ValueError):
        return None


def _rule_form_coherence(post, blocks, root) -> Iterator[Finding]:
    """Form-coherence (§4.3.2.1, §7.8): a record carrying `<!--section <form-id>-->` MUST
    satisfy the form overlay's declared `checks` — required envelope fields present, codebook
    indexes in range, addresses on the declared axes and monotonic. There is no half-asserted
    form. An unknown form id (no overlay) is a warning (an asserted form may precede its
    overlay); a missing/out-of-range codebook or envelope field is an error."""
    for top_i, blk in enumerate(blocks, 1):
        if not isinstance(blk, _segments.Section) or not blk.form:
            continue
        overlay = _schemas.load_form_overlay(root, blk.form)
        if not overlay:
            yield Finding(
                rule_id="form-overlay-unknown",
                severity="warning",
                message=(
                    f"section {top_i} declares form `{blk.form}` but no `form/{blk.form}` "
                    f"overlay resolves — coherence cannot be checked (spec §7.8)."
                ),
                address=_addr_str(blk.address),
            )
            continue
        checks = overlay.get("checks") or {}
        header = dict(blk.extra or {})

        for field_name in checks.get("envelope_required") or []:
            if field_name not in header:
                yield Finding(
                    rule_id="form-envelope-missing",
                    severity="error",
                    message=(
                        f"section {top_i} (form `{blk.form}`) is missing required envelope "
                        f"field `{field_name}` (spec §4.3.2.1)."
                    ),
                    address=_addr_str(blk.address),
                )

        for rule in checks.get("codebook") or []:
            seg_field = rule.get("segment_field")
            book_field = rule.get("codebook_field")
            codebook = header.get(book_field)
            book_len = len(codebook) if isinstance(codebook, list) else None
            for seg in blk.segments:
                if seg_field not in (seg.extra or {}):
                    continue
                idx = (seg.extra or {}).get(seg_field)
                if not isinstance(idx, int) or book_len is None or idx < 0 or idx >= book_len:
                    yield Finding(
                        rule_id="form-codebook-index-out-of-range",
                        severity="error",
                        message=(
                            f"section {top_i} (form `{blk.form}`): `{seg_field}: {idx!r}` does "
                            f"not index the `{book_field}` codebook "
                            f"(size {book_len if book_len is not None else 'absent'})."
                        ),
                        address=_addr_str(seg.address),
                    )

        axes = set(checks.get("address_axes") or [])
        monotonic = bool(checks.get("monotonic"))
        prev_low: int | None = None
        for seg in blk.segments:
            param, value = _leading_axis(seg.address)
            if axes and param and param not in axes:
                yield Finding(
                    rule_id="form-address-axis",
                    severity="warning",
                    message=(
                        f"section {top_i} (form `{blk.form}`): child address axis `{param}=` "
                        f"is not among the form's declared axes {sorted(axes)}."
                    ),
                    address=_addr_str(seg.address),
                )
            if monotonic:
                low = _axis_low(value)
                if low is not None and prev_low is not None and low < prev_low:
                    yield Finding(
                        rule_id="form-address-nonmonotonic",
                        severity="warning",
                        message=(
                            f"section {top_i} (form `{blk.form}`): child addresses are not "
                            f"monotonic (`{param}={value}` follows a higher position)."
                        ),
                        address=_addr_str(seg.address),
                    )
                if low is not None:
                    prev_low = low


# ---------- rule registry + entry point ---------- #


_REGISTRY: tuple[tuple[str, Any], ...] = (
    ("id-format", _rule_id_format),
    ("frontmatter-legacy-status", _rule_legacy_status),
    ("editorial-override-placeholder", _rule_editorial_override_shape),
    ("description-too-long", _rule_editorial_override_shape),
    ("editorial-override-redundant", _rule_editorial_override_redundant),
    ("transport-format", _rule_transport_format),
    ("canonical-format", _rule_canonical_format),
    ("perceptual-format", _rule_perceptual_format),
    ("visibility-invalid", _rule_visibility_invalid),
    ("touch-format", _rule_touch_format),
    ("artifact-block-missing", _rule_artifact_block_missing),
    ("origins-empty", _rule_origins_empty),
    ("origin-uri-shape", _rule_origin_uri_shape),
    ("embed-format", _rule_embed_format),
    ("atom-invalid", _rule_atom_invalid),
    ("segment-non-text-with-body", _rule_segment_non_text_with_body),
    ("segment-perceptual-format", _rule_segment_perceptual_format),
    ("section-empty", _rule_section_empty),
    ("section-address-span", _rule_section_address_span),
    ("segment-address-duplicate", _rule_segment_address_duplicate),
    ("issue-shape", _rule_issue_shape),
    ("context-shape", _rule_context_shape),
    ("classify-block-retired", _rule_classify_retired),
    # normalizer-support parity (luklacloud intent)
    ("description-too-long", _rule_description_too_long),
    ("mime-extension-mismatch", _rule_mime_extension_mismatch),
    ("entry-missing", _rule_entry_missing),
    ("segment-body-requires-lossless", _rule_segment_body_lossless_contract),
    ("segment-description-required", _rule_segment_body_lossless_contract),
    ("section-description-redundant", _rule_section_description_redundant),
    ("segment-mode-deprecated", _rule_segment_mode_deprecated),
    ("embed-description-empty-on-normalized", _rule_embed_description_empty_on_normalized),
    ("embed-unreferenced", _rule_embed_unreferenced),
    ("embed-missing-target", _rule_embed_missing_target),
    ("body-empty-normalized", _rule_body_empty_normalized),
    ("body-html-residue", _rule_body_html_residue),
    ("body-wikilink-malformed", _rule_body_wikilink_malformed),
    ("body-codefence-unbalanced", _rule_body_codefence_unbalanced),
    ("body-unknown-comment", _rule_body_unknown_comment),
    # 3.0 byte-mark + form-coherence (§4.3.2.1, §4.3.2.3, §7.8).
    ("structural-level-invalid", _rule_structural_byte_mark),
    ("form-overlay-unknown", _rule_form_coherence),
    ("form-envelope-missing", _rule_form_coherence),
    ("form-codebook-index-out-of-range", _rule_form_coherence),
    ("form-address-axis", _rule_form_coherence),
    ("form-address-nonmonotonic", _rule_form_coherence),
)

# The rule subset `corpus diagnose` runs for its quick-lint section — the cheap, high-signal
# frontmatter/structure checks (athenaeum's idiomatic rule_ids).
DIAGNOSE_QUICK_RULES: tuple[str, ...] = (
    "editorial-override-placeholder",
    "editorial-override-redundant",
    "frontmatter-legacy-status",
    "transport-format",
    "canonical-format",
    "touch-format",
    "artifact-block-missing",
    "origins-empty",
    "entry-missing",
    "atom-invalid",
)


def lint(
    post: frontmatter.Post,
    blocks: list[_segments.Block],
    corpus_root: Path,
    *,
    rules: Iterable[str] | None = None,
) -> list[Finding]:
    """Run every registered rule against a record. Returns findings in declaration
    order (frontmatter → metadata-zone → segments → embeds → annotations).

    `blocks` is the content-zone parse from `segments.iter_blocks(post.content)`.

    `rules` filters findings to a named subset — when None, every rule runs.
    """
    wanted = set(rules) if rules is not None else None
    out: list[Finding] = []
    seen_fns: set[int] = set()
    for _rule_id, fn in _REGISTRY:
        # A handler may be registered under several rule_ids (e.g. the retired-block /
        # lossless-contract validators each emit a family of rule_ids); run each unique
        # function once and let it yield its full family.
        if id(fn) in seen_fns:
            continue
        seen_fns.add(id(fn))
        for finding in fn(post, blocks, corpus_root):
            if wanted is None or finding.rule_id in wanted:
                out.append(finding)
    return out


# ---------- helpers ---------- #


def _addresses(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(a) for a in raw if a]
    return [str(raw)]


def _addr_str(raw: Any) -> str:
    addrs = _addresses(raw)
    return ",".join(addrs) if addrs else ""
