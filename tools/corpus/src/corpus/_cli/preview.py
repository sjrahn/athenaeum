"""Render an artifact for an agent's eyes — outline region(s) on the full image and
fit the result to a vision-model's input budget.

The inspection surface for the cropping / normalization loop: an agent proposes a
bbox, previews where it lands *in context* on the full page, adjusts, then commits
the segment address. Builds a `corpus://<id>?[page=N&][dpi=D&]mark=...&fit=llm` URI
and resolves it (spec §6.2 `mark=` / `fit=`). Read-only — never writes the record.

Fits to the `llm` preset by default precisely because this render IS going into a
model's context; pass --full to render at native resolution (e.g. for a human, or a
codex embedding the crop in a deliverable).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from corpus import functional_uri as furi
from corpus import paths, resolver
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root
from corpus.store import ArtifactMissing


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="A record id, hex prefix, record path, or corpus://<id> URI.")
    parser.add_argument(
        "--page",
        type=int,
        default=None,
        help="For a paged artifact (PDF): render this 1-indexed page first.",
    )
    parser.add_argument(
        "--mark",
        action="append",
        default=[],
        metavar="X,Y,W,H",
        help="Outline a bbox region (fractions in [0,1], origin top-left) on the full "
        "image. Repeatable — each box is auto-labeled 1..N.",
    )
    parser.add_argument(
        "--fit",
        default="llm",
        metavar="WxH|PRESET",
        help="Downscale-to-fit budget (default: llm). Aspect-preserving, reduce-only.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Skip fitting — render at native resolution.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="Rasterization DPI for --page (default 200).",
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="Copy the rendered PNG here (else print the resolver cache path).",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Bypass the resolver cache and re-render.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    rid = _record_id(corpus_root, args.target)

    params: list[str] = []
    if args.page is not None:
        params.append(f"page={args.page}")
    if args.dpi is not None:
        params.append(f"dpi={args.dpi}")
    if args.mark:
        regions = ";".join(m.strip() for m in args.mark)
        params.append(f"mark={regions}")
    if not args.full:
        params.append(f"fit={args.fit}")

    uri = f"corpus://{rid}" + ("?" + "&".join(params) if params else "")
    try:
        out = resolver.resolve(uri, corpus_root, regenerate=args.regenerate)
    except ArtifactMissing as e:
        print(str(e), file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError, NotImplementedError) as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, args.out)
        print(args.out)
    else:
        print(out)
    return 0


def _record_id(corpus_root: Path, target: str) -> str:
    if target.startswith("corpus://"):
        return furi.parse(target).hash
    rid, _ = paths.resolve_record(corpus_root, target)
    return rid
