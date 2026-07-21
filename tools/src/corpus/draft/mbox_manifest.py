"""Selective mbox → message-embed manifest draft (deterministic, no LLM; spec §12.11).

The mbox sibling of `zip_manifest` / `tar_manifest`, with one design difference: a mailbox
may hold 10^5 messages, so members are NOT all manifested at ingest. The drafter declares
only the messages a caller names — `corpus draft <mbox-id> --messages 5,12,90-95` — recording
each as a `message/rfc822` **embed** (blake3 `transport` over the un-stuffed member bytes,
addressed `msg=<N>`, plus the message's Date / From / Subject and byte length). The content
zone stays empty: like the archive manifests, the declared messages ARE the manifest (the
embed blocks), and each is **promotable** (§8.1) without leaving the mailbox.

Idempotent and cumulative. Existing `msg=<N>` embeds on the record are the already-declared
set; re-running unions the newly-named ordinals with them. An identical re-declaration folds
silently; a changed hash for an already-declared ordinal is a hard error (`MessageHashConflict`).
A plain draft with no ordinals declares an empty manifest (the mailbox summary only).

The single streaming pass (`mboxfile.scan`) never loads the mailbox — or a whole message —
whole. `transport_algos` (the promoted message's `sha256`) are NOT pre-computed here: they
are a promote/ingest concern (§12.3.3), derived from the `message/rfc822` schema when a
message is actually promoted, exactly as archive members are — so the embed carries the
blake3 identity only, like every other manifest drafter.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from corpus import mboxfile, records
from corpus.draft import DrafterResult, register_strategy

if TYPE_CHECKING:
    from corpus import recordbuild

_MSG_ADDR_RE = re.compile(r"^msg=(\d+)$")


class MessageHashConflict(ValueError):
    """A requested ordinal is already declared, but re-extraction yields a different blake3 —
    the mailbox bytes or the prior declaration are stale. A hard error (spec §12.11)."""


def parse_message_spec(spec: str) -> list[int]:
    """Parse a `--messages` value — a comma list of 1-indexed ordinals and `lo-hi` ranges
    (`5,12,90-95`) — into a sorted, de-duplicated ordinal list. Raises `ValueError` on a
    malformed token."""
    out: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo_s, _, hi_s = chunk.partition("-")
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError:
                raise ValueError(f"--messages: {chunk!r} is not a `lo-hi` range") from None
            if lo < 1 or hi < lo:
                raise ValueError(f"--messages: {chunk!r} is not a valid 1-indexed range")
            out.update(range(lo, hi + 1))
        else:
            try:
                n = int(chunk)
            except ValueError:
                raise ValueError(f"--messages: {chunk!r} is not an ordinal") from None
            if n < 1:
                raise ValueError("--messages: ordinals are 1-indexed (>= 1)")
            out.add(n)
    return sorted(out)


def declared_ordinals(post: Any) -> list[int]:
    """The 1-indexed ordinals already declared on a record's `msg=<N>` embeds, sorted. Empty
    for a record that declares none (or any non-mbox record) — the way `redraft` recovers the
    selection to re-declare it (the ordinals are user intent, not derivable from the bytes)."""
    return sorted(declared_transports(post))


def declared_transports(post: Any) -> dict[int, str]:
    """Map already-declared ordinal → its embed `transport:` string — conflict detection
    here, and the declared-set fallback for window-reduction dedup (spec §12.3.13)."""
    meta = post.metadata if hasattr(post, "metadata") else post
    out: dict[int, str] = {}
    for embed in (meta.get("_embeds") or []):
        addr = embed.get("address")
        addr = addr[0] if isinstance(addr, list) else addr
        m = _MSG_ADDR_RE.match(str(addr or ""))
        if m:
            out[int(m.group(1))] = str(embed.get("transport") or "")
    return out


@register_strategy("mbox-manifest")
def draft(
    mbox_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
    mime_schema: dict[str, Any] | None = None,
    messages: list[int] | None = None,
) -> DrafterResult:
    existing = declared_transports(record_metadata or {})
    requested = sorted(set(messages or []))

    # One streaming pass: total count + first/last separator (date span) + per-ordinal facts
    # for exactly the requested messages (blake3 + byte length + Date/From/Subject).
    scan = mboxfile.scan(mbox_path, set(requested))

    embeds: list[dict[str, Any]] = []
    for n in requested:
        facts = scan.facts[n]
        transport = records.format_hash("blake3", facts.blake3)
        prior = existing.get(n)
        if prior is not None:
            if prior != transport:
                raise MessageHashConflict(
                    f"msg={n} is already declared as {prior}, but re-extraction yields "
                    f"{transport} — the mailbox bytes or the declaration is stale."
                )
            continue  # identical re-declaration folds silently
        embeds.append(
            {
                "media_type": "message/rfc822",
                "address": f"msg={n}",
                "transport": transport,
                "fields": _embed_fields(facts),
            }
        )

    declared_total = len(existing) + len(embeds)
    fields: dict[str, Any] = {
        "message_count": scan.count,
        "bytes": _file_size(mbox_path),
        "declared_count": declared_total,
    }
    span = mboxfile.date_span(scan.first_sep, scan.last_sep)
    if span:
        fields["date_start"], fields["date_end"] = span

    return {"fields": fields, "embeds": embeds, "issues": []}


def _embed_fields(facts: mboxfile.MessageFacts) -> dict[str, Any]:
    out: dict[str, Any] = {"bytes": facts.bytes}
    if facts.date:
        out["date"] = facts.date
    if facts.sender:
        out["from"] = facts.sender
    if facts.subject:
        out["subject"] = facts.subject
    return out


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
