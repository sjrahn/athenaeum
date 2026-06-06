"""`corpus-api serve` — launch the read-only Corpus Console API with uvicorn.

    corpus-api serve --corpus public=/path/to/corpus --corpus scratch=/path/to/corpus-test
    corpus-api serve            # falls back to ATH_API_CORPORA, then cwd discovery

uvicorn is imported inside `main()` so the package stays importable without the server
running (and the base library never pulls it in — gotcha #24).
"""

from __future__ import annotations

import argparse
import sys

from corpus.api.config import ApiConfig, ConfigError, load_config


def _build(specs: list[str] | None) -> ApiConfig:
    cfg = load_config(specs or None)
    if not cfg.corpora:
        raise ConfigError("no corpora configured (use --corpus id=path or ATH_API_CORPORA)")
    return cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corpus-api", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument(
        "--corpus",
        action="append",
        dest="corpora",
        metavar="ID=PATH",
        help="serve corpus ID rooted at PATH (repeatable)",
    )
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--reload", action="store_true", help="uvicorn autoreload (dev)")

    args = parser.parse_args(argv)
    if args.command != "serve":
        parser.print_help()
        return 2

    try:
        cfg = _build(args.corpora)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for entry in cfg.corpora:
        print(f"serving {entry.id!r} from {entry.root}", file=sys.stderr)

    import uvicorn

    from corpus.api.app import create_app

    uvicorn.run(create_app(cfg), host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
