"""Scaffolding — `corpus init` materializes the minimal corpus seam.

A new corpus repo contains `records/` + `schema/origin/origin.yaml` +
`schema/context/<ns>/` (plus the untracked `artifacts/` `capture/` `cache/`
`export/`). Universal `mime` and `atom` schemas come from the package's bundled
defaults; `origin` and `composite` are **per-corpus concerns** (sources of
retrieval and classification axes are corpus-specific decisions) so the scaffold
seeds the universal origin overlay locally.

This module exports:
- `scaffold(target, *, force=False)` — create the tree.
"""

from __future__ import annotations

from pathlib import Path

_GITIGNORE = """\
# Untracked corpus state — regenerable from records/ + schema/. Root-anchored
# (leading /) so the `capture/` staging dir is ignored without also ignoring any
# same-named tracked dir nested elsewhere under schema/.
/artifacts/
/capture/
/cache/
/queue/
/export/

# Editor / OS scratch
.DS_Store
*.swp
"""

_UNIVERSAL_ORIGIN_YAML = """\
# Universal origin-block fields — applied to every <!--origin--> block, regardless of
# whether the opener names a specific origin schema. Bare `<!--origin-->` uses just
# these fields; qualified forms (`<!--origin <id>-->`) layer additional fields from
# per-id yamls under a URI-scheme-family sub-namespace — web (http/https) sources
# live at `schema/origin/web/<host>.yaml`.
#
# Origin is a per-corpus concern (sources of retrieval are corpus-specific), so this
# file is corpus-local — the `athenaeum` package does NOT bundle a universal origin.
# Extend or constrain as your corpus requires.
#
# See spec/corpus.md §7.2.

description: |
  Universal fields every origin block carries.

extended_fields:
  uri:
    type: string_or_list
    required: false
    semantic_type: uri
    description: |
      One or more URIs from which the artifact's bytes are retrievable for this
      origin. String when there's one URI; YAML list when canonical + shortlinks +
      post-redirect final URLs collapse to a single logical origin. Aggregated into
      the `uris` derived view (§9.3). Present for a RETRIEVAL origin (web capture,
      synthetic scheme like imessage://); OMITTED for a dropped-in local file — the
      staging path is unlinked at ingest, so there is nothing to re-fetch. Such an
      origin carries `filename`/`source_modified` instead. Spec §7.2.
  snapshot:
    type: string
    required: true
    semantic_type: timestamp
    description: |
      ISO-8601 timestamp of when this origin was observed. For an origin block
      emitted at ingest, this is the capture timestamp; for re-captures, the most
      recent observation. Aggregated into the `timeline` derived view (§9.4).
  filename:
    type: string
    required: false
    description: |
      Basename of a dropped-in local-file source (a bare `corpus ingest` with no
      capture sidecar). The durable identity a `file://` staging path could not
      provide. Absent for retrieval origins. Spec §7.2.
  source_modified:
    type: string
    required: false
    semantic_type: timestamp
    description: |
      ISO-8601 mtime of a dropped-in local-file source at ingest — typically when
      the file was authored / scanned / exported. The keeper provenance for a local
      file (the staging path is ephemeral). Aggregated into the `timeline` derived
      view (§9.4). Absent for retrieval origins. Spec §7.2.
  # (3.2) Host-agnostic yt-dlp sidecar lift (spec §7.2, §7.1 `sidecar.ytdlp_keys`): every
  # mime schema whose artifact carries a yt-dlp `.info.json` enrichment (audio/video)
  # declares the same `ytdlp_title`/`ytdlp_description` keys, so the mark belongs on THIS
  # universal overlay rather than any one per-host file — it reaches every qualified origin
  # block through the loader's universal-then-per-id layering, e.g. `<!--origin youtube.com-->`.
  # `ytdlp_title` is the canonical §4.2.3 example: a video record derives an honest display
  # title from its sidecar lift alone, no LLM pass needed.
  ytdlp_title:
    type: string
    required: false
    role: title
    description: |
      The source post's title, lifted from the yt-dlp `.info.json` sidecar at ingest
      (spec §7.1 `sidecar.ytdlp_keys`, §7.2). Present only on origin blocks whose artifact
      mime schema declares the sidecar lift and whose capture actually carried one.
  ytdlp_description:
    type: string
    required: false
    role: description
    description: |
      The source post's own description text, lifted from the yt-dlp `.info.json` sidecar
      at ingest (spec §7.1 `sidecar.ytdlp_keys`, §7.2). Same presence condition as
      `ytdlp_title` above.
"""

_README_TEMPLATE = """\
# {name}

The corpus layer of an Athenaeum instance (spec/corpus.md, Part II) — content-addressed
records under `records/`, origin overlays under `schema/origin/`, annotation overlays under
`schema/context/<namespace>/`. Universal `mime` / `atom` / `context/issue` schemas resolve
from the Athenaeum distribution's bundled defaults (the `ath`/`corpus` CLIs, installed from
the distribution with `uv tool install --editable tools/`, find this instance by walking up
for `athenaeum.yaml`); `origin` and `context` are per-corpus concerns so they live here.

## Layout

```
{name}/
├── records/              # TRACKED — record markdown files (sharded by id[:2])
├── schema/
│   ├── origin/          # Origin overlays, namespaced by URI scheme family
│   │   ├── origin.yaml   # Universal origin fields (uri/snapshot) — corpus owns this
│   │   └── web/          # http(s) sources, keyed by host (urn/file/s3 get their own subns)
│   │       └── <host>.yaml   # Per-host: origin fields + optional `capture:` config
│   └── context/          # THIS corpus's annotation overlays (issue/reference/relation ids)
├── artifacts/            # UNTRACKED — binary store
├── capture/              # UNTRACKED — capture staging
├── cache/                # UNTRACKED — resolver output cache
├── queue/                # UNTRACKED — normalization request/claim state
└── export/               # UNTRACKED — portable export bundles
```

## Common commands

```bash
corpus find             # list records
corpus show <hash>      # record summary
corpus lint <hash>      # conformance check
corpus diagnose <hash>  # snapshot + quick-lint one-pager
```

See the Athenaeum distribution's spec/ and README for the full surface.
"""

_EXAMPLE_ORIGIN_OVERLAY_YAML = """\
# Example per-host origin overlay. Copy to schema/origin/web/<host>.yaml, uncomment, and
# edit. (Origin overlays are namespaced by URI scheme family; http(s) sources live under
# web/.) Matched against an origin's host (apex<->www aware); corpus-local first. One
# host-keyed file carries BOTH the origin-block field overlays (extended_fields, for
# record validation) AND, optionally, a `capture:` section (read only at capture time)
# describing how to fetch this source.
#
# applies_to:
#   host_pattern: example.com        # or host_patterns: [a, b]; "*" = catch-all
#   include_subdomains: true
#
# # Origin-block extended fields beyond the universal uri:/snapshot:, if this source
# # needs any. Validated on every <!--origin--> block for matching records.
# extended_fields: {}
#
# # Capture-time behavior. Two jobs: (1) surface ALL displayable media (lazy-load,
# # carousels, tabs, accordions) before the self-contained snapshot, and (2) REMOVE
# # page chrome (nav/header/footer/ads/cookie notices). The HTML drafter is purely
# # mechanical -- it never guesses what is chrome, so removing it is a per-host decision
# # made HERE, where the site's real structure is known. Absent a recipe, the browser
# # capturer's defaults apply (headless + scroll/expand, no removal). Global defaults can
# # go on the universal origin.yaml `capture:`; per-host `capture:` here overrides.
# capture:
#   capturer: browser                # packaged (browser | video) or a corpus-local name
#   transport: headless              # headless | headed | cdp  (headed/cdp need a display
#                                    # or a running Chrome -- see `corpus capture --transport`)
#   fidelity: balanced               # exact | balanced | lean SingleFile snapshot tier.
#                                    # exact = byte-faithful (presentation IS content); balanced
#                                    # (default) drops redundant font/image/media alternates
#                                    # (~-76%); lean also prunes unused CSS (~-91%, info-faithful).
#                                    # Records are identical across tiers; only artifacts shrink.
#   interactions:
#     - scroll: full                   # hydrate lazy-loaded / below-the-fold media
#     - click: {selector: "button[aria-label='Next']", repeat: 12, delay_ms: 500}
#     - expand: all                    # open <details> + aria-expanded accordions/tabs
#     - remove: ['#header', 'footer', 'nav', '.cookie-banner', '.related', '#ad']
#                                      # delete chrome so it isn't inlined/embedded or
#                                      # leaked into the drafter's text segment
#     # `eval` is the escape hatch for site-specific JS. Two common high-fidelity uses:
#     #  (a) fetch+inject an AJAX-on-click tab/panel (same-origin fetch -> innerHTML).
#     #  (b) promote a click-to-zoom HIGH-RES image into `src` so it gets inlined+embedded
#     #      -- for data-* zoom URLs SingleFile doesn't inline (WooCommerce
#     #      data-large_image, magic/cloud-zoom data-zoom-image, etc.). A plain higher-res
#     #      `srcset` is already embedded automatically by the drafter; this is only for
#     #      the data-* case.
#     - eval: |
#         document.querySelectorAll('img[data-large_image], img[data-zoom-image]')
#           .forEach((i) => i.setAttribute('src',
#             i.getAttribute('data-large_image') || i.getAttribute('data-zoom-image')));
#   viewport: 1280x900
#   # --- paginated works (thread / multi-page article / gallery) ---  Walk the ?page=N /
#   # /page-N pages, MERGE them, and ingest ONE content-addressed record (not page-1-only,
#   # not N fragments). Bare `true` auto-detects everything: follow <link/a rel=next> and
#   # structurally diff page 1 vs page 2 to find the content region. A map gives control:
#   pagination: true
#   # pagination:
#   #   content_selector: '.js-replyNewMessageContainer'  # the per-page content region
#   #   next: {rel: true, selector: 'a.pageNav-jump--next'}  # rel=next default; CSS override
#   #   max_pages: 100                                     # safety cap (flags if hit)
#   #   expect_count: {selector: '.pairs dd'}             # advertised count -> completeness check
#   # Pairs naturally with url_rewrite to pin one render form across every page (e.g. a flat
#   # view). Constituent page URLs are recorded as origin aliases; only the merged artifact
#   # is content-addressed.
#   # --- url_equivalent (IDENTITY only, never changes the fetch) ---  Declare which URL
#   # spellings are the SAME resource so an inbound variant matches the record and the origin
#   # list stays minimal. `query: drop` (default keep) treats all query params as noise;
#   # `rules` are {pattern, replacement} regex subs (like url_rewrite) on the identity key;
#   # `on_rewritten: true` computes identity from the url_rewrite output. Opt-in: absent this,
#   # identity is plain normalize (string match). A bare list form = rules only.
#   # url_equivalent:
#   #   query: drop                      # nested_view / affiliate / utm params == noise
#   #   rules:
#   #     - {pattern: '/page-1(?=[/?#]|$)', replacement: ''}   # /page-1 == bare thread
#   # --- dependent reference material (capture.references) ---  Declare which OUTBOUND
#   # links are part of the capture itself -- a product page's manual / spec sheet -- so
#   # the drafter emits a `reference` annotation for each (spec §4.3.3.3 / §7.2) and, opt-in,
#   # fetches it alongside. Match keys per rule (selector / href_pattern / text_pattern / rel)
#   # are ANDed; rules are ORed. `role` labels it; `capture: true` grabs the target at depth 1
#   # as its OWN record (default false = annotate only); `cross_host: allow` (default) reaches
#   # off-host manuals, `same` restricts to this host. A reference resolves to a corpus:// link
#   # on the next draft once its target is captured. Preview: `corpus links --references <rec>`;
#   # deferred fetch of pending ones: `corpus crawl --references`.
#   # references:
#   #   - match: {selector: '#product-details a[href$=".pdf"]'}
#   #     role: manual
#   #     capture: true                  # grab the manual alongside the page (depth 1)
#   #   - match: {text_pattern: '(?i)spec sheet', href_pattern: '\\.pdf'}
#   #     role: spec-sheet               # annotate only (capture defaults false)
#
# # --- video hosts (yt-dlp) ---  `capturer: video` is the ONLY thing that routes a host
# # to yt-dlp; there is no built-in video-host list. yt-dlp options pass straight through.
# capture:
#   capturer: video
#   ytdlp:                             # merged into YoutubeDL(opts) (outtmpl/logger/cookies
#     format: "bv*+ba/b"               #   stay library-owned). e.g. prefer muxed h264 on
#     getcomments: true                #   TikTok: "best[vcodec^=avc]/bv*+ba/b"
#     impersonate: chrome              # browser impersonation (needs the [media] extra)
#   cookies_from_host: true            # pull this host's cookies from a CDP browser (login)
#
# # --- per-host transcription (read at DRAFT time) ---
# transcription:
#   enabled: true                      # false -> skip (no warning); absent -> global config
#   adapter: http-whisper              # override the global [corpus.transcription] backend
#   base_url: "http://localhost:9000"
"""

# YouTube platform-provenance overlay — the distribution's one worked, UNCOMMENTED
# per-host origin overlay (`example.com.yaml` above stays a commented, inert seed).
# Ships alongside it at `schema/origin/web/youtube.com.yaml` so a new corpus has a
# real example of the one namespace every user must author (origin overlays are a
# per-corpus concern, spec §7.2 — the distribution packages none by default), and it
# closes a documentation gap: the packaged video/audio mime schemas mechanically lift
# yt-dlp sidecar fields (`sidecar.ytdlp_keys`, spec §7.1) onto the origin block, but
# nothing declared those fields' types/semantics until now.
#
# Byte-identical with `tools/tests/data/origin_youtube.com.yaml` in the distribution's
# own test tree — `test_origin_youtube.py::test_fixture_matches_shipped_template`
# guards the two from drifting apart.
_YOUTUBE_ORIGIN_OVERLAY_YAML = """\
# YouTube platform-provenance overlay — the distribution's one worked, uncommented
# example of a per-host origin overlay (see also the commented generic seed,
# `example.com.yaml`, that `ath init` seeds alongside this file). This exact content
# also ships as `ath init`'s worked example (`corpus.scaffold._YOUTUBE_ORIGIN_OVERLAY_YAML`)
# and as this test fixture — `tools/tests/test_origin_youtube.py` asserts the two stay
# byte-identical.
#
# Matches any record whose <!--origin--> block carries a URI on a YouTube host — apex
# + subdomains covers www./m./music., `youtu.be` is a distinct domain and needs its
# own pattern. Declares the extended fields the video/audio mime schemas' yt-dlp
# sidecar lift actually produces (spec §7.1 `sidecar.ytdlp_keys`) beyond
# `ytdlp_title`/`ytdlp_description`, which are host-agnostic and already declared
# (role-marked) on the universal `schema/origin/origin.yaml` — every yt-dlp capture
# gets those two, not just YouTube's.
description: |
  YouTube — video/audio captured via yt-dlp. This overlay is platform-keyed,
  orthogonal to any body-shape overlay a corpus declares (e.g. `media-format/webinar`):
  a YouTube webinar carries both. The origin block's `ytdlp_*` fields are the sidecar
  lift's flat metadata (spec §7.1) — non-primary-source facts about the source POST,
  never the primary-artifact bytes. Other video platforms (Vimeo, a raw mp4 on a
  publisher CDN) get their own `origin/web/<host>.yaml`.
applies_to:
  host_patterns:
    - youtube.com
    - youtu.be
    - m.youtube.com
    - music.youtube.com
  include_subdomains: true
capture:
  capturer: video
  ytdlp:
    format: "bv*+ba/b"
    getcomments: true # populates `ytdlp_comments` below; omit to skip top comments
normalization:
  guidance: |
    Every field below is the yt-dlp `.info.json` sidecar's ground truth (spec §7.1) —
    present on the origin block once ingest lifts it, never re-derived from the
    transcript, and never copied into the body, the artifact block, or the frontmatter
    (§7.1's non-primary-source rule; the body stays faithful to the MEDIA bytes alone).
    `ytdlp_title` / `ytdlp_description` are declared on the universal origin overlay,
    not here — they're host-agnostic and role-marked there (`role: title` /
    `role: description`), so every yt-dlp capture derives an honest display title and
    description with no pass, per spec §4.2.3. There is nothing to "promote": the
    title/description are never stored, so a wrong one means the source `.info.json`
    was wrong at capture — re-capture, don't hand-edit.

    **Chapters are already structural, not a field.** The uploader's `chapters[]` is
    lifted mechanically at ingest as `<!--segment structural-->` byte-marks (spec
    §4.3.2.3's byte-mark rule, §12.3.7) — each chapter's own title already renders
    verbatim in the body at its `time=` mark. Do not additionally render a "Key
    topics" table or otherwise restate chapter titles in body prose; that would
    duplicate content the structural marks already carry faithfully.

    **`ytdlp_comments` stays metadata.** When the capture's `ytdlp:` config sets
    `getcomments: true`, the sidecar's top comments land in `ytdlp_comments` here
    (author/like_count/timestamp per entry) — origin-block metadata only. It is never
    rendered into the body (no "Top comments" section): the body is the transcript,
    faithful to the audio, and nothing else.

    **Identity and engagement fields are ground truth, not to re-derive.**
    `ytdlp_uploader(_id|_url)`, `ytdlp_channel(_id|_url)`, `ytdlp_upload_date`,
    `ytdlp_view_count`, `ytdlp_like_count`, `ytdlp_comment_count`,
    `ytdlp_repost_count`, `ytdlp_track`, `ytdlp_artists` are stale-by-definition
    snapshots at capture time (view/like/comment counts especially) — don't "correct"
    them against a later look at the live page; a re-capture is how they refresh.

    **Extending the lift.** yt-dlp's info.json also reports `availability`
    (`public`/`unlisted`/`subscriber_only`/`premium_only`/`needs_auth`/…),
    `live_status` (`not_live`/`is_live`/`was_live`/…), and `was_live` — useful signals
    the packaged mime schemas don't lift by default (extend the corpus's own copy of
    `sidecar.ytdlp_keys` locally to add them; they then surface here as
    `ytdlp_availability` / `ytdlp_live_status` / `ytdlp_was_live`, under the same rules
    as every field above). Where a corpus does lift them: a non-public
    `ytdlp_availability` means the URL may not survive re-capture — emit a
    record-scope `<!--context issue/partial-content-->`. A `was_live` true (or
    `live_status: was_live`) recording has a different speech-flow than a scripted
    upload (speaker overlap, off-camera moments, audience-chat references) — a
    `<!--context issue/format-loss-->` at the affected segment is the honest signal,
    not a silent edit.

    **Canonical URL — already automatic.** yt-dlp's `webpage_url`/`original_url` fold
    into the origin block's `uri:` alias list mechanically at ingest (spec §7.2, the
    sidecar-lift merge) — a `youtu.be/<id>` short link, a tracker-tagged share URL, and
    the canonical `youtube.com/watch?v=…` form all collapse under one origin block
    with no overlay work needed here.
extended_fields:
  ytdlp_uploader:
    type: string
    required: false
    description: |-
      Uploader display name from yt-dlp's info.json. Often equal to `ytdlp_channel`,
      but YouTube exposes them separately, so they're kept separate here too.
  ytdlp_uploader_id:
    type: string
    semantic_type: identifier
    required: false
    description: Stable uploader/handle id from yt-dlp.
  ytdlp_uploader_url:
    type: string
    semantic_type: uri
    required: false
    description: |-
      Uploader profile URL (handle form, e.g. 'https://www.youtube.com/@name').
      Distinct from `ytdlp_channel_url`, which uses the channel-id form.
  ytdlp_channel:
    type: string
    required: false
    description: Channel display name from yt-dlp's info.json.
  ytdlp_channel_id:
    type: string
    semantic_type: identifier
    required: false
    description: |-
      Stable channel id (e.g. 'UCxxxxxxxxxxxxxxxxxxxxxx'). Survives channel renames;
      pair with `ytdlp_channel` for human-readable provenance.
  ytdlp_channel_url:
    type: string
    semantic_type: uri
    required: false
    description: Direct URL to the channel page, channel-id form.
  ytdlp_upload_date:
    type: string
    semantic_type: timestamp
    required: false
    description: |-
      Upload date, yt-dlp's native `YYYYMMDD` form (the sidecar lift copies the
      info.json value verbatim — no reformatting at draft time).
  ytdlp_view_count:
    type: number
    required: false
    description: View count at capture time. Stale by definition — not refreshed.
  ytdlp_like_count:
    type: number
    required: false
    description: |-
      Like count at capture time. Engagement signal orthogonal to view count; stale
      by definition.
  ytdlp_comment_count:
    type: number
    required: false
    description: Total comment count the platform reported at capture time.
  ytdlp_repost_count:
    type: number
    required: false
    description: |-
      Share/repost count at capture time, where the platform reports one (yt-dlp's
      shared field name across hosts — rarely populated on YouTube proper, more
      common on other yt-dlp-backed origins).
  ytdlp_track:
    type: string
    required: false
    description: |-
      Track title, for YouTube Music captures. Absent for ordinary video uploads.
  ytdlp_artists:
    type: array
    required: false
    description: |-
      Credited artists, for YouTube Music captures. Absent for ordinary video
      uploads.
  ytdlp_comments:
    type: array
    required: false
    description: |-
      Top comments captured alongside the video (present only when the capture's
      `ytdlp: {getcomments: true}` was set) — each entry `{text, author?,
      like_count?, timestamp?}`, sorted and capped by the capturer. Origin-block
      metadata only; never rendered into the body.
"""


def scaffold(target: Path, *, force: bool = False) -> Path:
    """Create the minimal corpus seam at `target`.

    Writes:
      - records/ (empty)
      - .gitignore (untracked dirs)
      - README.md (overview)

    Does NOT write universal mime/atom/context-issue schemas — those resolve
    from the package via the schema-fallback loader. Does NOT create the untracked
    artifacts/capture/cache/queue/export dirs (they materialize when first used).


    Returns the resolved target path. Raises FileExistsError if records/ or
    schema/ already exists and force=False.
    """
    target = Path(target).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    records_dir = target / "records"
    schema_dir = target / "schema"
    if not force:
        if records_dir.exists() and any(records_dir.iterdir()):
            raise FileExistsError(f"{records_dir} is not empty (pass force=True to override)")
        if schema_dir.exists() and any(schema_dir.iterdir()):
            raise FileExistsError(f"{schema_dir} is not empty (pass force=True to override)")

    records_dir.mkdir(exist_ok=True)
    schema_dir.mkdir(exist_ok=True)

    # Universal origin overlay — corpus-supplied, not packaged. Every corpus
    # carries the baseline uri/snapshot field declarations; corpora may extend
    # them or add per-host overlays alongside.
    origin_dir = schema_dir / "origin"
    origin_dir.mkdir(parents=True, exist_ok=True)
    origin_yaml = origin_dir / "origin.yaml"
    if not origin_yaml.exists() or force:
        origin_yaml.write_text(_UNIVERSAL_ORIGIN_YAML, encoding="utf-8")

    # Pluggable-capture seam (tracked, optional): per-origin capture config lives under a
    # `capture:` section on a per-host origin overlay. Origin overlays are namespaced by
    # URI scheme family — web (http/https) sources live under `schema/origin/web/<host>.yaml`
    # (matched by host). Seeded with a commented example that is inert until edited.
    web_dir = origin_dir / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    example_overlay = web_dir / "example.com.yaml"
    if not example_overlay.exists() or force:
        example_overlay.write_text(_EXAMPLE_ORIGIN_OVERLAY_YAML, encoding="utf-8")

    # The one worked, uncommented origin-overlay example (see the constant's own
    # docstring above) — ships beside the commented `example.com.yaml` seed.
    youtube_overlay = web_dir / "youtube.com.yaml"
    if not youtube_overlay.exists() or force:
        youtube_overlay.write_text(_YOUTUBE_ORIGIN_OVERLAY_YAML, encoding="utf-8")

    gi = target / ".gitignore"
    if not gi.exists() or force:
        gi.write_text(_GITIGNORE, encoding="utf-8")

    readme = target / "README.md"
    if not readme.exists() or force:
        readme.write_text(
            _README_TEMPLATE.format(name=target.name),
            encoding="utf-8",
        )

    return target
