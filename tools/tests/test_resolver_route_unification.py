"""Route unification + member re-chaining, generalized to every member axis (spec §6.2,
"Route unification" / "Member re-chaining", v33).

v32 shipped both mechanisms for `stream_id=`/`path=` only:
  - route unification: `corpus://<leaf>?<ops>` and `corpus://<container>?<axis>=<n>&<ops>`
    were one resolution (one cache entry) for a promoted media-stream leaf, but a promoted
    mbox/eml/vcard member leaf still minted a SECOND, duplicate cache entry for its bare
    identity — the container route and the leaf route never met.
  - member re-chaining: an extracted member re-entered the working-kind table only past
    `path=` (a zip/tar member); `?msg=N&part=M` on a mailbox failed outright ("transform
    'part' not applicable to working kind 'bytes'").

This covers the generalization: an mbox `msg=` promoted leaf and an eml `part=` promoted
leaf each share ONE cache entry with their container route (not two), the base form is
disclosed for both axes, `?msg=N&part=M` chains straight to an attachment without ever
promoting the intermediate eml as its own record, a standalone (non-lineage) leaf is
unaffected, and a terminal member address still serves raw bytes — now under its own
sniffed extension rather than the generic `bytes` kind's `.bin` (the extension-asymmetry
fix, which falls out of the same sniff the terminal-textual-decode check already did).

Fixtures are built in-test with `email` (mirrors `test_eml.py`'s `_rich_eml` / `test_mbox.py`'s
mbox-builder patterns) — no shared conftest fixtures.
"""

from __future__ import annotations

import argparse
import shutil
from email import policy
from email.message import EmailMessage
from pathlib import Path

import blake3

from corpus import functional_uri as furi
from corpus import hashing, mboxfile, paths, records, resolver, schemas
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli
from corpus._cli import resolve as resolve_cli

CRLF = b"\r\n"
_PDF = b"%PDF-1.4\nfake contract payload\n"


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _rich_eml() -> bytes:
    """A message with a plain/html alternative (an inline image on the html side) plus one
    PDF attachment at `part=4` (DFS parts: 1 plain, 2 html, 3 image, 4 pdf) — a trimmed
    self-contained cousin of `test_eml.py`'s `_rich_eml`."""
    em = EmailMessage()
    em["From"] = "Bjorn <bjorn@example.com>"
    em["To"] = "sjrahn@example.com"
    em["Date"] = "Tue, 02 Feb 2021 09:00:00 +0000"
    em["Subject"] = "Contract"
    em["Message-ID"] = "<msg-2@example.com>"
    em.set_content("Plain body.\n", cte="base64")
    em.add_alternative("<html><body><p>HTML body.</p></body></html>", subtype="html")
    html_part = em.get_payload()[1]
    html_part.add_related(
        b"\x89PNG\r\n\x1a\ninline-image-bytes", maintype="image", subtype="png",
        cid="inline-img-1",
    )
    em.add_attachment(_PDF, maintype="application", subtype="pdf", filename="contract.pdf")
    return em.as_bytes(policy=policy.SMTP)


# ---------- corpus harness (mirrors test_mbox.py / test_eml.py) ---------- #


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults
    schemas.cache_clear()
    return root


def _ingest(root: Path, artifact: Path) -> str:
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / artifact.name
    shutil.copy(artifact, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    return hashing.hash_file(artifact)["blake3"]


def _draft(root: Path, target: str, messages: str | None = None) -> int:
    from tests._draftlib import draft_for_test

    return draft_for_test(root, target, messages=messages)


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


def _write_mbox_with(tmp_path: Path, message: bytes) -> tuple[Path, str]:
    """One message, no stuffing — the mbox precedent's `test_three_hop_promote_and_resolve`
    separator shape. Returns `(mbox_path, mbox_id)`."""
    mbox = b"From 1@x Mon Jan 01 00:00:00 +0000 2020" + CRLF + message
    p = tmp_path / "mail.mbox"
    p.write_bytes(mbox)
    return p, _b3(mbox)


# ---------- mbox msg= leaf <-> container: one cache entry, base form disclosed ---------- #


def test_mbox_msg_leaf_and_container_share_one_cache_entry(tmp_path):
    root = _corpus(tmp_path)
    m = _rich_eml()
    p, mbox_id = _write_mbox_with(tmp_path, m)
    _ingest(root, p)
    _draft(root, mbox_id, messages="1")
    assert _promote(root, f"corpus://{mbox_id}?msg=1") == 0
    leaf_id = _b3(m)

    from_leaf = resolver.resolve(f"corpus://{leaf_id}", root)
    from_container = resolver.resolve(f"corpus://{mbox_id}?msg=1", root)
    # Literally the same cache file — not merely equal bytes via two separate mechanisms
    # (the v32 gap this closes: a leaf's bare identity route and its container's `msg=`
    # route used to mint two different cache entries for byte-identical content).
    assert from_leaf == from_container
    assert from_leaf.read_bytes() == m
    # The extension-asymmetry fix: sniffed from the message's own headers, not the
    # generic `bytes` kind's `.bin`.
    assert from_leaf.suffix == ".eml"


def test_mbox_msg_leaf_discloses_the_base_form(tmp_path):
    root = _corpus(tmp_path)
    m = _rich_eml()
    p, mbox_id = _write_mbox_with(tmp_path, m)
    _ingest(root, p)
    _draft(root, mbox_id, messages="1")
    assert _promote(root, f"corpus://{mbox_id}?msg=1") == 0
    leaf_id = _b3(m)

    assert resolve_cli._base_form(root, f"corpus://{leaf_id}") == f"corpus://{mbox_id}?msg=1"
    # Not disclosed for a URI that already carries an op — it would just repeat itself back.
    assert resolve_cli._base_form(root, f"corpus://{leaf_id}?msg=1") is None
    # Not disclosed for the container itself — it carries no lineage of its own.
    assert resolve_cli._base_form(root, f"corpus://{mbox_id}") is None


# ---------- eml part= leaf <-> container: one cache entry, base form disclosed ---------- #


def test_eml_part_leaf_and_container_share_one_cache_entry(tmp_path):
    root = _corpus(tmp_path)
    eml = tmp_path / "m.eml"
    eml.write_bytes(_rich_eml())
    eid = _ingest(root, eml)
    _draft(root, eid)
    assert _promote(root, f"corpus://{eid}?part=4") == 0
    pid = _b3(_PDF)

    from_leaf = resolver.resolve(f"corpus://{pid}", root)
    from_container = resolver.resolve(f"corpus://{eid}?part=4", root)
    assert from_leaf == from_container
    assert from_leaf.read_bytes() == _PDF
    assert from_leaf.suffix == ".pdf"  # sniffed, not the generic `.bin`


def test_eml_part_leaf_discloses_the_base_form(tmp_path):
    root = _corpus(tmp_path)
    eml = tmp_path / "m.eml"
    eml.write_bytes(_rich_eml())
    eid = _ingest(root, eml)
    _draft(root, eid)
    assert _promote(root, f"corpus://{eid}?part=4") == 0
    pid = _b3(_PDF)

    assert resolve_cli._base_form(root, f"corpus://{pid}") == f"corpus://{eid}?part=4"


# ---------- ?msg=N&part=M chains straight to the attachment ---------- #


def test_msg_and_part_chain_to_the_attachment_without_a_promoted_eml(tmp_path):
    """`corpus://<mbox>?msg=1&part=4` reaches the PDF attachment through the mbox in one
    URI — the composition the mbox precedent always implied (§6.2 "Member re-chaining") —
    without ever promoting the intermediate eml as its own record."""
    root = _corpus(tmp_path)
    m = _rich_eml()
    p, mbox_id = _write_mbox_with(tmp_path, m)
    _ingest(root, p)

    out = resolver.resolve(f"corpus://{mbox_id}?msg=1&part=4", root)
    assert out.read_bytes() == _PDF
    assert out.suffix == ".pdf"


def test_msg_and_part_chain_equals_the_promoted_record_route(tmp_path):
    root = _corpus(tmp_path)
    m = _rich_eml()
    p, mbox_id = _write_mbox_with(tmp_path, m)
    _ingest(root, p)
    _draft(root, mbox_id, messages="1")
    eml_id = _b3(m)
    assert _promote(root, f"corpus://{mbox_id}?msg=1") == 0
    _draft(root, eml_id)
    assert _promote(root, f"corpus://{eml_id}?part=4") == 0
    pid = _b3(_PDF)

    chained = resolver.resolve(f"corpus://{mbox_id}?msg=1&part=4", root)
    promoted = resolver.resolve(f"corpus://{pid}", root)
    assert chained.read_bytes() == promoted.read_bytes() == _PDF


# ---------- non-lineage leaf (standalone record) unaffected ---------- #


def test_standalone_eml_has_no_lineage_and_is_not_redirected(tmp_path):
    root = _corpus(tmp_path)
    eml = tmp_path / "standalone.eml"
    eml.write_bytes(_rich_eml())
    eid = _ingest(root, eml)
    post = records.load(paths.record_path(root, eid))

    assert resolver.member_lineage(post) is None
    parsed = furi.parse(f"corpus://{eid}?part=4")
    assert resolver._member_route_redirect(root, parsed, post) is None
    # Resolves normally — from its own bytes, no redirect involved.
    out = resolver.resolve(f"corpus://{eid}?part=4", root)
    assert out.read_bytes() == _PDF


# ---------- terminal member address still raw bytes ---------- #


def test_terminal_msg_is_raw_unstuffed_bytes(tmp_path):
    root = _corpus(tmp_path)
    m = _rich_eml()
    p, mbox_id = _write_mbox_with(tmp_path, m)
    _ingest(root, p)

    out = resolver.resolve(f"corpus://{mbox_id}?msg=1", root)
    assert out.read_bytes() == mboxfile.resolve_member(p, 1) == m


def test_terminal_part_is_raw_bytes_never_reencoded(tmp_path):
    root = _corpus(tmp_path)
    eml = tmp_path / "m.eml"
    eml.write_bytes(_rich_eml())
    eid = _ingest(root, eml)
    _draft(root, eid)

    out = resolver.resolve(f"corpus://{eid}?part=4", root)
    assert out.read_bytes() == _PDF
    assert out.suffix == ".pdf"
