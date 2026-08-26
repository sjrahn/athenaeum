"""The YouTube origin overlay — the distribution's one worked example of a per-host
overlay (spec §7.2), rewritten from a fork's `yt_*`-prefixed draft to current law
(`ytdlp_*`, sidecar-as-ground-truth, mechanical structural chapters). Ships two ways:
as this test fixture (`tools/tests/data/origin_youtube.com.yaml`) and as `ath init`'s
worked example (`corpus.scaffold._YOUTUBE_ORIGIN_OVERLAY_YAML`) — kept byte-identical
by `test_fixture_matches_shipped_template` below.
"""

from __future__ import annotations

from pathlib import Path

from corpus import schemas
from corpus._cli import schema_lint

_FIXTURE = Path(__file__).parent / "data" / "origin_youtube.com.yaml"

# The two mime schemas whose `sidecar.ytdlp_keys` declaration the overlay must cover
# (spec §7.1) — one concrete subtype per axis is enough since both axes' common files
# declare the identical key list, and `load_mime_schema` deep-merges the concrete
# subtype over its axis's common file.
_MIME_TYPES = ("video/mp4", "audio/mpeg")


def _root(tmp_path: Path) -> Path:
    """A real scaffolded corpus (`corpus.scaffold.scaffold`, not a hand-built tree) — the
    universal `schema/origin/origin.yaml` (role-marking `ytdlp_title`/`ytdlp_description`)
    has to be present for the merged-overlay assertions below to mean anything, and
    scaffolding also writes `web/youtube.com.yaml` from the SAME template this fixture
    mirrors (`test_fixture_matches_shipped_template` is what keeps that meaningful)."""
    from corpus import scaffold

    root = tmp_path / "c"
    scaffold.scaffold(root)
    schemas.cache_clear()
    return root


# ---------- fixture / template parity ---------- #


def test_fixture_matches_shipped_template():
    """The fixture and `ath init`'s worked example are two literal copies (scaffold.py's
    existing templates are all inline string constants — no package-data read
    mechanism exists to source one from the other), so nothing but this assertion stops
    them drifting apart."""
    from corpus import scaffold

    assert _FIXTURE.read_text(encoding="utf-8") == scaffold._YOUTUBE_ORIGIN_OVERLAY_YAML


# ---------- host matching (spec §7.2 applies_to) ---------- #


def test_resolves_for_every_declared_host_variant(tmp_path):
    """Each host pattern the overlay declares actually matches a representative URL —
    `youtu.be` is a distinct registrable domain (not a subdomain of youtube.com) so it
    needs its own explicit pattern; `m.` / `music.` are subdomains, covered by
    `include_subdomains: true`, but declared explicitly too per the fork's original
    host set."""
    root = _root(tmp_path)
    variants = [
        "https://www.youtube.com/watch?v=RtywqDFBYnQ",
        "https://youtube.com/watch?v=RtywqDFBYnQ",
        "https://youtu.be/RtywqDFBYnQ",
        "https://m.youtube.com/watch?v=RtywqDFBYnQ",
        "https://music.youtube.com/watch?v=RtywqDFBYnQ",
    ]
    for uri in variants:
        ids = schemas.origin_ids_for_uris(root, [uri])
        assert ids == ["youtube.com"], f"{uri} -> {ids}"


def test_resolves_for_an_undeclared_subdomain_via_include_subdomains(tmp_path):
    """`include_subdomains: true` on the `youtube.com` pattern covers ANY subdomain, not
    just the ones enumerated in `host_patterns` — a historical or future subdomain
    (`gaming.youtube.com`) still resolves without an overlay edit."""
    root = _root(tmp_path)
    ids = schemas.origin_ids_for_uris(root, ["https://gaming.youtube.com/watch?v=x"])
    assert ids == ["youtube.com"]


def test_an_unrelated_host_does_not_match(tmp_path):
    root = _root(tmp_path)
    assert schemas.origin_ids_for_uris(root, ["https://vimeo.com/12345"]) == []


# ---------- field coverage (spec §7.1 sidecar.ytdlp_keys) ---------- #


def test_declared_fields_cover_every_packaged_sidecar_key(tmp_path):
    """The whole point of this fixture: every `ytdlp_<key>` the packaged video/audio mime
    schemas' `sidecar.ytdlp_keys` can actually produce must resolve to a DECLARED,
    typed extended field somewhere in the merged overlay — universal `origin/origin.yaml`
    (`ytdlp_title`/`ytdlp_description`, role-marked, host-agnostic) plus this overlay
    (everything else). A key added to the mechanical lift with no matching declaration
    here is exactly the documentation gap this fixture exists to close, so this
    assertion is what stops it re-opening silently."""
    root = _root(tmp_path)
    overlay = schemas.load_origin_overlay_by_id(root, "youtube.com")
    assert overlay is not None
    declared = set((overlay.get("extended_fields") or {}).keys())

    expected: set[str] = {"ytdlp_comments"}  # always-available list field, not a bare key
    for mime in _MIME_TYPES:
        schema = schemas.load_mime_schema(root, mime)
        assert schema is not None, mime
        keys = ((schema.get("sidecar") or {}).get("ytdlp_keys")) or []
        assert keys, f"{mime} declares no sidecar.ytdlp_keys — fixture assumption stale"
        expected |= {f"ytdlp_{k}" for k in keys}

    missing = expected - declared
    assert not missing, f"undeclared ytdlp_* fields: {sorted(missing)}"


def test_video_and_audio_sidecar_key_lists_are_identical(tmp_path):
    """Both axes share one sidecar key list today (schemas_default's own duplication) —
    if that ever forks, `test_declared_fields_cover_every_packaged_sidecar_key` above
    still catches an undeclared field on EITHER axis; this test just documents the
    current fact so a silent fork doesn't go unnoticed. No corpus-local schema/ needed —
    a bare tmp_path with none resolves mime schemas from the packaged tree alone (the
    `scaffold.test_vendor_nothing_...` fallback path)."""
    schemas.cache_clear()
    video = schemas.load_mime_schema(tmp_path, "video/mp4")
    audio = schemas.load_mime_schema(tmp_path, "audio/mpeg")
    assert video is not None and audio is not None
    assert video["sidecar"]["ytdlp_keys"] == audio["sidecar"]["ytdlp_keys"]


def test_title_and_description_are_not_redeclared_on_the_host_overlay(tmp_path):
    """`ytdlp_title`/`ytdlp_description` are host-agnostic and already role-marked on the
    universal `schema/origin/origin.yaml` (every yt-dlp capture gets them, not just
    YouTube's) — redeclaring them here would be a second, driftable source of truth for
    the same two fields. The merged overlay still carries both (through the universal
    layer), but this file's OWN declaration does not repeat them."""
    root = _root(tmp_path)
    own_text = (root / "schema" / "origin" / "web" / "youtube.com.yaml").read_text(
        encoding="utf-8"
    )
    assert "ytdlp_title:" not in own_text
    assert "ytdlp_description:" not in own_text
    # ...yet both resolve through the merged (universal + per-host) overlay:
    overlay = schemas.load_origin_overlay_by_id(root, "youtube.com")
    declared = set((overlay.get("extended_fields") or {}).keys())
    assert {"ytdlp_title", "ytdlp_description"} <= declared


# ---------- schema-lint ---------- #


def test_schema_lint_clean_with_the_overlay_installed(tmp_path):
    """`corpus schema-lint` validates guidance PROSE against declared vocabulary — but its
    scope is `mime`/`atom`/`form`/`context` only (`schema_lint._PROSE_NAMESPACES`); the
    `origin` namespace is per-corpus and deliberately unwalked
    (`schema_lint.py`'s own module docstring / `_PROSE_NAMESPACES` comment). So this
    assertion is necessarily weak today — it can't fail on anything this overlay's own
    guidance says — but it costs nothing to keep, and it starts working for real the day
    origin/ guidance joins the walk."""
    root = _root(tmp_path)
    schemas._sources.cache_clear()
    findings = schema_lint.lint_schema(root)
    errors = [f for f in findings if f.severity == "error"]
    assert errors == []
