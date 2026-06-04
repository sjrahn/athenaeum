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
# `enum:` declared on the layered `composite/issue` schema (a corpus may extend it); these
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
    `composite/issue` schema's `enum:` declarations (spec §4.3.3.1: the vocab is
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
    for _rule_id, fn in _REGISTRY:
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
