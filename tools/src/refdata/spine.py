"""The spine resolution layer (spec/ledger.md §§15.1-15.3): resolves a
`{dataset}:{id-or-label}` reference form — an `extends:` chain's parent, or
any other spot the ontology layer names a spine term — against the
instance's registered spine datasets.

A spine dataset is an ordinary registered reference dataset (`ath.manifest`,
spec/athenaeum.md §2.3) marked `spine: true` (§15.2): its mirror bytes are a
corpus artifact, materialized and adapter-resolved exactly like any other
`references:` entry (`refdata.materialize`/`resolve_adapter_name`). What
distinguishes spine resolution from an ordinary `ref://` citation lookup
(`refdata.resolve`/`search`) is the reference **form** — a native id, or a
label unique in the resolved release, always at the dataset's `latest` (no
`@tag` pin ever admitted here) — and that ambiguity itself is a validation
error, never a caller's problem to disambiguate silently.

Three entry points:

- `resolve_term(spec, references, corpora_roots)` — the full resolution:
  spec grammar -> registered spine dataset -> materialized mirror -> adapter
  -> term. Raises the typed errors below on any failure a caller needs to
  branch on; where the mirror bytes are not locally materialized (or the
  adapter itself is unavailable), the ordinary `refdata` "honestly
  unverifiable, never a crash" outcomes propagate unchanged
  (`MirrorUnavailable`, `AdapterUnavailable`, `MirrorCorrupt` — §6.5's own
  idiom, not reinvented here): every other failure — bad grammar, an
  unregistered or non-spine dataset, a pin, an unresolvable id/label, an
  ambiguous label — is a hard validation error regardless of mirror state
  (§15.2: "grammar, registration, and snapshot-binding checks stay
  mechanical everywhere").
- `spine_bindings(references)` — every registered `spine: true` dataset's
  resolved `(tag, artifact blake3)` binding, config data alone (no mirror
  access) — the tuple `ath ledger export`'s reproducibility stamp pins
  (§15.7).
- `ResolvedTerm` / `SpineBinding` — the two result shapes above.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ath.manifest import Reference

from . import ADAPTERS, adapter_available, materialize, resolve_adapter_name
from .errors import (
    AdapterUnavailable,
    AmbiguousSpineLabel,
    InvalidSpineReference,
    MirrorUnavailable,
    NotSpineDataset,
    SpineIncapableAdapter,
    SpineTermNotFound,
    UnknownTag,
)

__all__ = [
    "ResolvedTerm",
    "SpineBinding",
    "resolve_term",
    "spine_bindings",
]


@dataclass(frozen=True)
class ResolvedTerm:
    """One `{dataset}:{id-or-label}` spine reference, resolved (spec/ledger.md
    §15.2). `native_id`/`label` are the resolved release's own — for an id
    spec these are simply looked up; for a label spec, `native_id` is what
    the label resolved to. `deprecated` is the release's own mark: callers
    (the ontology check pass) decide whether to warn on it — resolution
    itself does not refuse a deprecated term."""

    dataset: str
    native_id: str
    label: str
    deprecated: bool


@dataclass(frozen=True)
class SpineBinding:
    """One registered spine dataset's resolved `latest` binding — config data
    alone, no mirror access (spec/ledger.md §15.7's reproducibility tuple)."""

    dataset: str
    tag: str
    artifact: str


def _split_spec(spec: str) -> tuple[str, str]:
    if "@" in spec:
        raise InvalidSpineReference(
            f"{spec!r}: spine references are always bare — no @tag pin admitted "
            "(spec/ledger.md §15.2, 'one spine version per instance')"
        )
    dataset, sep, ident = spec.partition(":")
    if not sep or not dataset or not ident:
        raise InvalidSpineReference(
            f"{spec!r} is not a valid spine reference — want '{{dataset}}:{{id-or-label}}'"
        )
    return dataset, ident


def _spine_reference(dataset: str, references: Sequence[Reference]) -> Reference:
    for ref in references:
        if ref.dataset == dataset:
            if not ref.spine:
                raise NotSpineDataset(
                    f"{dataset!r} is a registered reference dataset but not marked "
                    "spine: true (spec/ledger.md §15.2)"
                )
            return ref
    raise NotSpineDataset(f"{dataset!r} is not a registered reference dataset")


def _open_handle(reference: Reference, corpora_roots: Sequence[Path]) -> tuple[str, Any]:
    """Open `reference`'s `latest` snapshot mirror — spine resolution admits
    no tag other than `latest` (§15.2). Mirrors `refdata._resolve_handle`'s
    order (adapter resolution and availability before materialization) but
    with no index-path plumbing: no spine-capable adapter needs a sidecar.

    The `iter_terms` capability check runs right after the adapter is known
    — a static property of the adapter module — and before materialization,
    so a dataset misregistered as `spine: true` on a plain reference adapter
    (`zim`, `osm-pbf`) reports `SpineIncapableAdapter` regardless of whether
    its mirror bytes even exist yet."""
    tag = reference.latest
    if tag not in reference.snapshots:
        raise UnknownTag(f"{reference.dataset}: latest tag {tag!r} names no registered snapshot")
    adapter_name = resolve_adapter_name(reference, corpora_roots)
    if not adapter_available(adapter_name):
        raise AdapterUnavailable(
            f"{reference.dataset}: adapter {adapter_name!r} is unregistered or its "
            "optional dependency is not installed in this environment"
        )
    if not hasattr(ADAPTERS[adapter_name], "iter_terms"):
        raise SpineIncapableAdapter(
            f"adapter {adapter_name!r} ({reference.dataset}) carries no iter_terms — it "
            "cannot root a spine (spec/ledger.md §15.2)"
        )
    mirror_path = materialize(reference, tag, corpora_roots)
    if mirror_path is None:
        raise MirrorUnavailable(
            f"{reference.dataset}@{tag}: no local bytes (neither the declared path: "
            "override nor any given corpus root's artifact store or attached location) "
            "— spine resolution against it is honestly unverifiable until materialized"
        )
    return adapter_name, ADAPTERS[adapter_name].open_archive(mirror_path)


def resolve_term(
    spec: str,
    references: Sequence[Reference],
    corpora_roots: Sequence[Path] = (),
) -> ResolvedTerm:
    """Resolve one `{dataset}:{id-or-label}` spine reference (spec/ledger.md
    §15.2) against `references` (the instance's full registered set —
    `ath.manifest.load_references`; only entries with `spine: true` are
    eligible roots).

    Tries `ident` as a native id first, then — if no term carries that id —
    as a label, unique-in-the-release required. Raises `InvalidSpineReference`
    for bad grammar or an `@tag` pin, `NotSpineDataset` for an unregistered or
    non-spine dataset, `SpineIncapableAdapter` if the resolved adapter carries
    no `iter_terms`, `SpineTermNotFound` if neither an id nor a label matches,
    `AmbiguousSpineLabel` if a label matches more than one term — and, from
    the mirror layer unchanged, `MirrorUnavailable`/`AdapterUnavailable`/
    `MirrorCorrupt` when the mirror or its adapter isn't usable in this
    environment (§6.5's honestly-unverifiable idiom, never a hard failure).
    """
    dataset, ident = _split_spec(spec)
    reference = _spine_reference(dataset, references)
    adapter_name, handle = _open_handle(reference, corpora_roots)
    adapter = ADAPTERS[adapter_name]

    terms = list(adapter.iter_terms(handle))
    by_id = {t.native_id: t for t in terms}
    term = by_id.get(ident)
    if term is None:
        matches = [t for t in terms if t.label == ident]
        if not matches:
            raise SpineTermNotFound(
                f"{spec}: no term with id or label {ident!r} in {dataset}@{reference.latest}"
            )
        if len(matches) > 1:
            raise AmbiguousSpineLabel(
                f"{spec}: label {ident!r} matches {len(matches)} terms in "
                f"{dataset}@{reference.latest} "
                f"({', '.join(sorted(m.native_id for m in matches))}) — cite the native id"
            )
        term = matches[0]

    return ResolvedTerm(
        dataset=dataset, native_id=term.native_id, label=term.label, deprecated=term.deprecated
    )


def spine_bindings(references: Sequence[Reference]) -> list[SpineBinding]:
    """Every registered `spine: true` dataset's resolved `(latest tag, mirror
    artifact blake3)` binding — pure config data, no mirror materialization
    or adapter access (spec/ledger.md §15.7: the export's reproducibility
    stamp pins exactly this). Sorted by dataset name for a deterministic
    stamp."""
    bindings: list[SpineBinding] = []
    for ref in references:
        if not ref.spine:
            continue
        snapshot = ref.snapshots.get(ref.latest)
        if snapshot is None:
            raise UnknownTag(
                f"{ref.dataset}: latest {ref.latest!r} names no registered snapshot"
            )
        bindings.append(
            SpineBinding(dataset=ref.dataset, tag=ref.latest, artifact=snapshot.artifact)
        )
    return sorted(bindings, key=lambda b: b.dataset)
