"""`shape.form_for_record` — the origin overlay `form:` declaration lookup (spec §7.2).

Covers both the original single-declaration dict form (`{id, mapping?}`) and the 3.2
additive **route-keyed** list form (`[{match?, id, mapping?}, ...]`) for a multi-shape
origin (one host serving several page shapes matched by URI). No ingest/shaping
machinery is needed here — only the origin overlay schema + the record's origin
blocks, which is all `form_for_record` reads."""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import records, schemas
from corpus import shape as shape_pkg


def _corpus(tmp_path: Path, overlays: dict[str, str], name: str = "c") -> Path:
    root = tmp_path / name
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    for schema_id, yaml_text in overlays.items():
        (odir / f"{schema_id}.yaml").write_text(yaml_text, encoding="utf-8")
    schemas.cache_clear()
    return root


def _post(origins: list[tuple[str, str | list[str] | None]]) -> frontmatter.Post:
    """A bare post carrying one `<!--origin <id>-->` block per `(schema_id, uri)` entry,
    in order — no ingest needed, `form_for_record` only reads the origin blocks."""
    post = frontmatter.Post("")
    for schema_id, uri in origins:
        records.append_origin_block(
            post, uri=uri, snapshot="2026-01-01T00:00:00Z", schema_id=schema_id
        )
    return post


_DICT_OVERLAY = """\
applies_to:
  schemes: [dicttest]
kind: interpretive
form:
  id: conversation
  mapping:
    messages: messages
"""

def test_dict_form_unchanged(tmp_path):
    """Regression: the original `form: {id, mapping}` declaration still resolves."""
    root = _corpus(tmp_path, {"conv-export": _DICT_OVERLAY})
    post = _post([("conv-export", "convexport://chat/1")])
    assert shape_pkg.form_for_record(post, root) == (
        "conv-export",
        "conversation",
        {"messages": "messages"},
    )


def test_route_list_first_match_wins(tmp_path):
    """Two overlapping rules both match the URI; the first in declaration order wins."""
    overlay = """\
applies_to:
  schemes: [routetest]
kind: interpretive
form:
  - match: 'widget'
    id: rule-a
  - match: 'wid'
    id: rule-b
"""
    root = _corpus(tmp_path, {"route-host": overlay})
    post = _post([("route-host", "routetest://site/widget-42")])
    assert shape_pkg.form_for_record(post, root) == ("route-host", "rule-a", {})


def test_route_list_matches_primary_uri_only(tmp_path):
    """The block's `uri:` is a list; a rule is tested against the PRIMARY (first) uri
    ONLY — dedup-folded aliases are not gate-grade route evidence (§7.2, narrowed
    2026-07-17: the form-adopt-32 execution measured a SPA whose single-result category
    collapse pollutes aliases in both directions)."""
    overlay = """\
applies_to:
  schemes: [routetest]
kind: interpretive
form:
  - match: 'special-page'
    id: special
    mapping:
      k: v
"""
    root = _corpus(tmp_path, {"route-host": overlay})

    # The rule's pattern appears only in an ALIAS uri: no match, no declaration.
    post = _post(
        [
            (
                "route-host",
                ["routetest://site/normal-page", "routetest://site/special-page"],
            )
        ]
    )
    assert shape_pkg.form_for_record(post, root) is None

    # The same pattern in the PRIMARY uri declares, aliases notwithstanding.
    post2 = _post(
        [
            (
                "route-host",
                ["routetest://site/special-page", "routetest://site/normal-page"],
            )
        ]
    )
    assert shape_pkg.form_for_record(post2, root) == ("route-host", "special", {"k": "v"})


def test_route_list_no_match_falls_through_to_next_origin_dict_form(tmp_path):
    """No rule matches the first (list-form) origin block — the walk continues to the
    record's next qualified origin block, which declares the plain dict form."""
    list_overlay = """\
applies_to:
  schemes: [routetest]
kind: interpretive
form:
  - match: 'procedure'
    id: procedure
"""
    root = _corpus(
        tmp_path, {"route-host": list_overlay, "conv-export": _DICT_OVERLAY}
    )
    post = _post(
        [
            ("route-host", "routetest://site/unmatched-page"),
            ("conv-export", "convexport://chat/1"),
        ]
    )
    assert shape_pkg.form_for_record(post, root) == (
        "conv-export",
        "conversation",
        {"messages": "messages"},
    )


def test_route_list_no_match_anywhere_returns_none(tmp_path):
    """No rule matches, and there is no further origin block to fall through to."""
    overlay = """\
applies_to:
  schemes: [routetest]
kind: interpretive
form:
  - match: 'procedure'
    id: procedure
  - match: 'bulletin'
    id: bulletin
"""
    root = _corpus(tmp_path, {"route-host": overlay})
    post = _post([("route-host", "routetest://site/index-page")])
    assert shape_pkg.form_for_record(post, root) is None


def test_route_list_fallback_rule_without_match(tmp_path):
    """A rule without a `match` key is a terminal fallback: it matches everything not
    already caught by an earlier, more specific rule."""
    overlay = """\
applies_to:
  schemes: [routetest]
kind: interpretive
form:
  - match: 'procedure'
    id: procedure
  - id: index
"""
    root = _corpus(tmp_path, {"route-host": overlay})
    post = _post([("route-host", "routetest://site/whatever-else")])
    assert shape_pkg.form_for_record(post, root) == ("route-host", "index", {})

    # The specific rule still wins over the fallback when it matches.
    post2 = _post([("route-host", "routetest://site/procedure-7")])
    assert shape_pkg.form_for_record(post2, root) == ("route-host", "procedure", {})


def test_route_list_tolerates_rule_missing_id_and_non_list_dict_form(tmp_path):
    """A rule missing `id` is skipped (parsed tolerantly, never raised); a `form:` value
    that is neither dict nor list is ignored, treated as absent."""
    overlay = """\
applies_to:
  schemes: [routetest]
kind: interpretive
form:
  - match: 'special'
    mapping:
      broken: true
  - match: 'special'
    id: recovered
"""
    root = _corpus(tmp_path, {"route-host": overlay})
    post = _post([("route-host", "routetest://site/special-thing")])
    # The id-less rule is skipped; the next matching rule with an id is the declaration.
    assert shape_pkg.form_for_record(post, root) == ("route-host", "recovered", {})

    # A malformed `form:` scalar (neither dict nor list) is ignored — falls through to
    # the next origin block, or None with no further block.
    scalar_overlay = (
        "applies_to:\n  schemes: [routetest]\nkind: interpretive\n"
        "form: not-a-dict-or-list\n"
    )
    root2 = _corpus(tmp_path, {"route-host": scalar_overlay}, name="c2")
    post2 = _post([("route-host", "routetest://site/anything")])
    assert shape_pkg.form_for_record(post2, root2) is None
