"""A manifest value keeps its digits (arbre-ath-steven, first v49 uses, 2026-09-28).

`_typed()` read every all-digit token as an int, so a receipt's `transaction=00000003`
compiled to `3`. v48 made `transaction` a verbatim identifier. A numeral with a leading zero
is never an int, and a `section` header field its form declares `type: string` is kept
verbatim, so a stored `transaction: '7710'` round-trips as the string it is.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from corpus import recordbuild, schemas, segments


def _section_fields(tmp_path: Path, line: str) -> dict:
    corpus = tmp_path / "corpus"
    (corpus / "schema" / "form").mkdir(parents=True, exist_ok=True)
    (corpus / "schema" / "form" / "slip.yaml").write_text(
        "description: A slip.\nextended_fields:\n"
        "  transaction: {type: string}\n  copies: {type: integer}\n", encoding="utf-8")
    schemas.cache_clear()
    frag = tmp_path / "frag.corpus"
    frag.write_text(line + "\n", encoding="utf-8")
    post = recordbuild.read_fragment(frag, corpus)
    (sec,) = [b for b in segments.iter_blocks(post.content)
              if isinstance(b, segments.Section)]
    return sec.extra


def test_a_leading_zero_numeral_is_not_an_int():
    assert recordbuild._typed("00000003") == "00000003"
    assert recordbuild._typed("-007") == "-007"
    assert recordbuild._typed("0") == 0
    assert recordbuild._typed("42") == 42
    assert recordbuild._typed("[01|2]") == ["01", 2]


def test_a_form_declared_string_field_keeps_its_value_verbatim(tmp_path):
    emitted = recordbuild._fmt_scalar("7710")  # a stored string emits bare
    fields = _section_fields(
        tmp_path, f"section form=slip transaction={emitted} copies=2 note=5")
    assert fields == {"transaction": "7710", "copies": 2, "note": 5}
    assert shlex.split(f"t={emitted}") == ["t=7710"]
