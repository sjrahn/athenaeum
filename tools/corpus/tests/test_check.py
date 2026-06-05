"""`corpus check` (read-only redirect-aware dedup probe) + the capture short-circuit's
redirect-aware second stage.

Builds a tmp corpus with a captured TikTok video and a `tiktok.com` overlay whose
`url_equivalent` drops the volatile `?_r`/`?_t` query the canonical resolves with. The
redirect follow is mocked at `redirects.resolve_final_url` (no network) so a fresh short link
resolves to that canonical. Covers: short link → reported as dup; fresh URL → not captured;
volatile-query normalization; `--force` bypass of the pre-download dedup; redirect-follow
skipped when the URL isn't a short link; exit codes + `--json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import frontmatter

from corpus import capture, paths, records
from corpus._cli import check as check_cli
from corpus._cli import dispatch

VIDEO_ID = "7616385236439485709"
CANONICAL = f"https://www.tiktok.com/@user/video/{VIDEO_ID}"
# The canonical resolves with volatile per-request query params that differ each time.
CANONICAL_VOLATILE = f"{CANONICAL}?_r=1&_t=ZS-abc123"
SHORT_A = "https://vt.tiktok.com/ZSQdnsm4M/"
SHORT_B = "https://vt.tiktok.com/ZSQdWDhqp/"

# tiktok.com overlay: drop the whole query so `?_r`/`?_t` noise doesn't defeat identity.
_OVERLAY = (
    "applies_to: {host_pattern: tiktok.com, include_subdomains: true}\n"
    "capture:\n"
    "  url_equivalent:\n"
    "    query: drop\n"
)

RID = "b2" * 32


def _corpus(tmp_path: Path, *, overlay: str | None = _OVERLAY) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    if overlay is not None:
        d = root / "schema" / "origin" / "web"
        d.mkdir(parents=True, exist_ok=True)
        (d / "tiktok.com.yaml").write_text(overlay, encoding="utf-8")
    return root


def _captured_video(root: Path, uri: str = CANONICAL) -> None:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=RID, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="video/mp4")
    records.append_origin_block(post, uri=uri, snapshot="2026-06-04T00:00:00Z")
    records.dump(post, paths.record_path(root, RID))


def _resolve_to(target: str):
    """A `resolve_final_url` stub that maps any short link to `target`."""
    return mock.patch("corpus.redirects.resolve_final_url", side_effect=lambda u, **k: target)


def _stub_capture():
    """Patch `capture()` to a no-op result so capture_and_ingest can run without a browser."""
    result = capture.CaptureResult(capture_path=Path("/x"), used_video=True)
    return mock.patch.object(capture, "capture", return_value=result)


# ---------- corpus check (CLI) ---------- #


def test_check_short_link_resolves_to_captured_canonical(tmp_path, capsys):
    root = _corpus(tmp_path)
    _captured_video(root)
    with _resolve_to(CANONICAL_VOLATILE):
        rc = dispatch(["check", SHORT_A, "--json", "--corpus-root", str(root)])
    assert rc == check_cli.EXIT_CAPTURED  # 0
    out = json.loads(capsys.readouterr().out)
    assert out["captured"] is True
    assert out["record"] == RID
    assert out["redirected"] is True
    assert out["resolved_url"] == CANONICAL_VOLATILE
    # volatile query params were normalized away from the identity key
    assert out["identity_key"] == CANONICAL


def test_check_fresh_url_not_captured(tmp_path, capsys):
    root = _corpus(tmp_path)
    _captured_video(root)
    rc = dispatch(
        ["check", "https://example.com/never-seen", "--no-follow-redirects",
         "--json", "--corpus-root", str(root)]
    )
    assert rc == check_cli.EXIT_NOT_CAPTURED  # 1
    out = json.loads(capsys.readouterr().out)
    assert out["captured"] is False
    assert out["record"] is None
    assert out["redirected"] is False


def test_check_second_short_link_to_same_video(tmp_path):
    # Two DIFFERENT short links both resolve to the one video → both report captured.
    root = _corpus(tmp_path)
    _captured_video(root)
    for short in (SHORT_A, SHORT_B):
        with _resolve_to(CANONICAL_VOLATILE):
            rc = dispatch(["check", short, "--corpus-root", str(root)])
        assert rc == check_cli.EXIT_CAPTURED


def test_check_no_follow_misses_short_link(tmp_path):
    # With --no-follow-redirects the short link is matched on string identity only → miss.
    root = _corpus(tmp_path)
    _captured_video(root)
    rc = dispatch(["check", SHORT_A, "--no-follow-redirects", "--corpus-root", str(root)])
    assert rc == check_cli.EXIT_NOT_CAPTURED


def test_check_is_read_only(tmp_path):
    # The probe must not write anything: the record file is byte-identical afterward and no
    # new records appear.
    root = _corpus(tmp_path)
    _captured_video(root)
    rec = paths.record_path(root, RID)
    before = rec.read_bytes()
    record_count = len(list((root / "records").rglob("*.md")))
    with _resolve_to(CANONICAL_VOLATILE):
        dispatch(["check", SHORT_A, "--corpus-root", str(root)])
    assert rec.read_bytes() == before
    assert len(list((root / "records").rglob("*.md"))) == record_count


def test_check_human_output(tmp_path, capsys):
    root = _corpus(tmp_path)
    _captured_video(root)
    with _resolve_to(CANONICAL_VOLATILE):
        rc = dispatch(["check", SHORT_A, "--corpus-root", str(root)])
    assert rc == check_cli.EXIT_CAPTURED
    out = capsys.readouterr().out
    assert "captured" in out and RID in out and "via redirect" in out


# ---------- capture_and_ingest pre-download dedup ---------- #


def test_capture_redirect_dedup_short_circuits_before_download(tmp_path):
    # A fresh short link to an already-captured video is caught BEFORE any capture/download.
    root = _corpus(tmp_path)
    _captured_video(root)
    # If capture() ran we'd hit a network/browser; assert it's never called.
    with _resolve_to(CANONICAL_VOLATILE), mock.patch.object(
        capture, "capture", side_effect=AssertionError("capture() must not run on a dup")
    ):
        out = capture.capture_and_ingest(
            SHORT_A, corpus_root=root, opts=capture.CaptureOptions(force=False)
        )
    assert out == paths.record_path(root, RID)
    # the short link was folded into the record's origin uri list (no re-download)
    post = records.load(out)
    uris = list(records.iter_origin_uris(post))
    assert any("vt.tiktok.com/ZSQdnsm4M" in u for u in uris)


def test_capture_force_bypasses_redirect_dedup(tmp_path):
    # --force must skip BOTH dedup stages and proceed to capture (which we stub to a no-op
    # record path so no network is needed).
    root = _corpus(tmp_path)
    _captured_video(root)
    sentinel = paths.record_path(root, "ff" * 32)
    with _resolve_to(CANONICAL_VOLATILE) as resolve_mock, _stub_capture(), mock.patch.object(
        capture, "_ingest_capture", return_value=sentinel
    ):
        out = capture.capture_and_ingest(
            SHORT_A, corpus_root=root, opts=capture.CaptureOptions(force=True)
        )
    assert out == sentinel  # went through capture, not the dedup short-circuit
    resolve_mock.assert_not_called()  # --force never even probes redirects


def test_capture_redirect_probe_skipped_for_non_short_link(tmp_path):
    # A normal canonical URL that ISN'T already captured must NOT trigger a redirect probe
    # (the heuristic gates the network round-trip off the hot path).
    root = _corpus(tmp_path)
    _captured_video(root)
    fresh = "https://www.tiktok.com/@user/video/9999999999999999999"  # different video
    sentinel = paths.record_path(root, "ee" * 32)
    with mock.patch(
        "corpus.redirects.resolve_final_url",
        side_effect=AssertionError("must not probe a non-short-link"),
    ), _stub_capture(), mock.patch.object(capture, "_ingest_capture", return_value=sentinel):
        out = capture.capture_and_ingest(
            fresh, corpus_root=root, opts=capture.CaptureOptions(force=False)
        )
    assert out == sentinel  # proceeded to capture; no redirect probe raised


def test_capture_existing_canonical_still_short_circuits_cheaply(tmp_path):
    # The cheap string-identity stage still works without any redirect probe.
    root = _corpus(tmp_path)
    _captured_video(root)
    with mock.patch(
        "corpus.redirects.resolve_final_url",
        side_effect=AssertionError("cheap hit must not probe redirects"),
    ):
        out = capture.capture_and_ingest(
            CANONICAL, corpus_root=root, opts=capture.CaptureOptions(force=False)
        )
    assert out == paths.record_path(root, RID)
