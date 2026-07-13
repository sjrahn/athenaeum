"""The `?transcribe` resolver op as a 3.0 derivation op (spec §6.2, §6.3, §6.4, §7.2).

The `transcribe` transform + adapters (NoOp / HTTPWhisper) are covered in test_transcription.
This exercises the RESOLVER op path: version-labeled caching by engine (§6.4) and per-host
`transcription:` overlay selection (§7.2), which the op path was missing."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from corpus import functional_uri as furi
from corpus import hashing, paths, records, resolver, schemas
from corpus.store import LocalArtifactStore
from corpus.transcription import TranscriptionResult, TranscriptionUnavailable


class _FakeTranscriber:
    def __init__(self, engine: str, text: str = "the transcript") -> None:
        self.engine = engine
        self._text = text

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        return TranscriptionResult(text=self._text, payload={"text": self._text})

    def render_payload(self, payload: dict) -> str:
        return str(payload.get("text") or "")


def _corpus(tmp_path: Path, *, overlay: str | None = None) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    if overlay is not None:
        odir = root / "schema" / "origin" / "web"
        odir.mkdir(parents=True)
        (odir / "x.test.yaml").write_text(overlay, encoding="utf-8")
    schemas.cache_clear()
    return root


def _ingest_audio(root: Path, *, uri: str) -> str:
    src = root / "clip.mp3"
    src.write_bytes(b"ID3\x00\x00\x00fake-mp3-bytes")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "mp3", src)
    src.unlink()
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "", "status": "stub",
         "transport": f"sha256:{h['sha256']}", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="audio/mpeg", fields={})
    records.append_origin_block(post, uri=uri, snapshot="2026-01-01T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_transcribe_op_is_version_labeled(tmp_path):
    """The transcribe cache key includes the engine and the sidecar records it (§6.4), so a
    different engine yields a distinct cache entry (determinism per engine)."""
    root = _corpus(tmp_path)
    rid = _ingest_audio(root, uri="https://plain.test/clip.mp3")

    out = resolver.resolve(
        f"corpus://{rid}?transcribe", root, transcriber=_FakeTranscriber("eng:v1")
    )
    import json
    assert out.read_text("utf-8").strip() == "the transcript"
    sidecar = json.loads(furi.cache_sidecar_path(out).read_text("utf-8"))
    assert sidecar["engine"] == "eng:v1"  # §6.4 version-label recorded

    # A different engine → a different cache file (version-keyed), not a stale hit.
    out2 = resolver.resolve(
        f"corpus://{rid}?transcribe", root, transcriber=_FakeTranscriber("eng:v2", "v2 text")
    )
    assert out2 != out
    assert out2.read_text("utf-8").strip() == "v2 text"


def test_transcribe_op_honors_per_host_config(tmp_path):
    """§7.2: the record's origin-overlay `transcription:` section selects the backend for the
    op — proven by the per-host http-whisper adapter being chosen (its unreachable-backend
    error), not the NoOp default (`no transcription adapter configured`)."""
    overlay = (
        "applies_to:\n  host_pattern: x.test\n"
        "transcription:\n  adapter: http-whisper\n  base_url: http://127.0.0.1:1\n  model: base\n"
    )
    root = _corpus(tmp_path, overlay=overlay)
    rid = _ingest_audio(root, uri="https://x.test/clip.mp3")
    # No injected transcriber → the resolver resolves the per-host adapter (http-whisper),
    # which fails to reach 127.0.0.1:1 — proving it was selected over the global NoOp default.
    with pytest.raises(TranscriptionUnavailable, match="whisper backend unreachable"):
        resolver.resolve(f"corpus://{rid}?transcribe", root)


def test_transcribe_op_skips_when_disabled(tmp_path):
    """§7.2: `transcription.enabled: false` on the host overlay skips the op — a clear disabled
    signal, not a fall-through to the global backend."""
    overlay = "applies_to:\n  host_pattern: x.test\ntranscription:\n  enabled: false\n"
    root = _corpus(tmp_path, overlay=overlay)
    rid = _ingest_audio(root, uri="https://x.test/clip.mp3")
    with pytest.raises(TranscriptionUnavailable, match="transcription disabled"):
        resolver.resolve(f"corpus://{rid}?transcribe", root)


def test_engine_ids_carry_version(tmp_path):
    """The adapters' engine identity carries a version component (§6.4), not just a class
    name: `noop@1`, `http-whisper[/<model>]@<version>`."""
    from corpus.transcription import HTTPWhisperTranscriber, NoOpTranscriber

    assert NoOpTranscriber().engine == "noop@1"
    assert HTTPWhisperTranscriber(base_url="http://x").engine == "http-whisper@1"
    assert (
        HTTPWhisperTranscriber(base_url="http://x", model="large-v3").engine
        == "http-whisper/large-v3@1"
    )
