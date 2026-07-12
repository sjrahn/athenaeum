"""application/json — the verbatim-passthrough drafter.

JSON is a carrier syntax: the faithful representation of a JSON artifact is its own
text. The drafter decodes the bytes (JSON is UTF-8 by spec; a BOM is tolerated), emits
ONE `text/code` segment (language `json`) spanning every line, and derives two cheap
shape facts (`json_root`, `json_top_count`) for the artifact block. It parses only to
*validate* — a malformed document still drafts (parse tolerantly), carrying a
`malformed-json` warning issue instead of failing the record.

What any given JSON *means* — which fields matter, what its elements represent — is
origin-overlay guidance plus ledger knowledge (ATH-CORPUS 2.0), never hardcoded here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from corpus import recordbuild, touches
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.segments import Segment

_DRAFTER_DETECTOR_ID = touches.script_identifier("draft.application/application_json")

_ROOT_KINDS = {
    dict: "object",
    list: "array",
    str: "string",
    bool: "boolean",  # before int/float — bool is an int subclass
    int: "number",
    float: "number",
    type(None): "null",
}


def _root_kind(value: Any) -> str:
    for typ, kind in _ROOT_KINDS.items():
        if isinstance(value, typ):
            return kind
    return "unknown"


@register("application/application_json")
def draft(
    json_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
) -> DrafterResult:
    raw = json_path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")

    fields: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        issues.append(
            {
                "id": "malformed-json",
                "severity": "warning",
                "resolution": "open",
                "detector": _DRAFTER_DETECTOR_ID,
                "fields": {
                    "description": (
                        "The artifact does not parse as JSON "
                        f"({exc}); the text passes through verbatim."
                    ),
                },
            }
        )
    else:
        fields["json_root"] = _root_kind(parsed)
        if isinstance(parsed, dict | list):
            fields["json_top_count"] = len(parsed)

    n_lines = max(1, text.count("\n") + (0 if text.endswith("\n") else 1))
    text_algos = algos_for_atom("text", fingerprint)
    recordbuild.add_blocks(
        build,
        [
            Segment(
                atom="text",
                overlay="text/code",
                address=f"line=1-{n_lines}" if n_lines > 1 else "line=1",
                perceptual=text_fingerprints(text, text_algos),
                body=text,
                extra={"language": "json"},
            )
        ],
    )
    return {
        "fields": fields,
        "embeds": [],
        "issues": issues,
        "canonical": None,
        "origin_uri_aliases": [],
    }
