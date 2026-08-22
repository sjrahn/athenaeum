#!/usr/bin/env python3
"""Generator for testdata/synthetic/ — the three fixture shapes the real-artifact exemplar
library (testdata/exemplars.yaml) skipped because no suitably-small real artifact existed
(see testdata/README.md's "synthetic tier" paragraph).

The bytes this script produces are committed to the repo and are what the manifest actually
pins (blake3 over the committed file, not over a fresh run of this script) — an encoder
version drift (ffmpeg / libheif) changes the bytes without changing the content, and the
whole point of v32's payload-identity ruling (spec/CHANGELOG.md) is that identity should
never hang on tool-version-sensitive wrapper bytes. Re-running this script is for
*regenerating or extending* the fixture set later, not for reproducing today's committed
bytes byte-for-byte.

Three fixtures:

  synthetic-audio.m4a     — ffmpeg: 1s mono sine wave, AAC, ISOBMFF/M4A container.
                            Provenance: ffmpeg n9.0.1 (see below for the exact invocation).
  synthetic-message.eml   — pure stdlib, hand-assembled bytes (no email.generator — this
                            script controls header order, boundary strings, and line endings
                            exactly, so the file is reproducible byte-for-byte across runs).
                            Deterministic: fixed Date/Message-ID/boundaries, ASCII-only.
  synthetic-image.heic    — heif-enc (libheif): a tiny 4x4 solid-color PNG (built in-code,
                            no Pillow) re-encoded to HEIC.
                            Provenance: libheif 1.23.1 heif-enc.

Usage:
    uv run --no-sync python testdata/synthetic/gen.py [--skip-audio] [--skip-heic]

(The .eml generation has no external dependency and always runs.)
"""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# synthetic-audio.m4a — ffmpeg, 1s mono sine wave, AAC in an M4A container.
# ---------------------------------------------------------------------------

_FFMPEG_ARGS = [
    "ffmpeg", "-hide_banner", "-y",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
    "-ac", "1", "-ar", "8000",
    "-c:a", "aac", "-b:a", "24k",
    "-movflags", "+faststart",
]


def gen_audio(out_path: Path) -> bool:
    """1s mono 440Hz sine wave, AAC LC, 8kHz/24kbps, M4A container (`ftyp` brand `M4A `, so
    it sniffs as audio/mp4 by mime._SIGNATURES with no reliance on the .m4a extension).
    Smallest reasonable settings — mono, low sample rate, low bitrate — for a <30KB target."""
    if shutil.which("ffmpeg") is None:
        print("SKIP synthetic-audio.m4a: ffmpeg not found on PATH")
        return False
    result = subprocess.run(
        [*_FFMPEG_ARGS, str(out_path)], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"SKIP synthetic-audio.m4a: ffmpeg failed:\n{result.stderr}")
        return False
    print(f"generated {out_path.name} ({out_path.stat().st_size} bytes)")
    return True


# ---------------------------------------------------------------------------
# synthetic-message.eml — hand-assembled, deterministic RFC5322/2046 bytes.
# ---------------------------------------------------------------------------

_CRLF = b"\r\n"
_OUTER_BOUNDARY = b"OUTER-BOUNDARY-SYNTH-0001"


def _tiny_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A minimal valid PNG, solid color, built by hand (struct + zlib, no Pillow) — RGB,
    no alpha, no interlace, one IDAT chunk. Deterministic (zlib compression level pinned)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        crc = struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + body + crc

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    idat = chunk(b"IDAT", zlib.compress(raw, 9))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _wrap_base64(data: bytes) -> bytes:
    """Base64, wrapped at the RFC 2045 canonical 76 chars/line, CRLF-terminated —
    hand-wrapped (not `email.generator`) so the exact bytes are pinned across Python versions."""
    import base64

    b64 = base64.b64encode(data)
    lines = [b64[i : i + 76] for i in range(0, len(b64), 76)]
    return _CRLF.join(lines) + _CRLF


def _nested_submessage() -> bytes:
    """A small, complete RFC5322 message — the payload of the outer message's nested
    `message/rfc822` part. This is the shape tools/src/corpus/emlfile.py's verbatim-byte-slice
    identity fix (commit 680a756) regression-covers: the nested part's member identity is this
    exact byte span sliced out of the outer container, never a re-serialization of it."""
    headers = _CRLF.join(
        [
            b"Message-ID: <synthetic-nested-0001@athenaeum.example>",
            b"MIME-Version: 1.0",
            b"Date: Mon, 01 Jan 2024 00:00:00 +0000",
            b"From: nested-sender@athenaeum.example",
            b"To: nested-recipient@athenaeum.example",
            b"Subject: Nested synthetic sub-message",
            b'Content-Type: text/plain; charset="us-ascii"',
            b"Content-Transfer-Encoding: 7bit",
        ]
    )
    body = (
        b"This is the body of a small, complete nested message, embedded verbatim as a "
        b"message/rfc822 part of the outer synthetic exemplar. It exists to exercise the "
        b"nested-message identity path: its bytes are sliced directly out of the container, "
        b"never re-serialized."
    )
    return headers + _CRLF + _CRLF + body


def gen_message(out_path: Path) -> bool:
    """`message/rfc822` with three addressable parts: a text/plain body (consumed by body
    rendering, not an embed), a nested message/rfc822 sub-message (part=2), and a PNG
    attachment (part=3). Fully deterministic: fixed Date, fixed Message-ID, fixed boundary
    string, ASCII-only throughout, hand-assembled (no email.generator in the write path)."""
    outer_body_text = (
        b"This is the reply-text body of a synthetic exemplar email message. It carries no "
        b"private content: every byte here was generated for spec and tooling regression "
        b"testing (see testdata/README.md). The message also carries a nested message/rfc822 "
        b"sub-message and a small PNG attachment, to exercise the eml drafter's members block."
    )

    png_bytes = _tiny_png(4, 4, (180, 180, 200))
    nested_bytes = _nested_submessage()

    part_text = _CRLF.join(
        [
            b'Content-Type: text/plain; charset="us-ascii"',
            b"Content-Transfer-Encoding: 7bit",
            b"",
            outer_body_text,
        ]
    )
    part_nested = _CRLF.join(
        [
            b"Content-Type: message/rfc822",
            b"",
            nested_bytes,
        ]
    )
    part_png = _CRLF.join(
        [
            b'Content-Type: image/png; name="pixel.png"',
            b"Content-Transfer-Encoding: base64",
            b'Content-Disposition: attachment; filename="pixel.png"',
            b"",
            _wrap_base64(png_bytes).rstrip(_CRLF),
        ]
    )

    dashes = b"--" + _OUTER_BOUNDARY
    body = _CRLF.join(
        [
            dashes,
            part_text,
            dashes,
            part_nested,
            dashes,
            part_png,
            dashes + b"--",
            b"",
        ]
    )

    headers = _CRLF.join(
        [
            b"Message-ID: <synthetic-message-0001@athenaeum.example>",
            b"MIME-Version: 1.0",
            b"Date: Wed, 01 Jan 2025 00:00:00 +0000",
            b"From: sender@athenaeum.example",
            b"To: recipient@athenaeum.example",
            b"Subject: Synthetic exemplar message",
            b'Content-Type: multipart/mixed; boundary="' + _OUTER_BOUNDARY + b'"',
        ]
    )

    raw = headers + _CRLF + _CRLF + body
    out_path.write_bytes(raw)
    print(f"generated {out_path.name} ({len(raw)} bytes)")
    return True


# ---------------------------------------------------------------------------
# synthetic-image.heic — heif-enc (libheif), from an in-code-generated tiny PNG.
# ---------------------------------------------------------------------------


def gen_heic(out_path: Path) -> bool:
    """A 16x16 solid-color HEIC. Tries `heif-enc` (libheif) first, then ImageMagick
    `magick`/`convert` with a HEIC delegate, then ffmpeg's HEIF muxer. If NO encoder on this
    machine can produce a valid HEIC, this function returns False and the caller must NOT
    fabricate bytes by hand — the shape stays skipped. The intermediate source PNG is
    generated into a scratch temp dir, never left behind in testdata/synthetic/."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        png_path = Path(tmp) / "synthetic-image-source.png"
        png_path.write_bytes(_tiny_png(16, 16, (90, 140, 200)))

        if shutil.which("heif-enc"):
            result = subprocess.run(
                ["heif-enc", "-q", "50", str(png_path), "-o", str(out_path)],
                capture_output=True, text=True,
            )
            if result.returncode == 0 and out_path.is_file():
                print(f"generated {out_path.name} via heif-enc ({out_path.stat().st_size} bytes)")
                return True
            print(f"heif-enc failed:\n{result.stderr}")

        for exe in ("magick", "convert"):
            if shutil.which(exe):
                result = subprocess.run(
                    [exe, str(png_path), str(out_path)], capture_output=True, text=True
                )
                if result.returncode == 0 and out_path.is_file():
                    print(f"generated {out_path.name} via {exe} ({out_path.stat().st_size} bytes)")
                    return True
                print(f"{exe} HEIC encode failed:\n{result.stderr}")

        if shutil.which("ffmpeg"):
            ffmpeg_args = [
                "ffmpeg", "-hide_banner", "-y",
                "-i", str(png_path), "-c:v", "hevc", str(out_path),
            ]
            result = subprocess.run(ffmpeg_args, capture_output=True, text=True)
            if result.returncode == 0 and out_path.is_file():
                print(f"generated {out_path.name} via ffmpeg ({out_path.stat().st_size} bytes)")
                return True
            print(f"ffmpeg HEIC encode failed:\n{result.stderr}")

    print("SKIP synthetic-image.heic: no HEIC encoder (heif-enc / magick / ffmpeg) available")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument("--skip-heic", action="store_true")
    args = parser.parse_args()

    ok = True
    gen_message(HERE / "synthetic-message.eml")
    if not args.skip_audio:
        ok = gen_audio(HERE / "synthetic-audio.m4a") and ok
    if not args.skip_heic:
        ok = gen_heic(HERE / "synthetic-image.heic") and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
