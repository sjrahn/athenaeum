"""The retired `corpus draft` verb + the transitional `derive_record` core.

*(3.0.)* `corpus draft` is **retired** (§12.4.6): the draft stage's three duties split —
byte-facts to ingest **attestation** (`corpus reattest`), content extraction to the **`body`
derivation op**, body-writing to the normalize pass. The `run()` here is a signpost that
errors with those pointers.

`derive_record` — the transitional whole-record re-derivation (attest + store the mechanical
body on a record with no stored rendering) — survives as the shared core `redraft_record`
(the test-helper successor of `corpus redraft`, §12.19) still calls; it runs the drafter
through `corpus.derive.build_content_zone` and stores the body a 3.0 record would derive on
demand. A re-derived mechanical body on a record with no governing form is exactly the
grandfathered shape (§4.1's `rendered` state — §12.18 step 3), superseded by the record's next
pass. It is not exposed as a CLI verb.
"""

from __future__ import annotations

import argparse
import sys

from corpus import (
    content_hash,
    paths,
    recordbuild,
    records,
    touches,
)
from corpus._cli._common import add_corpus_root_arg
from corpus.derive import DeriveError, build_content_zone
from corpus.derive import apply_drafter_result as _apply_drafter_result

# `corpus draft` is the transitional (2.x-shape) verb: it applies the drafter's attested
# facts AND stores the derived body, leaving the record formless (§4.1). In 3.0 those split
# — ingest attests, the `body` op derives, normalize authors — but the stage is retired lazily
# (the grandfathered-body path, §12.18 step 3): a re-derived mechanical body with no governing
# form is exactly the `rendered` derived state. The shared drafter-run core lives in
# `corpus.derive`; `DraftError` is kept as the historical alias of `DeriveError` for existing
# callers/tests.
DraftError = DeriveError


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", nargs="?", default=None, help="(retired) record target.")
    parser.add_argument("--messages", default=None, help="(retired) → `corpus reattest --messages`.")
    parser.add_argument(
        "--fingerprint", action=argparse.BooleanOptionalAction, default=None,
        help="(retired) → `corpus reattest --fingerprint`.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    """`corpus draft` is retired (3.0, §12.4.6). Its three duties split: fact-stamping is now
    ingest **attestation** (automatic at `corpus ingest`; re-run with `corpus reattest`);
    content extraction is the **`body` derivation op** (`corpus body` / `corpus resolve
    <uri>?body`); body-writing is the normalize pass. The mbox selective declaration re-homes
    to `corpus reattest --messages`."""
    sys.stderr.write(
        "corpus draft is RETIRED (ATH-CORPUS 3.0). The draft stage split:\n"
        "  - byte-facts  → ingest attests automatically; re-run with `corpus reattest`\n"
        "  - the body    → the derivation op: `corpus body <id>` or `corpus resolve "
        "'corpus://<id>?body'`\n"
        "  - mbox msgs   → `corpus reattest <mbox-id> --messages 5,12,90-95`\n"
        "  - the authored form is written by the normalize pass.\n"
    )
    return 2


def derive_record(
    post,
    corpus_root,
    *,
    fingerprint_cli: bool | None = None,
    messages: list[int] | None = None,
) -> None:
    """Re-derive `post`'s mechanical content from its retained artifact, **in place**: run the
    matching drafter (via the shared `corpus.derive.build_content_zone` core), apply the
    metadata-zone result, emit + grammar-validate the content zone, apply the per-host
    canonical content-scoping override, and append the draft touch. The record stays
    formless (§4.1) — no form is stamped here: a re-derived mechanical body with no
    governing form is exactly the grandfathered `rendered` state (§12.18 step 3), superseded
    by its next pass. No dedup and no write — the caller owns those. `post` must have no
    stored rendering yet. The transitional core shared by `corpus draft` and the
    `redraft_record` test helper (§12.19). Raises `DraftError` (missing schema / drafter) or
    `ArtifactMissing` (artifact not local)."""
    from corpus.derive import produces_body, reattach_descriptions, strip_attested_layer

    build, result, mt_schema, binary_file, mime_schema_id = build_content_zone(
        post, corpus_root, fingerprint_cli=fingerprint_cli, messages=messages
    )
    media_type = records.media_type_for(post)
    canonical_algo = (mt_schema.get("canonical_strategy") or {}).get("algo")

    # Idempotent attest: strip any attested layer already present (a 3.0 ingest attests at
    # stub time) before re-applying, so a transitional draft never doubles embeds/issues.
    # The mbox manifest is EXEMPT — it is cumulative by design (its result is the delta over
    # the already-declared embeds; §12.11), and ingest attests it with no messages (an empty
    # manifest), so there is nothing to double.
    strategy = str((mt_schema.get("draft") or {}).get("strategy") or "")
    if strategy != "mbox-manifest":
        authored_desc = strip_attested_layer(post)
        _apply_drafter_result(post, result, mime_schema_id, corpus_root)
        reattach_descriptions(post, authored_desc)
    else:
        _apply_drafter_result(post, result, mime_schema_id, corpus_root)

    # Emit the content zone the drafter built on the Build — body-draft schemas only
    # (spec §7.1). `finish` re-parses to surface grammar errors before any write.
    if produces_body(mt_schema):
        recordbuild.finish(build)

    # Opt-in per-host canonical content-scoping: if the record's origin host declares a
    # `canonical.content_selector` in its overlay, recompute the canonical hash over just
    # that content region, overriding the drafter's whole-document hash. This makes the
    # same article reached by different links (different title/breadcrumb framing) share a
    # canonical → collapse via content-dedup. Absent the overlay section, the drafter's
    # whole-document canonical stands (no behaviour change for other corpora).
    if canonical_algo and post.metadata.get("canonical"):
        from corpus.capture import recipes

        selector = recipes.canonical_content_selector_for_url(
            corpus_root, records.primary_origin_uri(post)
        )
        if selector:
            post.metadata["canonical"] = records.format_hash(
                canonical_algo.split("-", 1)[0],
                content_hash.compute(canonical_algo, binary_file, content_selector=selector),
            )

    # Opt-in overlay-declared dependent references (spec §4.3.3.3 / §7.2): if the record's
    # origin host declares `capture.references` rules, emit a `provenance: auto` `reference`
    # context block for each declared dependent link in the page (a PDP's product manual,
    # etc.) at tier 2 (`source_url`) — tier 3 is a read-time edge, never stored (spec
    # §4.4.5). HTML-only (the rules match a DOM); pure opt-in (no rules → nothing
    # emitted); idempotent under `redraft` (re-stub clears context blocks first).
    if media_type == "text/html":
        from corpus import references

        references.emit_overlay_references(post, corpus_root, binary_file)

    # Append the draft touch. A re-derived mechanical body with no governing form is a
    # grandfathered materialized derivation (§4.1's `rendered` state, §12.18 step 3) — the
    # touch id is history (kept unchanged), not lifecycle. *(3.1)* No `status` field to set —
    # the record's derived state falls out of what it now carries (§4.1).
    touches.record_touch(post, touches.script_identifier("draft." + mime_schema_id))


def _discard_duplicate(corpus_root, record_id: str, record_file, extension: str) -> None:
    """Remove a content-duplicate record's `.md` + its local artifact after its URL was
    folded into the original. Best-effort on the artifact (a remote store keeps its own
    copy; the local capture is the orphan we clean). The artifacts dir is regenerable."""
    record_file.unlink(missing_ok=True)
    artifact = corpus_root / "artifacts" / paths.shard(record_id) / f"{record_id}.{extension}"
    artifact.unlink(missing_ok=True)


def _cleanup_enrichment(corpus_root, record_id: str) -> None:
    """Delete the record's draft-time enrichment sidecars from `capture/` once the draft
    has consumed them (the yt-dlp `.info.json`, and any `<hash>.*` enrichment a capturer
    staged). Enrichment is one-shot — not persisted past draft; the extracted fields and
    segments already live in the record. Best-effort; `capture/` is staging-only."""
    capture_dir = corpus_root / "capture"
    if not capture_dir.is_dir():
        return
    for p in capture_dir.glob(f"{record_id}.*"):
        p.unlink(missing_ok=True)
