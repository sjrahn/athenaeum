"""P6 — end-to-end acceptance against a vendor-nothing scratch corpus.

Drives the real CLI (`corpus._cli.dispatch`, the same path the console script runs)
through the full lifecycle on a corpus that vendors NO universal schemas — proving
the generalization holds:

  (a) every step succeeds though `schema/` holds only `composite/<ns>/` + the local
      origin overlay — the universal mime / atom / composite-issue schemas resolve
      from the packaged defaults;
  (b) no `corpus.toml` / creds — `LocalArtifactStore` writes + reads `artifacts/`;
  (c) a video with the NoOp transcriber drafts to a record + a spec-clean
      `transcription-unavailable` issue (no crash);
  (d) re-running a `resolve` is a cache hit — the urihash is stable.

This is the integration gate the per-phase unit tests don't cover: real init, real
ingest of real bytes, real draft → lint, real chained transforms.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from corpus import hashing
from corpus._cli import dispatch

_DATA = Path(__file__).parent / "data"
_HAVE_FFMPEG = shutil.which("ffmpeg") is not None


def _init(tmp_path: Path) -> Path:
    root = tmp_path / "scratch"
    assert dispatch(["init", str(root), "--namespace", "document"]) == 0
    # Vendor-nothing: no universal mime/atom schemas live locally.
    assert not (root / "schema" / "mime").exists()
    assert not (root / "schema" / "atom").exists()
    assert (root / "schema" / "composite" / "document").is_dir()
    assert not (root / "corpus.toml").exists()  # (b) no config
    return root


def _ingest(root: Path, src: Path) -> str:
    """Copy `src` into the corpus and ingest it; return the record id (blake3)."""
    rid = hashing.hash_file(src)["blake3"]
    staged = root / src.name
    shutil.copyfile(src, staged)
    assert dispatch(["ingest", str(staged), "--corpus-root", str(root)]) == 0
    return rid


def test_e2e_pdf_lifecycle(tmp_path, capsys):
    root = _init(tmp_path)
    pdf = _ingest(root, _DATA / "onepager.pdf")
    capsys.readouterr()

    # (b) bytes landed in the local store, no config needed.
    assert (root / "artifacts" / pdf[:2] / f"{pdf}.pdf").is_file()

    # Stub lints clean; draft; draft lints clean.
    assert dispatch(["lint", pdf, "--corpus-root", str(root)]) == 0
    assert dispatch(["draft", pdf, "--corpus-root", str(root)]) == 0
    assert dispatch(["lint", pdf, "--corpus-root", str(root)]) == 0
    capsys.readouterr()

    # The drafter ran: status advanced and PDF metadata was extracted. (onepager.pdf
    # is image-only — no text layer — so a zero-segment body is the correct outcome;
    # `body` still runs cleanly.)
    from corpus import paths, records

    post = records.load(paths.record_path(root, pdf))
    assert post.metadata["status"] == "draft"
    assert "page_count" in post.metadata["_artifact"]["fields"]
    assert dispatch(["body", pdf, "--corpus-root", str(root)]) == 0
    capsys.readouterr()

    # (d) resolve page=1, then again → identical cache path (stable urihash).
    assert dispatch(["resolve", f"corpus://{pdf}?page=1", "--corpus-root", str(root)]) == 0
    first = capsys.readouterr().out.strip()
    assert dispatch(["resolve", f"corpus://{pdf}?page=1", "--corpus-root", str(root)]) == 0
    second = capsys.readouterr().out.strip()
    assert first == second
    assert Path(first).is_file() and Path(first).suffix == ".png"

    # Chained transforms: pdf → page → image → bbox → resize.
    chained = f"corpus://{pdf}?page=1&bbox=0.1,0.1,0.5,0.5&resize=400x300"
    assert dispatch(["resolve", chained, "--corpus-root", str(root)]) == 0
    chained_out = capsys.readouterr().out.strip()
    assert Path(chained_out).is_file()
    assert chained_out != first  # different URI → different cache file

    # Edit loop: decompose → compile (lint-gated rebuild).
    work = tmp_path / "work"
    assert dispatch(["decompose", pdf, "--into", str(work), "--corpus-root", str(root)]) == 0
    assert (work / "manifest.corpus").is_file()
    assert dispatch(["compile", str(work), "--corpus-root", str(root)]) == 0
    assert dispatch(["lint", pdf, "--corpus-root", str(root)]) == 0


def test_e2e_png_and_packaged_fallback(tmp_path, capsys):
    root = _init(tmp_path)
    png = _ingest(root, _DATA / "sample.png")
    capsys.readouterr()

    assert dispatch(["draft", png, "--corpus-root", str(root)]) == 0
    assert dispatch(["lint", png, "--corpus-root", str(root)]) == 0
    capsys.readouterr()

    # (a) `atoms` lists packaged overlays though the corpus vendors none locally.
    assert dispatch(["atoms", "--corpus-root", str(root)]) == 0
    atoms_out = capsys.readouterr().out
    assert "text/transcript" in atoms_out
    assert "text/data-table" in atoms_out

    # health runs offline and sees the records.
    assert dispatch(["health", "--corpus-root", str(root)]) == 0
    assert '"total_records": 1' in capsys.readouterr().out


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg not installed")
def test_e2e_video_noop_transcription(tmp_path, capsys):
    """(c) A video drafts to a record + a spec-clean transcription-unavailable issue
    under the default NoOp transcriber — no crash, lint stays clean."""
    from corpus import paths, records

    root = _init(tmp_path)
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-shortest", str(clip),
        ],
        check=True,
    )
    vid = _ingest(root, clip)
    capsys.readouterr()

    assert dispatch(["draft", vid, "--corpus-root", str(root)]) == 0
    assert dispatch(["lint", vid, "--corpus-root", str(root)]) == 0

    post = records.load(paths.record_path(root, vid))
    issues = list(records.iter_issue_blocks(post))
    assert any(i["id"] == "transcription-unavailable" for i in issues)
    tu = next(i for i in issues if i["id"] == "transcription-unavailable")
    assert tu["fields"]["severity"] == "warning"
    assert tu["fields"]["resolution"] == "open"
