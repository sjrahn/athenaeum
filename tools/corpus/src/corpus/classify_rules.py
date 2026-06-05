"""Deterministic, draft-time auto-classification (spec §7.4 `classify_when`).

A composite overlay MAY carry a `classify_when` predicate over a fixed, normalized fact base
(MIME, origin URL parts, `media.*` aliases over the lifted `ytdlp_*` fields). When the
predicate matches a record, the drafter stamps a `<!--classify <ns>/<id>-->` block with a
reserved `provenance: auto` field. Mechanical: no network, no LLM, no clock — same record
bytes + same overlay set → identical classifications every run.

This is the **mechanical, membership-at-draft** path. It is complementary to
`classify_match.candidates()` (the **interpretive, body-cue, normalizer-facing** matcher) —
the two are deliberately not merged (spec §7.4). Two contract rules carry the no-false-positive
guarantee:

- **A missing fact is FALSE**, never a wildcard — an HTML record has no `media.channel_id`, so
  a video rule can never fire on it. (Falls out of the empty-value-list semantics below; only
  `exists: false` is True on an absent fact.)
- **Body-text cues are never a deterministic trigger** — `applies_to.cues.body_contains` stays
  interpretive (normalizer-only); it is not part of this fact base.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import frontmatter

from . import records, schemas
from . import urls as urlcanon

# The classify-block field that marks an engine-stamped membership. Its absence (or
# `provenance: asserted`) means a hand-/normalizer-asserted block, which the engine never
# touches. Reserved — no composite may use `provenance` as an `extended_field` (spec §4.3.1.3).
PROVENANCE_FIELD = "provenance"
PROVENANCE_AUTO = "auto"

# `media.<field>` is the inverse of the `ytdlp_<field>` origin fields the sidecar lifts
# (`draft/_sidecar.py::_YTDLP_KEYS`) — strip this prefix to expose the alias. Tracks the lifted
# key set automatically: a key added to `sidecar.ytdlp_keys` becomes a `media.*` fact for free.
_MEDIA_PREFIX = "ytdlp_"

_COMBINATORS = frozenset({"all_of", "any_of", "none_of"})

# A fact base maps each fact name to the list of values it holds across the record's origins
# (any-origin semantics). An absent fact is simply a missing key (== the empty list).
FactBase = dict[str, list[str]]


# ---------- fact extraction ---------- #


def build_facts(corpus_root: Path, post: frontmatter.Post) -> FactBase:
    """Extract the spec §7.4 fact base from an in-memory record.

    Every fact is **list-valued** (any-origin semantics — one value per contributing origin;
    operators test "any element"). An absent fact is the empty list, so every operator except
    `exists: false` evaluates False on it — the missing-fact-⇒-false rule, for free.

    Facts: `mime`; `origin.uri` / `origin.host` / `origin.path` / `origin.fragment` /
    `origin.query.<k>` / `origin.id`; `media.<field>` (inverse of the `ytdlp_<field>` origin
    fields). `dom.*` is reserved for v2 — the resolver slots in here.
    """
    facts: FactBase = {}

    def add(key: str, value: Any) -> None:
        if value is None or value == "":
            return
        facts.setdefault(key, []).append(str(value))

    mime = records.media_type_for(post)
    if mime:
        add("mime", mime)

    uris = list(records.iter_origin_uris(post))
    for uri in uris:
        parts = urlsplit(uri)
        add("origin.uri", uri)
        add("origin.host", urlcanon.host_of(uri))
        add("origin.path", parts.path)
        add("origin.fragment", parts.fragment)
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            add(f"origin.query.{key}", value)

    for origin_id, _schema in schemas.origin_overlays_for_uris(corpus_root, uris):
        add("origin.id", origin_id)

    for origin in records.iter_origin_blocks(post):
        for key, value in (origin.get("fields") or {}).items():
            if not key.startswith(_MEDIA_PREFIX):
                continue
            media_key = "media." + key[len(_MEDIA_PREFIX) :]
            for item in value if isinstance(value, list) else [value]:
                add(media_key, item)

    return facts


# ---------- predicate evaluation ---------- #


def evaluate(predicate: Any, facts: FactBase) -> bool:
    """Evaluate a `classify_when` predicate against `facts`. Pure and total — an unknown shape
    or operator is False (fail-closed). Combinators `all_of`/`any_of`/`none_of` each take a
    list; a bare mapping of one-or-more `{fact: {op: value}}` is `all_of` sugar; combinator
    keys and leaf keys at one level are AND-ed."""
    if not isinstance(predicate, dict) or not predicate:
        return False
    results: list[bool] = []
    for key, value in predicate.items():
        if key == "all_of":
            results.append(all(evaluate(child, facts) for child in _as_list(value)))
        elif key == "any_of":
            results.append(any(evaluate(child, facts) for child in _as_list(value)))
        elif key == "none_of":
            results.append(not any(evaluate(child, facts) for child in _as_list(value)))
        else:
            results.append(_eval_leaf(key, value, facts))
    return all(results)


def _eval_leaf(fact: str, cond: Any, facts: FactBase) -> bool:
    """A leaf `{<fact>: {<op>: <value>}}` — every op in `cond` must hold (AND)."""
    if not isinstance(cond, dict) or not cond:
        return False
    values = facts.get(fact, [])
    return all(_eval_op(op, operand, values) for op, operand in cond.items())


def _eval_op(op: str, operand: Any, values: list[str]) -> bool:
    if op == "exists":
        return (len(values) > 0) == bool(operand)
    if op == "equals":
        return any(v == str(operand) for v in values)
    if op == "in":
        choices = {str(x) for x in _as_list(operand)}
        return any(v in choices for v in values)
    if op == "glob":
        return any(fnmatch.fnmatch(v, str(operand)) for v in values)
    if op == "matches":
        try:
            pattern = re.compile(str(operand))
        except re.error:
            return False
        return any(pattern.fullmatch(v) is not None for v in values)
    return False  # unknown operator → fail closed


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


# ---------- matching + application ---------- #


@dataclass(frozen=True)
class Match:
    """One composite overlay whose `classify_when` matched, with the satisfying facts (the
    `--dry-run` "why")."""

    class_id: str
    why: str


@dataclass
class AutoDelta:
    """The net effect of an `apply_auto_classifications` pass. `added`/`removed` are the
    id-set change (a still-matching block is `kept`, not churned); `changed` drives the
    write."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def matching_classes(corpus_root: Path, post: frontmatter.Post) -> list[Match]:
    """Every composite overlay (base + subclass) whose `classify_when` matches `post`, in
    schema-declaration order. Overlays without `classify_when` are skipped — the engine is
    pure opt-in, so a corpus with no rules returns `[]`."""
    facts = build_facts(corpus_root, post)
    out: list[Match] = []
    for class_id, schema in schemas.iter_all_classifications(corpus_root):
        predicate = schema.get("classify_when")
        if predicate and evaluate(predicate, facts):
            out.append(Match(class_id=class_id, why=_why(predicate, facts)))
    return out


def apply_auto_classifications(corpus_root: Path, post: frontmatter.Post) -> AutoDelta:
    """Strip every `provenance: auto` classify block and regenerate from the current overlay
    rules — the idempotent self-heal core shared by the draft hook and `corpus
    classify`/`reclassify`. Hand-/normalizer-asserted blocks (no `provenance`) are preserved.

    Auto blocks are placed **before** any surviving non-auto block: a `classify_when` match is
    decided at draft (mechanical execution order), so it precedes interpretive blocks per spec
    §4.3.1.3. Deterministic — matches keep schema-declaration order. Strip-all-auto +
    regen-from-rules is a fixpoint, so a re-draft / reclassify after a rule change converges."""
    existing = list(records.iter_classify_blocks(post))
    prev_auto = [class_id_of(b) for b in existing if _is_auto(b)]
    survivors = [b for b in existing if not _is_auto(b)]

    matches = matching_classes(corpus_root, post)
    new_ids = [m.class_id for m in matches]

    auto_blocks: list[dict[str, Any]] = []
    for class_id in new_ids:
        namespace, id_, subtype = _split_class_id(class_id)
        auto_blocks.append(
            {
                "namespace": namespace,
                "id": id_,
                "subtype": subtype,
                "fields": {PROVENANCE_FIELD: PROVENANCE_AUTO},
            }
        )
    post.metadata["_classifies"] = auto_blocks + survivors

    prev_set, new_set = set(prev_auto), set(new_ids)
    return AutoDelta(
        added=[i for i in new_ids if i not in prev_set],
        removed=[i for i in prev_auto if i not in new_set],
        kept=[i for i in new_ids if i in prev_set],
        matches=matches,
    )


def auto_class_ids(post: frontmatter.Post) -> list[str]:
    """The class ids of the record's `provenance: auto` classify blocks (for display/report)."""
    return [class_id_of(b) for b in records.iter_classify_blocks(post) if _is_auto(b)]


def class_id_of(block: dict[str, Any]) -> str:
    """Reconstruct a classify block's namespace-qualified class id, collapsing `id == namespace`
    to the bare form (matches `records.derived_classifications`)."""
    namespace = block.get("namespace") or ""
    id_ = block.get("id") or namespace
    subtype = block.get("subtype")
    base = id_ if id_ == namespace else f"{namespace}/{id_}"
    return f"{base}/{subtype}" if subtype else base


def _is_auto(block: dict[str, Any]) -> bool:
    return (block.get("fields") or {}).get(PROVENANCE_FIELD) == PROVENANCE_AUTO


def _split_class_id(class_id: str) -> tuple[str, str, str | None]:
    """`<namespace>/<id>[/<subtype>]` → `(namespace, id, subtype)`; a single segment becomes
    `(seg, seg, None)` (namespace == id, the bare form)."""
    parts = [p for p in class_id.split("/") if p]
    if len(parts) <= 1:
        only = parts[0] if parts else class_id
        return only, only, None
    if len(parts) == 2:
        return parts[0], parts[1], None
    return parts[0], parts[1], parts[2]


def _why(predicate: Any, facts: FactBase) -> str:
    """A short, ASCII summary of the present facts the predicate references — for `--dry-run`."""
    parts: list[str] = []
    for fact in _collect_leaf_facts(predicate):
        values = facts.get(fact)
        if values:
            parts.append(f"{fact}={values[0]}" if len(values) == 1 else f"{fact} in {values}")
    return ", ".join(dict.fromkeys(parts))  # de-dup, keep order


def _collect_leaf_facts(predicate: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(predicate, dict):
        return out
    for key, value in predicate.items():
        if key in _COMBINATORS:
            for child in _as_list(value):
                out.extend(_collect_leaf_facts(child))
        else:
            out.append(key)
    return out
