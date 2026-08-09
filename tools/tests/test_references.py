"""Overlay-declared dependent references (spec §7.2 `capture.references`, §8.1).

Pure-function units for the rule parser + DOM matcher, plus integration over a tmp corpus
+ origin overlay (no browser/network): `corpus links --references` and the depth-1
auto-grab (`fetch_references` / `corpus capture --with-references` / `corpus crawl
--references`) with `capture_and_ingest` faked. Opt-in is proven by the with-/without-rules
contrast. The declaration is purely a capture instruction (#157, ruling 2026-08-09): the
record-side emission retired with the `reference` context namespace (3.5 §4.3.3.3), and
the writer left the codebase with it.
"""

from __future__ import annotations

from pathlib import Path

import blake3
import frontmatter

from corpus import paths, records, references
from corpus._cli import capture as capture_cli
from corpus._cli import dispatch
from corpus._cli import draft as draft_cli
from corpus.store import LocalArtifactStore

HOST = "shop.test"
BASE = f"https://{HOST}/product/123"
MANUAL = "https://cdn.other.test/manual-123.pdf"
SPEC = "https://cdn.other.test/spec-123.pdf"

PDP_HTML = (
    "<html><body>"
    '<div id="details">'
    f'<a href="{MANUAL}">Product Manual (PDF)</a>'
    '<a href="/related/widget">Related widget</a>'
    "</div>"
    f'<a href="{SPEC}">Spec Sheet (PDF)</a>'
    '<a href="#top">back to top</a>'
    '<a href="mailto:sales@shop.test">email us</a>'
    "</body></html>"
)

# Two rules: a manual grabbed alongside (capture:true), a spec sheet annotate-only.
OVERLAY = (
    f"applies_to: {{host_pattern: {HOST}}}\n"
    "capture:\n"
    "  references:\n"
    "    - match: {selector: '#details a[href$=\".pdf\"]'}\n"
    "      role: manual\n"
    "      capture: true\n"
    "    - match: {text_pattern: '(?i)spec', href_pattern: '\\.pdf'}\n"
    "      role: spec-sheet\n"
)

ID_PDP = "a1" * 32
ID_MANUAL = "b2" * 32


# ---------- fixtures ---------- #


def _corpus(tmp_path: Path, *, overlay: str | None = None, name: str = "c") -> Path:
    root = tmp_path / name
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    if overlay is not None:
        d = root / "schema" / "origin" / "web"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{HOST}.yaml").write_text(overlay, encoding="utf-8")
    return root


def _html_record(root: Path, rid: str, uri, html: str) -> frontmatter.Post:
    """A stub HTML record with its artifact in the store (draftable + readable)."""
    src = root / f"_src_{rid[:8]}.html"
    src.write_text(html, encoding="utf-8")
    LocalArtifactStore(root).put(rid, "html", src)
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri=uri, snapshot="2026-06-04T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))
    return post


def _fake_id(url: str) -> str:
    return blake3.blake3(url.encode("utf-8")).hexdigest()


def _fake_capturer(record_html: str = "<html></html>"):
    """A `capture_and_ingest` stand-in: materializes a record for the URL (so a later
    `find_by_uri` resolves it) and records the call. Returns `(fn, calls)`."""
    calls: list[str] = []

    def fake(url, *, corpus_root, opts=None):
        calls.append(url)
        rid = _fake_id(url)
        _html_record(corpus_root, rid, url, record_html)
        return paths.record_path(corpus_root, rid)

    return fake, calls


# ---------- pure units: parse_rules ---------- #


def test_parse_rules_list_and_flat_forms():
    rules = references.parse_rules(
        [
            {"match": {"selector": "#a a"}, "role": "manual", "capture": True},
            {"href_pattern": r"\.pdf$", "role": "spec"},  # flat (no `match:` wrapper)
        ]
    )
    assert len(rules) == 2
    assert rules[0].selector == "#a a" and rules[0].role == "manual" and rules[0].capture
    assert rules[1].href_pattern == r"\.pdf$" and rules[1].capture is False


def test_parse_rules_tolerant():
    rules = references.parse_rules(
        [
            "not-a-dict",
            {"role": "x"},  # no match key → skipped
            {"selector": "a", "cross_host": "weird"},  # bad cross_host → default allow
        ]
    )
    assert len(rules) == 1
    assert rules[0].selector == "a" and rules[0].cross_host == "allow"


def test_parse_rules_non_list_is_empty():
    assert references.parse_rules(None) == []
    assert references.parse_rules({"selector": "a"}) == []
    assert references.parse_rules("garbage") == []


# ---------- pure units: match ---------- #


def test_match_selector_and_dedup():
    rules = references.parse_rules([{"selector": '#details a[href$=".pdf"]', "role": "manual"}])
    out = references.match(PDP_HTML, BASE, rules)
    assert [m.url for m in out] == [MANUAL]
    assert out[0].role == "manual"


def test_match_and_within_rule():
    # text_pattern AND href_pattern must both hold.
    rules = references.parse_rules([{"text_pattern": "(?i)spec", "href_pattern": r"\.pdf"}])
    out = references.match(PDP_HTML, BASE, rules)
    assert [m.url for m in out] == [SPEC]
    # a text match whose href fails the pattern yields nothing
    mismatch = references.parse_rules([{"text_pattern": "(?i)spec", "href_pattern": r"\.zip"}])
    assert references.match(PDP_HTML, BASE, mismatch) == []


def test_match_or_across_rules_and_dedup():
    rules = references.parse_rules(
        [
            {"selector": '#details a[href$=".pdf"]', "role": "manual"},
            {"text_pattern": "(?i)spec", "role": "spec"},
            {"selector": "a"},  # would re-match both — deduped, first role wins
        ]
    )
    out = references.match(PDP_HTML, BASE, rules)
    urls_ = [m.url for m in out]
    assert MANUAL in urls_ and SPEC in urls_
    assert urls_.count(MANUAL) == 1  # deduped
    roles = {m.url: m.role for m in out}
    assert roles[MANUAL] == "manual" and roles[SPEC] == "spec"  # first rule wins


def test_match_drops_non_crawlable_and_resolves_relative():
    rules = references.parse_rules([{"selector": "a"}])
    out = references.match(PDP_HTML, BASE, rules)
    urls_ = [m.url for m in out]
    assert "mailto:sales@shop.test" not in urls_
    assert not any(u.endswith("#top") for u in urls_)
    assert "https://shop.test/related/widget" in urls_  # relative resolved against base


def test_match_cross_host_same_drops_offhost():
    rules = references.parse_rules([{"selector": "a", "cross_host": "same"}])
    out = references.match(PDP_HTML, BASE, rules, primary_host=HOST)
    urls_ = [m.url for m in out]
    assert MANUAL not in urls_ and SPEC not in urls_  # off-host cdn dropped
    assert "https://shop.test/related/widget" in urls_


def test_match_rel_token():
    html = '<html><body><a href="https://x.test/a.pdf" rel="nofollow noopener">a</a></body></html>'
    hit = references.match(html, "https://x.test/", references.parse_rules([{"rel": "nofollow"}]))
    assert [m.url for m in hit] == ["https://x.test/a.pdf"]
    miss = references.match(html, "https://x.test/", references.parse_rules([{"rel": "sponsored"}]))
    assert miss == []


def test_match_bad_selector_and_regex_skipped():
    assert references.match(PDP_HTML, BASE, references.parse_rules([{"selector": "a[", }])) == []
    assert references.match(PDP_HTML, BASE, references.parse_rules([{"href_pattern": "("}])) == []


# ---------- select_for_capture ---------- #


def test_select_for_capture_force_modes():
    matches = references.match(
        PDP_HTML, BASE,
        references.parse_rules(
            [
                {"selector": '#details a[href$=".pdf"]', "capture": True},
                {"text_pattern": "(?i)spec"},
            ]
        ),
    )
    assert {m.url for m in references.select_for_capture(matches, force=True)} == {MANUAL, SPEC}
    assert references.select_for_capture(matches, force=False) == []
    assert [m.url for m in references.select_for_capture(matches, force=None)] == [MANUAL]


# ---------- integration: rules_for_url + matches_for_record ---------- #


def test_rules_for_url_reads_overlay(tmp_path):
    root = _corpus(tmp_path, overlay=OVERLAY)
    rules = references.rules_for_url(root, BASE)
    assert len(rules) == 2
    assert rules[0].role == "manual" and rules[0].capture is True
    # a host with no overlay → no rules
    assert references.rules_for_url(root, "https://nope.test/x") == []


def test_matches_for_record_excludes_self_links(tmp_path):
    root = _corpus(
        tmp_path,
        overlay=(
            f"applies_to: {{host_pattern: {HOST}}}\n"
            "capture:\n"
            "  references:\n"
            "    - match: {selector: 'a'}\n"
        ),
    )
    self_html = (
        f'<html><body><a href="{BASE}">self</a>'
        f'<a href="{MANUAL}">manual</a></body></html>'
    )
    post = _html_record(root, ID_PDP, BASE, self_html)
    out = references.matches_for_record(root, post, self_html)
    urls_ = [m.url for m in out]
    assert MANUAL in urls_ and BASE not in urls_  # own origin excluded


# ---------- integration: the retired draft core no longer emits ---------- #


def test_derive_record_no_longer_emits_references(tmp_path):
    """ATH-CORPUS 3.12 reconciliation (#153) + the #157 ruling (2026-08-09): a full draft
    of a rules-carrying record emits NO `reference` context blocks — the namespace retired
    at 3.5 (§4.3.3.3), the draft core's call site left with #153, and the writer itself
    (`emit_overlay_references`) left with #157. The declaration is purely a capture
    instruction (spec §8.1); the declare/match/fetch machinery is what remains."""
    root = _corpus(tmp_path, overlay=OVERLAY)
    post = _html_record(root, ID_PDP, BASE, PDP_HTML)
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, ID_PDP))
    reloaded = records.load(paths.record_path(root, ID_PDP))
    assert list(records.iter_reference_blocks(reloaded)) == []


# ---------- corpus links --references ---------- #


def test_links_references_cli(tmp_path, capsys):
    root = _corpus(tmp_path, overlay=OVERLAY)
    _html_record(root, ID_PDP, BASE, PDP_HTML)
    rc = dispatch(["links", ID_PDP, "--references", "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert f"{MANUAL}  [role=manual, pending, auto]" in out
    assert f"{SPEC}  [role=spec-sheet, pending]" in out


def test_links_references_marks_captured(tmp_path, capsys):
    root = _corpus(tmp_path, overlay=OVERLAY)
    _html_record(root, ID_MANUAL, MANUAL, "<html></html>")  # manual already captured
    _html_record(root, ID_PDP, BASE, PDP_HTML)
    dispatch(["links", ID_PDP, "--references", "--corpus-root", str(root)])
    out = capsys.readouterr().out
    assert f"{MANUAL}  [role=manual, captured, auto]" in out


# ---------- depth-1 auto-grab: fetch_references ---------- #


def test_fetch_references_honors_per_rule_capture(tmp_path, monkeypatch):
    root = _corpus(tmp_path, overlay=OVERLAY)
    post = _html_record(root, ID_PDP, BASE, PDP_HTML)
    fake, calls = _fake_capturer()
    monkeypatch.setattr("corpus.capture.capture_and_ingest", fake)
    res = references.fetch_references(root, post, PDP_HTML, force=None)
    assert calls == [MANUAL]  # only capture:true rule fetched
    assert [u for u, _ in res.captured] == [MANUAL]


def test_fetch_references_force_all_and_dedup(tmp_path, monkeypatch):
    root = _corpus(tmp_path, overlay=OVERLAY)
    _html_record(root, ID_MANUAL, MANUAL, "<html></html>")  # already present → not refetched
    post = _html_record(root, ID_PDP, BASE, PDP_HTML)
    fake, calls = _fake_capturer()
    monkeypatch.setattr("corpus.capture.capture_and_ingest", fake)
    res = references.fetch_references(root, post, PDP_HTML, force=True)
    assert calls == [SPEC]  # manual deduped, only spec fetched
    assert MANUAL in res.existing
    assert [u for u, _ in res.captured] == [SPEC]


def test_fetch_references_dry_run_fetches_nothing(tmp_path, monkeypatch):
    root = _corpus(tmp_path, overlay=OVERLAY)
    post = _html_record(root, ID_PDP, BASE, PDP_HTML)
    fake, calls = _fake_capturer()
    monkeypatch.setattr("corpus.capture.capture_and_ingest", fake)
    res = references.fetch_references(root, post, PDP_HTML, force=True, dry_run=True)
    assert calls == []
    assert set(res.selected) == {MANUAL, SPEC}


# ---------- capture --with-references (CLI helper) + crawl --references ---------- #


def test_capture_with_references_helper(tmp_path, monkeypatch):
    root = _corpus(tmp_path, overlay=OVERLAY)
    _html_record(root, ID_PDP, BASE, PDP_HTML)
    fake, calls = _fake_capturer()
    monkeypatch.setattr("corpus.capture.capture_and_ingest", fake)

    class _A:
        with_references = True  # force: grab all declared
        no_references = False

    capture_cli._maybe_grab_references(_A(), root, paths.record_path(root, ID_PDP), opts=None)
    assert set(calls) == {MANUAL, SPEC}
    assert records.find_by_uri(MANUAL, corpus_root=root) == _fake_id(MANUAL)


def test_capture_no_references_suppresses(tmp_path, monkeypatch):
    root = _corpus(tmp_path, overlay=OVERLAY)
    _html_record(root, ID_PDP, BASE, PDP_HTML)
    fake, calls = _fake_capturer()
    monkeypatch.setattr("corpus.capture.capture_and_ingest", fake)

    class _A:
        with_references = False
        no_references = True

    capture_cli._maybe_grab_references(_A(), root, paths.record_path(root, ID_PDP), opts=None)
    assert calls == []


def test_crawl_references_dry_run_lists_pending(tmp_path, capsys):
    root = _corpus(tmp_path, overlay=OVERLAY)
    _html_record(root, ID_PDP, BASE, PDP_HTML)
    rc = dispatch(["crawl", "--references", "--dry-run", "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert MANUAL in out and SPEC in out


def test_crawl_references_sweep_captures(tmp_path, monkeypatch):
    root = _corpus(tmp_path, overlay=OVERLAY)
    _html_record(root, ID_PDP, BASE, PDP_HTML)
    fake, calls = _fake_capturer()
    monkeypatch.setattr("corpus.capture.capture_and_ingest", fake)
    rc = dispatch(["crawl", "--references", "--corpus-root", str(root)])
    assert rc == 0
    assert set(calls) == {MANUAL, SPEC}  # all declared, both pending → fetched
    assert records.find_by_uri(SPEC, corpus_root=root) == _fake_id(SPEC)
