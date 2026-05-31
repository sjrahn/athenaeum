"""Touch-chain audit field.

Per spec-corpus.md §4.2.2. Each record carries a `touch:` field (string or list[string]) —
one identifier per processing pass.

Forms:

- In-tree scripts: `corpus.<module>@<version>` (e.g. `corpus.ingest@0.1.0`,
  `corpus.draft.mime/text/html@0.1.0`).
- LLM models: canonical model identifier with optional context modifier in brackets
  (e.g. `claude-opus-4-7[1m]`).
- Combined script+model: `corpus.<module>@<version>+<model-id>` for a pass that is
  both a script run and the LLM pass it carries (e.g. a normalize pass committed via
  `corpus compile --model <id>`).

Consecutive identical touches are coalesced with a `_<count>` suffix — the audit
chain preserves *how many times* an operation ran without repeated lines.
`corpus.draft.video@0.1.0` followed by another `corpus.draft.video@0.1.0` becomes
`corpus.draft.video@0.1.0_2`. A different identifier between resets the count.

The current-shape provenance can be reset by `re-stub` (spec §8.4); per-pass timestamps
live in `state/<skill>/log.md` when a skill chooses to record them, not in the record.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import frontmatter

from . import __version__

_COUNT_SUFFIX_RE = re.compile(r"^(.*)_(\d+)$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def script_identifier(name: str) -> str:
    """Format a touch identifier for an in-tree script.

    `name` is the dotted module path under the `corpus` package, e.g. `ingest`,
    `draft.mime/application/pdf`. Resulting form: `corpus.{name}@{version}`.
    """
    return f"corpus.{name}@{__version__}"


def _split_count(entry: str) -> tuple[str, int]:
    """Return (base_identifier, count). Bare entries have count=1."""
    m = _COUNT_SUFFIX_RE.match(entry)
    if m:
        return m.group(1), int(m.group(2))
    return entry, 1


def record_touch(post: frontmatter.Post, identifier: str, *, at: str | None = None) -> None:
    """Record a processing pass on `post`.

    Appends `identifier` to `touch[]` unless the last entry is the same base
    identifier — in that case the suffix increments
    (`...@0.1.0` → `...@0.1.0_2` → `...@0.1.0_3`).

    `touch:` is stored as a bare string when the chain has exactly one entry, and
    as a list when there are two or more.

    The `at` parameter is accepted for API compatibility; the record itself doesn't
    carry per-touch timestamps (they live in skill-specific logs).
    """
    del at  # accepted for API back-compat; the record format doesn't persist timestamps
    raw = post.metadata.get("touch")
    if raw is None:
        history: list[str] = []
    elif isinstance(raw, str):
        history = [raw]
    else:
        history = [str(x) for x in raw]

    if history:
        last_base, last_count = _split_count(history[-1])
        if last_base == identifier:
            history[-1] = f"{identifier}_{last_count + 1}"
        else:
            history.append(identifier)
    else:
        history.append(identifier)

    if len(history) == 1:
        post.metadata["touch"] = history[0]
    else:
        post.metadata["touch"] = history


def touch_list(post: frontmatter.Post) -> list[str]:
    """Return the touch chain as a list, regardless of whether it's persisted as a
    bare string or a list."""
    raw = post.metadata.get("touch")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    return [str(x) for x in raw]
