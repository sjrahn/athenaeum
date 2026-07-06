"""SingleFile save provenance — the self-describing banner a SingleFile save carries.

Every page saved with the SingleFile browser extension self-describes in an HTML
comment in its first bytes::

    <!--
     Page saved with SingleFile
     url: https://www.example.com/page?x=1
     saved date: Mon Jul 06 2026 13:48:48 GMT-0600 (Mountain Daylight Time)
    -->

This module is the pure (stdlib-only) reader of that banner: it is the honest
provenance of a manual save — the URL the human was on and the moment they saved
it. Two consumers read it, and both must agree on the parse, so it lives here
rather than in either:

- **ingest** (`_cli/ingest.py`, §12.3.4): a SingleFile save dropped straight into
  `capture/` and ingested (no capture step) seeds a *retrieval* origin from the
  banner — `uri:` = the banner URL, `snapshot:` = the saved date — instead of the
  uri-less local-file origin a bare dropped file gets.
- **from-save capture** (`corpus.capture`, §12.3.12): a save replayed through the
  browser to run the host overlay's `capture.interactions:` reads the banner to
  find the URL (so it can look up the recipe) and the saved date (so the record's
  origin snapshot is when the human saved it, not when we re-snapshotted it).

The saved date is parsed from the JavaScript ``Date.prototype.toString()`` form to
ISO-8601 with the **numeric offset preserved** (``2026-07-06T13:48:48-06:00``): the
instant is not converted to UTC and the parenthesized zone name is ignored. Parsing
is done with an explicit month table (not ``strptime`` ``%a``/``%b``, which are
locale-dependent) so the result never depends on the host locale.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger("corpus.singlefile")

# Bytes to scan for the banner. The comment sits just inside `<html …>`, so the
# first few hundred bytes always hold it; 4 KB is a comfortable ceiling.
HEAD_BYTES = 4096

# The banner. `Page saved with SingleFile`, then a `url:` line and a `saved date:`
# line (each value runs to end-of-line — SingleFile pads with a trailing space
# before the newline, which `\s*` absorbs). DOTALL so the lazy `.*?` between the
# lines crosses newlines; the values themselves stop at the first line break.
_BANNER_RE = re.compile(
    r"Page saved with SingleFile\b"
    r".*?\burl:\s*(?P<url>\S.*?)\s*[\r\n]"
    r".*?\bsaved date:\s*(?P<date>.+?)\s*[\r\n]",
    re.IGNORECASE | re.DOTALL,
)

# The JS `Date.toString()` shape: `Wdy Mon DD YYYY HH:MM:SS GMT±HHMM (Zone Name)`.
# The weekday and the trailing parenthesized zone name are ignored; the numeric
# offset is what we keep.
_JS_DATE_RE = re.compile(
    r"[A-Za-z]{3}\s+"
    r"(?P<mon>[A-Za-z]{3})\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<year>\d{4})\s+"
    r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})\s+"
    r"GMT(?P<sign>[+-])(?P<oh>\d{2})(?P<om>\d{2})\b"
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_saved_date(raw: str) -> str | None:
    """Convert a JS `Date.toString()` string to ISO-8601 with its numeric offset.

    `Mon Jul 06 2026 13:48:48 GMT-0600 (Mountain Daylight Time)` →
    `2026-07-06T13:48:48-06:00`. The instant is **not** converted to UTC and the
    parenthesized zone name is dropped. Returns None on any unrecognized shape."""
    m = _JS_DATE_RE.search(raw or "")
    if not m:
        return None
    mon = _MONTHS.get(m["mon"].lower())
    if not mon:
        return None
    return (
        f"{int(m['year']):04d}-{mon:02d}-{int(m['day']):02d}"
        f"T{m['h']}:{m['m']}:{m['s']}{m['sign']}{m['oh']}:{m['om']}"
    )


def parse_banner(head: str) -> tuple[str, str] | None:
    """Parse a SingleFile banner out of an HTML head string.

    Returns `(url, saved_date_iso)` with the saved date already normalized to
    ISO-8601 (see `parse_saved_date`), or None when there is no banner or its
    saved date is unparseable (both fields are required for a retrieval origin)."""
    m = _BANNER_RE.search(head or "")
    if not m:
        return None
    url = m["url"].strip()
    saved = parse_saved_date(m["date"])
    if not url or not saved:
        if url and not saved:
            log.debug("SingleFile banner url %s but unparseable saved date %r", url, m["date"])
        return None
    return url, saved


def banner_origin(src: Path, *, head_bytes: int = HEAD_BYTES) -> tuple[str, str] | None:
    """Read `src`'s head and return `(url, saved_date_iso)` from its SingleFile
    banner, or None when the file has none / is unreadable. Best-effort: any read
    error is swallowed to None so a caller can fall through to its next tier."""
    try:
        with src.open("rb") as fh:
            head = fh.read(head_bytes)
    except OSError:
        return None
    return parse_banner(head.decode("utf-8", "replace"))
