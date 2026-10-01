"""`line=` and `uuid=` on NDJSON (spec §6.2, v51 — codex-steven R-0059): one transcript entry,
verbatim, by position or by its own `uuid` — standalone, or chained through a session
bundle's `path=` member, which is how an anchor cites one message of an archived session."""

from __future__ import annotations

import json
import zipfile

import pytest

from corpus import resolver
from corpus._cli import ingest as ingest_cli

_LINES = [
    {"type": "summary", "summary": "no uuid on this one"},
    {"type": "user", "uuid": "u-1", "message": {"role": "user", "content": "keep the zip"}},
    {"type": "assistant", "uuid": "a-1", "parentUuid": "u-1", "message": {"content": "ok"}},
]
_JSONL = "".join(json.dumps(x, separators=(",", ":")) + "\n" for x in _LINES).encode()


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "c"
    (r / "records").mkdir(parents=True)
    (r / "schema").mkdir()
    (r / "capture").mkdir()
    return r


def _ingest(root, name: str, data: bytes) -> str:
    p = root / "capture" / name
    p.write_bytes(data)
    assert ingest_cli._ingest_one(root, p) == 0
    return _b3(data)


def _b3(data: bytes) -> str:
    import blake3

    return blake3.blake3(data).hexdigest()


def test_line_and_uuid_select_one_entry_verbatim(root):
    rid = _ingest(root, "s.jsonl", _JSONL)
    by_line = resolver.resolve(f"corpus://{rid}?line=2", root).read_text("utf-8")
    by_uuid = resolver.resolve(f"corpus://{rid}?uuid=u-1", root).read_text("utf-8")
    assert by_line == by_uuid == _JSONL.decode().splitlines()[1]


def test_uuid_through_a_bundle_member(root, tmp_path):
    z = tmp_path / "session.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("abc.jsonl", _JSONL)
        zf.writestr("abc/tool-results/t1.txt", b"a tool result\n")  # two members: no collapse
    cid = _ingest(root, "session.zip", z.read_bytes())
    out = resolver.resolve(f"corpus://{cid}?path=abc.jsonl&uuid=a-1", root)
    assert json.loads(out.read_text("utf-8"))["parentUuid"] == "u-1"


@pytest.mark.parametrize(
    ("query", "match"),
    [("uuid=nope", "no line carries it"), ("line=9", "fewer lines"), ("line=0", "1-indexed")],
)
def test_an_anchor_that_names_nothing_fails(root, query, match):
    rid = _ingest(root, "s.jsonl", _JSONL)
    with pytest.raises(ValueError, match=match):
        resolver.resolve(f"corpus://{rid}?{query}", root)


def test_a_uuid_carried_twice_is_refused(root):
    twice = _JSONL + (json.dumps(_LINES[1]) + "\n").encode()
    rid = _ingest(root, "s.jsonl", twice)
    with pytest.raises(ValueError, match="more than one line"):
        resolver.resolve(f"corpus://{rid}?uuid=u-1", root)
