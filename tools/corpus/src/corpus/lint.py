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
_VALID_STATUSES = {"stub", "draft", "normalized"}
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


def _rule_status_invalid(post, blocks, root) -> Iterator[Finding]:
    s = post.metadata.get("status", "")
    if s not in _VALID_STATUSES:
        yield Finding(
            rule_id="status-invalid",
            severity="error",
            message=(
                f"`status` is {s!r}; must be one of {sorted(_VALID_STATUSES)} "
                f"(spec §4.2)."
            ),
        )


def _rule_description_format(post, blocks, root) -> Iterator[Finding]:
    """`description` is empty until normalize, then 1–3 sentences. Cap at ~600 chars."""
    status = post.metadata.get("status", "")
    desc = (post.metadata.get("description") or "").strip()
    if status == "normalized" and not desc:
        yield Finding(
            rule_id="description-empty",
            severity="error",
            message="`description` is empty on a normalized record (spec §4.2).",
        )
    if len(desc) > 600:
        yield Finding(
            rule_id="description-too-long",
            severity="warning",
            message=f"`description` is {len(desc)} chars; aim ≤600 (1–3 sentences).",
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
    """Each origin block carries a non-empty `uri:` (string or list) and a `snapshot:`."""
    for idx, origin in enumerate(_records.iter_origin_blocks(post)):
        fields = origin.get("fields") or {}
        uri = fields.get("uri")
        if uri is None or (isinstance(uri, list) and not uri) or (isinstance(uri, str) and not uri.strip()):
            yield Finding(
                rule_id="origin-uri-missing",
                severity="error",
                message=f"origin block #{idx + 1} missing required `uri:`.",
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


def _rule_segment_entry_outside_top_level(post, blocks, root) -> Iterator[Finding]:
    """In-section segments must not carry `entry:` — that's a section-only field."""
    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for seg in blk.segments:
                if seg.entry is not None:
                    yield Finding(
                        rule_id="segment-entry-in-section",
                        severity="error",
                        message=(
                            "segment carries `entry:` but is inside a section; "
                            "entry: is a top-level segment field only (spec §4.3.2.2)."
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


def _rule_reference_resolvable(post, blocks, root) -> Iterator[Finding]:
    """A `reference` context whose ladder has reached `source_uri` (a `corpus://<id>` link,
    §4.4.5) must point at an existing record — a dangling target is stale research."""
    from corpus import paths

    for idx, ctx in enumerate(_records.iter_context_blocks(post)):
        if (ctx.get("namespace") or "") != "reference":
            continue
        source_uri = str((ctx.get("fields") or {}).get("source_uri") or "").strip()
        if not source_uri:
            continue
        m = re.match(r"corpus://([0-9a-fA-F]{6,64})", source_uri)
        if not m or not paths.record_path(root, m.group(1)).is_file():
            yield Finding(
                rule_id="reference-unresolved",
                severity="warning",
                message=(
                    f"reference #{idx + 1} `source_uri: {source_uri}` does not resolve to a "
                    f"captured record."
                ),
            )


def _rule_classification_stale(post, blocks, root) -> Iterator[Finding]:
    """A `provenance: auto` classify block must correspond to a live composite overlay whose
    `classify_when` still matches the record (spec §7.4). When the overlay was deleted, dropped
    its rule, or the rule no longer fires, the stamp is stale — `corpus reclassify` regenerates.
    Hand-/normalizer-asserted blocks (no `provenance`) are exempt."""
    from corpus import classify_rules

    overlays = dict(_schemas.iter_all_classifications(root))
    facts = None
    for blk in _records.iter_classify_blocks(post):
        if (blk.get("fields") or {}).get("provenance") != "auto":
            continue
        class_id = classify_rules.class_id_of(blk)
        predicate = (overlays.get(class_id) or {}).get("classify_when")
        if not predicate:
            yield Finding(
                rule_id="classification-stale",
                severity="warning",
                message=(
                    f"auto classification `{class_id}` has no live `classify_when` overlay; "
                    f"run `corpus reclassify`."
                ),
            )
            continue
        if facts is None:
            facts = classify_rules.build_facts(root, post)
        if not classify_rules.evaluate(predicate, facts):
            yield Finding(
                rule_id="classification-stale",
                severity="warning",
                message=(
                    f"auto classification `{class_id}` no longer matches its rule; "
                    f"run `corpus reclassify`."
                ),
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


def _collect_extended_fields(ns_schema: dict, sub_schema: dict | None) -> dict[str, Any]:
    """Union of namespace-level and (optional) subclass-level `extended_fields`."""
    out: dict[str, Any] = {}
    ns_fields = ns_schema.get("extended_fields") or {}
    if isinstance(ns_fields, dict):
        out.update(ns_fields)
    if isinstance(sub_schema, dict):
        sub_fields = sub_schema.get("extended_fields") or {}
        if isinstance(sub_fields, dict):
            out.update(sub_fields)
    return out


def _value_matches_type(value: Any, expected_type: str) -> bool:
    """Light type validation (PyYAML-shaped). `None` always passes (required handled
    separately); `bool` is explicitly rejected for integer/number."""
    if value is None:
        return True
    t = expected_type.lower()
    if t in ("string", "str"):
        return isinstance(value, str)
    if t in ("integer", "int"):
        return isinstance(value, int) and not isinstance(value, bool)
    if t in ("number", "float"):
        return isinstance(value, int | float) and not isinstance(value, bool)
    if t in ("boolean", "bool"):
        return isinstance(value, bool)
    if t in ("array", "list"):
        return isinstance(value, list)
    if t in ("object", "dict", "mapping"):
        return isinstance(value, dict)
    return True  # unknown declared type — be permissive


def _rule_classify_fields(post, blocks, root) -> Iterator[Finding]:
    """Validate every applied classify block's fields against the overlay's
    `extended_fields` (union of namespace + subclass). Emits required-missing / type / unknown.

    `required` is a completeness contract, gated like §4.3.2.2 entries: a missing required field
    is an *error* on a normalized record but only a *warning* at draft, so a normalizer can apply
    an overlay and backfill its fields incrementally without tripping the draft lint gate."""
    status = post.metadata.get("status", "")
    for cb in _records.iter_classify_blocks(post):
        ns = cb.get("namespace") or ""
        cid = cb.get("id") or ""
        sub = cb.get("subtype") or ""
        if not ns:
            continue
        overlay_id = f"{ns}/{cid}" if cid and cid != ns else ns
        if sub:
            overlay_id = f"{overlay_id}/{sub}"
        schema = _schemas.load_classification_schema(root, ns)
        if not isinstance(schema, dict):
            continue
        sub_schema = (
            _schemas.load_classification_subclass(root, ns, cid) if cid and cid != ns else None
        )
        declared = _collect_extended_fields(schema, sub_schema)
        provided = cb.get("fields") or {}
        # reserved engine field — not an extended field (spec §4.3.1.3)
        provided = {k: v for k, v in provided.items() if k != "provenance"}
        for fname, fspec in declared.items():
            if (
                isinstance(fspec, dict)
                and fspec.get("required")
                and (fname not in provided or provided[fname] in (None, "", []))
            ):
                yield Finding(
                    rule_id="classify-field-required-missing",
                    severity="error" if status == "normalized" else "warning",
                    message=f"`{overlay_id}` requires field `{fname}` but it is missing or empty.",
                    subtype=overlay_id,
                    fields={"field": fname, "overlay": overlay_id},
                )
        for fname, value in provided.items():
            fspec = declared.get(fname)
            if not isinstance(fspec, dict):
                continue
            expected_type = str(fspec.get("type") or "string").lower()
            if not _value_matches_type(value, expected_type):
                yield Finding(
                    rule_id="classify-field-type",
                    severity="error",
                    message=(
                        f"`{overlay_id}` field `{fname}` value does not match declared type "
                        f"`{expected_type}` (got {type(value).__name__})."
                    ),
                    subtype=overlay_id,
                    fields={"field": fname, "expected_type": expected_type},
                )
        for fname in provided:
            if fname not in declared:
                yield Finding(
                    rule_id="classify-field-unknown",
                    severity="warning",
                    message=(
                        f"`{overlay_id}` carries field `{fname}` which is not declared in the "
                        f"overlay's `extended_fields`."
                    ),
                    subtype=overlay_id,
                    fields={"field": fname, "overlay": overlay_id},
                )


def _rule_section_composite_fields(post, blocks, root) -> Iterator[Finding]:
    """Validate a section-scope composite (`<!--section <ns>/<id>-->`): the overlay must
    declare `applies_at: section`, and the section's fields (its `description` + header extras)
    must satisfy the overlay's `extended_fields`. `description` is universal, never unknown.

    Required-field completeness is gated like the classify path: error at normalized, warning at
    draft (a section composite may be applied before its fields are backfilled)."""
    status = post.metadata.get("status", "")
    for top_i, blk in enumerate(blocks, 1):
        if not isinstance(blk, _segments.Section) or not blk.classification:
            continue
        parts = [p for p in str(blk.classification).split("/") if p]
        if not parts:
            continue
        ns = parts[0]
        cid = parts[1] if len(parts) >= 2 else ns
        overlay_id = str(blk.classification)
        schema = _schemas.load_classification_schema(root, ns)
        if not isinstance(schema, dict):
            yield Finding(
                rule_id="section-composite-scope-invalid",
                severity="error",
                message=f"section {top_i} declares composite `{overlay_id}` but no such overlay exists.",
                address=_addr_str(blk.address),
                fields={"overlay": overlay_id},
            )
            continue
        sub_schema = (
            _schemas.load_classification_subclass(root, ns, cid) if cid and cid != ns else None
        )
        applies_at = (sub_schema or schema).get("applies_at") or ["record"]
        if "section" not in applies_at:
            yield Finding(
                rule_id="section-composite-scope-invalid",
                severity="error",
                message=(
                    f"section {top_i} applies composite `{overlay_id}`, but the overlay does not "
                    f"declare `applies_at: section` (declares {applies_at})."
                ),
                address=_addr_str(blk.address),
                fields={"overlay": overlay_id},
            )
            continue
        declared = _collect_extended_fields(schema, sub_schema)
        provided: dict[str, Any] = dict(blk.extra or {})
        if blk.description is not None:
            provided["description"] = blk.description
        for fname, fspec in declared.items():
            if (
                isinstance(fspec, dict)
                and fspec.get("required")
                and (fname not in provided or provided[fname] in (None, "", []))
            ):
                yield Finding(
                    rule_id="section-field-required-missing",
                    severity="error" if status == "normalized" else "warning",
                    message=f"section {top_i} (`{overlay_id}`) requires field `{fname}` but it is missing or empty.",
                    address=_addr_str(blk.address),
                    subtype=overlay_id,
                    fields={"field": fname, "overlay": overlay_id},
                )
        for fname, value in provided.items():
            fspec = declared.get(fname)
            if isinstance(fspec, dict):
                expected_type = str(fspec.get("type") or "string").lower()
                if not _value_matches_type(value, expected_type):
                    yield Finding(
                        rule_id="section-field-type",
                        severity="error",
                        message=(
                            f"section {top_i} (`{overlay_id}`) field `{fname}` value does not match "
                            f"declared type `{expected_type}` (got {type(value).__name__})."
                        ),
                        address=_addr_str(blk.address),
                        subtype=overlay_id,
                        fields={"field": fname, "expected_type": expected_type},
                    )
        for fname in provided:
            if fname != "description" and fname not in declared:
                yield Finding(
                    rule_id="section-field-unknown",
                    severity="warning",
                    message=(
                        f"section {top_i} (`{overlay_id}`) carries field `{fname}` which is not "
                        f"declared in the overlay's `extended_fields`."
                    ),
                    address=_addr_str(blk.address),
                    subtype=overlay_id,
                    fields={"field": fname, "overlay": overlay_id},
                )


def _rule_entry_missing(post, blocks, root) -> Iterator[Finding]:
    """Every top-level block (section / top-level segment) should carry a non-empty `entry`
    (the §4.3.2.2 TOC label) — error on a normalized record, warning otherwise."""
    status = post.metadata.get("status", "")
    missing = [i + 1 for i, blk in enumerate(blocks) if not (getattr(blk, "entry", None) or "").strip()]
    if not missing:
        return
    ords = ", ".join(str(o) for o in missing[:20])
    more = f" (+{len(missing) - 20} more)" if len(missing) > 20 else ""
    where = " on a normalized record" if status == "normalized" else f" (status: {status})"
    yield Finding(
        rule_id="entry-missing",
        severity="error" if status == "normalized" else "warning",
        message=(
            f"{len(missing)} of {len(blocks)} top-level blocks are missing `entry`{where}. "
            f"Backfill: {ords}{more}."
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
    status = post.metadata.get("status", "")
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
                severity="warning" if status == "normalized" else "info",
                message=(
                    f"{label} (`{seg.overlay}`) is a non-lossless body-empty marker with no "
                    f"`description` — describe what the region is/computes on the segment header."
                ),
                address=_addr_str(seg.address),
                fields={"overlay": seg.overlay},
            )


def _rule_section_description_redundant(post, blocks, root) -> Iterator[Finding]:
    """A section whose every child segment is lossless does not need a `description` — the
    segments already hold the content faithfully (advisory, info)."""

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
    """A normalized record whose image/audio/video embed has no `description` is missing the
    normalizer's whole-asset summary (info — persist an issue if intentionally undescribed)."""
    if post.metadata.get("status") != "normalized":
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
                f"no `description` on a normalized record. Populate the whole-asset summary, or "
                f"persist an issue if the asset is intentionally undescribed (chrome, logo)."
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
    flow-assets, and "unreferenced" is not a defect."""
    has_segment = any(
        isinstance(b, _segments.Segment)
        or (isinstance(b, _segments.Section) and b.segments)
        for b in blocks
    )
    if not has_segment:
        return
    referenced: set[str] = _wikilink_addresses(post)
    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for child in blk.segments:
                referenced.update(_addresses(getattr(child, "address", None)))
            referenced.update(_addresses(getattr(blk, "address", None)))
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
    Artifact-self-slices (`frame=`/`page=`/`bbox=` rendered from the artifact) need no embed."""
    from corpus import embeds as _embeds
    from corpus import functional_uri as _furi

    record_id = post.metadata.get("id") or ""
    artifact_mime = _records.media_type_for(post)
    known = _embed_address_set(post)

    def _self_slice(addr: str) -> bool:
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
_HTML_COMMENT_OPENER_RE = re.compile(r"<!--\s*(/?[A-Za-z]+)")
# Closed block vocabulary (spec §4.3). `context` is the annotations family; `issue` is kept
# for the tolerant read of not-yet-upgraded legacy records.
_KNOWN_COMMENT_KEYWORDS = frozenset(
    {"artifact", "origin", "classify", "embed", "section", "segment", "context", "issue"}
)


def _rule_body_empty_normalized(post, blocks, root) -> Iterator[Finding]:
    if post.metadata.get("status") != "normalized" or (post.content or "").strip():
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
        message="content zone is empty on a normalized record.",
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
                f"Allowed block keywords: artifact, origin, classify, embed, section, segment, context."
            ),
            fields={"opener": kind, "count": count},
        )


def _rule_issue_on_draft(post, blocks, root) -> Iterator[Finding]:
    """A model-detected (`detector` not `corpus.*`) issue on a draft record — interpretive
    issues belong only on normalized records; a draft's problems are surfaced live by lint."""
    if post.metadata.get("status") != "draft":
        return
    for issue in _records.iter_issue_blocks(post):
        detector = (issue.get("fields") or {}).get("detector")
        if not isinstance(detector, str) or not detector or detector.startswith("corpus."):
            continue
        qualified = issue.get("id", "")
        if issue.get("subtype"):
            qualified = f"{qualified}/{issue['subtype']}"
        yield Finding(
            rule_id="issue-on-draft",
            severity="warning",
            message=(
                f"interpretive issue block `{qualified}` (detector {detector!r}) on a draft "
                f"record — model-written issues belong only on normalized records."
            ),
            fields={"id": qualified, "detector": detector},
        )


# ---------- rule registry + entry point ---------- #


_REGISTRY: tuple[tuple[str, Any], ...] = (
    ("id-format", _rule_id_format),
    ("status-invalid", _rule_status_invalid),
    ("description", _rule_description_format),
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
    ("segment-entry-in-section", _rule_segment_entry_outside_top_level),
    ("section-empty", _rule_section_empty),
    ("section-address-span", _rule_section_address_span),
    ("segment-address-duplicate", _rule_segment_address_duplicate),
    ("issue-shape", _rule_issue_shape),
    ("context-shape", _rule_context_shape),
    ("reference-resolvable", _rule_reference_resolvable),
    ("classification-stale", _rule_classification_stale),
    # normalizer-support parity (luklacloud intent)
    ("description-too-long", _rule_description_too_long),
    ("mime-extension-mismatch", _rule_mime_extension_mismatch),
    ("classify-field-required-missing", _rule_classify_fields),
    ("classify-field-type", _rule_classify_fields),
    ("classify-field-unknown", _rule_classify_fields),
    ("section-composite-scope-invalid", _rule_section_composite_fields),
    ("section-field-required-missing", _rule_section_composite_fields),
    ("section-field-type", _rule_section_composite_fields),
    ("section-field-unknown", _rule_section_composite_fields),
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
    ("issue-on-draft", _rule_issue_on_draft),
)

# The rule subset `corpus diagnose` runs for its quick-lint section — the cheap, high-signal
# frontmatter/structure checks (athenaeum's idiomatic rule_ids).
DIAGNOSE_QUICK_RULES: tuple[str, ...] = (
    "description",
    "status-invalid",
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
        # A handler may be registered under several rule_ids (e.g. the classify-field /
        # section-field / lossless-contract validators each emit a family of rule_ids); run
        # each unique function once and let it yield its full family.
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
