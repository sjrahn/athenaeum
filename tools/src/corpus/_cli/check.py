"""Read-only dedup probe: is a URL already captured? (resolves short links, no download).

Resolves a URL the way `corpus capture` would — `urls.normalize` + the host overlay's
`url_rewrite` / `url_equivalent` recipe — AND additionally follows HTTP redirects to resolve
opaque short links (`https://vt.tiktok.com/XXXX/` → `https://www.tiktok.com/@user/video/<id>`)
to their final URL. It then computes the identity key (so volatile query params the canonical
resolves with — e.g. TikTok's `?_r`/`?_t` — are stripped by the host's `url_equivalent`) and
asks whether any record already holds that resource.

Strictly READ-ONLY: it never captures, ingests, downloads the artifact, or writes anything —
the redirect follow is a body-less HEAD/GET. The intended use is scripting a capture decision
(`corpus check "$url" && echo "skip" || corpus capture "$url"`) and turning the throwaway
`curl -sIL | grep` short-link probe into a first-class command.

Exit codes (script contract):

    0   already captured — a record holds this resource. (matched record hash on stdout)
    1   not captured — no record holds it; `corpus capture` would download it.
    2   usage error (bad arguments — argparse).
    3   resolution error — the corpus root, overlay, or lookup could not be evaluated.

`--json` prints a single JSON object (see `run`) instead of the human line; the exit code is
the same either way. `--no-follow-redirects` skips the network probe (string identity only),
for offline / fast checks.
"""

from __future__ import annotations

import argparse
import json
import sys

from corpus import paths, records
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

EXIT_CAPTURED = 0
EXIT_NOT_CAPTURED = 1
# 2 is argparse's usage-error code (reserved).
EXIT_ERROR = 3


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("url", help="The URL to check (a short link is resolved via redirects).")
    parser.add_argument(
        "--no-follow-redirects",
        dest="follow_redirects",
        action="store_false",
        default=True,
        help="Skip the HTTP redirect probe — match on string identity only (offline / fast).",
    )
    parser.add_argument("--json", action="store_true", help="Emit a single JSON object.")
    add_corpus_root_arg(parser)
    parser.epilog = (
        "Exit codes: 0 already captured, 1 not captured, 2 usage error, 3 resolution error. "
        "READ-ONLY: never captures, ingests, downloads, or writes."
    )


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    from corpus.capture.recipes import resolve_identity_for_url

    try:
        final_url, key = resolve_identity_for_url(
            root, args.url, follow_redirects=args.follow_redirects
        )
        record_id = records.find_by_uri(key, corpus_root=root, _prekeyed=True)
    except Exception as e:
        return _emit_error(args, str(e))

    captured = record_id is not None
    record_path = str(paths.record_path(root, record_id)) if record_id else None
    payload = {
        "url": args.url,
        "resolved_url": final_url,
        "identity_key": key,
        "redirected": final_url != args.url,
        "captured": captured,
        "record": record_id,
        "path": record_path,
    }

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif captured:
        via = f" (via redirect → {final_url})" if payload["redirected"] else ""
        print(f"captured{via}: {record_id}")
        print(f"  {record_path}")
    else:
        via = f" → {final_url}" if payload["redirected"] else ""
        print(f"not captured: {args.url}{via}")

    return EXIT_CAPTURED if captured else EXIT_NOT_CAPTURED


def _emit_error(args: argparse.Namespace, message: str) -> int:
    if args.json:
        json.dump({"url": args.url, "error": message}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"check: error: {message}", file=sys.stderr)
    return EXIT_ERROR
