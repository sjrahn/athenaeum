"""Tolerant text comparison — one definition, two gates.

Both of the system's text-fidelity gates ask the same question in different directions:
`ath ledger verify` (spec/ledger.md §13.2) asks whether a claim's quote is found verbatim
in the record it cites, and `corpus.fidelity` (#159) asks whether a segment's body text is
found in the artifact element its address names. Neither can compare raw characters — a
record body carries markdown a source's DOM does not, an artifact carries entities and
typographic quotes a body renders decoded, and whitespace differs on every side — so both
compare a NORMALIZED form, and it must be the *same* normalized form: two definitions of
"verbatim modulo whitespace" that drift apart make one gate accept what the other refuses
on the same bytes.

This module is that definition; `ledger.verify._norm` / `_quote_found` are thin aliases
onto it, keeping their historical names for verify's own call sites.
"""

from __future__ import annotations

import html as _html
import re

__all__ = ["norm", "quote_found", "squash"]

_BLOCK_TAG_RE = re.compile(
    r"</?(?:td|th|tr|p|div|li|ul|ol|h[1-6]|table|thead|tbody|blockquote|section)[^<>]*>"
    r"|<br\s*/?>",
    re.I,
)
# Two defect generations teach this regex's shape. `[^>]+` (ledger 1.5 defect) let a
# stray `<` consume across newlines to the next unrelated `>` anywhere later. `[^<>]+`
# stopped the bracket-crossing but still ate any BRACKET-FREE prose span between the two
# comparison operators clinical text writes constantly — "patients <65 years … in >900
# patients" silently deleted the paragraphs between, 10% of a drug monograph invisible
# to the quote verifier (found by the 2026-08-14 scribe verification). A stripped run
# must now LOOK like a tag: `<` then a letter or `/`, as every element `norm` means to
# strip does (`<td>`, `<u>`, `</u>`, `<br/>`, `<span …>`) and no comparison operand,
# Discord `<3`, or bare `x < y` ever does.
_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_ELLIPSIS_RE = re.compile(r"\s*(?:\.\.\.|…|\|)\s*")
_CHAR_FOLD = str.maketrans(  # the fold table IS the ambiguous chars — noqa: RUF001
    {"’": "'", "‘": "'", "“": '"', "”": '"', " ": " "})  # noqa: RUF001
_SEPARATORS_RE = re.compile(r"[\s\-]+")


def norm(s: str, *, strip_markup: bool = True) -> str:
    """Markup-insensitive comparison form: entities decode, markdown links
    unwrap, markup becomes whitespace or vanishes (record bodies keep
    faithful HTML tables and inline markers; quotes cite the rendered text),
    typographic quotes fold to straight, whitespace collapses.

    `strip_markup=False` for text that is not normalizer-authored markdown — a
    resolver op's derived surface (raw JSON/CSV/vcard/chat-export bytes, ledger §13.2
    1.5), or an artifact element's own `get_text()` (#159): a Discord export's literal
    `<3`, `>` blockquote prefixes, `*` emphasis, or `[x]` brackets in ordinary message
    text are NOT markup to strip — record bodies are the one surface where that
    assumption holds."""
    s = _html.unescape(s).translate(_CHAR_FOLD)
    if strip_markup:
        # markdown links unwrap to their text; inline markers strip
        s = _MD_LINK_RE.sub(r"\1", s)
        s = s.replace("*", "").replace("`", "")
        # structural tags (cells, breaks) become whitespace; inline tags vanish
        # (an underline inside a word must not split it)
        s = _BLOCK_TAG_RE.sub(" ", s)
        s = _TAG_RE.sub("", s)
        s = s.replace("|", " ")
    s = " ".join(s.split())
    return re.sub(r"\s+(['.,;:!?])", r"\1", s)


def squash(s: str) -> str:
    """Whitespace and hyphens removed — the retry form. Absorbs list bullets, inline-markup
    word splits, and soft-wrap artifacts; the characters themselves stay verbatim."""
    return _SEPARATORS_RE.sub("", s)


def quote_found(quote: str, haystack: str, *, strip_markup: bool = True) -> bool:
    """Verbatim modulo normalization. `...`/`…` inside a quote is elision, and
    `|` separates fragments across cell boundaries; every fragment must be
    found verbatim IN DOCUMENT ORDER — a quote is a reading of the record,
    never a bag of true substrings (order-free matching let "Head bolts |
    100 ft-lb" assemble from the wrong table rows). What order cannot prove
    — which column a table cell sits in — belongs in the evidence `note`,
    not the quote. A separator-squashed retry (`squash`) absorbs list bullets,
    inline-markup word splits, and soft-wrap artifacts.

    `strip_markup=False` — see `norm`."""
    hay = norm(haystack, strip_markup=strip_markup)
    parts = [p for p in _ELLIPSIS_RE.split(quote) if p.strip()]

    def scan(h: str, squashed: bool) -> bool:
        pos = 0
        for part in parts:
            n = norm(part, strip_markup=strip_markup)
            if squashed:
                n = squash(n)
            i = h.find(n, pos)
            if i < 0:
                return False
            pos = i + len(n)
        return True

    return scan(hay, squashed=False) or scan(squash(hay), squashed=True)
