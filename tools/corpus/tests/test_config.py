"""Config loader tests — corpus.toml parsing + env-var overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from corpus import config


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def test_capture_video_hosts(tmp_path, monkeypatch):
    monkeypatch.delenv("CORPUS_VIDEO_HOSTS", raising=False)
    root = _make_corpus(tmp_path)
    # Default: no extra hosts.
    assert config.load_config(root).capture == {"video_hosts": []}
    # File hosts are normalized (lowercased, trailing dot stripped), deduped, sorted.
    (root / "corpus.toml").write_text(
        '[corpus.capture]\nvideo_hosts = ["PeerTube.example", "lectures.edu", "peertube.example"]\n',
        encoding="utf-8",
    )
    assert config.load_config(root).capture["video_hosts"] == ["lectures.edu", "peertube.example"]
    # Env unions with the file.
    monkeypatch.setenv("CORPUS_VIDEO_HOSTS", "extra.tv, lectures.edu")
    assert config.load_config(root).capture["video_hosts"] == [
        "extra.tv",
        "lectures.edu",
        "peertube.example",
    ]


def test_no_config_no_env_defaults_to_local_and_noop(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path)
    # Wipe any inherited env vars that would override defaults.
    for k in [
        "CORPUS_STORE",
        "CORPUS_TRANSCRIBE",
        "CORPUS_AZURE_ACCOUNT",
        "CORPUS_AZURE_CONTAINER",
        "CORPUS_AZURE_PREFIX",
        "CORPUS_S3_BUCKET",
        "CORPUS_S3_REGION",
        "CORPUS_S3_PREFIX",
        "WHISPER_BASE_URL",
    ]:
        monkeypatch.delenv(k, raising=False)
    cfg = config.load_config(root)
    assert cfg.store == {"backend": "local"}
    assert cfg.transcription == {"adapter": "noop"}


def test_corpus_toml_parsed(tmp_path, monkeypatch):
    for k in (
        "CORPUS_STORE",
        "CORPUS_TRANSCRIBE",
        "CORPUS_AZURE_ACCOUNT",
        "CORPUS_AZURE_CONTAINER",
        "CORPUS_AZURE_PREFIX",
        "WHISPER_BASE_URL",
    ):
        monkeypatch.delenv(k, raising=False)
    root = _make_corpus(tmp_path)
    (root / "corpus.toml").write_text(
        """\
[corpus.store]
backend = "azure"
account = "mystorage"
container = "corpus"
prefix = "artifacts/"

[corpus.transcription]
adapter = "http-whisper"
base_url = "http://whisper.internal:8000"
""",
        encoding="utf-8",
    )
    cfg = config.load_config(root)
    assert cfg.store["backend"] == "azure"
    assert cfg.store["account"] == "mystorage"
    assert cfg.store["container"] == "corpus"
    assert cfg.store["prefix"] == "artifacts/"
    assert cfg.transcription["adapter"] == "http-whisper"
    assert cfg.transcription["base_url"] == "http://whisper.internal:8000"


def test_env_overrides_file(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path)
    (root / "corpus.toml").write_text(
        """\
[corpus.store]
backend = "local"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CORPUS_STORE", "s3")
    monkeypatch.setenv("CORPUS_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("CORPUS_S3_REGION", "us-east-1")
    monkeypatch.delenv("CORPUS_TRANSCRIBE", raising=False)
    cfg = config.load_config(root)
    assert cfg.store["backend"] == "s3"
    assert cfg.store["bucket"] == "test-bucket"
    assert cfg.store["region"] == "us-east-1"


def test_whisper_base_url_env_back_compat(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path)
    monkeypatch.setenv("CORPUS_TRANSCRIBE", "http-whisper")
    monkeypatch.setenv("WHISPER_BASE_URL", "http://whisper.example:9000")
    monkeypatch.delenv("CORPUS_STORE", raising=False)
    cfg = config.load_config(root)
    assert cfg.transcription["adapter"] == "http-whisper"
    assert cfg.transcription["base_url"] == "http://whisper.example:9000"


def test_unknown_store_backend_raises(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path)
    monkeypatch.setenv("CORPUS_STORE", "weirdbackend")
    monkeypatch.delenv("CORPUS_TRANSCRIBE", raising=False)
    with pytest.raises(ValueError, match="unknown store backend"):
        config.load_config(root)


def test_unknown_transcription_adapter_raises(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path)
    monkeypatch.delenv("CORPUS_STORE", raising=False)
    monkeypatch.setenv("CORPUS_TRANSCRIBE", "whisper-but-spelled-wrong")
    with pytest.raises(ValueError, match="unknown transcription adapter"):
        config.load_config(root)


def test_malformed_toml_falls_through_to_defaults(tmp_path, monkeypatch):
    """Bad TOML doesn't crash the load; defaults apply."""
    for k in ("CORPUS_STORE", "CORPUS_TRANSCRIBE", "WHISPER_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    root = _make_corpus(tmp_path)
    (root / "corpus.toml").write_text("this isn't = valid [toml", encoding="utf-8")
    cfg = config.load_config(root)
    assert cfg.store == {"backend": "local"}
    assert cfg.transcription == {"adapter": "noop"}
