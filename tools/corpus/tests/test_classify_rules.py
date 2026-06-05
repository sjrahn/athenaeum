"""Deterministic auto-classification engine (`corpus.classify_rules`).

Pure units for the fact base, the operator grammar (incl. the missing-fact-⇒-false rule and
list-valued any-element semantics), and `matching_classes` / `apply_auto_classifications`
against a tmp corpus carrying a `source/majority-report` overlay with a `classify_when`.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import classify_rules as cr
from corpus import records

CHANNEL = "UC-3jIAlnQmbbVMV6gR7K8aQ"

# A source namespace base + a subclass keyed on (mime, channel id) — the real MR driver.
_BASE = "kind: interpretive\ndescription: src.\napplies_at: [record]\nextended_fields: {}\n"
_MR = (
    "kind: interpretive\n"
    "description: The Majority Report livestream.\n"
    "applies_at: [record]\n"
    "classify_when:\n"
    "  all_of:\n"
    "    - mime: {equals: video/mp4}\n"
    f"    - media.channel_id: {{equals: {CHANNEL}}}\n"
)


def _corpus(tmp_path: Path, *, with_rule: bool = True) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    src = root / "schema" / "composite" / "source"
    src.mkdir(parents=True)
    (src / "source.yaml").write_text(_BASE, encoding="utf-8")
    body = _MR if with_rule else "kind: interpretive\ndescription: x\napplies_at: [record]\n"
    (src / "majority-report.yaml").write_text(body, encoding="utf-8")
    return root


def _video(channel: str = CHANNEL, *, mime: str = "video/mp4", **extra) -> frontmatter.Post:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id="aa" * 32, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime=mime)
    records.append_origin_block(
        post, uri="https://www.youtube.com/watch?v=abcd", snapshot="2026-06-05T00:00:00Z"
    )
    fields = {"ytdlp_channel_id": channel, **extra}
    records.merge_origin_fields(post, fields)
    return post


# ---------- build_facts ---------- #


def test_build_facts_mime_origin_media(tmp_path):
    facts = cr.build_facts(tmp_path, _video(ytdlp_tags=["politics", "news"]))
    assert facts["mime"] == ["video/mp4"]
    assert facts["origin.host"] == ["www.youtube.com"]
    assert facts["origin.path"] == ["/watch"]
    assert facts["origin.query.v"] == ["abcd"]
    assert facts["media.channel_id"] == [CHANNEL]
    assert facts["media.tags"] == ["politics", "news"]  # list value flattened, any-element


def test_build_facts_any_origin_lists(tmp_path):
    post = _video()
    records.append_origin_block(
        post, uri="https://m.youtube.com/watch?v=z", snapshot="2026-06-05T00:00:00Z"
    )
    facts = cr.build_facts(tmp_path, post)
    assert set(facts["origin.host"]) == {"www.youtube.com", "m.youtube.com"}


def test_build_facts_fragment_for_spa_route(tmp_path):
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id="bb" * 32, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html")
    records.append_origin_block(
        post,
        uri="https://my.alldata.com/repair#/vehicle/1/diagram/42",
        snapshot="2026-06-05T00:00:00Z",
    )
    facts = cr.build_facts(tmp_path, post)
    assert facts["origin.fragment"] == ["/vehicle/1/diagram/42"]


# ---------- evaluate: operators ---------- #


def _facts():
    return {"mime": ["video/mp4"], "media.channel_id": [CHANNEL], "media.tags": ["a", "b"]}


def test_equals_and_all_of():
    assert cr.evaluate({"mime": {"equals": "video/mp4"}}, _facts())
    assert not cr.evaluate({"mime": {"equals": "image/png"}}, _facts())
    assert cr.evaluate(
        {"all_of": [{"mime": {"equals": "video/mp4"}}, {"media.channel_id": {"equals": CHANNEL}}]},
        _facts(),
    )


def test_in_glob_matches():
    assert cr.evaluate({"mime": {"in": ["audio/mpeg", "video/mp4"]}}, _facts())
    assert cr.evaluate({"media.channel_id": {"glob": "UC-*"}}, _facts())
    assert cr.evaluate({"media.channel_id": {"matches": "UC-[A-Za-z0-9]+"}}, _facts())
    assert not cr.evaluate({"media.channel_id": {"matches": "UC-[0-9]+"}}, _facts())  # anchored


def test_list_valued_any_element():
    assert cr.evaluate({"media.tags": {"equals": "b"}}, _facts())  # any element
    assert cr.evaluate({"media.tags": {"in": ["x", "a"]}}, _facts())
    assert cr.evaluate({"media.tags": {"exists": True}}, _facts())


def test_any_of_and_none_of():
    any_pred = {"any_of": [{"mime": {"equals": "x"}}, {"mime": {"equals": "video/mp4"}}]}
    assert cr.evaluate(any_pred, _facts())
    assert cr.evaluate({"none_of": [{"mime": {"equals": "image/png"}}]}, _facts())
    assert not cr.evaluate({"none_of": [{"mime": {"equals": "video/mp4"}}]}, _facts())


def test_missing_fact_is_false():
    # The core no-false-positive guarantee: an absent fact fails every op but `exists: false`.
    assert not cr.evaluate({"media.channel_id": {"equals": "x"}}, {"mime": ["text/html"]})
    assert not cr.evaluate({"media.channel_id": {"exists": True}}, {"mime": ["text/html"]})
    assert cr.evaluate({"media.channel_id": {"exists": False}}, {"mime": ["text/html"]})


def test_evaluate_fails_closed():
    assert not cr.evaluate({}, _facts())
    assert not cr.evaluate("nonsense", _facts())
    assert not cr.evaluate({"mime": {"unknown_op": "x"}}, _facts())


# ---------- matching_classes + apply ---------- #


def test_matching_classes_selects_exactly_the_match(tmp_path):
    root = _corpus(tmp_path)
    assert [m.class_id for m in cr.matching_classes(root, _video())] == ["source/majority-report"]
    # A different channel matches nothing.
    assert cr.matching_classes(root, _video(channel="UC-other")) == []
    # No rule on the overlay ⇒ no match (pure opt-in).
    root2 = _corpus(tmp_path / "x", with_rule=False)
    assert cr.matching_classes(root2, _video()) == []


def test_apply_is_idempotent_and_preserves_asserted(tmp_path):
    root = _corpus(tmp_path)
    post = _video()
    # A hand-asserted block must survive strip+regen.
    records.append_classify_block(post, namespace="document", id="document", fields={})

    d1 = cr.apply_auto_classifications(root, post)
    assert d1.added == ["source/majority-report"] and d1.removed == []
    assert "source/majority-report" in records.derived_classifications(post)
    assert "document" in records.derived_classifications(post)  # asserted preserved
    # Auto block precedes the asserted one (draft-time ordering, §4.3.1.3).
    blocks = list(records.iter_classify_blocks(post))
    assert blocks[0]["fields"].get("provenance") == "auto"

    # Running again is a fixpoint: no net change.
    d2 = cr.apply_auto_classifications(root, post)
    assert d2.changed is False and d2.kept == ["source/majority-report"]


def test_apply_removes_stale_auto_when_rule_drops(tmp_path):
    root = _corpus(tmp_path)
    post = _video()
    cr.apply_auto_classifications(root, post)
    assert cr.auto_class_ids(post) == ["source/majority-report"]

    # Overlay loses its rule → the auto block is stripped, not kept.
    (root / "schema" / "composite" / "source" / "majority-report.yaml").write_text(
        "kind: interpretive\ndescription: x\napplies_at: [record]\n", encoding="utf-8"
    )
    from corpus import schemas

    schemas.load_classification_schema.cache_clear()
    delta = cr.apply_auto_classifications(root, post)
    assert delta.removed == ["source/majority-report"] and delta.added == []
    assert cr.auto_class_ids(post) == []
