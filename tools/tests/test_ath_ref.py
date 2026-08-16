"""`ath ref` — the reference-dataset resolver's CLI slice (spec/ledger.md §6.5):
`status`, `resolve` (ref:// resolution + the corpus:// courtesy redirect), and
`hash` (the registration helper). All tests need the optional `libzim`
dependency to build fixture mirrors — gated at module scope, mirroring
`tests/test_refdata.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

libzim = pytest.importorskip("libzim")

import blake3 as _blake3  # noqa: E402
import libzim.writer as zw  # noqa: E402

from ath._cli import main  # noqa: E402

_HASH_V2 = "2" * 64
_HASH_V1 = "1" * 64
_HASH_BROKEN = "3" * 64
_HASH_NOMIRROR = "4" * 64
_HASH_STORE = "5" * 64
_HASH_ABSENT = "6" * 64
_HASH_UNREGISTERED = "7" * 64


class _Item(zw.Item):
    """Local copy of `tests/test_refdata.py`'s minimal fixture item — not
    imported from there per dispatch (own file, own copy)."""

    def __init__(self, path: str, title: str, content: str, mimetype: str = "text/html"):
        super().__init__()
        self._path = path
        self._title = title
        self._content = content
        self._mimetype = mimetype

    def get_path(self) -> str:
        return self._path

    def get_title(self) -> str:
        return self._title

    def get_mimetype(self) -> str:
        return self._mimetype

    def get_contentprovider(self) -> zw.ContentProvider:
        return zw.StringProvider(self._content)

    def get_hints(self) -> dict:
        return {zw.Hint.FRONT_ARTICLE: 1}


def _build_zim(path: Path, home_text: str, *, with_redirect: bool = False) -> None:
    """A tiny fixture mirror: one 'home' article plus, optionally, a redirect to
    it — enough surface for exact resolution and canonical-id redirect checks."""
    with zw.Creator(str(path)) as creator:
        creator.add_item(_Item("home", "Home", f"<html><body><p>{home_text}</p></body></html>"))
        if with_redirect:
            creator.add_redirection("redirect-to-home", "Redirect", "home", {})
        creator.set_mainpath("home")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A manifest registering four datasets, each exercising one resolution
    outcome: `testwiki` (two path-materialized snapshots — `v2` latest,
    `v1` pinned — with distinct content so bare-vs-pinned is provably
    distinct, plus a redirect on `v2`), `brokenset` (adapter name unregistered
    in this environment), `nomirror` (a registered zim snapshot with no bytes
    anywhere), and `storewiki` (one snapshot materialized only via the corpus
    artifact store, one registered but nowhere materialized — the status
    `store`/`absent` states)."""
    v2 = tmp_path / "v2.zim"
    v1 = tmp_path / "v1.zim"
    _build_zim(v2, "Newer revision.", with_redirect=True)
    _build_zim(v1, "Older revision.")

    corpus_root = tmp_path / "corpus"
    store_zim = corpus_root / "artifacts" / _HASH_STORE[:2] / f"{_HASH_STORE}.zim"
    store_zim.parent.mkdir(parents=True)
    _build_zim(store_zim, "Store-backed revision.")

    manifest = f"""\
org: https://x.test/athenaeum
corpora:
  corpus:
    visibility: public
    path: corpus
ledger:
  ledger: {{}}
references:
  testwiki:
    description: test wiki mirror
    adapter: zim
    latest: v2
    snapshots:
      v2: {{ artifact: {_HASH_V2}, path: {v2} }}
      v1: {{ artifact: {_HASH_V1}, path: {v1} }}
  brokenset:
    description: adapter unregistered in this environment
    adapter: not-a-real-adapter
    latest: t
    snapshots:
      t: {{ artifact: {_HASH_BROKEN} }}
  nomirror:
    description: registered but never materialized
    adapter: zim
    latest: t
    snapshots:
      t: {{ artifact: {_HASH_NOMIRROR} }}
  storewiki:
    description: store-materialized dataset
    adapter: zim
    latest: s1
    snapshots:
      s1: {{ artifact: {_HASH_STORE} }}
      absent: {{ artifact: {_HASH_ABSENT} }}
"""
    (tmp_path / "athenaeum.yaml").write_text(manifest, encoding="utf-8")
    return tmp_path


def _parse_status(out: str) -> dict[str, tuple[str, list[str]]]:
    """Group `ath ref status` output into dataset -> (header line, [snapshot row, …])."""
    blocks: dict[str, tuple[str, list[str]]] = {}
    current = ""
    for line in out.splitlines():
        if not line.startswith(" "):
            current = line.split()[0]
            blocks[current] = (line, [])
        else:
            blocks[current][1].append(line.strip())
    return blocks


# --- status --------------------------------------------------------------


def test_status_materialization_states(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ref", "status", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    blocks = _parse_status(out)

    _, testwiki_rows = blocks["testwiki"]
    assert any(
        row.startswith("v2") and "(latest)" in row and row.endswith("path")
        for row in testwiki_rows
    )
    assert any(
        row.startswith("v1") and "(latest)" not in row and row.endswith("path")
        for row in testwiki_rows
    )
    _, storewiki_rows = blocks["storewiki"]
    assert any(row.endswith("store") for row in storewiki_rows)
    assert any(row.endswith("absent") for row in storewiki_rows)
    broken_header, _ = blocks["brokenset"]
    assert "UNAVAILABLE" in broken_header


def test_status_no_datasets(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "athenaeum.yaml").write_text("org: https://x.test\n", encoding="utf-8")
    assert main(["ref", "status", "--root", str(tmp_path)]) == 0
    assert "no reference datasets registered" in capsys.readouterr().out


# --- resolve: ref:// ------------------------------------------------------


def test_resolve_bare_tracks_latest(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ref", "resolve", "ref://testwiki/home", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("testwiki@v2")
    assert "Newer revision." in out


def test_resolve_pinned(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ref", "resolve", "ref://testwiki@v1/home", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("testwiki@v1")
    assert "Older revision." in out


def test_resolve_redirect_reports_canonical_id(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["ref", "resolve", "ref://testwiki/redirect-to-home", "--root", str(root)])
    assert rc == 0
    header = capsys.readouterr().out.splitlines()[0]
    assert "home" in header
    assert "redirected from 'redirect-to-home'" in header


def test_resolve_meta_suppresses_body(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["ref", "resolve", "ref://testwiki/home", "--meta", "--root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Newer revision." not in out
    assert "artifact:" in out


def test_resolve_unregistered_dataset(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ref", "resolve", "ref://ghost/x", "--root", str(root)]) == 1
    assert "unregistered dataset" in capsys.readouterr().err


def test_resolve_unknown_tag(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ref", "resolve", "ref://testwiki@nope/home", "--root", str(root)]) == 1
    assert "unknown snapshot tag" in capsys.readouterr().err


def test_resolve_adapter_unavailable(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ref", "resolve", "ref://brokenset/x", "--root", str(root)]) == 1
    assert "adapter unavailable" in capsys.readouterr().err


def test_resolve_mirror_unavailable(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ref", "resolve", "ref://nomirror/x", "--root", str(root)]) == 1
    assert "mirror unavailable" in capsys.readouterr().err


def test_resolve_entry_not_found(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["ref", "resolve", "ref://testwiki/does-not-exist", "--root", str(root)])
    assert rc == 1
    assert "entry not found" in capsys.readouterr().err


def test_resolve_not_a_ref_or_corpus_uri(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ref", "resolve", "bogus://nope", "--root", str(root)]) == 2
    assert "not a ref:// or corpus:// URI" in capsys.readouterr().err


# --- resolve: corpus:// courtesy redirect ---------------------------------


def test_resolve_corpus_redirect_hit(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["ref", "resolve", f"corpus://{_HASH_V2}", "--root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "testwiki@v2" in out
    assert "ref://testwiki/" in out
    assert "corpus resolve" in out


def test_resolve_corpus_redirect_miss(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["ref", "resolve", f"corpus://{_HASH_UNREGISTERED}", "--root", str(root)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "not a registered mirror artifact" in err
    assert "corpus resolve" in err


# --- hash ------------------------------------------------------------------


def test_hash_digest_and_snippet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "mirror.bin"
    data = b"some mirror bytes" * 1000
    f.write_bytes(data)
    expected = _blake3.blake3(data).hexdigest()

    assert main(["ref", "hash", str(f)]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == expected
    assert f"artifact: {expected}" in out
    assert f"path: {f.resolve()}" in out
