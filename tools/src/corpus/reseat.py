"""The §12.30 placement migration: a member's rendering moves to the member's own record.

The mechanical half of ATH-CORPUS 3.8 (spec §4.3.2.4). One record at a time, and for each
member the record **positions** in its body:

1. **promote** it if it has no record yet — stream the member's bytes out of the container,
   blake3-verify against the roster row, mint the leaf (`corpus promote`'s engine, §8.1);
2. **re-seat** every rendering of that member from the parent onto the leaf, at the leaf's own
   address — the crop alone where the parent's address chained one (`el=<path>&bbox=…`), and
   **no address at all** where the rendering covers the whole member, which is the ordinary
   case and the whole-transport address 3.8 introduces (§4.3.2.2);
3. **replace** the parent's segments at that position — marker, transcription, or both — with
   one `<!--segment placement-->`.

What makes this worth doing rather than merely conforming is measured: 558 public members were
transcribed in more than one record, 1,481 transcription passes spent on bytes that had already
been rendered. After the sweep one leaf serves every parent.

**Refusals over guesses**, the §12.28 rule, and here the refusals are the interesting part:

- a member whose streamed bytes do not hash to the roster's `transport:` — the roster is stale
  or the bytes differ, and minting a record with a wrong id is unrecoverable;
- a leaf that already carries a **different** rendering of the same bytes. Two parents
  transcribed one member and disagreed; which reading is right is a judgment, not a merge, so
  the record is held and reported. (Agreement is the common case and is silent — that is the
  dedup win landing.)
- a chained address whose suffix is not an image op (`region=banner`, `part=2`,
  `caption=after` — 16 public segments): the suffix means something to whoever wrote it and
  nothing to the resolver, so it cannot be carried across mechanically;
- a content segment whose address list spans **two** members: it renders two assets at once,
  and splitting one body between two leaves is authoring, not migration.

**The leaf is left formless on purpose.** A form is asserted by judgment (§7.8, §12.22's
force-stamping discipline), and a sweep that stamped 14,446 of them would be inventing exactly
the kind of claim the corpus exists to keep verifiable. The leaves land as `rendered` — a state
§4.1 names — carrying normalization pressure from every parent that places them (§8.5), and a
pass adopts a form where one genuinely fits.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

import blake3
import frontmatter

from corpus import (
    containment,
    hashindex,
    hashing,
    lint,
    mime,
    paths,
    records,
    schemas,
    segments,
    touches,
)
from corpus.store import ArtifactMissing

#: Touch identifier stamped on every record the migration rewrites — parents and leaves alike.
TOUCH_ID = "migrate.placement-38"

# The prefix-ladder rungs (spec §7.9's registry table) — mirrored rather than imported from
# `corpus.hashing` (private there): a leaf's bytes are already fully resident here
# (`_MemberSource.bytes_for`), so `_bytes_recipe_hashes` computes them directly rather than
# through `hashing.compute_hashes` (which needs a standalone Path).
_LADDER_RUNGS: tuple[tuple[int, str], ...] = (
    (4 * 1024, "blake3-4k"),
    (64 * 1024, "blake3-64k"),
    (1024 * 1024, "blake3-1m"),
)

#: Address params that legitimately chain onto an image member and carry over to its own
#: record unchanged: the registered image ops (`corpus.transforms.image`). Anything else in a
#: chained suffix is authored vocabulary the resolver never knew, and the record is held rather
#: than have it silently rewritten or dropped.
_IMAGE_OPS = frozenset(
    {
        "autocontrast",
        "auto_orient",
        "bbox",
        "contrast",
        "cover",
        "crop",
        "fit",
        "format",
        "grayscale",
        "mark",
        "resize",
        "rotate",
    }
)

#: The one lint rule the neutrality gate cannot judge before the leaves are on disk: it asks
#: whether a placed member has a record, and the answer is yes only after this same operation
#: writes them. The invariant that replaces it is checked directly — every member this record
#: places is a member this run mints or confirms.
_DEFERRED_RULE = "placed-member-not-promoted"


class ReseatHold(ValueError):
    """A record the migration refuses to touch. Carries the reason."""


@dataclass
class LeafWrite:
    """One member's own record, as this migration would leave it."""

    record_id: str
    relpath: str
    #: "minted" (no record existed) · "rendered" (renderings moved onto it) ·
    #: "already-rendered" (its rendering already matches — the dedup win) · "placed-only"
    #: (nothing to move; the parent carried only a marker).
    outcome: str
    media_type: str
    new_text: str | None = None
    #: The leaf's own address for the moved rendering — None means the whole transport.
    address: str | None = None
    segments_moved: int = 0
    #: Positions on the parent that collapse to a placement for this member.
    positions: list[str] = dataclass_field(default_factory=list)


@dataclass
class RecordReseat:
    record_id: str
    relpath: str
    new_text: str | None = None
    changed: bool = False
    skipped: str | None = None
    hold: str | None = None
    counts: Counter[str] = dataclass_field(default_factory=Counter)
    leaves: list[LeafWrite] = dataclass_field(default_factory=list)


# ---------- address algebra ---------- #


def _base_and_suffix(addr: str) -> tuple[str, str]:
    """`el=3&bbox=0,0,1,1` → `("el=3", "bbox=0,0,1,1")`; a bare address → `(addr, "")`."""
    base, _, suffix = addr.partition("&")
    return base, suffix


def _is_whole_frame(suffix: str) -> bool:
    """True when a chained suffix crops nothing — the whole-frame `bbox=` §4.3.2.2 already
    calls "the same full-region transcription wearing a crop". Every spelling the fleet uses
    resolves to the same four numbers, so the test is numeric rather than textual: `0,0,1,1`,
    `0.0,0.0,1.0,1.0`, `0,0,1.0,1.0` are one value written three ways. `bbox=full` is the
    fourth spelling and is literal."""
    if not suffix.startswith("bbox="):
        return False
    value = suffix[len("bbox=") :]
    if value == "full":
        return True
    parts = value.split(",")
    if len(parts) != 4:
        return False
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError:
        return False
    return (x, y, w, h) == (0.0, 0.0, 1.0, 1.0)


def leaf_address(addr: str) -> str | None:
    """The address a rendering at `addr` takes on the MEMBER's own record.

    The `el=` (or `path=`, `msg=`, …) prefix names the member inside its container and means
    nothing on the member's own record, so it goes. What is left is the crop — already
    expressed in fractions of the member's own extent, so nothing is recomputed — or, when the
    rendering covers the whole member, **nothing**: the whole-transport address (§4.3.2.2).

    Raises `ReseatHold` for a suffix that is not an image op: it meant something to whoever
    wrote it and nothing to the resolver, and a migration may not guess."""
    _base, suffix = _base_and_suffix(addr)
    if not suffix or _is_whole_frame(suffix):
        return None
    for part in suffix.split("&"):
        param = part.partition("=")[0]
        if param not in _IMAGE_OPS:
            raise ReseatHold(
                f"chained address `{addr}` carries `{param}=`, which is not an image op — "
                f"it cannot be re-seated onto the member's record mechanically"
            )
    return suffix


# ---------- the member map ---------- #


def _member_rows(post: frontmatter.Post) -> dict[str, dict[str, Any]]:
    """`member address → row`. The dedup rule (§4.3.1.4) makes an address belong to at most
    one member, so this is total and unambiguous."""
    out: dict[str, dict[str, Any]] = {}
    for row in records.iter_members(post):
        for addr in _addr_list(row.get("address")):
            out[addr] = row
    return out


def _addr_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else []


def _transport_hex(row: dict[str, Any]) -> str:
    return str(row.get("transport") or "").partition(":")[2]


# ---------- member bytes (one artifact parse per record) ---------- #


_NON_WORD = re.compile(r"[^a-z0-9]+")

#: A line short enough that its presence or absence in the document proves nothing — a figure
#: number, a callout digit, a two-word label. Below this the test declines rather than guesses.
#: Public: #88's re-segment shares this threshold when it derives its own location probes from
#: a borrowed body, so the two migrations judge "long enough to mean something" identically.
JUDGEABLE_WORDS = 5


def bare_words(text: str) -> str:
    """Lowercase alphanumeric words, single-spaced. Deliberately brutal: it has to make a
    markdown rendering and its source HTML comparable, so `**Part Number** | Qty` and
    `<th>Part Number</th><td>Qty</td>` both reduce to `part number qty`.

    Public: #88's re-segment normalizes both its location probes and the document text it
    searches through the same way, so a probe built here and one built there are comparable."""
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())


def reads_off_the_member(body: str, document: str) -> bool:
    """Whether a bare `text` body at a non-text member's address is a reading of that member's
    BYTES rather than the container's own prose — sjrahn's rule, 2026-07-31:

        *is this text in the HTML? yes = article, no = picture.*

    It discriminates the two populations that share one address and that the verb previously
    refused together. Both are real and both are common:

    - **absent from the document** — a wiring-harness legend, a callout table, the labels on a
      schematic. Nobody could have typed it without looking at the picture, so it IS a
      rendering of the picture and belongs on the picture's record.
    - **present in the document** — the article's own procedure text, which landed on the
      image's `el=` because the paragraph had no element of its own (#88). Moving it would
      file a repair instruction under a photograph.

    **Biased toward leaving text where it is.** A single judgeable line found in the document
    is enough to decline, because the two errors are not symmetric: wrongly moving prose
    displaces an article's content onto a PNG plausibly and permanently, while wrongly leaving
    a transcription costs only that this record stays as it is today. Lines too short to judge
    make the whole body undecidable for the same reason.

    Public: this is the ONE test for the shape, reused rather than re-derived by #88's own
    re-segment migration (`corpus.resegment`) — the population that borrows a member's address
    is one population however it is finally repaired.
    """
    if not document:
        return False
    judgeable = [
        probe
        for line in (body or "").splitlines()
        if len((probe := bare_words(line)).split()) >= JUDGEABLE_WORDS
    ]
    if not judgeable:
        return False
    return not any(" ".join(probe.split()[:12]) in document for probe in judgeable)


class _MemberSource:
    """Materializes a record's members from ONE parse of its artifact.

    `containment.open_member_stream` is per-member by design and re-parses the container each
    time; on a 214-member page that is 214 parses of the same bytes. This holds the parsed
    document for the record's whole migration and walks it once per member — which is also why
    it exists here rather than in `containment`: the containment layer answers one lookup at a
    time, this answers a batch."""

    def __init__(self, corpus_root: Path, post: frontmatter.Post) -> None:
        self._root = corpus_root
        self._post = post
        self._media_type = records.media_type_for(post)
        self._el_addressing = records.el_addressing(post)
        self._path: Path | None = None
        self._soup: Any = None
        self._doc_words: str | None = None

    def document_text(self) -> str:
        """The container's own rendered text, normalized to bare words — the oracle for the
        transcription-vs-borrowed-prose test below.

        Cheap because the parse is already held for the member walk. Empty for a non-HTML
        container, which makes the test decline to classify rather than guess."""
        if self._doc_words is None:
            self._doc_words = ""
            if self._media_type == "text/html":
                from bs4 import BeautifulSoup

                from corpus.transforms import html as html_tf

                if self._soup is None:
                    self._soup = BeautifulSoup(
                        self._artifact().read_bytes(), html_tf.EL_PARSER_ID
                    )
                self._doc_words = bare_words(self._soup.get_text(" "))
        return self._doc_words

    def _artifact(self) -> Path:
        if self._path is None:
            rid = str(self._post.metadata.get("id") or "")
            ext = mime.extension_for(self._media_type)
            self._path = containment.ensure_local_bytes(self._root, rid, ext)
        return self._path

    def bytes_for(self, address: str) -> bytes:
        """The member's raw bytes at `address`, exactly as attestation hashed them."""
        base, _ = _base_and_suffix(address)
        key, _, value = base.partition("=")
        if self._media_type == "text/html" and key == "el":
            from bs4 import BeautifulSoup

            from corpus.transforms import html as html_tf

            if self._soup is None:
                self._soup = BeautifulSoup(self._artifact().read_bytes(), html_tf.EL_PARSER_ID)
            ctx: dict[str, Any] = {}
            if self._el_addressing:
                ctx["el_addressing"] = self._el_addressing
            ref = html_tf.extract_el(self._soup, value, ctx)  # type: ignore[arg-type]
            uri = html_tf.carrier_data_uri(ref.tag)
            if uri is None:
                raise ReseatHold(
                    f"member at `{base}` resolves to <{ref.tag.name}>, which carries no inline "
                    f"bytes — the roster row and the document disagree"
                )
            parsed = html_tf.parse_data_uri(uri)
            if parsed is None:
                raise ReseatHold(f"member at `{base}`: undecodable data URI")
            return parsed[1]
        with containment.open_member_stream(
            self._artifact(), self._media_type, base, el_addressing=self._el_addressing
        ) as fp:
            return fp.read()

    def source_metadata(self, address: str) -> dict[str, str]:
        base, _ = _base_and_suffix(address)
        return containment.member_source_metadata(
            self._artifact(), self._media_type, base, el_addressing=self._el_addressing
        )


# ---------- leaf construction ---------- #


def _mint_leaf(
    corpus_root: Path,
    member_hex: str,
    raw: bytes,
    declared_media_type: str,
    containment_uri: str,
    origin_fields: dict[str, Any],
    basename: str | None,
    member_address: str = "",
) -> frontmatter.Post:
    """A fresh promoted record for the member — `corpus promote`'s stub, built from bytes we
    already hold. The `id` is the verified blake3; the first origin is the containment lineage
    as history (§8.1), which is also what supplies a normalize pass its parent context."""
    media_type = mime.sniff_head(raw[:512], basename)
    if media_type == "unknown" and declared_media_type:
        media_type = declared_media_type
    # *(3.12)* A track member is a single-track ISOBMFF container, genuinely ambiguous between
    # `video/mp4` and `audio/mp4` — both share one `ftyp` brand, so magic alone always answers
    # `video/mp4`. A `stream_id=` address carries no filename for the ordinary suffix
    # refinement to work with, but the roster row recorded the track's real kind from the
    # container's own handler box at attestation — `corpus promote`'s own mint applies the
    # identical narrow refinement (`_cli/promote.py`), never overruling a sniff that found
    # something else.
    if (
        member_address.startswith("stream_id=")
        and media_type == "video/mp4"
        and declared_media_type in ("audio/mp4", "video/mp4")
    ):
        media_type = declared_media_type
    schema = schemas.load_mime_schema(corpus_root, media_type) or {}
    # No origin overlay layer (spec §7.9's third layer): the leaf's origin is containment
    # lineage (below), never a producer URI, exactly as a plain `corpus promote` mint — the
    # mime schema + corpus-wide default set is the correct floor.
    hash_values = _bytes_recipe_hashes(raw, hashing.resolve_recipes(schema, ()))
    record_hash_entries = {v.tag: v.hex for v in hash_values if v.record_resident}

    fm = records.stub_frontmatter(
        record_id=member_hex,
        touch_id=touches.script_identifier(TOUCH_ID),
    )
    post = frontmatter.Post(content="", **fm)
    if record_hash_entries:
        records.set_record_hashes(post, record_hash_entries)
    records.set_artifact_block(post, mime=media_type, fields={})
    records.append_origin_block(
        post, uri=containment_uri, snapshot=touches.now_iso(), fields=origin_fields or None
    )
    _write_hash_index_rows(corpus_root, member_hex, hash_values)
    return post


def _bytes_recipe_hashes(
    data: bytes, recipes: tuple[hashing.Recipe, ...]
) -> list[hashing.HashValue]:
    """Compute every value of `recipes` over `data` (spec §7.9) — the in-memory-bytes analogue
    of `hashing.compute_hashes` (which needs a standalone Path): the member bytes are already
    fully resident here (`_MemberSource.bytes_for`), so there is no stream to chunk and no
    reason to write them to disk first. `html-stampfree@1` reads `data` directly, same as every
    other recipe — nothing extra to buffer when the whole member is already in hand."""
    byte_stable = [r for r in recipes if r.residency == "byte-stable" and not r.multivalue]
    values: list[hashing.HashValue] = [
        hashing.HashValue(
            recipe=r.id,
            tag=r.id,
            hex=hashlib.new(r.id, data).hexdigest(),
            record_resident=r.record_resident,
        )
        for r in byte_stable
    ]
    if any(r.multivalue for r in recipes):
        for length, tag in _LADDER_RUNGS:
            if len(data) >= length:
                values.append(
                    hashing.HashValue(
                        recipe="blake3-prefix-ladder",
                        tag=tag,
                        hex=blake3.blake3(data[:length]).hexdigest(),
                        param=str(length),
                    )
                )
    if any(r.id == "html-stampfree@1" for r in recipes):
        values.append(
            hashing.HashValue(
                recipe="html-stampfree@1",
                tag="html-stampfree@1",
                hex=hashing.html_stampfree_digest(data),
            )
        )
    return values


def _write_hash_index_rows(corpus_root: Path, record_id: str, hash_values: list) -> None:
    """Mirror `hash_values` into the derived hash index (spec §12.9.1) — best-effort
    deployment state, never authoritative: a write failure here is reported and swallowed
    rather than failing an otherwise-successful reseat."""
    if not hash_values:
        return
    try:
        with hashindex.open_index(corpus_root) as conn:
            hashindex.upsert_rows(
                conn,
                [
                    hashindex.HashRow(
                        record_id=record_id, recipe=v.recipe, algo=v.tag, value=v.hex, param=v.param
                    )
                    for v in hash_values
                ],
            )
    except Exception as exc:  # deployment state (§12.9.1) — never fails reseat
        print(f"  note: hash-index write failed for {record_id[:12]}…: {exc}")


def _moved_segment(seg: segments.Segment, address: str) -> segments.Segment:
    """A parent-side rendering as it stands on the member's own record: same atom, same
    overlay, same body verbatim, re-addressed. `perceptual` carries over — it fingerprints the
    addressed content, which has not changed."""
    return segments.Segment(
        atom=seg.atom,
        address=leaf_address(address),
        perceptual=seg.perceptual,
        body=seg.body,
        extra=dict(seg.extra),
        overlay=seg.overlay,
    )


def _verbatim_segment(seg: segments.Segment) -> segments.Segment:
    """A parent-side rendering as it stands on the member's own record when the address is
    the member's own timeline, unchanged: same atom, same overlay, same body, same address
    (§7.1 — a promoted media-stream leaf resolves every timeline op in the same timeline its
    container reports, so `time_range=` needs no re-homing, unlike the `el=` crop suffix
    `_moved_segment` re-bases)."""
    return segments.Segment(
        atom=seg.atom,
        address=seg.address,
        perceptual=seg.perceptual,
        body=seg.body,
        extra=dict(seg.extra),
        overlay=seg.overlay,
    )


# ---------- the legacy container-composition rendering (pre-#131) ---------- #
#
# A manifest-disposition media container whose own body carries a rendering of ONE stream
# member's bytes, addressed on the CONTAINER's own composition axis (`time_range=…`) rather
# than the member's address — because default-member resolution (§6.2) makes the `stream_id=`
# prefix omittable when the container holds exactly one member of the needed kind. The
# ordinary member-address match above never sees this population: there is no member address
# on the segment for it to match. `container-carries-rendering` (lint.py) already names it;
# its two gating facts are reused here rather than re-derived — `disposition: manifest` and a
# stored rendering in the content zone.

#: Segment kind → the member media-type prefix that kind is a rendering OF. The audio-track
#: record owns the transcript, the video-track record owns on-screen text (§65) — the same
#: pairing default-member resolution uses to pick a bare `time_range=`/`frame=` op's target.
_LEGACY_KIND_STREAM_PREFIX: dict[str, str] = {
    "text/transcript": "audio/",
    "text/ocr": "video/",
}

#: Segment kind → the form id that kind's OWN rendering is shaped by, when one exists. Only
#: `text/transcript` has one (`form/transcript`'s `speakers:` codebook). This is deliberately
#: NOT "whatever form the enclosing section happens to declare": the legacy shape interleaves
#: an `image` frame marker and even a `text/ocr` reading inside the SAME `form: transcript`
#: section as the transcript utterances (both share the container's one span), and a section's
#: form belongs to the kind it was written to describe, not to every kind that happens to sit
#: inside it. A kind with no entry here always seats bare on its leaf — the same shape the
#: ordinary (non-legacy) association has always produced.
_LEGACY_KIND_FORM: dict[str, str] = {
    "text/transcript": "transcript",
}


def _legacy_container_segments(
    blocks: list[Any], member_map: dict[str, dict[str, Any]]
) -> list[tuple[segments.Section | None, segments.Segment]]:
    """Content-atom segments of a legacy kind whose address does not stand at, or chain from,
    any member's address — the population the ordinary match (`affected`, above) never
    collects, precisely because there is no member address on the segment."""
    out: list[tuple[segments.Section | None, segments.Segment]] = []
    for blk in blocks:
        container = blk if isinstance(blk, segments.Section) else None
        for seg in blk.segments if isinstance(blk, segments.Section) else [blk]:
            if not isinstance(seg, segments.Segment) or not seg.is_content:
                continue
            kind = seg.overlay or seg.atom
            if kind not in _LEGACY_KIND_STREAM_PREFIX:
                continue
            addrs = _addr_list(seg.address)
            if not addrs or any(_base_and_suffix(a)[0] in member_map for a in addrs):
                continue  # a real member address — the ordinary path already owns this one
            out.append((container, seg))
    return out


def _stream_candidates(post: frontmatter.Post, prefix: str) -> list[dict[str, Any]]:
    """Member rows whose `media_type` starts with `prefix` (`audio/`, `video/`), deduped by
    transport — the population default-member resolution (§6.2) picks from when exactly one
    exists. Two or more is the ambiguity §6.2 refuses to guess through; reseat holds on it the
    same way."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in records.iter_members(post):
        media_type = str(row.get("media_type") or "")
        if not media_type.startswith(prefix):
            continue
        hexval = _transport_hex(row)
        if hexval in seen:
            continue
        seen.add(hexval)
        out.append(row)
    return out


# ---------- seating a member onto its leaf (shared by every association path) ---------- #


def _seat_source_member(
    report: RecordReseat,
    corpus_root: Path,
    source: _MemberSource,
    rid: str,
    hexval: str,
    base: str,
    row: dict[str, Any],
) -> tuple[frontmatter.Post, str, str] | None:
    """Stream `base`'s bytes, blake3-verify against `hexval`, then load the member's existing
    record or mint a fresh stub. This is the load-bearing check shared by every association
    path: a promoted `id` that is not the member's true blake3 is unrecoverable (§8.1).
    Returns `(leaf_post, outcome, declared_media_type)` — `outcome` is "rendered" (an existing
    leaf) or "minted" (a fresh stub) — or `None` with `report.hold` set on refusal."""
    declared = str(row.get("media_type") or "")
    try:
        raw = source.bytes_for(base)
    except ReseatHold as exc:
        report.hold = str(exc)
        return None
    except (ArtifactMissing, ValueError, OSError) as exc:
        report.hold = f"member at `{base}` could not be materialized: {exc}"
        return None
    computed = blake3.blake3(raw).hexdigest()
    if computed != hexval:
        report.hold = (
            f"member at `{base}` streams to blake3 {computed[:12]}… but the roster declares "
            f"{hexval[:12]}… — the declaration is stale or the bytes differ; refusing to "
            f"mint a record with a wrong id"
        )
        return None

    leaf_file = paths.record_path(corpus_root, hexval)
    if leaf_file.is_file():
        return records.load(leaf_file), "rendered", declared

    meta = source.source_metadata(base)
    origin_fields: dict[str, Any] = {}
    if meta.get("filename"):
        origin_fields["filename"] = meta["filename"]
    if meta.get("source_modified"):
        origin_fields["source_modified"] = meta["source_modified"]
    basename = containment.member_sniff_name(base, meta.get("filename"))
    leaf_post = _mint_leaf(
        corpus_root,
        hexval,
        raw,
        declared,
        f"corpus://{rid}?{base}",
        origin_fields,
        basename,
        member_address=base,
    )
    return leaf_post, "minted", declared


def _seat_leaf(
    report: RecordReseat,
    corpus_root: Path,
    hexval: str,
    leaf_file: Path,
    declared: str,
    outcome: str,
    leaf_post: frontmatter.Post,
    moved_all: list[segments.Segment],
    positions: list[str],
    *,
    wrap: Any = None,
) -> bool:
    """Dedupe `moved_all` by the leaf's own identity — (opener-id, address) — then seat it onto
    `leaf_post`: minted-empty, placed-only, already-rendered (the dedup win), or written fresh
    behind a lint-clean gate. `wrap`, when given, turns the deduped segment list into the
    block(s) actually emitted (a form span carrying its envelope fields, for a rendering whose
    form travels with it) — bare segments otherwise, as an ordinary member rendering always
    was. Appends to `report.leaves`/`report.counts` and returns True on success; sets
    `report.hold` and returns False on any refusal. Shared by the ordinary member-address match
    and the container-composition inference below — once a member and its moved segments are
    known, seating onto the leaf is one job regardless of how the segments were found."""
    moved: list[segments.Segment] = []
    by_identity: dict[tuple[str, str | None], segments.Segment] = {}
    for cand in moved_all:
        addr = cand.address if isinstance(cand.address, str) else None
        key = (cand.overlay or cand.atom, addr)
        prior = by_identity.get(key)
        if prior is None:
            by_identity[key] = cand
            moved.append(cand)
            continue
        if prior.body.strip() == cand.body.strip():
            report.counts["duplicate renderings collapsed"] += 1
            continue
        report.hold = (
            f"member `{hexval[:12]}…` is transcribed twice in this record at one leaf "
            f"identity ({key[0]} @ {key[1] or 'whole transport'}) with DIFFERENT bodies — "
            f"two readings of one set of bytes is a judgment, not a merge"
        )
        return False

    leaf_relpath = str(leaf_file.relative_to(corpus_root))

    if not moved:
        report.leaves.append(
            LeafWrite(
                record_id=hexval,
                relpath=leaf_relpath,
                outcome="minted" if outcome == "minted" else "placed-only",
                media_type=declared,
                new_text=records.dumps(leaf_post) if outcome == "minted" else None,
                positions=positions,
            )
        )
        report.counts["members promoted" if outcome == "minted" else "members placed"] += 1
        return True

    wanted = segments.emit(wrap(moved) if wrap else moved).rstrip("\n")
    existing = (leaf_post.content or "").strip()
    if existing:
        if existing == wanted:
            # Two renderings of one member agree. This is the dedup win landing: the second
            # was work already done.
            report.leaves.append(
                LeafWrite(
                    record_id=hexval,
                    relpath=leaf_relpath,
                    outcome="already-rendered",
                    media_type=declared,
                    address=moved[0].address,
                    segments_moved=len(moved),
                    positions=positions,
                )
            )
            report.counts["renderings already on the leaf"] += len(moved)
            return True
        report.hold = (
            f"member `{hexval[:12]}…` already carries a DIFFERENT rendering on its own "
            f"record ({leaf_relpath}) — two readings of one set of bytes is a judgment, "
            f"not a merge"
        )
        return False

    leaf_post.content = wanted
    # A freshly minted leaf already carries this pass as `touch[0]` (the stub's own
    # identifier) — appending it again would read as two passes where there was one.
    if outcome != "minted":
        touches.record_touch(leaf_post, touches.script_identifier(TOUCH_ID))
    # The leaf is a record this pass is responsible for, so it passes the same gate a
    # record must pass to be committed. Cheap here (one small record), and it is the only
    # thing standing between a mechanical re-address and a fleet of records nobody linted —
    # the #61 lesson: run the cheap check before the correct-looking answer.
    leaf_errors = [
        f.rule_id
        for f in lint.lint(leaf_post, segments.iter_blocks(leaf_post.content or ""), corpus_root)
        if f.severity == "error"
    ]
    if leaf_errors:
        report.hold = (
            f"the member's own record would not lint clean "
            f"({', '.join(sorted(set(leaf_errors)))})"
        )
        return False
    report.leaves.append(
        LeafWrite(
            record_id=hexval,
            relpath=leaf_relpath,
            outcome=outcome,
            media_type=declared,
            new_text=records.dumps(leaf_post),
            address=moved[0].address,
            segments_moved=len(moved),
            positions=positions,
        )
    )
    report.counts["renderings re-seated"] += len(moved)
    if outcome == "minted":
        report.counts["members promoted"] += 1
    return True


# ---------- the sweep ---------- #


def reseat_record(record_file: Path, corpus_root: Path) -> RecordReseat:
    """Compute (never write) the §12.30 migration of one record. The caller applies
    `report.new_text` and every `leaf.new_text` together when `report.changed`; a `hold` means
    hands off — and it means hands off BOTH sides, since a parent whose placement points at a
    leaf we declined to write would be worse than either shape alone."""
    original = record_file.read_text(encoding="utf-8")
    post = records.load(record_file)
    rid = str(post.metadata.get("id") or record_file.stem)
    report = RecordReseat(record_id=rid, relpath=str(record_file.relative_to(corpus_root)))

    try:
        blocks = segments.iter_blocks(post.content or "")
    except ValueError as exc:
        report.hold = f"content zone does not parse: {exc}"
        return report

    member_map = _member_rows(post)
    if not member_map:
        report.skipped = "no members"
        return report

    # Which segments stand on a member — by exact address or by chaining from one (§4.3.1.4).
    affected: list[tuple[segments.Section | None, segments.Segment, str]] = []
    for blk in blocks:
        container = blk if isinstance(blk, segments.Section) else None
        for seg in blk.segments if isinstance(blk, segments.Section) else [blk]:
            if not isinstance(seg, segments.Segment) or not seg.is_content:
                continue
            hits = [a for a in _addr_list(seg.address) if _base_and_suffix(a)[0] in member_map]
            if not hits:
                continue
            # Two ADDRESSES are not two members: the roster dedupes by transport, so a
            # multi-region segment naming both positions of one asset is the legitimate case
            # (§4.3.2.2) and re-seats to one leaf. Two distinct TRANSPORTS is the real problem —
            # one body renders two different assets, and splitting it is authoring.
            member_hexes = {_transport_hex(member_map[_base_and_suffix(a)[0]]) for a in hits}
            if len(member_hexes) > 1:
                bases = sorted({_base_and_suffix(a)[0] for a in hits})
                report.hold = (
                    f"a {seg.overlay or seg.atom} segment addresses {len(member_hexes)} distinct "
                    f"members at once ({', '.join(bases)}) — splitting one body between two "
                    f"leaves is authoring, not migration"
                )
                return report
            if len(hits) != len(_addr_list(seg.address)):
                report.hold = (
                    f"a {seg.overlay or seg.atom} segment at "
                    f"`{','.join(_addr_list(seg.address))}` addresses a member AND a non-member "
                    f"region — re-address it deliberately before re-seating"
                )
                return report
            # Every hit is kept: a multi-region segment naming both positions of one asset
            # must yield a placement at BOTH, or the second position silently loses its
            # marker.
            affected.append((container, seg, hits))

    # The legacy pre-#131 population `affected` never sees: a manifest-disposition container's
    # own body rendering a stream member's bytes on the CONTAINER's own composition axis
    # (`time_range=…`), rather than the member's address — the same population
    # `container-carries-rendering` (lint.py) already names, reusing its two gating facts.
    legacy: list[tuple[segments.Section | None, segments.Segment]] = []
    if schemas.resolved_disposition_for_record(corpus_root, post) == "manifest":
        legacy = _legacy_container_segments(blocks, member_map)

    if not affected and not legacy:
        report.skipped = "no member is marked or rendered on this record"
        return report

    # Serializer stability, the §12.28 rule: the rewrite goes through the real serializer, so
    # a difference it would introduce on its own must be disclosed before we add ours.
    if records.dumps(post) != original:
        report.hold = "record is not dumps-stable; the serializer would introduce unrelated changes"
        return report

    before = Counter(f.rule_id for f in lint.lint(post, blocks, corpus_root))

    source = _MemberSource(corpus_root, post)

    # Group by member, preserving first-appearance order so the parent's reading order holds.
    order: list[str] = []
    per_member: dict[str, list[tuple[segments.Section | None, segments.Segment, str]]] = {}
    for container, seg, addrs in affected:
        base = _base_and_suffix(addrs[0])[0]
        hexval = _transport_hex(member_map[base])
        if not hexval:
            report.hold = f"member at `{base}` carries no blake3 transport — cannot promote it"
            return report
        if hexval not in per_member:
            per_member[hexval] = []
            order.append(hexval)
        per_member[hexval].append((container, seg, addrs))

    for hexval in order:
        entries = per_member[hexval]
        base = _base_and_suffix(entries[0][2][0])[0]
        row = member_map[base]
        leaf_file = paths.record_path(corpus_root, hexval)

        seated = _seat_source_member(report, corpus_root, source, rid, hexval, base, row)
        if seated is None:
            return report
        leaf_post, outcome, declared = seated

        # The renderings to move: only segments that actually carry one. A bare marker moves
        # nothing — its whole content was the position, and the placement now holds that.
        #
        # A BARE `text` body at a non-text member's address is refused, and this is the single
        # most consequential refusal in the verb. §4.3.2.2 admits plain prose as a lossless
        # rendering — for text. Pixels do not render as plain prose: the overlay is how a
        # segment declares it is a faithful, shaped transcription of the region it addresses
        # (`text/data-table`, `text/ocr`), and a bare `text` makes no such declaration. On this
        # fleet the population proves what such a segment actually is: procedure prose and figure
        # legends printed BESIDE the image, pinned to the image's own `el=` — which is #88, a
        # known mis-addressing over 1,054 records and ~3,821 segments. Migrating that onto the
        # member's record would move an article's instructions onto a PNG and call it a
        # transcription of the pixels, permanently and plausibly. So: re-address first (#88),
        # reseat after.
        bare = [
            seg
            for _c, seg, _a in entries
            if (seg.body or "").strip() and seg.overlay is None and seg.atom == "text"
        ]
        if bare and not declared.startswith("text/"):
            # Discriminate rather than refuse the pair. Holding on every bare body was correct
            # while nothing could tell the two populations apart, but it deadlocked the two
            # tickets against each other — #88's remainder says "this is #101's placement
            # arc", and this verb said "re-address it first (#88)" — with 8,421 findings
            # behind it and neither able to move. `reads_off_the_member` is the test #88
            # itself built and proved; the refusal now names only what genuinely borrowed the
            # address.
            borrowed = [
                seg for seg in bare if not reads_off_the_member(seg.body, source.document_text())
            ]
            if borrowed:
                report.hold = (
                    f"member `{hexval[:12]}…` ({declared or 'unknown type'}) carries "
                    f"{len(borrowed)} of {len(bare)} bare `text` body(ies) whose words appear "
                    f"in the container's own document — prose printed beside the figure and "
                    f"pinned to its address (#88), not a rendering of the bytes: re-address "
                    f"it before re-seating"
                )
                return report
            report.counts["pixel readings re-seated"] += len(bare)
        try:
            moved_all = [
                _moved_segment(seg, addrs[0])
                for _c, seg, addrs in entries
                if (seg.body or "").strip()
            ]
        except ReseatHold as exc:
            report.hold = str(exc)
            return report

        positions = sorted({_base_and_suffix(a)[0] for _c, _s, aa in entries for a in aa})
        if not _seat_leaf(
            report,
            corpus_root,
            hexval,
            leaf_file,
            declared,
            outcome,
            leaf_post,
            moved_all,
            positions,
        ):
            return report

    # ---- the legacy container-composition association ---- #
    #
    # Ambiguity is a hold, never a skip: zero or two-or-more candidate stream members of the
    # matching kind, a hash disagreement (`_seat_source_member`), or a leaf already carrying a
    # conflicting rendering (`_seat_leaf`) — each holds with a reason, the same refusal
    # discipline `container-carries-rendering` names but cannot itself act on.
    legacy_doomed: dict[int, list[str]] = {}
    legacy_hexvals: set[str] = set()
    sections_to_bare: set[int] = set()
    if legacy:
        legacy_by_kind: dict[str, list[tuple[segments.Section | None, segments.Segment]]] = {}
        for container, seg in legacy:
            legacy_by_kind.setdefault(seg.overlay or seg.atom, []).append((container, seg))

        for kind, kind_entries in legacy_by_kind.items():
            prefix = _LEGACY_KIND_STREAM_PREFIX[kind]
            stream_word = prefix.rstrip("/")
            candidates = _stream_candidates(post, prefix)
            if not candidates:
                report.hold = (
                    f"container carries {len(kind_entries)} `{kind}` segment(s) addressed on "
                    f"its own timeline but the roster names no {stream_word} stream member to "
                    f"seat them on — promote one first, or this rendering has nowhere faithful "
                    f"to go"
                )
                return report
            if len(candidates) > 1:
                report.hold = (
                    f"container carries {len(kind_entries)} `{kind}` segment(s) addressed on "
                    f"its own timeline and the roster names {len(candidates)} {stream_word} "
                    f"stream members — which one they render is a judgment, not a migration"
                )
                return report
            row = candidates[0]
            base_addrs = _addr_list(row.get("address"))
            if not base_addrs:
                report.hold = f"the {stream_word} stream member carries no roster address"
                return report
            base = base_addrs[0]
            hexval = _transport_hex(row)
            if not hexval:
                report.hold = (
                    f"the {stream_word} stream member carries no blake3 transport — cannot "
                    f"promote it"
                )
                return report
            leaf_file = paths.record_path(corpus_root, hexval)

            seated = _seat_source_member(report, corpus_root, source, rid, hexval, base, row)
            if seated is None:
                return report
            leaf_post, outcome, declared = seated

            # The form span this kind's OWN rendering was shaped by travels WITH it — envelope
            # fields (a diarization codebook) are mechanically derivable only from the segments
            # that just moved, so a form the container no longer carries content for is a claim
            # the container can no longer make (§4.3.2.1). Only `text/transcript` has one
            # (`_LEGACY_KIND_FORM`); every other kind seats bare, exactly like the ordinary
            # (non-legacy) association always has, `wrap` unset. And "shares a section" is not
            # "owns its form": the legacy shape interleaves an `image` marker (and can interleave
            # a `text/ocr` reading) inside the SAME `form: transcript` section as the transcript
            # utterances — a section's form belongs to the kind it was written to describe, so
            # only a section that actually DECLARES this kind's governing form is eligible; a
            # section merely hosting this kind's segments under someone else's form contributes
            # nothing to carry. Only when every doomed segment of this kind shares ONE such
            # section: split across two is not one mechanical move.
            governing_form = _LEGACY_KIND_FORM.get(kind)
            target_section: segments.Section | None = None
            wrap_fn = None
            if governing_form is not None:
                owning_sections = {
                    id(c): c for c, _s in kind_entries if c is not None and c.form == governing_form
                }
                if len(owning_sections) > 1:
                    report.hold = (
                        f"`{kind}` renderings addressed on the container's own timeline span "
                        f"{len(owning_sections)} different `form: {governing_form}` sections — "
                        f"moving the form span whole is not one mechanical move"
                    )
                    return report
                target_section = next(iter(owning_sections.values()), None)
                if target_section is not None:

                    def wrap_fn(
                        moved_segs: list[segments.Segment], _s: Any = target_section
                    ) -> list[Any]:
                        return [
                            segments.Section(
                                form=_s.form, segments=moved_segs, extra=dict(_s.extra)
                            )
                        ]

            moved_all = [
                _verbatim_segment(seg) for _c, seg in kind_entries if (seg.body or "").strip()
            ]
            if not _seat_leaf(
                report,
                corpus_root,
                hexval,
                leaf_file,
                declared,
                outcome,
                leaf_post,
                moved_all,
                [base],
                wrap=wrap_fn,
            ):
                return report

            legacy_hexvals.add(hexval)
            for _c, seg in kind_entries:
                legacy_doomed[id(seg)] = [base]
            if wrap_fn is not None:
                sections_to_bare.add(id(target_section))

            # A sweep vouching for this kind's extraction (§4.3.3.6) is a claim about the
            # container's OWN content zone; once the rendering moves, so does the claim — the
            # band's `address:` is on the same timeline the segments were, so it carries over
            # unchanged. The just-appended leaf write is amended in place (rather than risking
            # a "no write" outcome silently dropping the sweep) so the declaration never lands
            # nowhere.
            moved_sweeps = [
                ctx
                for ctx in (post.metadata.get("_contexts") or [])
                if ctx.get("namespace") == "sweep" and (ctx.get("fields") or {}).get("kind") == kind
            ]
            if moved_sweeps:
                post.metadata["_contexts"] = [
                    ctx
                    for ctx in (post.metadata.get("_contexts") or [])
                    if ctx not in moved_sweeps
                ]
                leaf_post.metadata.setdefault("_contexts", []).extend(
                    dict(ctx) for ctx in moved_sweeps
                )
                report.leaves[-1].new_text = records.dumps(leaf_post)
                report.counts["sweep declarations re-seated"] += len(moved_sweeps)

    # ---- the parent rewrite ---- #
    #
    # Order is preserved exactly: a top-level formless segment can only precede the first
    # section (§4.3.2.1's before-only rule), so the record is that run followed by its sections
    # in order. `seen` spans the whole record, so a member marked at `el=3` and transcribed at
    # `el=3&bbox=…` in two different blocks yields ONE placement, at the first position.
    doomed: dict[int, list[str]] = {
        id(seg): [_base_and_suffix(a)[0] for a in aa] for _c, seg, aa in affected
    }
    doomed.update(legacy_doomed)
    seen: set[str] = set()
    written: list[str] = []
    new_blocks: list[Any] = list(
        _rewrite([b for b in blocks if isinstance(b, segments.Segment)], doomed, seen, written)
    )
    for blk in blocks:
        if isinstance(blk, segments.Section):
            blk.segments = _rewrite(blk.segments, doomed, seen, written)
            if id(blk) in sections_to_bare:
                # The form no longer has content to govern here — it moved (above) to the leaf
                # that now genuinely carries it.
                blk.form = None
                blk.extra = {}
            new_blocks.append(blk)
    blocks = new_blocks
    report.counts["placements written"] += len(written)

    empty = [b for b in blocks if isinstance(b, segments.Section) and not b.segments]
    if empty:
        report.hold = (
            f"{len(empty)} form span(s) would be left with no children — the span's whole "
            f"content was a member's rendering, so what the form governs is now a question, "
            f"not a rewrite"
        )
        return report

    post.content = segments.emit(blocks).rstrip("\n") + "\n"
    touches.record_touch(post, touches.script_identifier(TOUCH_ID))
    new_text = records.dumps(post)

    # Round-trip on the TEXT, not the objects. A section's `address` is derived from its
    # children (§4.3.2.1, 3.7), and replacing a rendering with a placement changes the
    # children — so the in-memory envelope is stale by construction here and comparing objects
    # would report every multi-member record as lossy. Re-emitting the reparse is the check
    # that actually matters: what a fresh reader produces from these bytes is these bytes.
    try:
        reparsed = segments.iter_blocks(post.content)
    except ValueError as exc:
        report.hold = f"rewritten content zone does not parse: {exc}"
        return report
    if segments.emit(reparsed).rstrip("\n") != post.content.rstrip("\n"):
        report.hold = "rewritten content zone does not survive an emit round-trip losslessly"
        return report
    blocks = reparsed

    # The neutrality gate (§12.28), minus the one rule that cannot be true until the leaves
    # are on disk. Its invariant is checked directly instead: every member placed is a member
    # this run mints or confirms.
    after = Counter(f.rule_id for f in lint.lint(post, blocks, corpus_root))
    worse = sorted(
        rule
        for rule in set(before) | set(after)
        if rule != _DEFERRED_RULE and after[rule] > before[rule]
    )
    if worse:
        report.hold = (
            "rewrite would raise lint findings ("
            + ", ".join(f"{r}: {before[r]}→{after[r]}" for r in worse)
            + ")"
        )
        return report
    confirmed = {leaf.record_id for leaf in report.leaves}
    expected = set(order) | legacy_hexvals
    if confirmed != expected:
        report.hold = "internal: a placed member has no leaf write — refusing a dangling placement"
        return report

    report.new_text = new_text
    report.changed = True
    return report


def _rewrite(
    segs: list[segments.Segment],
    doomed: dict[int, list[str]],
    seen: set[str],
    written: list[str],
) -> list[segments.Segment]:
    """Replace each run of doomed segments with one placement per member position, at the
    position of its first occurrence — so the parent's reading order is exactly preserved, a
    member marked at two positions keeps both, and a member marked *and* transcribed at one
    position collapses to one. `doomed` maps a doomed segment's `id()` to the position(s) its
    placement belongs at — ordinarily derived from the segment's own address, but for the
    legacy container-composition association (above) the position is the associated member's
    address, which the segment's own (`time_range=…`) address never names. `seen` is the
    caller's, shared across the whole record; an already-present placement counts as seen, so
    re-running is inert."""
    out: list[segments.Segment] = []
    for seg in segs:
        target_positions = doomed.get(id(seg))
        if target_positions is None:
            if seg.is_placement:
                seen.update(_addr_list(seg.address))
            out.append(seg)
            continue
        for base in target_positions:
            if base not in seen:
                seen.add(base)
                written.append(base)
                out.append(segments.Segment(atom="placement", address=base))
    return out
