"""Operating-mode runbooks for the tooling (spec §8.5 and friends).

    corpus workflow                      list the available workflows
    corpus workflow <name>               the workflow's overview + its sections
    corpus workflow <name> <section>     one section in full
    corpus workflow <name> --full        the whole runbook

Guidance for *running* the tooling — loop operating modes, the queue's result
lifecycle — distinct from `corpus guidance <id>` (per-record normalization
guidance). Runbooks ship with the package and update with it, so the operating
modes are maintained once, centrally, not copied into each corpus.
"""

from __future__ import annotations

import argparse
import json
import sys

from corpus import workflows


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", nargs="?", help="Workflow to show (omit to list all).")
    parser.add_argument(
        "section", nargs="?", help="Narrow to one section (its slug, or a unique prefix)."
    )
    parser.add_argument(
        "--full", action="store_true", help="Print the whole runbook, not just the overview."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")


def run(args: argparse.Namespace) -> int:
    if not args.name:
        return _list(args.json)
    wf = workflows.get(args.name)
    if wf is None:
        names = [w.name for w in workflows.list_workflows()]
        print(
            f"corpus workflow: no workflow {args.name!r}. "
            f"Available: {', '.join(names) or '(none)'}",
            file=sys.stderr,
        )
        return 2
    if args.section:
        return _section(wf, args.section, args.json)
    if args.full:
        return _full(wf, args.json)
    return _overview(wf, args.json)


def _list(as_json: bool) -> int:
    wfs = workflows.list_workflows()
    if as_json:
        print(json.dumps([{"name": w.name, "summary": w.summary} for w in wfs], indent=2))
        return 0
    if not wfs:
        print("no workflows packaged")
        return 0
    print("Workflows (run `corpus workflow <name>` for one):\n")
    width = max(len(w.name) for w in wfs) + 2
    for w in wfs:
        print(f"  {w.name:<{width}}{w.summary}")
    return 0


def _overview(wf: workflows.Workflow, as_json: bool) -> int:
    secs = workflows.sections(wf.body)
    if as_json:
        print(
            json.dumps(
                {
                    "name": wf.name,
                    "title": wf.title,
                    "summary": wf.summary,
                    "intro": workflows.intro(wf.body),
                    "sections": [{"slug": s.slug, "title": s.title} for s in secs],
                },
                indent=2,
            )
        )
        return 0
    print(workflows.intro(wf.body))
    if secs:
        print(f"\nSections (run `corpus workflow {wf.name} <section>` for the full text):")
        width = max(len(s.slug) for s in secs) + 2
        for s in secs:
            print(f"  {s.slug:<{width}}{s.title}")
    return 0


def _full(wf: workflows.Workflow, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"name": wf.name, "title": wf.title, "body": wf.body}, indent=2))
    else:
        print(wf.body.rstrip())
    return 0


def _section(wf: workflows.Workflow, query: str, as_json: bool) -> int:
    secs = workflows.sections(wf.body)
    q = workflows.slugify(query)
    exact = [s for s in secs if s.slug == q]
    matches = exact or [s for s in secs if s.slug.startswith(q)]
    if len(matches) != 1:
        avail = ", ".join(s.slug for s in secs) or "(none)"
        problem = "no section" if not matches else "ambiguous section"
        print(
            f"corpus workflow {wf.name}: {problem} {query!r}. Sections: {avail}",
            file=sys.stderr,
        )
        return 2
    sec = matches[0]
    if as_json:
        print(json.dumps({"slug": sec.slug, "title": sec.title, "text": sec.text}, indent=2))
    else:
        print(sec.text)
    return 0
