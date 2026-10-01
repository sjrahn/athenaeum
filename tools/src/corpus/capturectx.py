"""Capture context — who asked for a capture, carried onto the origin block it lands
(spec §7.2 universal `capture_*` fields, v51 — codex-steven R-0059).

An origin block says what produced the bytes and when they were observed. A capture made on
someone's request also has a cause: the prompt(s) in a Claude Code session that asked for
it, the tracked request it answers, the session that performed it, or — for an unprompted
capture — the watcher or timer that fired. That cause belongs to the ENCOUNTER, so it rides
the origin block the capture appends (a re-encounter by a different request appends its
own), never the producer's overlay fields and never the frontmatter:

    capture_session   the session id the asking prompt(s) live in
    capture_host      that session's host
    capture_messages  the asking prompt(s)' transcript uuids — with the session archived,
                      `corpus://<session-record>?path=<id>.jsonl&uuid=<u>` is the prompt
    capture_request   the tracked request answered (`R-0060`)
    capture_actor     the session/agent that performed the capture
    capture_trigger   what fired an unprompted capture (a watcher, a timer)

Two channels supply it, the first that is present winning: a staged file's capture sidecar
(`capture_context:` mapping, beside `origin_schema:`), or the `ATHENAEUM_CAPTURE_CONTEXT`
environment variable (the same mapping as JSON or YAML) — the latter reaches every verb
that ingests or promotes without each growing a flag. A malformed context refuses the
capture: provenance that silently did not land is worse than none.
"""

from __future__ import annotations

import json
import os
from typing import Any

ENV = "ATHENAEUM_CAPTURE_CONTEXT"

#: sidecar key → origin-block field
FIELDS: dict[str, str] = {
    "session_id": "capture_session",
    "host": "capture_host",
    "message_uuids": "capture_messages",
    "request": "capture_request",
    "actor": "capture_actor",
    "trigger": "capture_trigger",
}


class ContextError(ValueError):
    """A malformed capture context."""


def fields(raw: Any) -> dict[str, Any]:
    """The origin-block fields a `capture_context` mapping stamps. Raises `ContextError`."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ContextError("capture_context must be a mapping")
    unknown = sorted(set(map(str, raw)) - set(FIELDS))
    if unknown:
        raise ContextError(
            f"capture_context: unknown key(s) {unknown} (known: {', '.join(FIELDS)})"
        )
    out: dict[str, Any] = {}
    for key, name in FIELDS.items():
        value = raw.get(key)
        if value is None or value == "" or value == []:
            continue
        if key == "message_uuids":
            items = value if isinstance(value, list) else [value]
            if not all(isinstance(v, str) and v.strip() for v in items):
                raise ContextError("capture_context.message_uuids: a uuid or a list of them")
            items = [v.strip() for v in items]
            out[name] = items[0] if len(items) == 1 else items
        elif isinstance(value, (str, int)) and str(value).strip():
            out[name] = str(value).strip()
        else:
            raise ContextError(f"capture_context.{key}: expected a string, got {value!r}")
    if "capture_messages" in out and "capture_session" not in out:
        raise ContextError(
            "capture_context: message_uuids name prompts within a session — give session_id"
        )
    return out


def from_env() -> dict[str, Any]:
    """The `ATHENAEUM_CAPTURE_CONTEXT` mapping's fields, or {} when unset."""
    text = os.environ.get(ENV, "").strip()
    if not text:
        return {}
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        import yaml

        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ContextError(f"{ENV} is neither JSON nor YAML: {exc}") from exc
    return fields(raw)


def resolve(sidecar: dict[str, Any] | None) -> dict[str, Any]:
    """The capture-context fields for one capture: the sidecar's mapping when it declares
    one, else the environment's."""
    if sidecar and "capture_context" in sidecar:
        return fields(sidecar.get("capture_context"))
    return from_env()
