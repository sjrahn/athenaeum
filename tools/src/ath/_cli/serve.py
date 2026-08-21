"""`ath serve` — the read surface (spec/athenaeum.md §5.1): a read-only HTTP
surface over an instance, serving the corpus + ledger join through the same
contracts library consumers get.

Guard-imports `ath.serve` (fastapi/uvicorn) — the base install stays clean
without the `serve` extra, same pattern as `refdata`'s adapter extras.
"""

from __future__ import annotations

import secrets
import sys
from collections.abc import Sequence
from pathlib import Path

from ath._cli._common import base_parser, resolve_root

_USAGE_EXTRA = (
    "\nOwner-plane token: --owner-token FILE reads a pre-generated token from "
    "a file; --owner generates a fresh one and prints it once to stderr "
    "(save it — it is not written anywhere and cannot be recovered). Neither "
    "flag: the owner plane is not enabled at all — every request reads as "
    "public (§5.1).\n"
    "\nAudience planes: --audience-token NAME=FILE reads a pre-generated "
    "token from a file for the declared audience NAME (repeatable, one per "
    "audience); --audience NAME generates a fresh one for NAME and prints it "
    "once to stderr (repeatable). NAME must name an audience declared in the "
    "instance's tenancy.audiences (§athenaeum.md §2.3) — an audience token "
    "for an undeclared name is refused."
)


def run(argv: Sequence[str]) -> int:
    ap = base_parser("ath serve", (__doc__ or "") + _USAGE_EXTRA)
    ap.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8321, help="bind port (default 8321)")
    ap.add_argument(
        "--owner-token", metavar="FILE", default=None,
        help="file containing the owner-plane bearer token",
    )
    ap.add_argument(
        "--owner", action="store_true",
        help="generate a random owner-plane token and print it once to stderr",
    )
    ap.add_argument(
        "--audience-token", action="append", default=[], metavar="NAME=FILE",
        help="file containing an audience-plane bearer token for the declared "
             "audience NAME (repeatable, one per audience)",
    )
    ap.add_argument(
        "--audience", action="append", default=[], metavar="NAME",
        help="generate a random audience-plane token for the declared "
             "audience NAME and print it once to stderr (repeatable, one per "
             "audience; save it — it is not written anywhere and cannot be "
             "recovered)",
    )
    ns = ap.parse_args(list(argv))

    if ns.owner_token and ns.owner:
        print("ath serve: --owner-token and --owner are mutually exclusive", file=sys.stderr)
        return 2

    owner_token: str | None = None
    if ns.owner_token:
        token_path = Path(ns.owner_token)
        try:
            owner_token = token_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            print(f"ath serve: {token_path}: {e}", file=sys.stderr)
            return 2
        if not owner_token:
            print(f"ath serve: {token_path} is empty — no owner token to gate the "
                  "owner plane with", file=sys.stderr)
            return 2
    elif ns.owner:
        owner_token = secrets.token_urlsafe(32)
        print(f"ath serve: owner-plane token (printed once, save it): {owner_token}",
              file=sys.stderr)

    audience_tokens: dict[str, str] = {}
    for spec in ns.audience_token:
        name, sep, file_ = spec.partition("=")
        if not sep or not name or not file_:
            print(f"ath serve: --audience-token expects NAME=FILE, got {spec!r}",
                  file=sys.stderr)
            return 2
        if name in audience_tokens:
            print(f"ath serve: audience {name!r} given more than once across "
                  "--audience-token/--audience", file=sys.stderr)
            return 2
        token_path = Path(file_)
        try:
            token = token_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            print(f"ath serve: {token_path}: {e}", file=sys.stderr)
            return 2
        if not token:
            print(f"ath serve: {token_path} is empty — no token for audience {name!r}",
                  file=sys.stderr)
            return 2
        audience_tokens[name] = token
    for name in ns.audience:
        if name in audience_tokens:
            print(f"ath serve: audience {name!r} given more than once across "
                  "--audience-token/--audience", file=sys.stderr)
            return 2
        token = secrets.token_urlsafe(32)
        print(f"ath serve: audience {name!r} plane token (printed once, save it): {token}",
              file=sys.stderr)
        audience_tokens[name] = token

    try:
        from ath.serve import create_app
    except ImportError as e:
        print("ath serve: the read surface needs the serve extra — "
              "uv pip install 'athenaeum[serve]'", file=sys.stderr)
        print(f"  ({e})", file=sys.stderr)
        return 2

    root = resolve_root(ns.root)
    try:
        app = create_app(root, owner_token, audience_tokens=audience_tokens or None)
    except ValueError as e:
        print(f"ath serve: {e}", file=sys.stderr)
        return 2

    import uvicorn

    uvicorn.run(app, host=ns.host, port=ns.port)
    return 0
