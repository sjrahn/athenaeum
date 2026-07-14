"""text/vcard → card-embed manifest attest (deterministic, no LLM; spec §12.18 step 4, §12.11).

The vCard sibling of `mbox_manifest`, with one design difference in the opposite direction: a
`.vcf` is SMALL, so — unlike a mailbox's selective declaration — ALL cards attest **eagerly** at
ingest. Each `BEGIN:VCARD … END:VCARD` card becomes a `text/vcard` **embed** (blake3 `transport`
over the card's exact member bytes, addressed `card=<N>` in 1-indexed card order, byte length,
and the card's display name on the embed `description:`). The content zone stays empty: the cards
ARE the manifest (the embed blocks), and each is **promotable** (§8.1) — a downstream ledger
consumer (the cross-platform "identity-v2" pass) cites an INDIVIDUAL card, and an embed member is
promotable where a text segment is not.

**This replaces the 2.x per-card `el=` TEXT-segment drafting** (`corpus.draft.vcard`, retired):
the labeled per-property rendering that drafter wrote is now a `body`-derivation / read-time
concern, never the attested layer, because a text segment cannot be promoted to its own record
and a manifest member can.

Byte identity is verbatim (`corpus.vcardfile` pins the byte span, CRLF/LF-agnostic); RFC 6350
line-unfolding is a consumer read-time concern, never applied to the member bytes. An
embedded-bytes `PHOTO` stays INSIDE its card's member bytes — it is NOT lifted to a separate
image embed here (the 2.x drafter lifted it; that now belongs to normalize/annotation if a
describe pass wants the face). A malformed card (no matching `END`) is skipped, counted in a
`partial-content` issue, never failing the file (house doctrine).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from corpus import records, touches, vcardfile
from corpus.draft import DrafterResult, register_strategy

if TYPE_CHECKING:
    from corpus import recordbuild

_DETECTOR = touches.script_identifier("draft.vcard-manifest")


@register_strategy("vcard-manifest")
def draft(
    binary_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
    mime_schema: dict[str, Any] | None = None,
) -> DrafterResult:
    raw = binary_path.read_bytes()
    scan = vcardfile.scan(raw)

    embeds: list[dict[str, Any]] = []
    versions: list[str] = []
    prodids: list[str] = []
    for facts in scan.facts:
        _collect(versions, facts.version)
        _collect(prodids, facts.prodid)
        embeds.append(
            {
                "media_type": "text/vcard",
                "address": f"card={facts.ordinal}",
                "transport": records.format_hash("blake3", facts.blake3),
                "fields": {"bytes": facts.bytes, "description": facts.display_name},
            }
        )

    # No content zone: cards are transports (embeds), not content atoms.

    fields: dict[str, Any] = {"card_count": scan.count}
    if versions:
        fields["vcard_version"] = versions[0] if len(versions) == 1 else versions
    # PRODID is per-card (each contact records the exporter that last touched it), so a
    # long-lived address book carries many; only surface it as a file fact when uniform.
    if len(prodids) == 1:
        fields["product_id"] = prodids[0]

    issues: list[dict[str, Any]] = []
    if scan.count == 0:
        issues.append(_issue("no BEGIN:VCARD cards parsed from the file.", subtype="empty-body"))
    if scan.skipped:
        issues.append(
            _issue(
                f"{scan.skipped} malformed card(s) skipped (no END:VCARD, or unparseable) — "
                f"parse-tolerant per house doctrine.",
                severity="warning",
                fields={"skipped_cards": scan.skipped},
            )
        )

    return {"fields": fields, "embeds": embeds, "issues": issues}


def _collect(acc: list[str], value: str | None) -> None:
    v = (value or "").strip()
    if v and v not in acc:
        acc.append(v)


def _issue(
    description: str,
    *,
    severity: str = "info",
    subtype: str | None = None,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "id": "partial-content",
        "severity": severity,
        "resolution": "open",
        "detector": _DETECTOR,
        "fields": {"description": description, **(fields or {})},
    }
    if subtype:
        issue["subtype"] = subtype
    return issue
