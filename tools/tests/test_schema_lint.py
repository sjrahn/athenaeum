"""`corpus schema-lint` — the schema-tree guidance-prose validator."""

from __future__ import annotations

from pathlib import Path

import yaml

from corpus import schemas
from corpus._cli import schema_lint


def _write_yaml(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _findings(root: Path, *, rule: str | None = None) -> list[schema_lint.Finding]:
    schemas._sources.cache_clear()
    findings = schema_lint.lint_schema(root)
    return [f for f in findings if rule is None or f.rule_id == rule]


# ---------- rule detection ---------- #


def test_unknown_field_token_flagged(tmp_path):
    """A backticked snake_case token no overlay declares is `guidance-unknown-field`."""
    root = tmp_path / "c"
    _write_yaml(
        root / "schema" / "context" / "sweep" / "widget.yaml",
        {"description": "Carries a `totally_unknown_field` nobody ever declared."},
    )
    findings = _findings(root, rule="guidance-unknown-field")
    tokens = {f.token for f in findings}
    assert "totally_unknown_field" in tokens
    hit = next(f for f in findings if f.token == "totally_unknown_field")
    assert hit.severity == "error"
    assert hit.path == "context/sweep/widget.yaml"


def test_unknown_overlay_token_flagged(tmp_path):
    """A backticked `<ns>/<id>` resolving to no schema file is `guidance-unknown-overlay`
    (a warning) — `bogus-ns` matches no mime axis, atom, form, or context namespace, so
    the mime-prefix loose-pass (a bare MIME type is ordinary prose) doesn't swallow it."""
    root = tmp_path / "c"
    _write_yaml(
        root / "schema" / "context" / "sweep" / "widget.yaml",
        {"description": "See the `bogus-ns/bogus-id` overlay for details."},
    )
    findings = _findings(root, rule="guidance-unknown-overlay")
    tokens = {f.token for f in findings}
    assert "bogus-ns/bogus-id" in tokens
    hit = next(f for f in findings if f.token == "bogus-ns/bogus-id")
    assert hit.severity == "warning"


def test_normalization_guidance_scanned_at_any_depth(tmp_path):
    """`normalization.guidance` is scanned; `extended_fields` is never scanned even
    though it is a sibling of `normalization` in the same file."""
    root = tmp_path / "c"
    _write_yaml(
        root / "schema" / "context" / "sweep" / "widget.yaml",
        {
            "description": "Fine.",
            "normalization": {"guidance": "Mind the `guidance_only_token` here."},
            "extended_fields": {
                "real_field": {"description": "mentions `extended_fields_only_token`"}
            },
        },
    )
    findings = _findings(root, rule="guidance-unknown-field")
    tokens = {f.token for f in findings}
    assert "guidance_only_token" in tokens
    assert "extended_fields_only_token" not in tokens  # never scanned


# ---------- tree-derived vocabulary ---------- #


def test_declared_extended_field_passes(tmp_path):
    """A field declared in `extended_fields` anywhere in the tree resolves — the
    vocabulary is derived from the schema tree, not a hardcoded list."""
    root = tmp_path / "c"
    _write_yaml(
        root / "schema" / "context" / "sweep" / "widget.yaml",
        {
            "description": "Carries `my_declared_field`, set at draft time.",
            "extended_fields": {
                "my_declared_field": {"type": "string", "required": False, "description": "x"}
            },
        },
    )
    findings = _findings(root, rule="guidance-unknown-field")
    assert not any(f.token == "my_declared_field" for f in findings)


def test_declared_overlay_id_passes(tmp_path):
    """A form's own declared `form_id` resolves both bare and slash-qualified."""
    root = tmp_path / "c"
    _write_yaml(
        root / "schema" / "form" / "widget.yaml",
        {"form_id": "widget", "description": "See `form/widget` for the shape contract."},
    )
    findings = _findings(root, rule="guidance-unknown-overlay")
    assert not any(f.token == "form/widget" for f in findings)


def test_corpus_local_override_layers_over_packaged(tmp_path):
    """The lint walks the SAME resolved view `corpus.schemas` reads elsewhere:
    corpus-local schema/ layers over the packaged tree, not a bare filesystem walk."""
    root = tmp_path / "c"
    _write_yaml(
        root / "schema" / "context" / "issue" / "corpus-local-issue.yaml",
        {"description": "Names `corpus_local_only_field` (declared right here).",
         "extended_fields": {"corpus_local_only_field": {"type": "string", "description": "x"}}},
    )
    findings = _findings(root, rule="guidance-unknown-field")
    assert not any(f.token == "corpus_local_only_field" for f in findings)
    # And the packaged tree is still visible alongside the corpus-local addition.
    paths = {relpath for relpath, _ in schema_lint._iter_schema_files(root)}
    assert "context/issue/corpus-local-issue.yaml" in paths
    assert "mime/mime.yaml" in paths  # packaged file, not shadowed


# ---------- allowlist ---------- #


def test_allowlisted_external_token_passes(tmp_path):
    """A token in `_ALLOW` is real vocabulary that lives outside schema/ — it passes
    without being declared anywhere in the tree."""
    root = tmp_path / "c"
    _write_yaml(
        root / "schema" / "context" / "sweep" / "widget.yaml",
        {"description": "Try `auto_orient` first."},
    )
    findings = _findings(root, rule="guidance-unknown-field")
    assert not any(f.token == "auto_orient" for f in findings)


# ---------- the packaged tree itself ---------- #


def test_packaged_tree_is_clean(tmp_path):
    """The packaged tree (no corpus-local schema/ at all — this distribution repo's own
    layout) has zero errors. The one standing warning is deliberate: the pdf guidance
    illustrates overlay stubbing with a subclass id no tree is expected to declare."""
    findings = schema_lint.lint_schema(tmp_path)  # tmp_path has no schema/ of its own
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], errors
    warnings = [(f.path, f.token) for f in findings if f.severity == "warning"]
    assert warnings == [
        ("mime/application/application_pdf.yaml", "document/product-manual")
    ], warnings
