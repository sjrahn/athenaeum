"""`sidecar:` `format: xml` (spec v51, owner-approved R-0060): an XML sidecar walks under one
fixed tree convention, and everything else about the sidecar — physical pairing, off the
roster, reached through its frame, lifted at promote — is v45 unchanged.

The fixture is a fictional clip producer shaped like a camera's per-clip metadata XML: a
default namespace, attribute-carried values, repeated siblings told apart by an attribute.
The engine knows nothing about it.
"""

from __future__ import annotations

import json

import pytest

from corpus import functional_uri as furi
from corpus import resolver, sidecar
from tests.test_sidecar_lift import _b3, _container, _origin, _promote, _write_overlays
from tests.test_sidecar_through_frame_v45 import _reattest, _roster

_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ClipMeta xmlns="urn:example:clipmeta:ver.1" xmlns:lib="urn:example:lib"
          lastUpdate="2025-11-04T10:37:49-05:00">
  <Duration value="900"/>
  <CreationDate value="2025-11-04T10:37:34-05:00"/>
  <TimecodeTable tcFps="30">
    <Change frameCount="0" value="46484904" status="increment"/>
    <Change frameCount="899" value="45835004" status="end"/>
  </TimecodeTable>
  <VideoFormat>
    <VideoFrame videoCodec="HEVC_3840_2160" captureFps="59.94p" formatFps="59.94p"/>
  </VideoFormat>
  <AudioFormat numOfChannel="2">
    <AudioPort audioCodec="LPCM16" trackDst="CH1"/>
    <AudioPort audioCodec="LPCM24" trackDst="CH2"/>
  </AudioFormat>
  <Device manufacturer="Acme" modelName="CAM-1" serialNo="4294967295"/>
  <RecordingMode type="normal" cacheRec="false" proxy="true"/>
  <Acquisition>
    <Group name="CameraUnit">
      <Item name="Gamma" value="rec709"/>
      <Item name="Primaries" value="rec2020"/>
    </Group>
  </Acquisition>
  <Note>shot on the ridge</Note>
</ClipMeta>
"""


@pytest.fixture
def doc():
    return sidecar.parse_xml(_XML, "C0001M01.XML")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("Duration@value", "900"),  # the default namespace is transparent
        ("@lastUpdate", "2025-11-04T10:37:49-05:00"),  # the document element's own attribute
        ("VideoFormat.VideoFrame@videoCodec", "HEVC_3840_2160"),
        ("TimecodeTable.Change[1]@value", "46484904"),  # positions count from 1
        ("TimecodeTable.Change[@status=end]@frameCount", "899"),
        ("AudioFormat.AudioPort@audioCodec", ["LPCM16", "LPCM24"]),  # repeated siblings: a list
        ("AudioFormat.AudioPort[@trackDst='CH2']@audioCodec", "LPCM24"),
        ("Acquisition.Group[@name=CameraUnit].Item[@name=Primaries]@value", "rec2020"),
        ("VideoFormat.VideoFrame[@captureFps=59.94p]@formatFps", "59.94p"),  # `.` in a value
        ("RecordingMode@proxy", True),  # xsd:boolean words are the format's booleans
        ("RecordingMode@cacheRec", False),
        ("Note", "shot on the ridge"),  # a path ending on an element reads its text
    ],
)
def test_the_xml_tree_convention(doc, path, value):
    assert sidecar._walk(doc, path) == value


@pytest.mark.parametrize(
    "path", ["Device@lens", "Missing.Thing@x", "TimecodeTable.Change[3]@value", "VideoFormat"]
)
def test_a_path_naming_nothing_is_missing(doc, path):
    assert sidecar._walk(doc, path) is sidecar._MISSING


@pytest.mark.parametrize(
    "path", ["Device@a.b@c", "Group[@name=x", "Item[0]@v", "Group[name]@v", "", "Device@x.Lens"]
)
def test_a_malformed_xml_path_refuses_the_declaration(path):
    raw = {"pairing": {"template": "{stem}M01.XML"}, "format": "xml", "prefix": "c_",
           "subtype": "clip", "lift": {"f": path}}
    with pytest.raises(sidecar.DeclarationError, match="XML sidecar path"):
        sidecar.parse_declaration(raw, source_id="clip-export")


def test_a_doctype_is_refused_before_parsing():
    bomb = b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><a v="&x;"/>'
    with pytest.raises(ValueError, match="DOCTYPE"):
        sidecar.parse_xml(bomb, "evil.XML")


def test_present_only_and_flags_read_xml_as_they_read_json(doc):
    decl = sidecar.parse_declaration(
        {
            "pairing": {"template": "{stem}M01.XML"}, "format": "xml", "prefix": "c_",
            "subtype": "clip",
            "lift": {
                "codec": "VideoFormat.VideoFrame@videoCodec",
                "cache_rec": "RecordingMode@cacheRec",  # false: lifts nothing
                "serial": {"path": "Device@serialNo", "omit": ["4294967295"]},
                "modes": {"flags": ["RecordingMode@cacheRec", "RecordingMode@proxy"]},
            },
        },
        source_id="clip-export",
    )
    assert sidecar.project(decl, doc, "C0001.MP4", ()) == {
        "c_codec": "HEVC_3840_2160",
        "c_modes": ["RecordingMode@proxy"],
    }


_OVERLAY = """\
description: a fictional clip producer — one metadata XML beside each clip
sidecar:
  pairing: {template: "{stem}M01.XML"}
  format: xml
  prefix: clip_
  subtype: clip
  lift:
    created: CreationDate@value
    duration_frames: Duration@value
    video_codec: VideoFormat.VideoFrame@videoCodec
    audio_codecs: AudioFormat.AudioPort@audioCodec
    tc_start: TimecodeTable.Change[1]@value
    gamma: Acquisition.Group[@name=CameraUnit].Item[@name=Gamma]@value
"""

_SUB = """\
description: a promoted clip
extended_fields:
  clip_created: {type: string, required: false, description: creation time}
  clip_duration_frames: {type: string, required: false, description: frames}
  clip_video_codec: {type: string, required: false, description: codec}
  clip_audio_codecs: {type: string_or_list, required: false, description: codecs}
  clip_tc_start: {type: string, required: false, description: packed start timecode}
  clip_gamma: {type: string, required: false, description: gamma}
"""

_MEMBERS = {
    "CLIP/C0001.MP4": b"not really an mp4\n",
    "CLIP/C0001M01.XML": _XML,
    "CLIP/C0002.MP4": b"a clip with no sidecar\n",
}


@pytest.fixture
def clips(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    _write_overlays(root, "clip-export", _OVERLAY, "clip", _SUB)
    cid = _container(tmp_path, root, _MEMBERS, "clip-export")
    _reattest(root, cid)
    return root, cid


def test_the_xml_sidecar_is_off_the_roster_and_lifts_at_promote(clips):
    root, cid = clips
    assert set(_roster(root, cid)) == {"CLIP/C0001.MP4", "CLIP/C0002.MP4"}

    assert _promote(root, f"corpus://{cid}?path=CLIP/C0001.MP4") == 0
    block = _origin(root, _b3(_MEMBERS["CLIP/C0001.MP4"]))
    assert (block["id"], block["subtype"]) == ("clip-export", "clip")
    f = block["fields"]
    assert f["clip_created"] == "2025-11-04T10:37:34-05:00"
    assert f["clip_duration_frames"] == "900"
    assert f["clip_audio_codecs"] == ["LPCM16", "LPCM24"]
    assert f["clip_tc_start"] == "46484904"
    assert f["clip_gamma"] == "rec709"

    # the frame with no XML beside it lifts nothing and is not refused
    assert _promote(root, f"corpus://{cid}?path=CLIP/C0002.MP4") == 0
    bare = _origin(root, _b3(_MEMBERS["CLIP/C0002.MP4"]))
    assert not any(k.startswith("clip_") for k in bare.get("fields") or {})


def test_the_sidecar_reading_serves_the_xml_verbatim(clips):
    root, cid = clips
    out = resolver.resolve(f"corpus://{cid}?path=CLIP/C0001.MP4&sidecar", root)
    assert out.suffix == ".xml" and out.read_bytes() == _XML
    meta = json.loads(furi.cache_sidecar_path(out).read_text("utf-8"))
    assert meta["mime"] == "application/xml"
