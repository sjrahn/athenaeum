"""Shared CLI helpers — corpus-root discovery, record resolution, output formatting."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from corpus import paths


def resolved_corpus_root(args: argparse.Namespace) -> Path:
    """Get the corpus root from `args.corpus_root` (set via --corpus-root) or by
    discovery from cwd. Exits with a friendly message if neither works."""
    explicit = getattr(args, "corpus_root", None)
    if explicit:
        root = Path(explicit).resolve()
        if not (root / "records").is_dir() or not (root / "schema").is_dir():
            sys.exit(
                f"--corpus-root {root} does not look like a corpus "
                f"(missing records/ or schema/)"
            )
        return root
    try:
        return paths.find_corpus_root()
    except FileNotFoundError as e:
        sys.exit(str(e))


def human_bytes(n: int) -> str:
    """Render a byte count as a short human-readable size (e.g. `683.0 KB`, `2.2 GB`)."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def add_corpus_root_arg(parser: argparse.ArgumentParser) -> None:
    """Add the `--corpus-root <path>` option to a subcommand parser."""
    parser.add_argument(
        "--corpus-root",
        dest="corpus_root",
        default=None,
        help="Path to corpus root (default: walk up from cwd to find records/+schema/).",
    )


def parse_current_period(raw: str | None) -> tuple[int, int]:
    """Parse a `--current-period YYYY-MM` value into `(year, month)`, defaulting to the
    current UTC year-month when absent. Shared by every schedule-driven splitter
    (`mbox-split`, `period-split`, spec §12.3.14) that needs a deterministic "what counts
    as the open month" boundary for testing, rather than always reading the real clock."""
    if not raw:
        now = datetime.now(UTC)
        return now.year, now.month
    year_s, _, month_s = raw.partition("-")
    try:
        return int(year_s), int(month_s)
    except ValueError:
        sys.exit(f"--current-period: expected YYYY-MM, got {raw!r}")


def bucket_year_month(dt: datetime) -> tuple[int, int]:
    """The period-bucketing UTC boundary rule (spec §12.3.14, v34 owner ruling): an
    AWARE `dt` (carries an offset — an RFC 5322 `Date:` header, an offset-bearing ISO
    timestamp) converts to UTC before its `(year, month)` is read; a NAIVE `dt` (no
    offset anywhere in the bytes — an EXIF-style local time) buckets at face value,
    because inventing an offset would fabricate a fact the bytes do not carry. Shared by
    every schedule-driven splitter (`mbox-split`, `period-split`) so the rule is applied
    identically on both the mbox Date-header axis and the sidecar date axis."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.year, dt.month


# The functional-URI transform grammar (spec §6.2), shown in `corpus resolve`/`preview`
# --help. Authoritative one-liners so an agent never has to guess a param's shape — in
# particular that bbox/crop are x,y,WIDTH,HEIGHT (position + size), not corners.
TRANSFORM_GRAMMAR = """\
Transform params — append to a corpus://<hash> URI as `?k=v&k2=v2`; they compose
left-to-right, each operating on the previous step's output:

  PDF — select a page, then ask for a rendering (or probe the whole document):
  page=N             select page N (1-indexed). A bare page=N renders it -> image
  page=N&render      render the selected page -> image (explicit form of a bare page=N)
  page=N&text        the page's embedded text layer -> text  (empty if it's a scan)
  page=N&words       per-word boxes [{text, bbox:x,y,w,h}] as JSON -> json
  page=N&probe       per-page probe: dims, rotation, text/image stats, shape hint -> json
  probe              whole-document probe: per-page table + /Info + outline flag -> json
  outline            the PDF outline / TOC tree -> json
  (page=N&bbox=… and the image ops below auto-render the page first.)

  Image:
  bbox=x,y,w,h       crop a region. x,y,w,h are FRACTIONS in [0,1]: a position (x,y)
  crop=x,y,w,h       plus a SIZE (WIDTH,HEIGHT) — NOT corners. x+w and y+h must be <=1.
  mark=x,y,w,h[;...] draw the region(s) on the FULL image (see where a crop lands;
                     ';'-separated for several, labeled 1..N). Does not crop.
  rotate=90|180|270  rotate clockwise (90/270 swap width and height)
  auto_orient        apply the EXIF orientation tag (right a sideways/flipped photo)
  autocontrast       stretch contrast to full range (faint scans)
  contrast=F         scale contrast by factor F (1.0 = unchanged; try 1.5-2.5)
  grayscale          convert to single-channel grayscale
  fit=WxH | fit=llm  downscale to fit a box, aspect-preserving, never enlarges
                     (the `llm` preset caps to a vision-model input budget)
  resize=WxH         resize to exact pixel dimensions (may distort or enlarge)
  dpi=N              rasterization DPI for page= (default 200; position-independent)
"""


def attach_transform_grammar(parser: argparse.ArgumentParser) -> None:
    """Show the transform-grammar reference in this subcommand's --help."""
    parser.epilog = TRANSFORM_GRAMMAR
    parser.formatter_class = argparse.RawDescriptionHelpFormatter


def attach_workflow_note(parser: argparse.ArgumentParser, workflow: str) -> None:
    """Note in this subcommand's --help that it is one verb in a larger tooling
    workflow, pointing at the central runbook. The runbook (`corpus workflow
    <workflow>`) is maintained in the package, so the operating modes and lifecycle
    guidance update with the tooling — not per corpus."""
    parser.epilog = (
        f"Part of the '{workflow}' workflow. Run `corpus workflow {workflow}` for the "
        f"operating modes and result lifecycle (one runbook, maintained in the tooling)."
    )
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
