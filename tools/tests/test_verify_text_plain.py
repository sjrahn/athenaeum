"""A formless `raw`-surface `text/*` record verifies against its decoded artifact text.

`corpus inspect` calls such a record citable ("record-wide quotes are honest", corpus
§7.1; ledger §6.3), but verify used to build `full_text` from stored segments alone — of
which a plain `.txt` table has none — so every quote of it WARNed "not found verbatim".
"""

from __future__ import annotations

import json

from corpus import mime as mime_mod
from corpus import paths
from ledger.verify import decode_text_artifact
from tests.test_html_text_and_cid import _corpus, _stage_record

_TABLE = (
    "  Fundamental Physical Constants --- Complete Listing\n\n"
    "  Quantity                       Value                 Uncertainty           Unit\n"
    "-------------------------------------------------------------------------------\n"
    "Bohr radius                      5.291 772 105 44 e-11  0.000 000 000 82 e-11  m\n"
    "speed of light in vacuum         299 792 458            (exact)               m s^-1\n"
    "Wien wavelength *displacement*   2.897 771 955... e-3   (exact)               m K\n"
)


def _verify(tmp_path, data: bytes, quote: str):
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    root = _corpus(tmp_path)
    rid = _stage_record(root, data, mime="text/plain", name="allascii.txt")
    ledger = root.parent / "ledger"
    (ledger / "facts" / "quantity").mkdir(parents=True)
    (ledger / "facts" / "quantity" / "c.json").write_text(json.dumps({
        "id": "c", "type": "quantity", "name": "c",
        "sources": {"s1": {"record": rid}},
        "claims": [{"id": "c:value", "predicate": "value", "value": "299792458",
                    "status": "confirmed", "asof": "2026-11-17",
                    "evidence": [{"source": "s1", "quote": quote,
                                  "kind": "authoritative"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    return verify_ledger(ledger, join, {}, stamp=False, today="2026-11-17"), root, rid


def test_record_wide_quote_of_a_table_line_verifies(tmp_path):
    line = "speed of light in vacuum         299 792 458            (exact)               m s^-1"
    res, _, _ = _verify(tmp_path, _TABLE.encode(), line)
    assert not res.errors and res.unverifiable == 0, (res.errors, res.notes)
    assert res.verified == 1


def test_quotes_compare_verbatim_not_as_markdown(tmp_path):
    """The bytes are not markdown: `*displacement*` is literal, and a quote that drops the
    asterisks (as markup-stripping would allow) is not what the file says."""
    res, _, _ = _verify(tmp_path, _TABLE.encode(), "Wien wavelength *displacement*")
    assert not res.errors and res.verified == 1, (res.errors, res.notes)
    res, _, _ = _verify(tmp_path / "b", _TABLE.encode(), "Wien wavelength displacement")
    assert res.verified == 0 and any("not found verbatim" in e for e in res.errors)


def test_a_wrong_quote_still_fails(tmp_path):
    res, _, _ = _verify(tmp_path, _TABLE.encode(), "speed of light in vacuum 299 792 459")
    assert res.verified == 0 and any("not found verbatim" in e for e in res.errors)


def test_a_non_utf8_file_decodes_by_sniffed_charset(tmp_path):
    data = "magnetic constant mu_0 = 1.256 637 06 e-6 N A^-2 (µ0)\n".encode("cp1252")
    res, _, _ = _verify(tmp_path, data, "N A^-2 (µ0)")
    assert not res.errors and res.verified == 1, (res.errors, res.notes)
    assert decode_text_artifact("½".encode("utf-16")) == "½"
    assert decode_text_artifact(b"\xef\xbb\xbfplain") == "plain"


def test_absent_bytes_are_unverifiable_not_wrong(tmp_path):
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    _, root, rid = _verify(tmp_path, _TABLE.encode(), "Bohr radius")
    paths.artifact_path(root, rid, mime_mod.extension_for("text/plain")).unlink()
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(root.parent / "ledger", join, {}, stamp=False, today="2026-11-17")
    assert res.verified == 0 and not res.errors and res.unverifiable == 1, (res.errors,
                                                                            res.notes)
