"""message/rfc822 draft extraction (deterministic, no LLM; spec §12.11).

Mechanical drafter for a single email message — one promoted out of an mbox
(`corpus://<mbox-id>?msg=<N>`, §8.1) or ingested standalone as an `.eml`. Three moves:

1. **Headers → artifact block** (RFC2047-decoded, single-line, omit-empty): subject (also the
   `title` candidate), from / to / cc / bcc, date, message_id, in_reply_to, references (list,
   file order), thread_id (Gmail `X-GM-THRID`). Thread reconstruction is then a frontmatter
   query — references / in_reply_to ↔ message_id joins across siblings, thread_id groups them.
2. **Body = the reply text only.** Renders the `text/plain` part (else `text/html` reduced to
   text) and mechanically trims trailing **quoted history** (the prior thread lives as its own
   records; raw bytes retain everything). See `_trim_quoted_history` for the pinned, conservative
   markers — it prefers false negatives (keeps everything when no marker matches confidently).
   Signatures are part of the reply and kept.
3. **Every non-body MIME part → an embed** (the HTML/EPUB embed model). Each attachment, inline
   image, and nested `message/rfc822` becomes a `part=<N>` embed (`transport` = blake3 over the
   CTE-decoded payload, `bytes` = decoded size, plus filename / disposition / content_id), so it
   is promotable (§8.1). The text alternatives the body consumed are skipped (they are content,
   not members). Enumeration + addressing live in `corpus.emlfile` (shared with the transform).

Tolerates the multipart shapes real mail takes: `multipart/alternative` nested in
`multipart/mixed` / `multipart/related`, base64 / quoted-printable, non-UTF-8 charsets.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import blake3

from corpus import emlfile, recordbuild, records, touches
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.segments import Segment

_DETECTOR = touches.script_identifier("draft.message/message_rfc822")

# Headers lifted onto the artifact block as `field: value`, RFC2047-decoded, single-line.
_SCALAR_HEADERS = (
    ("subject", "Subject"),
    ("from", "From"),
    ("to", "To"),
    ("cc", "Cc"),
    ("bcc", "Bcc"),
    ("date", "Date"),
    ("message_id", "Message-ID"),
    ("in_reply_to", "In-Reply-To"),
)


@register("message/message_rfc822")
def draft(
    binary_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
) -> DrafterResult:
    raw = binary_path.read_bytes()
    try:
        msg = emlfile.parse(raw)
    except Exception:
        return {"issues": [_partial("message could not be parsed as RFC822/MIME.")]}

    fields = _artifact_fields(msg)
    text = _trim_quoted_history(_message_text(msg))
    embeds = _part_embeds(msg)

    if text:
        text_algos = algos_for_atom("text", fingerprint)
        recordbuild.add_blocks(
            build,
            [
                Segment(
                    atom="text",
                    address="block=1",
                    perceptual=text_fingerprints(text, text_algos),
                    body=text,
                )
            ],
        )

    issues: list[dict[str, Any]] = []
    if not text:
        issues.append(
            _partial(
                "message carries no text body (headers on the artifact block, parts as embeds).",
                severity="info",
            )
        )
    return {"fields": fields, "embeds": embeds, "issues": issues}


# ---------- headers → artifact block ---------- #


def _artifact_fields(msg) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, header in _SCALAR_HEADERS:
        if value := _header(msg, header):
            fields[key] = value
    if subject := fields.get("subject"):
        fields["title"] = subject  # title candidate; the normalizer authors frontmatter title
    if refs := _references(msg):
        fields["references"] = refs
    if thread_id := _header(msg, "X-GM-THRID"):
        fields["thread_id"] = thread_id
    return fields


def _header(msg, name: str) -> str | None:
    """A single-line, RFC2047-decoded header value (`policy.default` decodes + unfolds), or
    None. Whitespace collapsed so a folded header reads as one line."""
    value = msg[name]
    if value is None:
        return None
    collapsed = " ".join(str(value).split())
    return collapsed or None


def _references(msg) -> list[str] | None:
    """The `References` message-ids as a list in file order (the thread-join key)."""
    raw = msg["References"]
    if raw is None:
        return None
    ids = re.findall(r"<[^>]+>", str(raw))
    return ids or None


# ---------- body text (reply only) ---------- #


def _message_text(msg) -> str:
    """The message's text body — the `text/plain` part, else `text/html` reduced to text.
    Returns '' when the message carries no textual body (attachments only)."""
    part = emlfile.body_part(msg)
    if part is None:
        return ""
    content = _decode_text_part(part)
    if part.get_content_subtype() == "html":
        return _html_to_text(content)
    return content.strip("\n")


def _decode_text_part(part) -> str:
    """Transfer-decode + charset-decode a text part to `str`, replacing undecodable bytes
    rather than raising (tolerate non-UTF-8 charsets)."""
    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
    except (LookupError, ValueError):
        pass
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


# Reply-history containers HTML mail wraps quotes in — removed structurally in the text/html
# fallback path so the text-marker trim below has less to catch (text/plain is preferred, so
# this path is the fallback). Generic `<blockquote>` is included: in a reply it is quoted
# history, and the raw bytes retain everything if a fresh-email blockquote is over-trimmed.
_HTML_QUOTE_SELECTORS = ".gmail_quote, .gmail_extra, .yahoo_quoted, blockquote"


def _html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.select(_HTML_QUOTE_SELECTORS):
        tag.decompose()
    return soup.get_text("\n", strip=True)


# --- quoted-history trim (pinned, conservative; spec §12.11 / schema description) --- #

_ATTRIB_ONELINE = re.compile(r"^\s*On\b.*\bwrote:\s*$")
_ATTRIB_START = re.compile(r"^\s*On\b")
_ATTRIB_END = re.compile(r"\bwrote:\s*$")
_ORIG_MSG = re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.IGNORECASE)
_UNDERSCORE_RULE = re.compile(r"^_{10,}\s*$")
_QUOTE = re.compile(r"^\s*>")
_OUTLOOK_FROM = re.compile(r"^\s*From:\s", re.IGNORECASE)
_OUTLOOK_SENT = re.compile(r"^\s*Sent:\s", re.IGNORECASE)
_OUTLOOK_TOSUBJ = re.compile(r"^\s*(To|Subject):\s", re.IGNORECASE)


def _trim_quoted_history(text: str) -> str:
    """Strip trailing quoted history from the FIRST confidently-matched marker to EOF; keep
    everything when none matches (prefer false negatives). Markers:
      - an `On <…> wrote:` attribution (one line, or wrapped over two) directly preceding a
        `>`-quoted line;
      - `-----Original Message-----`;
      - a long underscore rule (Outlook);
      - an Outlook forwarded-header block (`From:` with a nearby `Sent:` and `To:`/`Subject:`);
      - a `>`-quoted run that extends to EOF (no attribution needed)."""
    if not text:
        return text
    lines = text.split("\n")
    n = len(lines)
    for i, line in enumerate(lines):
        if _ATTRIB_ONELINE.match(line) and _next_nonblank_is_quote(lines, i + 1):
            return _cut(lines, i)
        if (
            _ATTRIB_START.match(line)
            and not _ATTRIB_ONELINE.match(line)
            and i + 1 < n
            and _ATTRIB_END.search(line + " " + lines[i + 1])
            and _next_nonblank_is_quote(lines, i + 2)
        ):
            return _cut(lines, i)
        if _ORIG_MSG.match(line) or _UNDERSCORE_RULE.match(line):
            return _cut(lines, i)
        if _OUTLOOK_FROM.match(line):
            window = lines[i : i + 6]
            if any(_OUTLOOK_SENT.match(w) for w in window) and any(
                _OUTLOOK_TOSUBJ.match(w) for w in window
            ):
                return _cut(lines, i)
    for i, line in enumerate(lines):
        if _QUOTE.match(line) and all(_QUOTE.match(w) for w in lines[i:] if w.strip()):
            return _cut(lines, i)
    return text


def _next_nonblank_is_quote(lines: list[str], start: int) -> bool:
    j = start
    while j < len(lines) and lines[j].strip() == "":
        j += 1
    return j < len(lines) and bool(_QUOTE.match(lines[j]))


def _cut(lines: list[str], i: int) -> str:
    return "\n".join(lines[:i]).rstrip()


# ---------- non-body parts → embeds ---------- #


def _part_embeds(msg) -> list[dict[str, Any]]:
    """One embed per addressable part the body did NOT consume — attachments, inline images,
    nested messages. Addressed `part=<N>` over the shared enumeration; `transport` is blake3 of
    the CTE-decoded payload (the promotable member identity)."""
    skip = emlfile.body_skip_ids(msg)
    embeds: list[dict[str, Any]] = []
    for ordinal, part in enumerate(emlfile.addressable_parts(msg), start=1):
        if id(part) in skip:
            continue
        decoded = emlfile.part_decoded_bytes(part)
        media_type, part_fields = emlfile.part_facts(part, decoded)
        embeds.append(
            {
                "media_type": media_type,
                "address": f"part={ordinal}",
                "transport": records.format_hash("blake3", blake3.blake3(decoded).hexdigest()),
                "fields": part_fields,
            }
        )
    return embeds


# ---------- issues ---------- #


def _partial(description: str, *, severity: str = "blocking") -> dict[str, Any]:
    issue: dict[str, Any] = {
        "id": "partial-content",
        "severity": severity,
        "resolution": "open",
        "detector": _DETECTOR,
        "fields": {"description": description},
    }
    if severity == "blocking":
        issue["subtype"] = "empty-body"
    return issue
