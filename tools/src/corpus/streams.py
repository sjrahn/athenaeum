"""Engine-free ISOBMFF reading for media containers (mp4/m4a/mov) — the **oracle** half
of the 3.12 identity contract (spec §12.20 item 1).

Since 3.12 this module does not produce member bytes. A promoted track's identity bytes
are a single-track container of the source's own family, muxed by `corpus.mux` — see that
module for why an engine is admitted there. What lives here is everything needed to
*read* a container without one, which is exactly what makes it a usable check on the
producer: a verification sharing the producer's implementation would share its failure
mode, so this module stays deliberately ffmpeg-free.

This module owns two things:

- `probe_streams(path)` — read the container's `moov` box tree and report one
  `StreamInfo` per track (index, kind, codec, media_type), by parsing the sample
  description (`stsd`) and codec configuration record (`avcC`/`hvcC`/`esds`/`dOps`).
  Cheap: only the (small) `moov` subtree is read, never sample data.
- `sample_count(path, stream_id)` — how many samples a track holds per the container's
  own tables (`stsc`/`stsz`/`stco`/`co64`), counting the layout without reading sample
  data. This is the number the `framing:` stamp carries (§7.2.1) and the number
  `corpus.mux` checks a muxed member against.

**What was removed at 3.12, and why it is worth knowing.** This module used to own the
per-codec pinned *elementary* forms: h264/hevc reframed to Annex-B, aac wrapped in
synthesized ADTS headers, opus in a corpus-defined length-prefixed framing. That rule
failed on its own terms. ADTS encodes the audio object type in a **2-bit** field (AOT
1-4), so AAC at `audioObjectType=29` (HE-AAC v2) has no representable ADTS header at all
— and 84 of 102 public containers hold exactly that, which made their audio track
permanently unpromotable. The elementary form was also insufficient in a second way: it
carries no timescale and no duration, so a promoted leaf reported a meaningless frame
rate and could not be seeked. Both are fixed by muxing into the source's own family
instead, where admissibility is true by construction.

Non-ISOBMFF containers (Matroska/WebM and kin) raise a clear error — ISOBMFF only (spec
§12.20's deferred item). A `stsd` with more than one sample-description entry on a track
is refused loudly — never guess which config applies to which samples.

Deliberately unparsed: `tkhd`/`mdhd` (track/media timing — track order comes from `trak`
box order in `moov`, the spec's `stream_id=` integer; sample layout comes entirely from
`stbl`) and `ctts` (composition-time offsets — display order, not decode order).

NO ffmpeg/ffprobe anywhere in this module — that is the point of it. `corpus.mux` owns
the muxer; `corpus.transforms.video` / `corpus.transforms.audio` own the engine-backed
playable-rendering path (`format=`, §12.20 item 1's second layer).
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

# ---------- public result type ---------- #


@dataclass(frozen=True)
class StreamInfo:
    """One elementary stream (track) reported by `probe_streams`.

    `index` is 0-based track order within `moov` — the spec's `stream_id=` integer.
    `codec` is the resolved codec name for the four pinned forms ("h264", "hevc",
    "aac", "opus"); for anything else it is the container's own identifier (the
    `stsd` sample-entry fourcc, or an AAC `objectTypeIndication` annotation) so an
    unsupported track is still nameable — `corpus.mux` raises on it.
    `media_type` is the promoted record's MIME — since 3.12 the single-track *container*
    type for the track's KIND (`video/mp4`, `audio/mp4`), never an elementary-stream type
    (`video/h264`, `audio/aac`), which no longer names any promoted record. `None` when the
    codec is outside the pinned set: such a track is a real fact the roster still reports,
    it just has no member the oracle can vouch for.
    """

    index: int
    kind: str  # "video" / "audio" / "subtitle" / "other"
    codec: str
    media_type: str | None


# The codec is still resolved and reported (it is a real track fact, and the roster names
# it), but since 3.12 it no longer decides the promoted member's MIME. A member's bytes are
# a single-track container of the source's own family, so its type follows the TRACK KIND:
# a video-only mp4 is `video/mp4`, an audio-only one is `audio/mp4` (what an `.m4a` is).
# Before 3.12 this map returned elementary-stream types (`video/h264`, `audio/aac`) because
# the member's bytes were a bare stream; those types no longer name any promoted record.
_MEDIA_TYPE_BY_KIND = {
    "video": "video/mp4",
    "audio": "audio/mp4",
}

#: *(Retired 2026-07-31.)* This was `{h264, hevc, aac, opus}` — the codecs whose config
#: record this module could parse — and it gated whether a track was promotable at all.
#:
#: **Under the elementary rule that gate was the whole point:** a member's bytes had to be
#: SYNTHESIZED (Annex-B from `avcC` NALs, ADTS from the `AudioSpecificConfig`, a
#: corpus-defined framing from `dOps`), so a codec whose config we could not read was a
#: codec whose member we could not build. 3.12 deleted that synthesis — the muxer copies
#: whatever the container holds and never asks what it means — and the gate outlived it.
#:
#: **Measured cost of leaving it in place:** 17 public containers whose AV1 video track was
#: silently unrostered, on a fleet re-attest that otherwise doubled every roster. The track
#: `-c copy` muxes fine (rc=0, 1,081 MB out, sample sequence preserved, byte-identical
#: across runs) — nothing was ever wrong except the allowlist. This is the same shape as
#: the AOT-29 refusal 3.12 exists to end, surviving one layer down.
#:
#: **What replaced it is the question that actually matters:** can this track's samples be
#: laid out? `_iter_sample_layout` answers that from `stsz`/`stsc`/`stco`, which every
#: ISOBMFF track carries regardless of codec, and a track whose tables are malformed still
#: raises rather than guessing. The kind gate below stays — a subtitle track leaves the
#: family (§12.36) and a chapter/timecode track is metadata about other tracks (§12.37).
#:
#: The config parsing itself is deliberately NOT removed here; whether the reader still
#: earns its size is the question §12.37 defers, and answering it in the same change that
#: alters what gets rostered would make the fleet diff unauditable.

_START_CODE = b"\x00\x00\x00\x01"

# esds objectTypeIndication values this module treats as AAC (MPEG-4 Audio, the value
# every modern muxer — including ffmpeg — stamps for AAC-in-esds regardless of the
# internal AAC profile, which lives in the AudioSpecificConfig instead).
_AAC_OBJECT_TYPE_INDICATION = 0x40

_H264_FOURCCS = frozenset({"avc1", "avc3"})
_HEVC_FOURCCS = frozenset({"hev1", "hvc1"})

# VisualSampleEntry / AudioSampleEntry fixed-field byte counts (ISO/IEC 14496-12)
# between the sample entry's own box header and its first child box (avcC/hvcC/esds/
# dOps/...). Constant regardless of box version — SampleEntry carries no version field.
_VIDEO_SAMPLE_ENTRY_FIXED = 78
_AUDIO_SAMPLE_ENTRY_FIXED = 28

_EBML_MAGIC = b"\x1a\x45\xdf\xa3"  # Matroska/WebM's EBML header — the non-ISOBMFF tell.


# ---------- generic box walking ---------- #


def _iter_boxes(fh: IO[bytes], start: int, end: int) -> Iterator[tuple[str, int, int]]:
    """Yield `(box_type, payload_start, payload_end)` for each direct child box in the
    byte range `[start, end)`. Absolute file offsets; `payload_start`/`payload_end`
    bound the box's content, after its 8- or 16-byte header. Handles 32-bit sizes,
    64-bit `largesize` (size field == 1), and size == 0 (box runs to `end`) — the
    "64-bit sizes" case for very large boxes (typically `mdat`)."""
    pos = start
    while pos + 8 <= end:
        fh.seek(pos)
        header = fh.read(8)
        if len(header) < 8:
            break
        size, box_type_raw = struct.unpack(">I4s", header)
        box_type = box_type_raw.decode("latin-1")
        header_len = 8
        if size == 1:
            largesize_bytes = fh.read(8)
            if len(largesize_bytes) < 8:
                raise ValueError(f"truncated largesize for box {box_type!r} at offset {pos}")
            size = struct.unpack(">Q", largesize_bytes)[0]
            header_len = 16
        elif size == 0:
            size = end - pos
        box_end = pos + size
        if size < header_len or box_end > end:
            raise ValueError(f"malformed box {box_type!r} at offset {pos}: size {size}")
        yield box_type, pos + header_len, box_end
        pos = box_end


def _find_box(fh: IO[bytes], box_type: str, start: int, end: int) -> tuple[int, int] | None:
    for bt, ps, pe in _iter_boxes(fh, start, end):
        if bt == box_type:
            return ps, pe
    return None


# ---------- track (`trak`) parsing ---------- #

_KIND_BY_HANDLER = {"vide": "video", "soun": "audio"}
_SUBTITLE_HANDLERS = frozenset({"sbtl", "text", "subt"})


def _kind_for_handler(handler_type: str) -> str:
    if handler_type in _KIND_BY_HANDLER:
        return _KIND_BY_HANDLER[handler_type]
    if handler_type in _SUBTITLE_HANDLERS:
        return "subtitle"
    return "other"


def _read_handler_type(fh: IO[bytes], ps: int) -> str:
    # hdlr (FullBox): version+flags(4) + pre_defined(4) + handler_type(4) + ...
    fh.seek(ps + 8)
    return fh.read(4).decode("latin-1")


@dataclass
class _Track:
    """Everything the sample-layout walk needs for one track, parsed once from `moov`. Sample
    data itself is never read here — `stsz`/`stsc`/`stco` are kept as box byte-ranges
    and only materialized lazily, at extraction time, so `probe_streams` stays cheap
    regardless of file length."""

    index: int
    kind: str
    codec: str
    # h264/hevc: list of parameter-set NAL bytes (config-record order). aac: (audioObjectType,
    # sampling_frequency_index, channel_configuration). opus: the dOps payload, verbatim.
    # Else: None.
    config: object
    length_size: int | None  # avcC/hvcC NAL length-prefix width in bytes (h264/hevc only).
    stsz: tuple[int, int]
    stsc: tuple[int, int]
    stco: tuple[int, int]
    stco_is64: bool


def _parse_stsd(fh: IO[bytes], ps: int, pe: int) -> tuple[str, int, int]:
    """Return `(fourcc, entry_payload_start, entry_payload_end)` for a `stsd` box's sole
    sample entry. Refuses (`NotImplementedError`) when `entry_count` != 1 — this module
    never guesses which config record applies to which samples (spec §12.20.1)."""
    fh.seek(ps + 4)  # skip stsd's own version+flags
    entry_count = struct.unpack(">I", fh.read(4))[0]
    entries = list(_iter_boxes(fh, ps + 8, pe))
    if entry_count != 1 or len(entries) != 1:
        noun = "entry" if len(entries) == 1 else "entries"
        raise NotImplementedError(
            f"stsd entry_count={entry_count} ({len(entries)} {noun} found) — multiple sample "
            "descriptions on one track are not supported, refusing to guess which config "
            "record applies to which samples"
        )
    fourcc, entry_ps, entry_pe = entries[0]
    return fourcc, entry_ps, entry_pe


def _parse_avcc(fh: IO[bytes], ps: int, pe: int) -> tuple[list[bytes], int]:
    """AVCDecoderConfigurationRecord → (SPS-then-PPS NAL list in stored order, NAL
    length-prefix byte width)."""
    fh.seek(ps)
    data = fh.read(pe - ps)
    if len(data) < 6:
        raise ValueError("avcC too short")
    length_size = (data[4] & 0x03) + 1
    num_sps = data[5] & 0x1F
    pos = 6
    nals: list[bytes] = []
    for _ in range(num_sps):
        nal_len = struct.unpack(">H", data[pos : pos + 2])[0]
        pos += 2
        nals.append(data[pos : pos + nal_len])
        pos += nal_len
    num_pps = data[pos]
    pos += 1
    for _ in range(num_pps):
        nal_len = struct.unpack(">H", data[pos : pos + 2])[0]
        pos += 2
        nals.append(data[pos : pos + nal_len])
        pos += nal_len
    return nals, length_size


def _parse_hvcc(fh: IO[bytes], ps: int, pe: int) -> tuple[list[bytes], int]:
    """HEVCDecoderConfigurationRecord → (parameter-set NAL list in stored array order —
    conventionally VPS/SPS/PPS, NAL length-prefix byte width)."""
    fh.seek(ps)
    data = fh.read(pe - ps)
    if len(data) < 23:
        raise ValueError("hvcC too short")
    length_size = (data[21] & 0x03) + 1
    num_arrays = data[22]
    pos = 23
    nals: list[bytes] = []
    for _ in range(num_arrays):
        pos += 1  # array_completeness(1) + reserved(1) + NAL_unit_type(6) — type unused, take all
        num_nalus = struct.unpack(">H", data[pos : pos + 2])[0]
        pos += 2
        for _ in range(num_nalus):
            nal_len = struct.unpack(">H", data[pos : pos + 2])[0]
            pos += 2
            nals.append(data[pos : pos + nal_len])
            pos += nal_len
    return nals, length_size


def _read_descriptor_len(data: bytes, pos: int) -> tuple[int, int]:
    """MPEG-4 descriptor variable-length size field (base-128, continuation bit high)."""
    val = 0
    for _ in range(4):
        b = data[pos]
        pos += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, pos
    raise ValueError("esds: descriptor length field too long")


def _parse_esds(fh: IO[bytes], ps: int, pe: int) -> tuple[bytes, int]:
    """esds (ES_Descriptor) → (raw AudioSpecificConfig bytes, objectTypeIndication)."""
    fh.seek(ps)
    data = fh.read(pe - ps)
    pos = 4  # skip esds's own version+flags
    tag = data[pos]
    pos += 1
    if tag != 0x03:
        raise ValueError(f"esds: expected ES_Descriptor tag 0x03, got 0x{tag:02x}")
    _len, pos = _read_descriptor_len(data, pos)
    pos += 2  # ES_ID
    flags = data[pos]
    pos += 1
    if flags & 0x80:  # streamDependenceFlag
        pos += 2
    if flags & 0x40:  # URL_Flag
        url_len = data[pos]
        pos += 1 + url_len
    if flags & 0x20:  # OCRstreamFlag
        pos += 2
    tag = data[pos]
    pos += 1
    if tag != 0x04:
        raise ValueError(f"esds: expected DecoderConfigDescriptor tag 0x04, got 0x{tag:02x}")
    _len, pos = _read_descriptor_len(data, pos)
    object_type = data[pos]
    pos += 1
    pos += 1 + 3 + 4 + 4  # streamType/upStream/reserved, bufferSizeDB, maxBitrate, avgBitrate
    tag = data[pos]
    pos += 1
    if tag != 0x05:
        raise ValueError(f"esds: expected DecoderSpecificInfo tag 0x05, got 0x{tag:02x}")
    asc_len, pos = _read_descriptor_len(data, pos)
    asc = data[pos : pos + asc_len]
    return asc, object_type


def _parse_audio_specific_config(asc: bytes) -> tuple[int, int, int]:
    """AudioSpecificConfig → (audioObjectType, sampling_frequency_index, channel_configuration)."""
    if len(asc) < 2:
        raise ValueError("AudioSpecificConfig too short")
    b0, b1 = asc[0], asc[1]
    audio_object_type = (b0 >> 3) & 0x1F
    sfi = ((b0 & 0x07) << 1) | (b1 >> 7)
    if sfi == 0xF:
        raise NotImplementedError(
            "AAC explicit sampling frequency (sampling_frequency_index 15) has no ADTS "
            "representation"
        )
    chan_cfg = (b1 >> 3) & 0x0F
    return audio_object_type, sfi, chan_cfg


def _resolve_codec(
    fh: IO[bytes], fourcc: str, entry_ps: int, entry_pe: int, fixed: int
) -> tuple[str, str | None, object, int | None]:
    """Return `(codec, config, length_size)` for a track's `stsd` sample
    entry. `config`/`length_size` are the codec-specific payload a consumer needs
    — see `_Track.config`. An unrecognized fourcc comes back as `(fourcc, None, None)`:
    named by its own four-character code and **still promotable**, because since 3.12 the
    member is muxed rather than synthesized and the muxer does not need a config record to
    copy samples (see `_PINNED_CODECS`, retired). A RECOGNIZED codec missing its mandatory
    config box still raises — that is a malformed track, not an unknown one."""
    children_start = entry_ps + fixed
    if fourcc in _H264_FOURCCS:
        avcc = _find_box(fh, "avcC", children_start, entry_pe)
        if avcc is None:
            raise ValueError(f"'{fourcc}' sample entry has no 'avcC' config box")
        nals, length_size = _parse_avcc(fh, *avcc)
        return "h264", nals, length_size
    if fourcc in _HEVC_FOURCCS:
        hvcc = _find_box(fh, "hvcC", children_start, entry_pe)
        if hvcc is None:
            raise ValueError(f"'{fourcc}' sample entry has no 'hvcC' config box")
        nals, length_size = _parse_hvcc(fh, *hvcc)
        return "hevc", nals, length_size
    if fourcc == "mp4a":
        esds = _find_box(fh, "esds", children_start, entry_pe)
        if esds is None:
            raise ValueError("'mp4a' sample entry has no 'esds' config box")
        asc, object_type = _parse_esds(fh, *esds)
        if object_type != _AAC_OBJECT_TYPE_INDICATION:
            return f"mp4a(objectType=0x{object_type:02x})", None, None
        config = _parse_audio_specific_config(asc)
        return "aac", config, None
    if fourcc == "Opus":
        dops = _find_box(fh, "dOps", children_start, entry_pe)
        if dops is None:
            raise ValueError("'Opus' sample entry has no 'dOps' config box")
        fh.seek(dops[0])
        payload = fh.read(dops[1] - dops[0])
        return "opus", payload, None
    return fourcc, None, None


def _parse_trak(fh: IO[bytes], trak_ps: int, trak_pe: int, index: int) -> _Track:
    mdia = _find_box(fh, "mdia", trak_ps, trak_pe)
    if mdia is None:
        raise ValueError(f"track {index}: no 'mdia' box")
    mdia_ps, mdia_pe = mdia

    hdlr = _find_box(fh, "hdlr", mdia_ps, mdia_pe)
    if hdlr is None:
        raise ValueError(f"track {index}: no 'hdlr' box")
    kind = _kind_for_handler(_read_handler_type(fh, hdlr[0]))

    minf = _find_box(fh, "minf", mdia_ps, mdia_pe)
    stbl = _find_box(fh, "stbl", *minf) if minf else None
    if stbl is None:
        raise ValueError(f"track {index}: no 'stbl' (sample table) box")
    stbl_ps, stbl_pe = stbl

    stsd = _find_box(fh, "stsd", stbl_ps, stbl_pe)
    if stsd is None:
        raise ValueError(f"track {index}: no 'stsd' box")
    fourcc, entry_ps, entry_pe = _parse_stsd(fh, *stsd)
    fixed = _VIDEO_SAMPLE_ENTRY_FIXED if kind == "video" else _AUDIO_SAMPLE_ENTRY_FIXED
    codec, config, length_size = _resolve_codec(fh, fourcc, entry_ps, entry_pe, fixed)

    stsz = _find_box(fh, "stsz", stbl_ps, stbl_pe)
    stsc = _find_box(fh, "stsc", stbl_ps, stbl_pe)
    stco = _find_box(fh, "stco", stbl_ps, stbl_pe)
    stco_is64 = False
    if stco is None:
        stco = _find_box(fh, "co64", stbl_ps, stbl_pe)
        stco_is64 = True
    if stsz is None or stsc is None or stco is None:
        raise ValueError(f"track {index}: missing sample table box(es) (stsz/stsc/stco|co64)")

    return _Track(
        index=index,
        kind=kind,
        codec=codec,
        config=config,
        length_size=length_size,
        stsz=stsz,
        stsc=stsc,
        stco=stco,
        stco_is64=stco_is64,
    )


def _parse_container(path: Path) -> list[_Track]:
    with path.open("rb") as fh:
        head = fh.read(4)
        if head == _EBML_MAGIC:
            raise ValueError(
                f"{path}: Matroska/WebM (EBML) container — stream extraction is ISOBMFF "
                "only (mp4/m4a/mov) in this increment"
            )
        size = path.stat().st_size
        moov = _find_box(fh, "moov", 0, size)
        if moov is None:
            raise ValueError(
                f"{path}: no 'moov' box found — not a supported ISOBMFF file "
                "(stream extraction is ISOBMFF only)"
            )
        tracks: list[_Track] = []
        for bt, ps, pe in _iter_boxes(fh, *moov):
            if bt != "trak":
                continue
            tracks.append(_parse_trak(fh, ps, pe, index=len(tracks)))
        return tracks


# ---------- sample table → (offset, size) layout ---------- #


def _read_stsz(fh: IO[bytes], ps: int, pe: int) -> list[int]:
    fh.seek(ps + 4)  # skip version+flags
    sample_size, sample_count = struct.unpack(">II", fh.read(8))
    if sample_size != 0:
        return [sample_size] * sample_count
    data = fh.read(sample_count * 4)
    return list(struct.unpack(f">{sample_count}I", data))


def _read_stsc(fh: IO[bytes], ps: int, pe: int) -> list[tuple[int, int, int]]:
    fh.seek(ps + 4)
    (entry_count,) = struct.unpack(">I", fh.read(4))
    data = fh.read(entry_count * 12)
    return [struct.unpack(">III", data[i : i + 12]) for i in range(0, len(data), 12)]


def _read_stco(fh: IO[bytes], ps: int, pe: int, is64: bool) -> list[int]:
    fh.seek(ps + 4)
    (entry_count,) = struct.unpack(">I", fh.read(4))
    if is64:
        data = fh.read(entry_count * 8)
        return list(struct.unpack(f">{entry_count}Q", data))
    data = fh.read(entry_count * 4)
    return list(struct.unpack(f">{entry_count}I", data))


def _iter_sample_layout(fh: IO[bytes], track: _Track) -> Iterator[tuple[int, int]]:
    """Yield `(file_offset, size)` for every sample of `track`, in decode order — the
    sample table's own order, which the `stsz`/`stsc`/`stco` triple defines directly:
    walk chunks in `stco` order, and within each chunk lay out `stsc`'s run-length
    sample-per-chunk count using `stsz`'s per-sample sizes, consecutively from the
    chunk's file offset."""
    sizes = _read_stsz(fh, *track.stsz)
    chunk_offsets = _read_stco(fh, *track.stco, track.stco_is64)
    stsc_entries = _read_stsc(fh, *track.stsc)
    num_chunks = len(chunk_offsets)
    total = len(sizes)
    sample_idx = 0
    for i, (first_chunk, samples_per_chunk, _sample_desc_index) in enumerate(stsc_entries):
        end_chunk = stsc_entries[i + 1][0] - 1 if i + 1 < len(stsc_entries) else num_chunks
        for chunk_num in range(first_chunk, end_chunk + 1):
            if chunk_num < 1 or chunk_num > num_chunks:
                break
            offset = chunk_offsets[chunk_num - 1]
            for _ in range(samples_per_chunk):
                if sample_idx >= total:
                    return
                size = sizes[sample_idx]
                yield offset, size
                offset += size
                sample_idx += 1


# ---------- public API ---------- #


def probe_streams(path: Path) -> list[StreamInfo]:
    """One `StreamInfo` per elementary stream (track) in the ISOBMFF container at
    `path`, in `moov` track order (`index` == the spec's `stream_id=` integer). Reads
    only the `moov` box tree — cheap regardless of file length. Raises `ValueError` for
    a non-ISOBMFF container or a malformed/incomplete track."""
    tracks = _parse_container(Path(path))
    return [
        StreamInfo(
            t.index,
            t.kind,
            t.codec,
            _MEDIA_TYPE_BY_KIND.get(t.kind),
        )
        for t in tracks
    ]


def sample_count(path: Path, stream_id: int) -> int:
    """How many samples track `stream_id` holds, per the container's OWN tables.

    The engine-free half of the 3.12 identity contract (spec §12.20 item 1): this is the
    number the `framing:` stamp carries, and the number a muxed member is checked against
    by `corpus.mux`. It is deliberately computed here — by this package's own ISOBMFF
    reader, which has no ffmpeg in it — so that the check and the thing it checks do not
    share an implementation, and therefore cannot share a failure mode.

    Counts the sample-table layout rather than reading any sample data, so it is cheap on
    a multi-GB track. Raises `ValueError` if `stream_id` doesn't name a track.
    """
    src = Path(path)
    tracks = _parse_container(src)
    track = next((t for t in tracks if t.index == stream_id), None)
    if track is None:
        raise ValueError(f"stream_id={stream_id}: no such track ({len(tracks)} track(s) in {src})")
    with src.open("rb") as fh:
        return sum(1 for _ in _iter_sample_layout(fh, track))


def sample_sizes(path: Path, stream_id: int) -> list[int]:
    """Track `stream_id`'s sample sizes, in decode order — the **re-framing fingerprint**.

    `sample_count` answers *how many*; this answers *which*, and the difference is what makes
    it a content check rather than a length check. Two members that hold the same samples have
    the same size sequence no matter how a muxer chose to lay the boxes out: re-enveloping
    moves every sample's file OFFSET and none of their SIZES. A re-encode, a dropped sample, a
    reordering, or a differently-framed payload all change it.

    This is what §12.37's continuity question actually needs. Byte containment cannot answer
    it — re-enveloping changes the artifact's blake3 by construction, so a comparison of ids
    can only ever report divergence (see `corpus.continuity`). The sample sequence is the
    invariant underneath the envelope.

    Engine-free, like everything else in this module, and reads only the sample tables — no
    sample payload is touched, so it stays cheap on a multi-GB track.
    """
    src = Path(path)
    tracks = _parse_container(src)
    track = next((t for t in tracks if t.index == stream_id), None)
    if track is None:
        raise ValueError(f"stream_id={stream_id}: no such track ({len(tracks)} track(s) in {src})")
    with src.open("rb") as fh:
        return [size for _offset, size in _iter_sample_layout(fh, track)]
