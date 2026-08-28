"""Validate the schema tree's PROSE against itself.

`corpus lint` validates a *record* against the schema. Nothing validated the schema
against itself, and this distribution already carries the gap's signature: a docx
mime schema forward-referencing "the `document` composite" and `corpus overlay
document` — a classification mechanism spec §7.4 retired in ATH-CORPUS 2.0, so
neither resolves to anything the tooling can read — and two files independently
listing `image/diagram` as a classify target for video frames when no such atom
overlay was ever authored (diagrams are `image/figure`, per that overlay's own
description). Both were live in the packaged tree before this lint existed. Every
structural schema-load check passed regardless, because the defect lives in text no
parser reads.

This is that parser. It cannot judge whether guidance is *good*, only whether the
nouns it uses still exist:

  guidance-unknown-field    a backticked snake_case token that no reachable overlay
                            declares as an extended field
  guidance-unknown-overlay  a backticked ``<ns>/<id>`` that resolves to no schema file

Both scan the *prose* only — a schema's top-level ``description`` and every
``normalization.guidance``, at any nesting depth — never the ``extended_fields``
subtree, whose field descriptions legitimately name enum values and nested sub-keys.

Scope is the four namespaces whose guidance the normalizer actually reads at
normalize time — ``mime/``, ``atom/``, ``form/``, ``context/`` (spec §3) — walked
through ``corpus.schemas``'s own two-source resolution (corpus-local overlay first,
packaged default second; a corpus-local whole-file override of a packaged relpath
wins that relpath entirely, same as every other schema read). Run with no reachable
corpus — this repo, the distribution, carries no ``records/`` at all — the walk
still sees the packaged tree alone, because that is what `corpus.schemas` itself
falls back to.

The known-good vocabulary is **derived from the tree at run time**, not hardcoded:
every declared ``extended_fields`` key (plus the vocabulary its own descriptions
name), every mapping key that appears anywhere in any schema, every
``address_scheme`` ``param`` name, the record's core frontmatter keys, the health
signal names, and — per namespace — the overlay ids the tree actually declares
(`corpus.schemas`'s own id conventions: ``class_id`` for atom, ``form_id`` for form,
the namespace-relative path for context, the axis/subtype path plus a loose
same-axis pass for mime, since a bare MIME type like `` `application/pdf` `` is
ordinary prose, not a schema cross-reference). Only genuinely-external vocabulary is
allowlisted below, each with a reason. That way the check tightens automatically as
the schema changes, instead of drifting into a stale list of its own.

Exit codes: 0 clean, 1 findings, 2 invocation failure.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Backticked snake_case: at least one underscore, no dots, no slashes. The underscore
# requirement is what keeps overlay ids (`document`, `receipt`), enum values (`minor`,
# `mixed`), and bare nouns out of the candidate set.
_FIELD_TOKEN = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")

# Backticked `<ns>/<id>` with exactly one slash and no dots — the shape of an overlay
# reference. Excludes paths (`scripts/x/y.py`), URIs (`corpus://…`), and slash-prefixed
# skill/command names (`/curate`).
_OVERLAY_TOKEN = re.compile(r"`([a-z][a-z0-9-]*/[a-z0-9-]+)`")

# The four namespaces whose guidance prose the normalizer reads (spec §3). `origin/` is
# per-corpus and not packaged (schemas.py's own docstring); `composite/` is retired
# (spec §7.4) and stays reserved-but-empty. Neither is worth walking here.
_PROSE_NAMESPACES = ("mime", "atom", "form", "context")

# Vocabulary that is real but lives outside schema/, so it cannot be derived.
_ALLOW: dict[str, str] = {
    # A retired `checks:` key name (spec §4.3.2.4) — `corpus.lint`'s own source still
    # comments on it by name (the rule it was replaced by, `member-rendered-on-parent`,
    # is what's live), and `form/schematic.yaml` explains the retirement as history. No
    # schema file can declare it going forward, so it can never be tree-derived.
    "embed_rendered": "retired checks: key (spec §4.3.2.4) — named as history, not declarable",
    # MPEG-4 ADTS/LOAS bitstream element name (ISO/IEC 14496-3) — a codec framing detail
    # `audio_aac.yaml`'s guidance names to explain the container's own byte layout, not a
    # corpus schema field.
    "raw_data_block": "MPEG-4 ADTS bitstream element name (ISO/IEC 14496-3), not a schema field",
    # Functional-URI transform-pipeline op (spec §6.2, `?auto_orient`) — a resolver
    # keyword documented in `_common.TRANSFORM_GRAMMAR`, not a corpus schema field.
    "auto_orient": "functional-URI transform op (spec §6.2) — resolver keyword, not a schema field",
    # Keys of the PDF `probe` op's JSON output (spec §6.2, `pdf_introspect.probe_page`) —
    # resolver-derived signals the pdf guidance teaches a normalizer to read, not fields
    # any schema declares.
    "shape_hint": "PDF probe-op JSON key (spec §6.2) — resolver output, not a schema field",
    "image_coverage": "PDF probe-op JSON key (spec §6.2) — resolver output, not a schema field",
    "text_char_count": "PDF probe-op JSON key (spec §6.2) — resolver output, not a schema field",
    "has_invisible_text": "PDF probe-op JSON key (spec §6.2) — resolver output, not a schema field",
}

# `guidance-unknown-overlay` is a warning, not an error: naming an overlay that does not
# exist is often deliberate. Schemas legitimately point at subclasses not yet authored,
# deny ones that will never exist ("there is no `text/chrome` overlay in v1.0"), and use
# open-ended vocabulary a normalizer may coin. Those read identically to a genuine
# dangling reference, so this rule hands the operator a review queue rather than a
# verdict. The field rule has no such ambiguity and stays an error.
_SEVERITY = {"guidance-unknown-field": "error", "guidance-unknown-overlay": "warning"}
_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass
class Finding:
    rule_id: str
    severity: str
    path: str
    token: str
    context: str


# ---------- schema-tree walk ---------- #


def _iter_schema_files(root: Path) -> list[tuple[str, dict[str, Any]]]:
    """`(relpath, doc)` for every yaml under the four prose namespaces, in the SAME
    resolved view `corpus.schemas` reads everywhere else: corpus-local first, packaged
    second, whole-file-wins per relpath (no cross-rung merge — this lints each file as
    authored, not the deep-merged runtime schema). `root` need not be a real corpus —
    when it carries no `schema/` dir at all (this distribution repo's own layout), the
    corpus-local source simply resolves nothing and the packaged tree alone is walked."""
    from corpus import schemas as _schemas

    sources = _schemas._sources(root)
    relpaths: dict[str, None] = {}
    for ns in _PROSE_NAMESPACES:
        for relpath in _schemas._discover_yaml(sources, ns):
            relpaths.setdefault(relpath, None)
    out: list[tuple[str, dict[str, Any]]] = []
    for relpath in sorted(relpaths):
        doc = _schemas._read_yaml_first(sources, relpath)
        if isinstance(doc, dict):
            out.append((relpath, doc))
    return out


# ---------- vocabulary derivation ---------- #


def _walk_keys(node: Any, out: set[str]) -> None:
    """Every mapping key anywhere in the tree, at any depth."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str):
                out.add(k)
            _walk_keys(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_keys(v, out)


# Keys whose string value IS prose — the exact text `_prose_of` scans. Walking their
# values back into the vocabulary would make the field rule check guidance against
# itself; every other string value in a schema is structural (`artifact_kind:
# self_contained`, `mode: body-draft`) and is fair game to derive from.
_PROSE_VALUE_KEYS = frozenset({"description", "guidance"})


def _walk_values(node: Any, out: set[str]) -> None:
    """Every scalar string VALUE anywhere in the tree, except prose. Structural
    declarations like `artifact_kind: self_contained` or `working_kind: video` state
    real, tree-declared enum vocabulary this way — guidance elsewhere is entitled to
    name that value verbatim, so it belongs in the derived vocabulary exactly like a
    declared field name does."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and k in _PROSE_VALUE_KEYS:
                continue
            if isinstance(v, str):
                out.add(v)
            else:
                _walk_values(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_values(v, out)


def _prose_of(doc: Any) -> list[str]:
    """The strings a human reads as guidance: top-level `description` plus every
    `normalization.guidance`, at any nesting depth. Deliberately skips
    `extended_fields` — a field's own description documents its *values*, and naming
    an enum member there is correct, not stale."""
    out: list[str] = []

    def rec(node: Any, *, top: bool) -> None:
        if not isinstance(node, dict):
            return
        if top and isinstance(node.get("description"), str):
            out.append(node["description"])
        norm = node.get("normalization")
        if isinstance(norm, dict) and isinstance(norm.get("guidance"), str):
            out.append(norm["guidance"])
        for k, v in node.items():
            if k == "extended_fields":
                continue
            if isinstance(v, dict):
                rec(v, top=False)

    rec(doc, top=True)
    return out


def _namespace_overlay_ids(root: Path, ns: str, relpath: str, doc: dict[str, Any]) -> set[str]:
    """The overlay id(s) `relpath`/`doc` resolves to, in the shape guidance prose
    actually names them — namespace-aware per `corpus.schemas`'s own id conventions
    for that namespace (module docstring, `load_atomic_overlay`/`load_form_overlay`/
    `load_context_schema`/`load_mime_schema`)."""
    stem = relpath.removeprefix(f"{ns}/").removesuffix(".yaml")
    if ns == "mime":
        # `<axis>/<axis>_<subtype>.yaml` -> id `<axis>/<axis>_<subtype>` (schemas.py's
        # `_mime_schema_id`). The common loose per-axis pass (any `` `<axis>/...` ``
        # token) is handled separately in `lint_schema` — a bare MIME type is ordinary
        # prose, not a cross-reference to a specific schema file.
        return {stem}
    if ns == "atom":
        # The declared `class_id` is the form guidance actually uses (`text/data-table`);
        # the path-derived id is kept too as a fallback for a malformed/missing one.
        ids = {stem}
        cid = doc.get("class_id")
        if isinstance(cid, str) and cid:
            ids.add(cid)
        return ids
    if ns == "form":
        # Flat `form/<id>.yaml`; guidance may name it bare (`` `manifest` ``, which
        # never matches the overlay-token shape anyway) or slash-qualified
        # (`` `form/manifest` ``) — register both spellings.
        ids = {f"form/{stem}"}
        fid = doc.get("form_id")
        if isinstance(fid, str) and fid:
            ids.add(fid)
            ids.add(f"form/{fid}")
        return ids
    if ns == "context":
        # `context/<namespace>/<rest>.yaml`. The per-namespace universal file
        # (`issue/issue.yaml`, `sweep/sweep.yaml`) resolves for the BARE namespace id
        # (`issue`, `sweep`) — schemas.py's own `rest = ... or namespace` fallback;
        # everything else is `<namespace>/<rest>` exactly as it sits on disk.
        namespace, _, rest = stem.partition("/")
        return {namespace} if (not rest or rest == namespace) else {f"{namespace}/{rest}"}
    return {stem}  # pragma: no cover — _PROSE_NAMESPACES is exhaustive


def build_vocabulary(root: Path) -> tuple[set[str], set[str], set[str]]:
    """Returns `(known_fields, known_overlays, mime_prefixes)`."""
    from corpus import health, records

    fields: set[str] = set()
    keys: set[str] = set()
    values: set[str] = set()
    overlays: set[str] = set()
    params: set[str] = set()
    mime_prefixes: set[str] = set()

    for relpath, doc in _iter_schema_files(root):
        ns = relpath.split("/", 1)[0]
        ef = doc.get("extended_fields")
        if isinstance(ef, dict):
            fields |= set(ef)
            # A field's own description documents its value vocabulary — a `status`
            # spec enumerating `draft`, `normalized`, and friends. Guidance elsewhere
            # may reference those values, so harvest them rather than flagging every
            # enum member as an unknown field.
            for spec in ef.values():
                desc = spec.get("description") if isinstance(spec, dict) else None
                if isinstance(desc, str):
                    fields |= set(_FIELD_TOKEN.findall(desc))
        _walk_keys(doc, keys)
        _walk_values(doc, values)
        for entry in doc.get("address_scheme") or []:
            if isinstance(entry, dict) and isinstance(entry.get("param"), str):
                params.add(entry["param"])
        # The `sidecar.ytdlp_keys` list (video/audio mime schemas) names the SUFFIXES
        # the drafter prefixes with `ytdlp_` when it lifts non-primary-source metadata
        # onto the origin block (§12.3's sidecar convention) — the resulting field
        # names (`ytdlp_title`, `ytdlp_view_count`, …) never appear as literal keys or
        # values anywhere in the tree, so they need this one targeted derivation.
        sidecar = doc.get("sidecar")
        if isinstance(sidecar, dict):
            for key in sidecar.get("ytdlp_keys") or []:
                if isinstance(key, str) and key:
                    fields.add(f"ytdlp_{key}")
            # *(v41)* An origin overlay's container-member `sidecar:` lifts
            # `<prefix><field>` for every `lift`/`references` key (spec §7.2) — the same
            # derivation, prefix declared rather than fixed.
            prefix = sidecar.get("prefix")
            if isinstance(prefix, str) and prefix:
                for section in ("lift", "references"):
                    entries = sidecar.get(section)
                    if isinstance(entries, dict):
                        fields |= {f"{prefix}{k}" for k in entries if isinstance(k, str)}
        overlays |= _namespace_overlay_ids(root, ns, relpath, doc)
        if ns == "mime":
            axis = relpath.removeprefix("mime/").split("/", 1)[0]
            if not axis.endswith(".yaml"):
                mime_prefixes.add(axis)

    known_fields = (
        fields
        | keys
        | values
        | params
        | set(_ALLOW)
        | set(health.SIGNAL_NAMES)
        | set(records._CORE_FIELD_ORDER)
    )
    return known_fields, overlays, mime_prefixes


# ---------- rules ---------- #


def lint_schema(root: Path) -> list[Finding]:
    known_fields, known_overlays, mime_prefixes = build_vocabulary(root)
    findings: list[Finding] = []

    for relpath, doc in _iter_schema_files(root):
        for prose in _prose_of(doc):
            for m in _FIELD_TOKEN.finditer(prose):
                tok = m.group(1)
                if tok in known_fields:
                    continue
                rid = "guidance-unknown-field"
                findings.append(
                    Finding(rid, _SEVERITY[rid], relpath, tok, _context(prose, m.start()))
                )
            for m in _OVERLAY_TOKEN.finditer(prose):
                tok = m.group(1)
                if tok in known_overlays or tok.split("/")[0] in mime_prefixes:
                    continue
                rid = "guidance-unknown-overlay"
                findings.append(
                    Finding(rid, _SEVERITY[rid], relpath, tok, _context(prose, m.start()))
                )
    return findings


def _context(text: str, at: int) -> str:
    """The sentence around the hit — enough to hand-edit from."""
    start = max(text.rfind(". ", 0, at), text.rfind("\n", 0, at)) + 1
    end = text.find(". ", at)
    end = len(text) if end == -1 else end + 1
    return " ".join(text[start:end].split())[:200]


# ---------- cli ---------- #


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--corpus-root",
        dest="corpus_root",
        default=None,
        help=(
            "Path to a corpus whose corpus-local schema/ overlays get layered over the "
            "packaged tree (default: walk up from cwd for one; falling back to the "
            "packaged tree alone when none is reachable — e.g. run from this repo)."
        ),
    )
    parser.add_argument(
        "--rule", action="append", default=[],
        help="restrict to this rule id (repeat to OR multiple).",
    )
    parser.add_argument(
        "--severity", choices=("info", "warning", "error"), default="info",
        help="suppress findings below this severity (default: info — show everything).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit findings as newline-delimited JSON instead of grouped text.",
    )


def _resolve_lint_root(args: argparse.Namespace) -> Path:
    """The root whose schema tree gets linted. Deliberately NOT `_common.resolved_corpus_root`
    — that insists on a `records/` dir, which a schema-lint run needs no more than
    `corpus schemas` needs one to list the packaged tree. An explicit `--corpus-root` need
    only carry a `schema/` dir; with none given, `paths.find_corpus_root` is tried, and its
    `FileNotFoundError` — no records/+schema/ pair above cwd, exactly this distribution
    repo's own layout — is not fatal: cwd is used instead, which resolves to zero
    corpus-local files and leaves the packaged tree as the whole visible view, same as
    every other schema read falls back to."""
    explicit = getattr(args, "corpus_root", None)
    if explicit:
        root = Path(explicit).resolve()
        if not (root / "schema").is_dir():
            sys.exit(f"--corpus-root {root}: no schema/ dir")
        return root
    from corpus import paths

    try:
        return paths.find_corpus_root()
    except FileNotFoundError:
        return Path.cwd()


def run(args: argparse.Namespace) -> int:
    root = _resolve_lint_root(args)
    files = _iter_schema_files(root)
    findings = lint_schema(root)
    if args.rule:
        findings = [f for f in findings if f.rule_id in set(args.rule)]
    threshold = _SEVERITY_ORDER[args.severity]
    findings = [f for f in findings if _SEVERITY_ORDER[f.severity] >= threshold]

    # Exit non-zero only on errors, so a `--severity error` gate can run in CI while the
    # warning queue stays visible to an operator running it bare.
    failed = any(f.severity == "error" for f in findings)

    if args.json:
        for f in findings:
            sys.stdout.write(json.dumps(f.__dict__, ensure_ascii=False) + "\n")
        return 1 if failed else 0

    n_checked = len(files)
    if not findings:
        print(f"✓ schema/ clean — {n_checked} file(s) checked.")
        return 0

    n_err = sum(1 for f in findings if f.severity == "error")
    print(
        f"{len(findings)} finding(s) in {len({f.path for f in findings})} file(s) "
        f"— {n_err} error, {len(findings) - n_err} warning  ({n_checked} checked)\n"
    )
    current = ""
    for f in sorted(findings, key=lambda x: (-_SEVERITY_ORDER[x.severity], x.path)):
        if f.path != current:
            current = f.path
            print(f"{current}")
        print(f"  {f.severity:7} {f.rule_id:26}  `{f.token}`")
        print(f"      {f.context}")
    print(
        "\nGuidance naming a field or overlay that no longer exists is stale guidance: "
        "the\nnormalizer acts on it, and no record-level check can see the error. Warnings "
        "are\noften deliberate (future subclasses, open-ended vocabulary) — read them, "
        "don't\njust clear them."
    )
    return 1 if failed else 0
