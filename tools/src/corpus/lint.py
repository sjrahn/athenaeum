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

from corpus import hashing as _hashing
from corpus import paths as _paths
from corpus import records as _records
from corpus import schemas as _schemas
from corpus import segments as _segments
from corpus import shape as _shape

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


#: Plausible byte-length bound for the hex half of a `<tag>:<hex>` hash value (spec §7.6)
#: - the same 32-128 hex-char floor/ceiling `_HASH_RE` enforced pre-v20, now applied
#: independently of tag shape (a procedure-versioned tag carries no algorithm to bound
#: the digest by, §7.6).
_HASH_HEXLEN = range(32, 129)


def _rule_hash_tag_grammar(post, blocks, root) -> Iterator[Finding]:
    """*(v20)* Every frontmatter `hash:` value is `<tag>:<hex>` (spec §7.6): a nonempty
    lowercase hex digest of plausible length, tagged either a bare algorithm id or a
    `<procedure>@<version>` (`hashing.parse_value`). Two tag classes are inadmissible on
    top of the grammar (spec §4.2.1, §7.9):

    - `blake3` bare — the primary identity lives on `id` alone and is never duplicated
      here (§4.2.1).
    - a tag whose registered recipe is **similarity**-class — `hash:` is identity-class
      only; a similarity value there would invite an equality join it cannot support
      (§7.9).

    An unknown-but-well-formed tag is NOT a finding: the recipe registry is open to
    extension (§7.9), so a value a newer deployment or a corpus-local recipe wrote must
    not lint red here just because this process's registry hasn't loaded it.

    Reads the already-normalized `hash:` field — `records.loads()` folds a lingering
    legacy `transport:` into it at parse time (spec §4.2.1), so this rule is oblivious
    to which frontmatter key produced the value; that provenance detail is
    `hash-legacy-transport`'s to report, not this rule's."""
    raw = post.metadata.get("hash")
    if raw is None:
        return
    values = raw if isinstance(raw, list) else [raw]
    for v in values:
        if not isinstance(v, str):
            yield Finding(
                rule_id="hash-tag-grammar",
                severity="error",
                message=f"`hash` entry {v!r} is not a string (spec §7.6).",
            )
            continue
        try:
            info, hexval = _hashing.parse_value(v)
        except ValueError as e:
            yield Finding(
                rule_id="hash-tag-grammar",
                severity="error",
                message=f"`hash` entry {v!r} is not `<tag>:<hex>`: {e} (spec §7.6).",
            )
            continue
        if len(hexval) not in _HASH_HEXLEN:
            yield Finding(
                rule_id="hash-tag-grammar",
                severity="error",
                message=(
                    f"`hash` entry {v!r} digest is {len(hexval)} hex chars, outside the "
                    f"plausible {_HASH_HEXLEN.start}-{_HASH_HEXLEN.stop - 1} range "
                    f"(spec §7.6)."
                ),
            )
        if info.tag == "blake3":
            yield Finding(
                rule_id="hash-tag-grammar",
                severity="error",
                message=(
                    "`hash` entry tagged bare `blake3` duplicates the primary identity, "
                    "which lives on `id` alone and is never repeated in `hash:` "
                    "(spec §4.2.1)."
                ),
            )
            continue
        recipe = _hashing.get_recipe(info.tag)
        if recipe is not None and recipe.comparison == "similarity":
            yield Finding(
                rule_id="hash-tag-grammar",
                severity="error",
                message=(
                    f"`hash` entry {v!r} is tagged with recipe `{info.tag}`, a "
                    f"similarity-class recipe (§7.9) — `hash:` admits identity-class "
                    f"values only; a fingerprint's equality claims nothing (spec "
                    f"§4.2.1, §7.9)."
                ),
            )


#: Legacy pre-v20 frontmatter keys `hash:` succeeds or absorbs (spec §4.2.1): `transport`
#: renames to `hash` (tolerantly folded at parse time, `records.loads()`); `canonical` is
#: retired outright; record-scope `perceptual` retires to the derived hash index with a
#: fleet population of zero (§7.7). All three parse tolerantly and are dropped on the
#: record's next write — none is re-emitted by `records.dumps()`.
_LEGACY_HASH_KEYS: tuple[str, ...] = ("transport", "canonical", "perceptual")


def _rule_hash_legacy_key(post, blocks, root) -> Iterator[Finding]:
    """*(v20)* A record still carrying a legacy hash-adjacent frontmatter key — same
    advisory discipline as `_rule_legacy_status` (spec §4.1): the key is read
    tolerantly (a lingering `transport:` folds into `hash:` at parse time, spec §4.2.1)
    but never re-emitted — `records.dumps()` drops it on the record's next write, so a
    stray key is transitional, not a defect. Flags `transport` (renamed `hash`),
    `canonical` (retired outright), and record-scope `perceptual` (retired to the
    derived hash index, §7.7) — one finding per key present, so a record carrying more
    than one gets more than one nudge rather than one that hides the rest."""
    for key in _LEGACY_HASH_KEYS:
        if key not in post.metadata:
            continue
        yield Finding(
            rule_id="hash-legacy-transport",
            severity="info",
            message=(
                f"frontmatter carries a legacy `{key}: {post.metadata.get(key)!r}` key "
                f"(spec §4.2.1) — a pre-v20 field, ignored and dropped on the record's "
                f"next write."
            ),
            subtype=key,
        )


def _registered_recipe_versions(procedure: str) -> list[str]:
    """Every version currently registered for `procedure` (spec §7.9) — i.e. every
    registered recipe id that parses as a `<procedure>@<version>` tag naming it. Reads
    the registry's id space through the public `parse_tag`/`get_recipe` surface rather
    than a procedure-name index, since none exists (`hashing` indexes recipes by their
    full tag, §7.9) and adding one is out of this rule's scope."""
    out: list[str] = []
    for rid in _hashing._REGISTRY:  # read-only registry scan, see docstring above
        try:
            info = _hashing.parse_tag(rid)
        except ValueError:
            continue
        if info.residency == "procedure-versioned" and info.procedure == procedure:
            out.append(info.version)
    return out


def _rule_hash_superseded_recipe_version(post, blocks, root) -> Iterator[Finding]:
    """*(v20)* A `<procedure>@<version>` value in `hash:` whose procedure is registered
    at a DIFFERENT version (spec §7.9) — e.g. a stored `html-stampfree@1` when the
    registry now ships `html-stampfree@2`. Version comparison is exact string
    inequality on the same procedure name (the version is an opaque tag, never a
    numeric ordering, spec §7.6).

    The stored value is not wrong — it stands as exactly what the OLD procedure
    computed, and stays that way: §7.9 is explicit that "a revision never rewrites
    stored values... lint may flag them for a deliberate re-flush, never silently."
    Warning, never error, on that authority — a superseded value is stale, honest
    attestation, not a malformed one."""
    raw = post.metadata.get("hash")
    if raw is None:
        return
    values = raw if isinstance(raw, list) else [raw]
    for v in values:
        if not isinstance(v, str):
            continue
        try:
            info, _hexval = _hashing.parse_value(v)
        except ValueError:
            continue  # hash-tag-grammar already reports a malformed entry
        if info.residency != "procedure-versioned":
            continue
        current = _registered_recipe_versions(info.procedure)
        if not current or info.version in current:
            # No registered recipe names this procedure at all (this process's registry
            # doesn't know it — not this rule's business, same "unknown, allowed"
            # discipline as `hash-tag-grammar`), or the stored version IS one of the
            # currently-registered versions for it — not superseded.
            continue
        yield Finding(
            rule_id="hash-superseded-recipe-version",
            severity="warning",
            message=(
                f"`hash` entry `{v}` is procedure `{info.procedure}` at version "
                f"`{info.version}`, but the registry now ships "
                f"{', '.join(f'{info.procedure}@{c}' for c in current)} — the stored "
                f"value stands as the old procedure's output; flag for a deliberate "
                f"re-flush, never rewritten automatically (spec §7.9)."
            ),
            fields={
                "procedure": info.procedure,
                "stored_version": info.version,
                "current_versions": current,
            },
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


def _rule_member_row_unknown_key(post, blocks, root) -> Iterator[Finding]:
    """The `<!--members-->` row is a CLOSED four-key shape — `address`, `media_type`,
    `transport`, `bytes` — and an unrecognized key is a validation error (spec §4.3.1.4):
    a closed shape needs a closed check, or the roster silently re-accumulates the
    descriptive payload 3.4 moved out of it into the `members` derivation.

    `address`/`media_type`/`transport` are popped into their own keys by the reader
    (`records._structure_member_rows`), so `bytes` is the only key a well-formed row's
    `fields` dict may still carry — anything else there is residue that survived a write
    path other than the strict one. `bytes` itself is required, and must be an int: it is
    the row's one field whose derivation is not uniformly cheap (§4.3.1.4), so a row that
    omits or mistypes it is exactly the case the admission rule was written to keep out.

    Legacy pre-3.4 `<!--embed-->` rows are EXEMPT (spec §12.26): they are read-only, still
    carry whatever the retired per-asset block stored, and are not this check's business.
    `post.metadata["_members_block"]` records which form the record was read from — False
    only when legacy per-asset blocks were actually read."""
    if not post.metadata.get("_members_block", True):
        return
    for idx, row in enumerate(_records.iter_members(post), 1):
        addr = _addr_str(row.get("address"))
        fields = row.get("fields") or {}
        unknown = sorted(k for k in fields if k != "bytes")
        if unknown:
            yield Finding(
                rule_id="member-row-unknown-key",
                severity="error",
                message=(
                    f"members row #{idx} carries unknown key(s) {unknown} — the row is "
                    f"closed to {{address, media_type, transport, bytes}} (spec §4.3.1.4)."
                ),
                address=addr,
                fields={"unknown_keys": unknown},
            )
        if "bytes" not in fields:
            yield Finding(
                rule_id="member-row-unknown-key",
                severity="error",
                message=f"members row #{idx} is missing required `bytes` (spec §4.3.1.4).",
                address=addr,
            )
        else:
            bytes_val = fields["bytes"]
            if isinstance(bytes_val, bool) or not isinstance(bytes_val, int):
                yield Finding(
                    rule_id="member-row-unknown-key",
                    severity="error",
                    message=(
                        f"members row #{idx} `bytes: {bytes_val!r}` is not an int "
                        f"(spec §4.3.1.4)."
                    ),
                    address=addr,
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
    # The fifth and sixth kinds carry no atom at all (§4.3.2.3, §4.3.2.4) — a byte-mark and a
    # placement are positions, and the atom vocabulary does not apply to either.
    if not seg.is_content:
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
    # each entry. *(v20)* Record-scope `perceptual:` retired outright (§4.2.1/§7.7,
    # `hash-legacy-transport`) — this is now the only surviving `perceptual:` shape check.
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
            # The terminal-contract inversion (spec §7.8, 3.3): a terminal form's
            # section is bare BY DESIGN — content there is the violation
            # (`terminal-stored-rendering`), so emptiness is conformance, not a defect.
            if blk.form and _schemas.is_terminal_form(root, blk.form):
                continue
            yield Finding(
                rule_id="section-empty",
                severity="warning",
                message="section has no child segments.",
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


def _rule_container_carries_rendering(post, blocks, root) -> Iterator[Finding]:
    """A container's own body holds a rendering of its members' bytes (spec §65, §4.3.2.2).

    A `disposition: manifest` record's members ARE its content: the content zone carries the
    container's own byte-marks (chapters) and nothing else, because anything a member says is
    that member's promoted record's to say (§4.3.2.4 — a parent's rendering of a member is a
    violation, not a style).

    **Why a warning and not an error, which is the subtle part.** `shape.governing_form`
    deliberately refuses to apply a class-level terminal default to a record that already
    carries a stored rendering, so such a record stands `rendered` rather than `terminal` and
    `terminal-stored-rendering` correctly does not fire. That guard is right — it is what lets
    a container's disposition be declared *before* its content is migrated, instead of
    reddening a fleet on a schema edit. But it also means the obligation would otherwise be
    stated nowhere: the record is legitimately `rendered` today and wrong in the long run, and
    silence reads as conformance. So this names it as owed work.

    The population that forced it: 102 public `video/mp4` containers holding ~17,500 rendering
    segments, because transcription ran against the container instead of its audio stream.

    **Gated on an actual RENDERING, not on `has_stored_rendering`'s broader "any content
    atom."** A body-empty `image`/`video` marker for a region of the container's own transport
    (a `frame=` self-slice, §4.3.2.4 Scope) is a legitimate positioning marker, not a claim
    about a member's bytes — it is exactly what §12.30's reseat migration leaves behind on a
    cleaned container. Gating on `has_stored_rendering` fired here regardless, and the finding
    then reported its own count from the non-empty-body subset — "carries 0 stored rendering
    segment(s)" on a container that renders nothing at all. The gate and the count are now the
    same set."""
    if _schemas.resolved_disposition_for_record(root, post) != "manifest":
        return
    segs = [s for s in _segments.leaf_segments(blocks) if (s.body or "").strip()]
    if not segs:
        return
    yield Finding(
        rule_id="container-carries-rendering",
        severity="warning",
        message=(
            f"container (`disposition: manifest`) carries {len(segs)} stored rendering "
            f"segment(s) in its own content zone. A container's members are its content "
            f"(§65); what a member says belongs on the member's promoted record. Promote "
            f"the member and move the rendering there."
        ),
        fields={"rendering_segments": len(segs)},
    )


def _rule_cutting_stamp_shape(post, blocks, root) -> Iterator[Finding]:
    """A `cutting:` stamp, if present, is well-formed (spec §7.2.1 — 3.11).

    The stamp is what makes a time-addressed record's segment boundaries auditable: it names
    the versioned strategy that produced them, the parameters it ran at, and the resulting
    cut count. The count is the drift check — the same role the element count plays for
    `addressing:` (§6.1.1) — so a stamp missing it is not merely incomplete, it is a stamp
    that cannot do the one job it exists for.

    Absence of the whole stamp is NOT a finding here. A stream promoted before its strategy
    existed is unresolved, not defective (§7.2.1), and re-attestation is what supplies it —
    the two hand-authored exemplar leaves are exactly this case."""
    stamp = _records.cutting(post)
    if stamp is None:
        return
    sid = str(stamp.get("id") or "").strip()
    if not sid:
        yield Finding(
            rule_id="cutting-stamp-malformed",
            severity="error",
            message="`cutting:` stamp names no strategy `id` (spec §7.2.1).",
        )
    elif "@" not in sid:
        yield Finding(
            rule_id="cutting-stamp-malformed",
            severity="error",
            message=(
                f"`cutting:` strategy id {sid!r} carries no version. A cut list is only "
                f"reproducible against a versioned strategy (spec §7.2.1)."
            ),
            fields={"id": sid},
        )
    cuts = stamp.get("cuts")
    if cuts is None:
        yield Finding(
            rule_id="cutting-stamp-malformed",
            severity="error",
            message=(
                "`cutting:` stamp carries no `cuts` count — the drift check is the reason "
                "the stamp exists (spec §7.2.1)."
            ),
        )
        return
    try:
        n = int(cuts)
    except (TypeError, ValueError):
        yield Finding(
            rule_id="cutting-stamp-malformed",
            severity="error",
            message=f"`cutting: cuts` is {cuts!r}, which is not a count.",
        )
        return
    if n < 1:
        yield Finding(
            rule_id="cutting-stamp-malformed",
            severity="error",
            message=f"`cutting: cuts` is {n}; a stamped strategy produced at least one cut.",
        )


def _rule_framing_stamp_shape(post, blocks, root) -> Iterator[Finding]:
    """A `framing:` stamp, if present, is well-formed (spec §7.1 — retired at v32).

    3.12 admitted a muxer into the identity path, and this stamp was the entire
    compensating control: it named the producer and its version, and carried a **sample
    count** any consumer could re-derive without an engine. v32's payload-identity
    principle (§2) removed the engine from the identity path entirely, so nothing new
    writes this stamp — a leaf's `samples:` field is what carries the count now (see
    `_rule_samples_stamp_shape`). A `framing:` stamp surviving on a pre-v32 leaf is honest
    history of the bytes it described, not a defect, so every finding here is `info`: a
    shape worth noticing, never an error to fix.

    Absence of the whole stamp is NOT a finding: a leaf promoted before 3.12, one promoted
    after v32, or one whose bytes were ingested standalone, is honestly unstamped. This
    checks only that a stamp which exists is legible as the history it claims to be.

    Deliberately shape-only. The *real* check — does the leaf's own sample table agree with
    the count — needs the artifact bytes, which for a promoted leaf means muxing it back out
    of its container. That is a verification pass over a named worklist, not a rule that runs
    on every record of every lint."""
    stamp = _records.framing(post)
    if stamp is None:
        return
    for key in ("muxer", "version"):
        if not str(stamp.get(key) or "").strip():
            yield Finding(
                rule_id="framing-stamp-malformed",
                severity="info",
                message=(
                    f"`framing:` stamp (pre-v32 history) names no `{key}` — an unnamed "
                    f"producer is exactly what the stamp existed to prevent."
                ),
            )
    samples = stamp.get("samples")
    if samples is None:
        yield Finding(
            rule_id="framing-stamp-malformed",
            severity="info",
            message=(
                "`framing:` stamp (pre-v32 history) carries no `samples` count — the "
                "independent check was the reason the stamp existed."
            ),
        )
        return
    try:
        n = int(samples)
    except (TypeError, ValueError):
        yield Finding(
            rule_id="framing-stamp-malformed",
            severity="info",
            message=f"`framing: samples` is {samples!r}, which is not a count.",
        )
        return
    if n < 1:
        yield Finding(
            rule_id="framing-stamp-malformed",
            severity="info",
            message=f"`framing: samples` is {n}; a muxed member holds at least one sample.",
        )


def _rule_samples_stamp_shape(post, blocks, root) -> Iterator[Finding]:
    """A `samples:` count, if present, is a positive integer (spec §7.1, v32).

    The payload-identity principle's own self-check: a promoted leaf's artifact block may
    attest `samples:` — the engine-free count `corpus.streams.sample_count` reads from
    the source container's tables — for `cutting:` and stored markers to compare against
    (§12.8's sample-sequence comparison). Absence is not a finding: a leaf promoted before
    v32, or whose count could not be resolved at promote time, is honestly unstamped.

    Deliberately shape-only, exactly as `_rule_cutting_stamp_shape` and the retired
    `_rule_framing_stamp_shape` are — the *real* check (does the leaf's own bytes hold
    that many samples) needs the artifact bytes, a verification-pass concern, not a rule
    that runs on every record of every lint."""
    n = (records_artifact_fields(post) or {}).get("samples")
    if n is None:
        return
    try:
        count = int(n)
    except (TypeError, ValueError):
        yield Finding(
            rule_id="samples-stamp-malformed",
            severity="error",
            message=f"`samples:` is {n!r}, which is not a count.",
        )
        return
    if count < 1:
        yield Finding(
            rule_id="samples-stamp-malformed",
            severity="error",
            message=f"`samples:` is {count}; a promoted track holds at least one sample.",
        )


def records_artifact_fields(post) -> dict[str, Any] | None:
    """The record's artifact-block `fields:` map, or None — the shared read
    `_rule_samples_stamp_shape` needs (`records.samples` itself returns only a validated
    int, which is exactly what this rule exists to check BEFORE trusting)."""
    artifact = _records.artifact_block(post)
    if not artifact:
        return None
    fields = artifact.get("fields")
    return fields if isinstance(fields, dict) else None


def _rule_whole_address_admissible(post, blocks, root) -> Iterator[Finding]:
    """An address-less segment is admissible only where the media type says so
    (spec §4.3.2.2, §7.2.1 — 3.10).

    3.8 made `address` optional with absence naming the whole transport, which is right
    for a still image (one contained presentation, and `bbox=` — its only axis — names
    nothing but a part) and wrong for a sequence. One address-less rendering over a PDF,
    a video, or an mbox asserts a reading of the whole while naming no element of it, and
    leaves a reader no route back into the artifact.

    The judgement is the schema's, not this rule's: `whole_address` is `admissible`,
    `forbidden`, or `single_unit_only`, the last gated on the attested count named by
    `whole_address_count`.

    **The gate compares; it never decodes.** A check that had to open the artifact would
    report red when a codec was missing rather than when a record was wrong — a report on
    the checking host, not on the corpus. That is not hypothetical: PIL reports an
    animation it cannot decode as single-frame (historically, any animated WebP in a
    build without animation support — Pillow 12 folded the old `webp_anim` feature flag
    into plain `webp`), and would have waved through exactly the population this rule
    exists to catch.

    An unstamped artifact of a `single_unit_only` type is UNRESOLVED, not admitted —
    there is no fact to compare, and defaulting to admissible would grandfather the whole
    pre-3.10 population in silence. `corpus reattest` supplies the count."""
    addressless = [
        seg for seg in _segments.leaf_segments(blocks)
        if not seg.address and (seg.body or "").strip()
    ]
    if not addressless:
        return
    artifact = _records.artifact_block(post) or {}
    mime = (artifact.get("mime") or "").strip()
    if not mime:
        return                                  # artifact-block-missing already reports
    schema = _schemas.load_mime_schema(root, mime) or {}
    verdict = schema.get("whole_address")
    if verdict in (None, "admissible"):
        return

    def _finding(msg: str) -> Finding:
        return Finding(
            rule_id="whole-address-not-admissible",
            severity="error",
            message=msg,
            fields={"mime": mime, "whole_address": verdict},
        )

    if verdict == "forbidden":
        for seg in addressless:
            yield _finding(
                f"`{seg.overlay or seg.atom}` segment omits its address, but `{mime}` "
                f"declares `whole_address: forbidden` — the medium is a sequence, or its "
                f"address space is already total, so there is no whole for absence to "
                f"name (spec §4.3.2.2)."
            )
        return

    if verdict == "single_unit_only":
        field = schema.get("whole_address_count")
        if not field:
            yield _finding(
                f"`{mime}` declares `whole_address: single_unit_only` but names no "
                f"`whole_address_count` field — the schema is incomplete (spec §7.2.1)."
            )
            return
        # attested byte-facts live under `fields`, not at the block's top level (which
        # carries only `mime`)
        count = (artifact.get("fields") or {}).get(field)
        if count is None:
            for seg in addressless:
                yield _finding(
                    f"`{seg.overlay or seg.atom}` segment omits its address and `{mime}` "
                    f"admits that only for a single unit, but the artifact block carries "
                    f"no `{field}` — unresolved, not admitted. Run `corpus reattest`."
                )
            return
        try:
            n = int(count)
        except (TypeError, ValueError):
            yield _finding(
                f"artifact block `{field}` is {count!r}, which is not a count."
            )
            return
        if n != 1:
            for seg in addressless:
                yield _finding(
                    f"`{seg.overlay or seg.atom}` segment omits its address, but this "
                    f"`{mime}` holds {n} units (`{field}: {n}`) — it is a sequence, and "
                    f"a whole rendering of it names no element (spec §4.3.2.2)."
                )


def _rule_address_region_grammar(post, blocks, root) -> Iterator[Finding]:
    """Every region-op value in every authored address conforms to the region grammar:
    `x,y,WIDTH,HEIGHT` as FRACTIONS of the image in [0,1], origin top-left (spec §6.2).

    This rule exists because nothing else in the system ever held a STORED address to
    the grammar it is written in. The render path validated correctly and raised a clear
    error — but only when someone resolved the address, and nobody did: 1,778 addresses
    on one origin carried PIXEL values (`bbox=0,0,2700,1920`), resolving to nothing at
    all, while lint, health, and compile every one of them read green. A record's
    address is the only provenance a lossless transcription has (§4.3.2.2), so an
    address that materializes nothing is a citation pointing at no bytes — an error, not
    a cosmetic defect.

    Covers sections, segments, and metadata-zone embeds — every place a record stores an
    address. *(3.4: body wikilinks are gone — segment bodies carry no stored addresses at
    all, §4.3.2.2 — so this no longer covers them.)* The judgement itself is
    `functional_uri.region_errors`, which is the same grammar the transform renders
    through, and which deliberately declines to judge a non-numeric value (a
    spreadsheet's `bbox=A1:D20` is a different grammar wearing the same key)."""

    def _check(addr: str, where: str) -> Iterator[Finding]:
        for param, problem in _region_problems(addr):
            yield Finding(
                rule_id="address-region-invalid",
                severity="error",
                message=f"{where} address `{addr}`: {problem}",
                address=addr,
                fields={"param": param},
            )

    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for addr in _addresses(blk.address):
                yield from _check(addr, "section")
            for seg in blk.segments:
                for addr in _addresses(getattr(seg, "address", None)):
                    yield from _check(addr, "segment")
        elif isinstance(blk, _segments.Segment):
            for addr in _addresses(getattr(blk, "address", None)):
                yield from _check(addr, "segment")
    for i, eb in enumerate(_records.iter_embed_blocks(post), 1):
        for addr in _addresses(eb.get("address")):
            yield from _check(addr, f"embed {i}")


def _rule_address_pipe_scalar(post, blocks, root) -> Iterator[Finding]:
    """Flag a multi-region address written as one pipe-joined SCALAR instead of a YAML list.

    Spec §4.3.2.2: a segment spanning several non-contiguous regions carries an address that
    is an ORDERED YAML LIST of single-region address strings. Writing them `|`-joined in one
    scalar (`page=1&bbox=…|page=2&bbox=…`) is a silent corruption — the whole string parses
    as ONE address, so the resolver folds the second region's own params into the first
    address's value and either fails deep in the transform chain or resolves to something
    plausible-looking but wrong. Nothing else catches it: the record parses as valid YAML,
    `compile` and the region-grammar rule above both pass, and the failure surfaces only when
    a reader finally tries to render the region.

    The bracket-pipe form (`[a|b]`) is the MANIFEST's own list encoding (`_fmt_addr`,
    `decompose`) and is correct there; this rule scans the record's/fragment's already-PARSED
    address value, never manifest source text, so only a genuine pipe-joined scalar trips it.
    """

    def _scan(addr: Any, where: str) -> Iterator[Finding]:
        if not isinstance(addr, str) or "|" not in addr:
            return
        parts = [p.strip() for p in addr.split("|") if p.strip()]
        yield Finding(
            rule_id="address-pipe-scalar",
            severity="error",
            message=(
                f"{where} address `{addr}` joins {len(parts)} regions with `|` in a single "
                f"scalar; a multi-region address must be a YAML list (spec §4.3.2.2). "
                "Rewrite as: " + "; ".join(f"- {p}" for p in parts)
            ),
            address=addr,
        )

    for blk in blocks:
        if isinstance(blk, _segments.Section):
            yield from _scan(blk.address, "section")
            for seg in blk.segments:
                yield from _scan(seg.address, "segment")
        elif isinstance(blk, _segments.Segment):
            yield from _scan(blk.address, "segment")
    for i, eb in enumerate(_records.iter_embed_blocks(post), 1):
        yield from _scan(eb.get("address"), f"embed {i}")


def _rule_address_frame_grammar(post, blocks, root) -> Iterator[Finding]:
    """Every `frame=` value in an IMAGE record's stored addresses is a declared axis,
    a valid 1-based index or inclusive span, within the attested `frame_count`, and
    leads its chain (#124; spec §6.2, §4.3.2.2).

    Scope is the image working kind alone: `frame=` is polymorphic (§6.2), and on a
    video it is a timecode this grammar must not judge. Three checks, same discipline
    as its siblings:

    - **Declared**: the mime's `address_scheme` must carry a `frame` param — the first
      code that reads that key; before this rule, an undeclared axis passed every gate
      silently, which is `address-region-invalid`'s 1,778-pixel-address story wearing a
      new key.
    - **Bounded, compare-never-decode**: the count is the attested field the schema
      names in `whole_address_count` (`frame_count`), never a decode of the artifact —
      the whole-address rule's reasoning, one rule up. `frame=` on an unstamped
      artifact is unresolved, not admitted: run `corpus reattest`.
    - **Leading**: `frame=` selects the surface the rest of the chain operates on, and
      the materialization reads the source bytes — a region param before `frame=` is
      an address that renders something other than what it says (§6.2)."""
    from corpus import functional_uri as _furi

    artifact = _records.artifact_block(post) or {}
    mime = (artifact.get("mime") or "").strip()
    if not mime.startswith("image/"):
        return
    schema = None      # loaded lazily — most image records carry no frame= at all
    count: int | None = None

    def _findings(addr: str, where: str) -> Iterator[Finding]:
        nonlocal schema, count
        parts = [p.partition("=") for p in addr.split("&")]
        keys = [k.strip() for k, _, _ in parts]
        if "frame" not in keys:
            return
        if schema is None:
            schema = _schemas.load_mime_schema(root, mime) or {}
            field = schema.get("whole_address_count")
            raw = (artifact.get("fields") or {}).get(field) if field else None
            try:
                count = int(raw) if raw is not None else None
            except (TypeError, ValueError):
                count = None

        def _finding(msg: str) -> Finding:
            return Finding(
                rule_id="address-frame-invalid",
                severity="error",
                message=f"{where} address `{addr}`: {msg}",
                address=addr,
                fields={"mime": mime},
            )

        declared = any(
            (p or {}).get("param") == "frame" for p in schema.get("address_scheme") or []
        )
        if not declared:
            yield _finding(
                f"`{mime}` declares no `frame` axis in its address scheme (spec §7.1) — "
                f"a frame address on this medium names nothing"
            )
            return
        if any(k in _furi.REGION_PARAMS for k in keys[: keys.index("frame")]):
            yield _finding(
                "frame= must lead its chain — it selects the surface the region params "
                "operate on (spec §6.2)"
            )
        if count is None:
            yield _finding(
                "the artifact block carries no attested frame count — unresolved, not "
                "admitted. Run `corpus reattest`."
            )
            return
        for key, sep, value in parts:
            for problem in _furi.frame_errors(key.strip(), value if sep else None, count=count):
                yield _finding(problem)

    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for addr in _addresses(blk.address):
                yield from _findings(addr, "section")
            for seg in blk.segments:
                for addr in _addresses(getattr(seg, "address", None)):
                    yield from _findings(addr, "segment")
        elif isinstance(blk, _segments.Segment):
            for addr in _addresses(getattr(blk, "address", None)):
                yield from _findings(addr, "segment")
    for i, eb in enumerate(_records.iter_embed_blocks(post), 1):
        for addr in _addresses(eb.get("address")):
            yield from _findings(addr, f"embed {i}")


def _rule_address_el_range_grammar(post, blocks, root) -> Iterator[Finding]:
    """Every stored `el=[A-B]` sibling range on an ORDINAL-scheme record (v35, spec
    §6.1.1) is in bounds and its endpoints are real siblings — the owner ruling learned
    from the retired 3.5 flat range's failure mode: a range bridging elements at
    different depths is not one structural thing, so the grammar refuses to let it mean
    anything the tree doesn't declare.

    Scope: `addressing.scheme: ordinal` records only — the frozen dotted/legacy grammars
    have no sibling-range constraint of this shape and are untouched (and cannot even
    reach this rule: their stamps carry no `scheme` key).

    Two independent checks, run separately because they need different access:

    - **Bounds** reads the attested `elements` count straight off the stamp — no artifact
      access, the `address-frame-invalid` precedent — so it always fires when the stamp
      is ordinal, regardless of whether the artifact is resident.
    - **Siblinghood** needs the parsed tree (§6.1.1: "not decidable from two addresses
      alone") and silently does not fire when the artifact is unavailable, unparseable,
      or the stamp's own attested facts disagree with this parse — the
      `segment-address-fidelity` artifact-optional discipline: a defect the artifact
      can't confirm is not reported, and a disagreeing stamp is another gate's finding."""
    addressing = _records.el_addressing(post)
    if not addressing or addressing.get("scheme") != "ordinal":
        return

    from corpus import functional_uri as _furi

    count_raw = addressing.get("elements")
    try:
        count = int(count_raw) if count_raw is not None else None
    except (TypeError, ValueError):
        count = None

    ranges: list[tuple[str, str, Any]] = []  # (address, where, ElOrdinal)

    def _collect(addr: str, where: str) -> None:
        for part in addr.split("&"):
            key, sep, value = part.partition("=")
            if key.strip() != "el":
                continue
            try:
                parsed = _furi.parse_el_ordinal(value if sep else None)
            except ValueError:
                return  # a malformed value is another rule's business — not a range defect
            if parsed.sibling_range is not None:
                ranges.append((addr, where, parsed))

    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for addr in _addresses(blk.address):
                _collect(addr, "section")
            for seg in blk.segments:
                for addr in _addresses(getattr(seg, "address", None)):
                    _collect(addr, "segment")
        elif isinstance(blk, _segments.Segment):
            for addr in _addresses(getattr(blk, "address", None)):
                _collect(addr, "segment")

    if not ranges:
        return

    for addr, where, parsed in ranges:
        a, b = parsed.sibling_range
        if count is not None and b > count:
            yield Finding(
                rule_id="address-el-range-invalid",
                severity="error",
                message=(
                    f"{where} address `{addr}`: range end {b} exceeds the record's "
                    f"attested {count} elements (spec §6.1.1)"
                ),
                address=addr,
                fields={"elements": count},
            )

    # Siblinghood — needs the tree; artifact-optional, and gated on the same two
    # attested-fact checks `extract_el`/`check_fidelity` run first.
    record_id = str(post.metadata.get("id") or "")
    if not record_id:
        return
    from bs4 import BeautifulSoup

    from corpus import mime as _mime
    from corpus.containment import ArtifactMissing, ensure_local_bytes
    from corpus.transforms.html import (
        EL_PARSER_ID,
        ordinals_are_siblings,
        path_root,
        total_element_count,
    )

    parser = str(addressing.get("parser") or "")
    if parser and parser != EL_PARSER_ID:
        return  # a foreign-parser stamp is `_rule_...` territory elsewhere, not this one

    try:
        artifact_path = ensure_local_bytes(
            root, record_id, _mime.extension_for(_records.media_type_for(post))
        )
        html = artifact_path.read_text(encoding="utf-8", errors="replace")
    except (ArtifactMissing, OSError, UnicodeError):
        return

    try:
        soup = BeautifulSoup(html, EL_PARSER_ID)
        if count is not None and total_element_count(soup) != count:
            return  # the trees disagree — another gate's finding, not this one's to judge
        el_root = path_root(soup)
        for addr, where, parsed in ranges:
            a, b = parsed.sibling_range
            try:
                siblings = ordinals_are_siblings(el_root, a, b)
            except ValueError:
                continue  # out of bounds — already reported by the bounds check above
            if not siblings:
                yield Finding(
                    rule_id="address-el-range-invalid",
                    severity="error",
                    message=(
                        f"{where} address `{addr}`: ordinals {a} and {b} are not "
                        f"siblings (spec §6.1.1, the v35 owner ruling) — a range's "
                        f"endpoints must share a parent element"
                    ),
                    address=addr,
                )
    except Exception:
        return  # unparseable — does not fire


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


# ---------- annotation-zone (sweep) rules, spec §4.3.3.6 ---------- #

_STRUCTURAL_KIND = "structural"


def _sweep_kind_resolves(root, kind: str) -> bool:
    """A sweep `kind` resolves the way a segment opener-id does (spec §3, §4.3.3.6): the
    literal `structural` byte-mark kind (checked by the caller before this is reached), a
    bare atom name (`text`/`image`/`audio`/`video` — an unoverlaid content kind), or a
    declared `atom/<atom>/<id>` overlay opener-id (`text/ocr`)."""
    if kind in _schemas.VALID_ATOMS:
        return True
    if "/" not in kind:
        return False
    atom, _, _ = kind.partition("/")
    return _schemas.load_atomic_overlay(root, atom, kind) is not None


def _rule_sweep_shape(post, blocks, root) -> Iterator[Finding]:
    """Every sweep block (`<!--context sweep/extraction-->`, spec §4.3.3.6) carries a
    `kind` that resolves — the literal `structural`, a bare atom, or a declared atom
    overlay opener-id — and a `detector` touch identifier. Both are required overlay
    fields; a sweep missing either is a violation, not a silent no-op."""
    for idx, sweep in enumerate(_records.iter_sweep_blocks(post)):
        fields = sweep.get("fields") or {}
        kind = fields.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            yield Finding(
                rule_id="sweep-kind-invalid",
                severity="error",
                message=f"sweep #{idx + 1} carries no `kind` (spec §4.3.3.6: required).",
            )
        elif kind.strip() != _STRUCTURAL_KIND and not _sweep_kind_resolves(root, kind.strip()):
            yield Finding(
                rule_id="sweep-kind-invalid",
                severity="error",
                message=(
                    f"sweep #{idx + 1} `kind: {kind!r}` resolves to neither the literal "
                    f"`structural` nor a declared atom overlay — declare it under "
                    f"schema/atom/<atom>/ or fix the id (spec §4.3.3.6)."
                ),
            )
        det = fields.get("detector")
        if not isinstance(det, str) or not _TOUCH_RE.match(det):
            yield Finding(
                rule_id="sweep-detector-format",
                severity="error",
                message=(
                    f"sweep #{idx + 1} `detector: {det!r}` is not a valid touch "
                    f"identifier (spec §4.3.3.6)."
                ),
            )


def _rule_sweep_address_grammar(post, blocks, root) -> Iterator[Finding]:
    """A sweep block's `address:` (when present) parses in the record's mime address
    scheme (spec §4.3.3.6: "`address` MUST parse in the record's scheme"). Reuses the
    same two checks a stored segment address gets: any region-shaped value (`bbox=`,
    `crop=`, ...) conforms to the region grammar (`address-region-invalid`'s), and every
    param key the band chains is one the mime's `address_scheme` actually declares —
    an undeclared axis names nothing, same reasoning as the `frame=` declared-ness check."""
    artifact = _records.artifact_block(post) or {}
    mime = (artifact.get("mime") or "").strip()
    schema = _schemas.load_mime_schema(root, mime) if mime else None
    declared_params = {
        (p or {}).get("param") for p in (schema or {}).get("address_scheme") or []
    }
    for idx, sweep in enumerate(_records.iter_sweep_blocks(post)):
        fields = sweep.get("fields") or {}
        addr = fields.get("address")
        if not addr or not isinstance(addr, str):
            continue  # missing/malformed `address` — `context-anchor-format` covers the latter
        for param, problem in _region_problems(addr):
            yield Finding(
                rule_id="sweep-address-invalid",
                severity="error",
                message=f"sweep #{idx + 1} address `{addr}`: {problem}",
                address=addr,
                fields={"param": param},
            )
        if schema is None:
            continue
        for part in addr.split("&"):
            key = part.partition("=")[0].strip()
            if key and key not in declared_params:
                yield Finding(
                    rule_id="sweep-address-invalid",
                    severity="error",
                    message=(
                        f"sweep #{idx + 1} address `{addr}`: `{key}=` is not a declared "
                        f"axis of `{mime}` (spec §7.1) — a sweep band naming an "
                        f"undeclared axis names nothing."
                    ),
                    address=addr,
                    fields={"param": key},
                )


def _sweep_range_params(schema: dict[str, Any] | None) -> set[str]:
    """Param keys the mime schema declares `type: range` (e.g. `time_range`) — the axes
    §4.3.3.6's overlap check can compare numerically."""
    return {
        (p or {}).get("param")
        for p in (schema or {}).get("address_scheme") or []
        if (p or {}).get("type") == "range"
    }


def _addr_params(addr: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for part in addr.split("&"):
        key, sep, value = part.partition("=")
        key = key.strip()
        if key:
            out[key] = value if sep else None
    return out


def _parse_numeric_range(value: str) -> tuple[float, float] | None:
    """Parse a `<start>-<end>` (or bare `<n>`) range value as a numeric span — honest
    only for a genuinely numeric axis (the `time_range=<s>-<e>` mold, spec §4.3.3.6).
    Anything else (an A1 range, a non-numeric token) returns None so the caller falls
    back to the conservative "not comparable" path rather than misreading a foreign
    grammar under the same param name."""
    raw = value.strip()
    parts = raw.split("-")
    try:
        if len(parts) == 1:
            v = float(parts[0])
            return (v, v)
        if len(parts) == 2:
            return (float(parts[0]), float(parts[1]))
    except ValueError:
        return None
    return None


def _sweep_bands_overlap(
    addr1: str | None, addr2: str | None, range_params: set[str]
) -> bool:
    """Whether two sweep bands of the SAME `kind` overlap (spec §4.3.3.6). A missing
    address is the whole transport and overlaps every band of its kind. Where the two
    bands share a schema-declared range axis, the check is numeric interval overlap on
    that axis (any disjoint shared axis proves the bands don't overlap); where they
    share a non-range axis, unequal values on it likewise prove no overlap (different
    `stream_id=`, say). Absent any axis that disproves overlap, this is CONSERVATIVE —
    it flags — because an unproven overlap is a worse failure mode than a false alarm on
    two sweeps of the same kind that turn out to be genuinely disjoint (spec §4.3.3.6:
    "a widened re-sweep replaces the band, never stacks on it")."""
    if not addr1 or not addr2:
        return True
    p1 = _addr_params(addr1)
    p2 = _addr_params(addr2)
    shared = set(p1) & set(p2)
    for key in shared - range_params:
        if p1[key] != p2[key]:
            return False
    shared_range = shared & range_params
    if not shared_range:
        return True  # no comparable range axis between the two — conservative
    for key in shared_range:
        r1 = _parse_numeric_range(p1[key] or "")
        r2 = _parse_numeric_range(p2[key] or "")
        if r1 is None or r2 is None:
            return True  # not cleanly numeric — conservative
        if r1[1] < r2[0] or r2[1] < r1[0]:
            return False  # this axis is disjoint: bands provably don't overlap
    return True


def _rule_sweep_band_overlap(post, blocks, root) -> Iterator[Finding]:
    """No two sweep blocks of the same `kind` may claim overlapping bands (spec
    §4.3.3.6: "two sweeps of the same `kind` MUST NOT overlap — a widened re-sweep
    replaces the band, never stacks on it")."""
    artifact = _records.artifact_block(post) or {}
    mime = (artifact.get("mime") or "").strip()
    schema = _schemas.load_mime_schema(root, mime) if mime else None
    range_params = _sweep_range_params(schema)
    by_kind: dict[str, list[tuple[int, str | None]]] = {}
    for idx, sweep in enumerate(_records.iter_sweep_blocks(post)):
        fields = sweep.get("fields") or {}
        kind = fields.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            continue  # sweep-kind-invalid already covers this
        addr = fields.get("address")
        by_kind.setdefault(kind.strip(), []).append(
            (idx, addr if isinstance(addr, str) else None)
        )
    for kind, entries in by_kind.items():
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                idx1, addr1 = entries[i]
                idx2, addr2 = entries[j]
                if _sweep_bands_overlap(addr1, addr2, range_params):
                    yield Finding(
                        rule_id="sweep-band-overlap",
                        severity="error",
                        message=(
                            f"sweep #{idx1 + 1} and sweep #{idx2 + 1} both vouch for "
                            f"`kind: {kind}` over overlapping bands "
                            f"({addr1 or 'whole transport'} / {addr2 or 'whole transport'}) "
                            f"— a widened re-sweep replaces its band, never stacks "
                            f"(spec §4.3.3.6)."
                        ),
                        fields={"kind": kind},
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


def _iter_segments_labelled(blocks):
    for top_i, blk in enumerate(blocks, 1):
        if isinstance(blk, _segments.Section):
            for sub_i, child in enumerate(blk.segments, 1):
                yield f"section {top_i}/segment {sub_i}", child
        elif isinstance(blk, _segments.Segment):
            yield f"segment {top_i}", blk


def _rule_segment_body_lossless_contract(post, blocks, root) -> Iterator[Finding]:
    """Body ⟺ lossless (spec §4.3.2.3). A `text` segment whose atomic overlay opts out of
    lossless (`enables_lossless: false`, e.g. `text/data-table-dynamic`) must stay a
    body-empty marker: the segment cannot narrate its own region (spec §4.2.3, §4.3.1.4 —
    no field survived 3.5 for a segment to carry that narration in). Where the region's
    content genuinely matters and can't be losslessly rendered, the honest residue is a
    typed `issue` block at that address (spec §12.27, §4.3.3.2), not a description field."""
    for label, seg in _iter_segments_labelled(blocks):
        if seg.atom != "text" or not seg.overlay:
            continue
        atom, _, sub = str(seg.overlay).partition("/")
        overlay = _schemas.load_atomic_overlay(root, atom, sub or atom)
        if not isinstance(overlay, dict) or overlay.get("enables_lossless") is not False:
            continue
        body = (seg.body or "").strip()
        if not body:
            continue
        snippet = body if len(body) <= 80 else body[:77] + "…"
        yield Finding(
            rule_id="segment-body-requires-lossless",
            severity="error",
            message=(
                f"{label} (`{seg.overlay}`) carries a body, but its overlay is non-lossless "
                f"(`enables_lossless: false`) — leave the marker body-empty; if the region's "
                f"content matters and can't be losslessly rendered, the honest residue is a "
                f"typed `issue` block at this address (spec §12.27, §4.3.3.2), not a "
                f"transcription. Body preview: {snippet!r}"
            ),
            address=_addr_str(seg.address),
            fields={"overlay": seg.overlay, "body_chars": len(body)},
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


def _embed_address_set(post) -> set[str]:
    out: set[str] = set()
    for eb in _records.iter_embed_blocks(post):
        out.update(_addresses(eb.get("address")))
    return out


def _rule_embed_unreferenced(post, blocks, root) -> Iterator[Finding]:
    """A metadata-zone embed whose address is referenced by no segment.

    *(3.4: body wikilinks are gone, §4.3.2.2 — a segment address is the only kind of
    reference left to check.)*

    Skipped for a **manifest** record — one with no content-zone segments at all (e.g. a
    self_contained archive recorded as embeds, where each member is an embedded transport).
    There is no content flow to position the embeds within, so they ARE the content, not
    flow-assets, and "unreferenced" is not a defect.

    Also skipped for a **message/rfc822** record: its `part=<N>` embeds are the email's MIME
    members (attachments, inline images, nested messages) declared for promotion, not
    body-flow assets a mechanical draft can position — the normalizer links an inline image
    into the body when it belongs there (spec §12.11).

    Also skipped for a member that already has its OWN promoted record (§8.1, §12.9's member
    index — same `address → transport → record path` lookup `placed-member-not-promoted`
    uses, below). "Unreferenced" exists to catch a member nobody has done anything with; a
    member that has been promoted and simply received no rendering yet (§12.30's reseat, for
    one — a placement is only owed to a member that was actually SEATED, never fabricated for
    one that wasn't) has plainly been acted on. Cheap for the same reason
    `placed-member-not-promoted` is: existence is a `stat`, no record loaded. Degrades to the
    unconditional warning when `root` is unavailable — this rule ran root-free before the
    member-index check existed, and a missing root should widen what it catches, never
    silently narrow it to nothing."""
    if _records.media_type_for(post) == "message/rfc822":
        return
    has_segment = any(
        isinstance(b, _segments.Segment)
        or (isinstance(b, _segments.Section) and b.segments)
        for b in blocks
    )
    if not has_segment:
        return
    referenced: set[str] = set()
    # Only SEGMENT addresses reference embeds (§4.3.1.4 — address membership on segments).
    # A section's span address does not: a 3.0 section is a form span, not an
    # embed-referencing grouping, and the 2.x leniency that counted it masked latent orphans.
    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for child in blk.segments:
                referenced.update(_addresses(getattr(child, "address", None)))
        elif isinstance(blk, _segments.Segment):
            referenced.update(_addresses(getattr(blk, "address", None)))
    # A segment that CHAINS INTO an embed references it: `el=3&bbox=…` is a crop of the
    # `el=3` asset, which is precisely how a lossless transcription cites the bytes it read
    # (§4.3.2.2). Matching only whole address strings would call such an embed an orphan on
    # the strength of a crop that plainly names it — and a crop is exactly what a faithful
    # transcription leaves behind once it has superseded the marker (§7.8 `embed_rendered`).
    chained = {a.split("&", 1)[0] for a in referenced if "&" in a}
    referenced |= chained
    members = _member_address_transports(post) if root is not None else {}
    for i, eb in enumerate(_records.iter_embed_blocks(post), 1):
        addrs = _addresses(eb.get("address"))
        if not addrs or any(a in referenced for a in addrs):
            continue
        if root is not None and any(
            (hexval := members.get(a)) and _paths.record_path(root, hexval).is_file()
            for a in addrs
        ):
            continue
        yield Finding(
            rule_id="embed-unreferenced",
            severity="warning",
            message=(
                f"embed {i} (`{eb.get('media_type')}` at `{','.join(addrs)}`) is not "
                f"referenced by any segment."
            ),
            address=",".join(addrs),
            fields={"media_type": eb.get("media_type")},
        )


def _member_address_transports(post) -> dict[str, str]:
    """*(3.8)* `member address → member transport hex` over every roster row (§4.3.1.4). The
    dedup rule makes this well-defined: identical content collapses to one row, so an address
    belongs to at most one member. The map is what a placement resolves through — address to
    row to blake3 to record — and what tells a content-atom segment it is standing on bytes
    that are not its record's to claim."""
    out: dict[str, str] = {}
    for row in _records.iter_members(post):
        hexval = str(row.get("transport") or "").partition(":")[2]
        for addr in _addresses(row.get("address")):
            out[addr] = hexval
    return out


def _rule_member_rendered_on_parent(post, blocks, root) -> Iterator[Finding]:
    """*(3.8, §4.3.2.4)* A content-atom segment standing at a **member's** address.

    A member is a transport with its own blake3, its own roster row, and — once positioned —
    its own record. The containing record positions it with a `placement` and says nothing
    else: an `image` marker there would claim residue in bytes it does not own, and a
    `text/<id>` transcription there is a rendering of someone else's bytes in the one place
    where it cannot be shared. Both are the same defect at different volumes, so both are one
    error with one repair: promote the member, move the rendering to the leaf, place it here.

    A CHAINED address counts: `el=<path>&bbox=…` crops the member's own pixels, so it is a
    rendering of the member's bytes wearing the container's address (§4.3.1.4). It re-homes onto
    the leaf with the crop kept and the `el=` prefix dropped — the fractions were always
    relative to the member's extent — except a whole-frame crop, which is not a region at all
    and takes the whole-transport address (§4.3.2.2).

    Structural byte-marks are exempt: a boundary the source declares at a position is a fact
    about this transport whatever sits there (§4.3.2.3)."""
    members = _member_address_transports(post)
    if not members:
        return
    for top_i, blk in enumerate(blocks, 1):
        segs = (
            [(f"section {top_i}/segment {j}", s) for j, s in enumerate(blk.segments, 1)]
            if isinstance(blk, _segments.Section)
            else ([(f"segment {top_i}", blk)] if isinstance(blk, _segments.Segment) else [])
        )
        for label, seg in segs:
            if not seg.is_content:
                continue
            hit = [a for a in _addresses(seg.address) if a.split("&", 1)[0] in members]
            if not hit:
                continue
            what = "renders" if (seg.body or "").strip() else "marks"
            yield Finding(
                rule_id="member-rendered-on-parent",
                severity="error",
                message=(
                    f"{label} ({seg.overlay or seg.atom}) {what} the member at "
                    f"`{','.join(hit)}`, whose bytes are their own record's to represent: "
                    f"promote the member and place it here instead (spec §4.3.2.4)."
                ),
                address=",".join(hit),
                fields={"member": f"blake3:{members[hit[0].split('&', 1)[0]]}"},
            )


def _rule_placement_without_member(post, blocks, root) -> Iterator[Finding]:
    """*(3.8, §4.3.2.4)* A placement whose address appears in no roster row.

    A placement's entire content is the member it names, and it names it by the address they
    share. One naming nothing is not a weak statement — it is an unresolvable one, and no
    reader can tell whether the roster lost a row or the address is wrong."""
    members = _member_address_transports(post)
    for seg in _iter_all_segments(blocks):
        if not seg.is_placement:
            continue
        addrs = _addresses(seg.address)
        # A DECONSTRUCTED placement chains the member's address with a suffix naming one of
        # the leaf's own segment addresses (§4.3.2.4), so the member is named by the BASE.
        if addrs and not any(a.split("&", 1)[0] in members for a in addrs):
            yield Finding(
                rule_id="placement-without-member",
                severity="error",
                message=(
                    f"placement at `{','.join(addrs)}` names no member — no roster row "
                    f"carries that address (spec §4.3.2.4/§4.3.1.4)."
                ),
                address=",".join(addrs),
            )


def _leaf_segment_addresses(root, hexval: str) -> tuple[set[str], bool] | None:
    """The distinct addresses the leaf declares on its own segments, and whether any segment
    is address-less (i.e. renders the whole transport, §4.3.2.2 — which cannot be chained to).
    `None` when the leaf is unreadable; its absence is `placed-member-not-promoted`'s finding,
    never restated here."""
    path = _paths.record_path(root, hexval)
    if not path.is_file():
        return None
    try:
        leaf = _records.load(path)
        blocks = _segments.iter_blocks(leaf.content or "")
    except Exception:
        return None
    addrs: set[str] = set()
    whole = False
    for seg in _iter_all_segments(blocks):
        if not (seg.is_content or seg.is_structural):
            continue
        got = _addresses(seg.address)
        if not got:
            whole = True
        addrs.update(got)
    return addrs, whole


def _rule_placement_deconstructed(post, blocks, root) -> Iterator[Finding]:
    """*(3.8, §4.3.2.4)* The two constraints on a **deconstructed import** — match, and
    exhaustive.

    A parent may position a member's parts individually by chaining the member's address with
    a suffix, but only against regions the **leaf has already declared**, and then against all
    of them. Both halves matter and they fail differently:

    - **Match** keeps the parent out of measuring someone else's pixels. A suffix the leaf does
      not carry is a region the parent invented — and an invented crop resolves to *something*
      forever, which is §12.24's failure exactly: an address wearing a green light while
      pointing at bytes nobody chose.
    - **Exhaustive** stops a parent quietly dropping a region. Partial placement is a silent,
      plausible omission, and it would let *some of the member* and *the member* look alike in
      the record while differing in what they show.

    Together they make drift mechanical: a leaf that re-crops, gains a region, or loses one
    breaks its parents' addresses at the next gate rather than sliding under them.

    **The grain is the address, not the segment.** A leaf may carry several segments at one
    address — identity is (opener-id, address), so a `text` and a `text/data-table` over the
    same region legitimately share one — and a placement naming that address imports all of
    them. So `declared` is a set of ADDRESSES: a member with four segments over two regions is
    exhaustively placed by two placements, not four.

    Costs a record load per deconstructed member, so it runs ONLY when a chained placement
    exists — the ordinary whole-import parent pays nothing, which is what keeps this out of the
    perf class §12.25 warns about."""
    if root is None:
        return
    members = _member_address_transports(post)
    if not members:
        return
    # member base address → the chained suffixes placed against it (None = placed whole)
    placed: dict[str, set[str | None]] = {}
    for seg in _iter_all_segments(blocks):
        if not seg.is_placement:
            continue
        for addr in _addresses(seg.address):
            base, sep, suffix = addr.partition("&")
            if base not in members:
                continue
            placed.setdefault(base, set()).add(suffix if sep else None)

    for base, suffixes in sorted(placed.items()):
        chained = {s for s in suffixes if s is not None}
        if not chained:
            continue  # a plain whole import asks nothing of the leaf
        hexval = members[base]
        if None in suffixes:
            yield Finding(
                rule_id="placement-form-mixed",
                severity="error",
                message=(
                    f"the member at `{base}` (`blake3:{hexval[:12]}…`) is placed both whole "
                    f"and deconstructed: a member is placed whole or placed in full, never "
                    f"both (spec §4.3.2.4)."
                ),
                address=base,
                fields={"member": f"blake3:{hexval}"},
            )
            continue
        got = _leaf_segment_addresses(root, hexval)
        if got is None:
            continue  # unreadable/absent leaf — `placed-member-not-promoted` owns that
        declared, whole = got
        if whole:
            yield Finding(
                rule_id="placement-region-undeclared",
                severity="error",
                message=(
                    f"the member at `{base}` (`blake3:{hexval[:12]}…`) renders its whole "
                    f"transport, so it has no regions to place: import it whole (spec "
                    f"§4.3.2.4, §4.3.2.2)."
                ),
                address=base,
                fields={"member": f"blake3:{hexval}"},
            )
            continue
        for extra in sorted(chained - declared):
            yield Finding(
                rule_id="placement-region-undeclared",
                severity="error",
                message=(
                    f"placement at `{base}&{extra}` names a region the member's own record "
                    f"does not declare: a parent may place a region the leaf has declared, "
                    f"never one it measured for itself (spec §4.3.2.4)."
                ),
                address=f"{base}&{extra}",
                fields={"member": f"blake3:{hexval}"},
            )
        missing = sorted(declared - chained)
        if missing:
            yield Finding(
                rule_id="placement-not-exhaustive",
                severity="error",
                message=(
                    f"the member at `{base}` (`blake3:{hexval[:12]}…`) is placed "
                    f"deconstructed but {len(missing)} of its {len(declared)} declared "
                    f"region(s) are unplaced (`{'`, `'.join(missing)}`): a member is placed "
                    f"whole or placed in full (spec §4.3.2.4)."
                ),
                address=base,
                fields={"member": f"blake3:{hexval}", "unplaced": missing},
            )


def _rule_placed_member_not_promoted(post, blocks, root) -> Iterator[Finding]:
    """*(3.8, §4.3.2.4)* A placed member with no record of its own — **placement means
    promotion**, and this is the half of that rule that can only live on the parent.

    The complement — a promoted member awaiting its rendering pass — is deliberately NOT here.
    That is demand, not a defect, it belongs on the leaf, and it is measured as normalization
    pressure (§8.5). What this rule catches is a record that positioned bytes and left nothing
    to reach: the placement resolves to a hash with no record behind it.

    Cheap by construction, which is why it can run in the default gate on a record with 214
    members: the leaf's path is a pure function of the roster hash (§12.1's sharding), so
    existence is a `stat` and no record is loaded. The state of a leaf that DOES exist is
    never read here — that read is what would have made this the perf class §12.25 warns
    about."""
    if root is None:
        return
    members = _member_address_transports(post)
    reported: set[str] = set()
    for seg in _iter_all_segments(blocks):
        if not seg.is_placement:
            continue
        for addr in _addresses(seg.address):
            hexval = members.get(addr)
            if not hexval or hexval in reported:
                continue
            if _paths.record_path(root, hexval).is_file():
                continue
            reported.add(hexval)
            yield Finding(
                rule_id="placed-member-not-promoted",
                severity="error",
                message=(
                    f"the member placed at `{addr}` (`blake3:{hexval[:12]}…`) has no record: "
                    f"placing a member obliges promoting it, or nothing carries its "
                    f"representation (spec §4.3.2.4, §8.1)."
                ),
                address=addr,
                fields={"member": f"blake3:{hexval}"},
            )


def _rule_embed_missing_target(post, blocks, root) -> Iterator[Finding]:
    """An image segment at an address that no embed in this record carries.
    Artifact-self-slices (`frame=`/`page=`/`bbox=` rendered from the artifact) and
    lineage-chained references (`turn=N&att=M`, §4.3.1.4) need no embed — the resolver
    materializes them on demand.

    *(3.4: the body-wikilink half is gone — segment bodies carry no stored addresses at
    all, §4.3.2.2 — so this rule now checks image segments only.)*

    *(3.8: and the rule's meaning inverts with §4.3.2.4 — a marker at a member's address is
    now `member-rendered-on-parent`'s error, so what remains here is the complement, and
    together the two say the one thing §4.3.2.2 requires: a content-atom marker addresses a
    region of its OWN transport. This half catches the marker that addresses nothing at all.)*"""
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


# ---------- body sanity (markdown) ---------- #

_HTML_RESIDUE_RE = re.compile(r"<\s*(script|style|iframe)\b", re.IGNORECASE)
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
    # *(3.3)* A TERMINAL-governed record (§7.8) legitimately has an empty content zone AND
    # no embeds (e.g. a bare `form/passthrough` stream/still) — the contract prescribes
    # exactly that. Exempt outright, ahead of the embeds check below.
    governing = _shape.governing_form(post, root)
    if governing is not None and governing[1]:
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


_BODY_WIKILINK_RE = re.compile(r"!?\[\[\s*(?:corpus://|[0-9a-f]{64})", re.IGNORECASE)


def _rule_body_corpus_link_forbidden(post, blocks, root) -> Iterator[Finding]:
    """A segment body carries **no intra-corpus links** (spec §4.3.2.2, §5.1 — the 3.4
    body-link retirement, §12.26). Both stored forms are gone: a bare `corpus://`
    functional URI, and a `[[`/`![[` wikilink opening onto either a `corpus://` URI or a
    raw 64-hex blake3 hash. The resolution either would name is derivable at read time
    from the record's own bytes plus its lineage (§12.4.7), so storing it duplicates a
    derivation and can disagree with it. Nothing inside one transport ever needed a link
    either — an inline asset is its own positioning segment, addressed on the artifact's
    own axis.

    A bare `[[` alone is NOT the signal — plenty of faithfully-transcribed source carries
    it innocently (Swift's `[[Foo]]` nested-array type syntax, for one, caught live during
    verification). Only a `[[`/`![[` opening directly onto the corpus-reference grammar
    counts.

    Scoped to **segment bodies in the content zone only**, via `_iter_all_segments` —
    never the metadata zone. A promoted record's origin-block lineage `uri:
    corpus://<container>?<address>` (present on thousands of records) is capture
    history, not a lookup route (§8.1, §12.15), and lives in `post.metadata`, not in any
    segment body, so it is structurally out of this rule's reach."""
    for seg in _iter_all_segments(blocks):
        body = seg.body or ""
        if "corpus://" in body or _BODY_WIKILINK_RE.search(body):
            yield Finding(
                rule_id="body-corpus-link-forbidden",
                severity="error",
                message=(
                    "segment body carries a `corpus://` reference or a `[[`/`![[` "
                    "wikilink onto one — segment bodies carry no intra-corpus links "
                    "(spec §4.3.2.2); express cross-artifact connection via the "
                    "source's own URL instead."
                ),
                address=_addr_str(seg.address),
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
    """A structural byte-mark (§4.3.2.3) carries a positive `level`, and its BODY is the
    mark's own text (3.8, §12.32) — an empty body being an unlabeled boundary, which is
    what an absent `mark:` used to say. The parser normalizes most of the shape (address
    required, level cast to int, a legacy `mark:`/`entry:` folded into the body); this
    guards the residue the grammar admits — a non-positive level, and a `mark:` field that
    somehow survived the fold."""
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
        if "mark" in (seg.extra or {}) or "entry" in (seg.extra or {}):
            yield Finding(
                rule_id="structural-mark-retired",
                severity="error",
                message=(
                    "structural byte-mark carries a retired `mark:`/`entry:` field; the "
                    "mark's own text is the segment BODY (spec §4.3.2.3, 3.8 — §12.32). A "
                    "scalar cannot hold what a heading renders."
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
    """The low integer of an axis value (`3` → 3, `2-6` → 2), or None when non-numeric.

    None is also the correct, deliberate outcome for a string-valued axis — e.g. a
    spreadsheet's `sheet=<tab-name>` (`form/document`'s `sheet` axis, xlsx/xls mime
    schemas): a tab name's lexical value bears no relationship to its true position
    (workbook tab order, preserved by the drafter/normalizer and not re-derivable from
    the address string alone), so treating a numeric-looking tab name (`sheet=2024`) as
    an orderable index would be actively wrong, not just inert. The monotonic check
    below skips ordering entirely when `_axis_low` returns None — correct for any
    non-sequence-numbered axis, never a false positive. A form wanting real
    interleaving-detection over such an axis needs contiguity (no segment for a given
    axis value after another value has intervened), not ascending-integer monotonicity;
    no form currently declares that check, so it isn't implemented here."""
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

        # `embed_rendered` — RETIRED in 3.8 (§4.3.2.4, §12.30), and retired rather than
        # re-keyed, because the amendment answers its question structurally instead of by
        # conformance. The check bound an attested member and asked that the span carry exactly
        # one of {a `lossless` rendering, a body-empty `marker`} for it — an XOR that was
        # sjrahn's 2026-07-26 ruling and correct for as long as a parent was where a member's
        # rendering lived. Under 3.8 it never is: a member is either **placed**, in which case
        # its own record renders it and the parent carries a placement, or **unplaced**, in
        # which case nothing is owed at all. So both branches of the XOR are now violations of
        # a stronger rule (`member-rendered-on-parent`), and the residual question — has the
        # leaf rendered yet — is DEMAND on the leaf (normalization pressure, §8.5), not a
        # conformance failure of the parent's form. A form has no standing to demand a
        # rendering; that was already the check's own caveat, and 3.8 makes it structural.
        #
        # *(A 2026-07-27 pass briefly inverted the XOR to `embed_marked` — "the marker is owed
        # either way" — citing a §4.3.2.2 paragraph drafted the same day. The paragraph was not
        # the spec speaking; the ruling stood, and now the whole check goes. #93, #101.)*
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


def _rule_terminal_stored_rendering(post, blocks, root) -> Iterator[Finding]:
    """The terminal-contract inversion (spec §7.8, 3.3): a TERMINAL contract
    (`form/passthrough` / `form/manifest`, or a corpus-declared one — keyed on the
    `terminal: true` overlay marker via `shape.governing_form`, never a hardcoded form id)
    prescribes the ABSENCE of a stored rendering. Every other form's conformance requires
    the shape to be PRESENT; this one requires it to be ABSENT — a record governed by a
    terminal contract that carries a stored content-zone rendering (a body-bearing segment,
    or any non-byte-mark content beyond structural marks and the optional whole-record
    opener — `has_stored_rendering`) is the violation, and it is an error: the contract was
    adopted as the judgment that no rendering would ever earn its place, so one existing
    means either the judgment was wrong or the rendering is stale residue either way."""
    resolved = _shape.governing_form(post, root)
    if resolved is None:
        return
    form_id, is_terminal = resolved
    if not is_terminal:
        return
    if _records.has_stored_rendering(post):
        yield Finding(
            rule_id="terminal-stored-rendering",
            severity="error",
            message=(
                f"record is governed by terminal contract `form/{form_id}` (spec §7.8) but "
                f"carries a stored content-zone rendering — a terminal contract prescribes "
                f"the ABSENCE of a stored rendering; drop the rendering or adopt a rendering "
                f"contract instead of a terminal one."
            ),
            fields={"form": form_id},
        )


# ---------- the link gate (#52's third acceptance gate, #118) ---------- #


def _rule_subject_link_flattened(post, blocks, root) -> Iterator[Finding]:
    """A normalize pass that flattens a subject-region anchor — keeps the source `<a href>`'s
    text in the body but drops the link itself — cannot reach finalize (spec #118, #52).

    Reads artifact bytes, unlike every other rule in `_REGISTRY`: a record's origin overlay
    must declare at least one `regions:` row with `renders: subject` (config-driven — a host
    with no declaration is never judged, spec §7.2) before this rule touches the artifact at
    all, so a corpus with no such overlay pays nothing for it. Beyond that gate, an
    unavailable artifact or a region-resolve failure means this rule silently does not fire
    (lint's parse-tolerant discipline, same as every other artifact-optional check) — it is
    never the reason a record fails to lint.

    The detector itself is `corpus.linkscan.scan_flattened`, the same function
    `scripts/accept_alldata.py`'s `check_links` now delegates to — ported rather than
    re-derived so the two can never drift (module docstring). Deliberately NOT exempted from
    any migration-verb neutrality allowlist: the neutrality gates (`home_rail.py`,
    `home_crumb.py`, `drop_retired.py`) compare this rule's finding count like any other, so a
    rewrite that RAISES flattening still holds — exactly right — while a pre-existing
    flattened anchor a migration doesn't touch is not this rule's problem to fix."""
    if _records.media_type_for(post) != "text/html":
        return
    record_id = str(post.metadata.get("id") or "")
    if not record_id:
        return

    decl: list[dict[str, Any]] | None = None
    for origin in _records.iter_origin_blocks(post):
        host = str(origin.get("id") or "")
        if not host:
            continue
        rows = _schemas.origin_regions(root, host)
        if any(row.get("renders") == "subject" for row in rows):
            decl = rows
            break
    if decl is None:
        return  # no origin overlay declares a subject region — nothing to judge (§7.2)

    from corpus import mime as _mime
    from corpus.containment import ArtifactMissing, ensure_local_bytes
    from corpus.linkscan import scan_flattened
    from corpus.regionmap import resolve as _resolve_regions

    ext = _mime.extension_for(_records.media_type_for(post))
    try:
        artifact_path = ensure_local_bytes(root, record_id, ext)
    except ArtifactMissing:
        return  # artifact unavailable — silently does not fire, not a lint failure

    html = artifact_path.read_text(encoding="utf-8", errors="replace")
    try:
        rmap = _resolve_regions(html, decl)
    except Exception:
        return  # region-resolve failure — does not fire

    self_urls = [
        str(u)
        for origin in _records.iter_origin_blocks(post)
        for u in ((origin.get("fields") or {}).get("uri") or [])
    ]
    result = scan_flattened(html, blocks, rmap, self_urls=self_urls)
    if not result["flattened"]:
        return
    samples = "; ".join(result["sample"])
    yield Finding(
        rule_id="subject-link-flattened",
        severity="error",
        message=(
            f"{result['flattened']} of {result['subject_anchors']} subject-region anchor(s) "
            f"render flattened — the link text survives in the body but the link does not "
            f"({samples}); a normalize pass must preserve source links as [text](url) (#118)"
        ),
        fields={
            "subject_anchors": result["subject_anchors"],
            "flattened": result["flattened"],
            "sample": result["sample"],
        },
    )


# ---------- the address-fidelity gate (#159) ---------- #


def _rule_segment_address_fidelity(post, blocks, root) -> Iterator[Finding]:
    """A segment whose body text does not come from the element its address names (#159).

    The #52 drain's biggest defect family, and the one no gate was asking about: lint judged
    the address's grammar and the body's shape, `check_order` judged address sequence, the
    link gate judged anchors — and nothing compared the two sides of the same segment. The
    detector is `corpus.fidelity.check_fidelity`, shared with `scripts/accept_alldata.py`'s
    census exactly as `subject-link-flattened` shares `linkscan.scan_flattened`.

    **Stamped records only.** `records.el_addressing` is the §6.1.1 grammar dispatch: an
    unstamped record's `el=5` names the 5th WHITELISTED element under the frozen pre-3.6
    index, not the body's 5th element child, so resolving it through the path walk would
    compare the segment against the wrong element and report the very defect this rule
    exists to find. Legacy-grammar records are frozen and never judged here. A stamped
    record judges under EITHER live grammar (`check_fidelity` dispatches on
    `addressing.scheme`, v35) — ordinal or the frozen 3.6 dotted path.

    Reads artifact bytes, and keeps the artifact-optional discipline of the link gate: an
    absent artifact, an unparseable one, or a stamp whose attested parser/element-count
    disagrees with this parse all mean the rule silently does not fire. A disagreeing stamp
    in particular is another gate's finding — under a different tree every address resolves
    somewhere else, so anything this rule said about it would be noise.

    The severity split is initial calibration, to be tuned against the drained population:
    `misplaced` (borrowed text) and `unresolvable` (an address naming nothing) are errors,
    `dropped` (addressed text the body never renders) and `unsourced` (body text the
    artifact carries nowhere) warn."""
    if _records.media_type_for(post) != "text/html":
        return
    record_id = str(post.metadata.get("id") or "")
    if not record_id:
        return
    addressing = _records.el_addressing(post)
    if addressing is None:
        return  # legacy el= grammar (§12.28) — frozen, never judged under the path walk

    from corpus import mime as _mime
    from corpus.containment import ArtifactMissing, ensure_local_bytes
    from corpus.fidelity import KINDS, check_fidelity

    ext = _mime.extension_for(_records.media_type_for(post))
    try:
        artifact_path = ensure_local_bytes(root, record_id, ext)
    except ArtifactMissing:
        return  # artifact unavailable — silently does not fire, not a lint failure

    # The overlay's `renders: never` regions, fetched the way `subject-link-flattened` does:
    # a region §7.2 says nobody renders is nobody's to have dropped. A record whose origin
    # declares none is judged in full, which is the honest default for an unmapped host.
    regions: list[dict[str, Any]] = []
    for origin in _records.iter_origin_blocks(post):
        host = str(origin.get("id") or "")
        if host and (rows := _schemas.origin_regions(root, host)):
            regions = rows
            break

    try:
        html = artifact_path.read_text(encoding="utf-8", errors="replace")
        result = check_fidelity(html, blocks, addressing, regions)
    except Exception:
        return  # unparseable, or a stamp attesting a different tree — does not fire

    severity = {
        "misplaced": "error",
        "unresolvable": "error",
        "dropped": "warning",
        "unsourced": "warning",
    }
    message = {
        "misplaced": "body line(s) that come from elsewhere in the artifact, not from the "
                     "element the segment's address names",
        "unresolvable": "segment address(es) that resolve to no element in the artifact",
        "dropped": "addressed element(s) whose text the segment body never renders",
        "unsourced": "body line(s) that appear nowhere in the artifact",
    }
    for kind in KINDS:
        findings = [f for f in result["findings"] if f["kind"] == kind]
        if not findings:
            continue
        samples = [s for f in findings for s in f["sample"]][:5]
        yield Finding(
            rule_id="segment-address-fidelity",
            severity=severity[kind],
            subtype=kind,
            message=(
                f"{result[kind]} {message[kind]} across {len(findings)} segment(s) "
                f"({'; '.join(samples)}) — a segment's address and its rendering must "
                f"describe the same content (#159)"
            ),
            fields={"kind": kind, "count": result[kind], "sample": samples},
        )


# ---------- rule registry + entry point ---------- #


_REGISTRY: tuple[tuple[str, Any], ...] = (
    ("id-format", _rule_id_format),
    ("frontmatter-legacy-status", _rule_legacy_status),
    ("hash-tag-grammar", _rule_hash_tag_grammar),
    ("hash-legacy-transport", _rule_hash_legacy_key),
    ("hash-superseded-recipe-version", _rule_hash_superseded_recipe_version),
    ("visibility-invalid", _rule_visibility_invalid),
    ("touch-format", _rule_touch_format),
    ("artifact-block-missing", _rule_artifact_block_missing),
    ("origins-empty", _rule_origins_empty),
    ("origin-uri-shape", _rule_origin_uri_shape),
    ("embed-format", _rule_embed_format),
    ("member-row-unknown-key", _rule_member_row_unknown_key),
    ("atom-invalid", _rule_atom_invalid),
    ("segment-non-text-with-body", _rule_segment_non_text_with_body),
    ("segment-perceptual-format", _rule_segment_perceptual_format),
    ("section-empty", _rule_section_empty),
    ("segment-address-duplicate", _rule_segment_address_duplicate),
    ("address-region-invalid", _rule_address_region_grammar),
    ("address-pipe-scalar", _rule_address_pipe_scalar),
    ("address-frame-invalid", _rule_address_frame_grammar),
    ("address-el-range-invalid", _rule_address_el_range_grammar),
    ("whole-address-not-admissible", _rule_whole_address_admissible),
    ("cutting-stamp-malformed", _rule_cutting_stamp_shape),
    ("framing-stamp-malformed", _rule_framing_stamp_shape),
    ("samples-stamp-malformed", _rule_samples_stamp_shape),
    ("container-carries-rendering", _rule_container_carries_rendering),
    ("issue-shape", _rule_issue_shape),
    ("context-shape", _rule_context_shape),
    ("sweep-shape", _rule_sweep_shape),
    ("sweep-address-invalid", _rule_sweep_address_grammar),
    ("sweep-band-overlap", _rule_sweep_band_overlap),
    ("classify-block-retired", _rule_classify_retired),
    # normalizer-support parity (luklacloud intent)
    ("mime-extension-mismatch", _rule_mime_extension_mismatch),
    ("segment-body-requires-lossless", _rule_segment_body_lossless_contract),
    ("segment-mode-deprecated", _rule_segment_mode_deprecated),
    ("embed-unreferenced", _rule_embed_unreferenced),
    ("embed-missing-target", _rule_embed_missing_target),
    # *(3.8)* The placement contract, §4.3.2.4 — three errors at the two grains the amendment
    # separates: what the parent may say about a member, what a placement must name, and
    # whether the named member exists at all.
    ("member-rendered-on-parent", _rule_member_rendered_on_parent),
    ("placement-without-member", _rule_placement_without_member),
    ("placement-form-mixed", _rule_placement_deconstructed),
    ("placement-region-undeclared", _rule_placement_deconstructed),
    ("placement-not-exhaustive", _rule_placement_deconstructed),
    ("placed-member-not-promoted", _rule_placed_member_not_promoted),
    ("body-empty-normalized", _rule_body_empty_normalized),
    ("body-html-residue", _rule_body_html_residue),
    ("body-corpus-link-forbidden", _rule_body_corpus_link_forbidden),
    ("body-codefence-unbalanced", _rule_body_codefence_unbalanced),
    ("body-unknown-comment", _rule_body_unknown_comment),
    # 3.0 byte-mark + form-coherence (§4.3.2.1, §4.3.2.3, §7.8).
    ("structural-level-invalid", _rule_structural_byte_mark),
    ("structural-mark-retired", _rule_structural_byte_mark),
    ("form-overlay-unknown", _rule_form_coherence),
    ("form-envelope-missing", _rule_form_coherence),
    ("form-codebook-index-out-of-range", _rule_form_coherence),
    ("form-address-axis", _rule_form_coherence),
    ("form-address-nonmonotonic", _rule_form_coherence),
    # terminal contracts (§7.8, 3.3) — the inverted conformance check.
    ("terminal-stored-rendering", _rule_terminal_stored_rendering),
    # #52/#118 — the link gate. Reads artifact bytes, unlike every rule above; see the rule's
    # own docstring for why that is cheap for a corpus whose overlays declare no subject region.
    ("subject-link-flattened", _rule_subject_link_flattened),
    # #159 — the address-fidelity gate. Reads artifact bytes; stamped records only.
    ("segment-address-fidelity", _rule_segment_address_fidelity),
)

# The rule subset `corpus diagnose` runs for its quick-lint section — the cheap, high-signal
# frontmatter/structure checks (athenaeum's idiomatic rule_ids).
DIAGNOSE_QUICK_RULES: tuple[str, ...] = (
    "frontmatter-legacy-status",
    "hash-tag-grammar",
    "touch-format",
    "artifact-block-missing",
    "origins-empty",
    "atom-invalid",
)


# ---------- fragment subset used by `corpus validate-fragment` ---------- #
#
# The rules meaningful on a single manifest FRAGMENT in isolation — segment / section /
# body-local checks that need no frontmatter, no whole-record members roster, no artifact
# bytes, and no other record on disk. A section-worker runs these against its own fragment
# (`corpus validate-fragment fragments/<file>.corpus`) to catch malformed addresses,
# body⟺lossless violations, and body-markdown defects BEFORE the orchestrator's single final
# `compile`.
#
# Deliberately excluded, and why: every frontmatter rule (id/hash/touch/visibility/…) — a
# fragment carries no frontmatter at all; every metadata-zone rule (artifact/origin/member
# roster) — the roster stays in the orchestrator's main manifest.corpus even under `--split`
# (reconciliation #1) and is never a worker's to touch; every rule that reads artifact bytes
# or another record's file on disk (address-frame-invalid, address-el-range-invalid,
# subject-link-flattened, segment-address-fidelity, container-carries-rendering, the whole
# placement family, embed-unreferenced/embed-missing-target, whole-address-not-admissible,
# terminal-stored-rendering) — none of that is resolvable from one fragment's own text; and
# every annotations-zone rule (issue-shape/context-shape/sweep-*) — issues and context blocks
# are orchestrator-owned ops that stay in the main manifest, never split into a fragment.
# `corpus compile --dry-run` (or the final compile itself) covers all of those on the
# fully-assembled record.
FRAGMENT_RULES: tuple[str, ...] = (
    "atom-invalid",
    "segment-non-text-with-body",
    "segment-perceptual-format",
    "section-empty",
    "segment-address-duplicate",
    "address-region-invalid",
    "address-pipe-scalar",
    "segment-body-requires-lossless",
    "segment-mode-deprecated",
    "structural-level-invalid",
    "structural-mark-retired",
    "form-overlay-unknown",
    "form-envelope-missing",
    "form-codebook-index-out-of-range",
    "form-address-axis",
    "form-address-nonmonotonic",
    "body-html-residue",
    "body-corpus-link-forbidden",
    "body-codefence-unbalanced",
    "body-unknown-comment",
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


# ---------- the resolve pass (opt-in; needs artifact bytes) ---------- #


def resolve_addresses(
    post: frontmatter.Post,
    blocks: list[_segments.Block],
    corpus_root: Path,
) -> list[Finding]:
    """Materialize every address this record stores and report the ones that fail.

    NOT part of `_REGISTRY`: every other rule is a pure inspector over the record text,
    while this one reads artifact bytes and runs the render chain, so it is opt-in
    (`corpus lint --resolve`) rather than part of the default gate.

    It is, however, the only mechanical proof that a stored address means anything. The
    grammar rule catches a fractional bbox written in pixels; this catches everything
    else that resolves to nothing — an `el=` past the end of the element list, an op the
    media type has no handler for, a chained address whose parent never materializes,
    artifact bytes absent from the store. Together they close the class that let 974
    records carry provenance pointing at no bytes while three gates read green.

    What it CANNOT do is judge whether a well-formed crop is the RIGHT region — that
    stays an authoring obligation (resolve it and look at it), which is why the
    normalizer's rule is "read it back", not "lint it"."""
    from corpus import resolver as _resolver
    from corpus.transforms import NotMaterializable

    record_id = str(post.metadata.get("id") or "")
    if not record_id:
        return []
    seen: set[str] = set()
    out: list[Finding] = []
    spans: list[str] = []
    for addr, where in _iter_stored_addresses(post, blocks):
        if addr in seen:
            continue
        seen.add(addr)
        if _region_problems(addr):
            continue  # `address-region-invalid` already reports it; don't say it twice
        uri = f"corpus://{record_id}?{addr}"
        try:
            path = _resolver.resolve(uri, corpus_root)
        except NotMaterializable:
            # The address names something REAL with no byte surface — a span envelope
            # (`el=1-8`), or a text element (`el=3` → `<table>`) whose content is the
            # record's own rendering. Not a defect; counted and declared below rather
            # than reported, because a text citation that resolves to no FILE is still
            # a correct citation. The render path says so by type, so lint does not have
            # to guess from a message.
            spans.append(addr)
            continue
        except Exception as exc:  # any other failure IS the finding — never swallowed
            out.append(
                Finding(
                    rule_id="address-unresolvable",
                    severity="error",
                    message=f"{where} address `{addr}` does not resolve: {_one_line(exc)}",
                    address=addr,
                    fields={"uri": uri, "error_type": type(exc).__name__},
                )
            )
            continue
        if not path.exists() or path.stat().st_size == 0:
            out.append(
                Finding(
                    rule_id="address-resolves-empty",
                    severity="error",
                    message=f"{where} address `{addr}` resolves to an empty surface.",
                    address=addr,
                    fields={"uri": uri},
                )
            )
    if spans:
        # Declare the coverage gap rather than leaving the pass looking exhaustive: a
        # silently-skipped address reads as a verified one.
        out.append(
            Finding(
                rule_id="address-not-materializable",
                severity="info",
                message=(
                    f"{len(spans)} address(es) name a real surface with no bytes to "
                    f"materialize (a span envelope, or a text element) and were not "
                    f"resolved: {', '.join(spans[:4])}"
                    f"{', …' if len(spans) > 4 else ''}. The region grammar still "
                    f"checked them."
                ),
                fields={"addresses": spans},
            )
        )
    return out


def _iter_stored_addresses(post, blocks) -> Iterator[tuple[str, str]]:
    """Every address the record stores, as `(address, where)` — the same surfaces the
    grammar rule walks, in the same order."""
    for blk in blocks:
        if isinstance(blk, _segments.Section):
            for addr in _addresses(blk.address):
                yield addr, "section"
            for seg in blk.segments:
                for addr in _addresses(getattr(seg, "address", None)):
                    yield addr, "segment"
        elif isinstance(blk, _segments.Segment):
            for addr in _addresses(getattr(blk, "address", None)):
                yield addr, "segment"
    for i, eb in enumerate(_records.iter_embed_blocks(post), 1):
        for addr in _addresses(eb.get("address")):
            yield addr, f"embed {i}"


def _one_line(exc: Exception) -> str:
    """First line of an exception message, trimmed — resolver errors can be paragraphs
    (the region grammar's own is three sentences) and a finding wants one line."""
    text = str(exc).strip().splitlines()
    first = text[0].strip() if text else type(exc).__name__
    return first if len(first) <= 240 else first[:237] + "…"


# ---------- helpers ---------- #


def _region_problems(addr: str) -> list[tuple[str, str]]:
    """`(param, problem)` for every region-op value in `addr` that breaks the region
    grammar. Empty when the address is fine — or when its region params speak a
    different grammar (a spreadsheet's `bbox=A1:D20`), which `region_errors` declines
    to judge."""
    from corpus import functional_uri as _furi

    out: list[tuple[str, str]] = []
    for part in addr.split("&"):
        key, sep, value = part.partition("=")
        key = key.strip()
        for problem in _furi.region_errors(key, value if sep else None):
            out.append((key, problem))
    return out


def _addresses(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(a) for a in raw if a]
    return [str(raw)]


def _addr_str(raw: Any) -> str:
    addrs = _addresses(raw)
    return ",".join(addrs) if addrs else ""
