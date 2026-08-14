"""`ath issue` — read the system's backlog, and keep an offline copy of it in the repo.

The tracker (Forgejo issues on the orchestrator repo) is the source of truth for ticket
state. This command is deliberately READ-ONLY plus one generator:

  list      query the tracker; falls back to the committed snapshot when offline
  show      one issue with its full comment trail
  sync      regenerate the in-repo snapshot from the tracker

Creating, editing, closing and — above all — COMMENTING are done with `fj` (forgejo-cli),
which already does them well. Duplicating them here would be a second way to do the same
thing, and the tracker would start disagreeing with itself.

**Why the snapshot exists.** Session boot reads the backlog. Without a committed copy, a
tailnet hiccup or a headless run without credentials boots blind to the whole backlog. The
snapshot keeps the contract honest: the tracker is authoritative, the snapshot
(`tickets.md` beside the manifest by default; `tracker.snapshot` in the manifest — point it
into a member repo to keep the trace committed) is the offline read and the git-history
trace of how the backlog moved.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from ath._cli._common import base_parser, resolve_root
from ath.manifest import ManifestError, Tracker, load_tracker

_USAGE = """\
usage: ath issue <list|show|sync> [options...]

  list [--state open|closed|all] [--label L] [--offline]
  show <number>
  sync [--check]

Ticket state lives in the tracker; `sync` mirrors it into the repo so a session can
boot without the network. Use `fj issue comment <n>` to record a decision — the trail
is the point.
"""


class TrackerError(RuntimeError):
    """The tracker could not be reached or answered badly."""


def _credentials(host: str) -> tuple[str, str] | None:
    """Ask git for the host's credentials.

    `git credential fill` rather than reading ~/.git-credentials directly, so whatever
    helper the user has configured is the one that answers — the file is only one helper.
    """
    try:
        res = subprocess.run(
            ["git", "credential", "fill"],
            input=f"protocol=https\nhost={host}\n\n",
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    got = dict(
        line.split("=", 1) for line in res.stdout.splitlines() if "=" in line
    )
    user, password = got.get("username"), got.get("password")
    return (user, password) if user and password else None


def _get(tracker: Tracker, path: str, *, timeout: int = 30):
    import base64

    host = tracker.base.split("://", 1)[1].split("/", 1)[0]
    req = urllib.request.Request(f"{tracker.base}{path}")
    creds = _credentials(host)
    if creds:
        token = base64.b64encode(f"{creds[0]}:{creds[1]}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raise TrackerError(f"HTTP {e.code} on {path}") from e
    except Exception as e:  # offline is a normal condition here, not a bug
        raise TrackerError(f"{tracker.base} unreachable: {e}") from e


def fetch_issues(tracker: Tracker, state: str = "all") -> list[dict]:
    """Every issue, paged. Pull requests share the issues endpoint — drop them."""
    out: list[dict] = []
    page = 1
    while True:
        batch = _get(tracker, f"{tracker.issues_path}?state={state}&limit=50&page={page}")
        if not batch:
            break
        out.extend(i for i in batch if not i.get("pull_request"))
        if len(batch) < 50:
            break
        page += 1
        if page > 40:  # a backstop, not a limit anyone should hit
            break
    return sorted(out, key=lambda i: i["number"])


def _labels(issue: dict) -> list[str]:
    return sorted(label["name"] for label in issue.get("labels") or [])


def _is_tombstone(issue: dict) -> bool:
    return "tombstone" in _labels(issue)


def _counts(open_: list[dict], closed: list[dict], tombs: list[int]) -> str:
    line = f"**{len(open_)} open · {len(closed)} closed**"
    if tombs:
        line += f" ({len(tombs)} reserved ids not listed: #{min(tombs)}–#{max(tombs)})"
    return line


def _render_snapshot(tracker: Tracker, issues: list[dict]) -> str:
    """The offline snapshot — generated, never hand-edited.

    Tombstones are summarised as a range rather than listed: 50 placeholder lines would
    bury the 72 tickets that carry meaning, and the snapshot exists to be READ at boot.
    """
    live = [i for i in issues if not _is_tombstone(i)]
    tombs = [i["number"] for i in issues if _is_tombstone(i)]
    open_, closed = (
        [i for i in live if i["state"] == "open"],
        [i for i in live if i["state"] != "open"],
    )
    lines = [
        "# Tickets — snapshot",
        "",
        "**GENERATED by `ath issue sync`. Do not hand-edit.** The tracker is the source of "
        f"truth: <{tracker.web}>.",
        "",
        "This file exists so a session can boot without the tailnet, and so the backlog's "
        "movement shows up in git history. If it disagrees with the tracker, the tracker "
        "wins — re-run `ath issue sync`.",
        "",
        _counts(open_, closed, tombs),
        "",
        "## Open",
        "",
    ]
    for i in open_:
        labs = " ".join(f"`{name}`" for name in _labels(i))
        row = f"- **[#{i['number']}]({i['html_url']})** — {i['title']}"
        lines.append(f"{row}  {labs}" if labs else row)
    lines += ["", "## Closed", ""]
    for i in closed:
        lines.append(f"- [#{i['number']}]({i['html_url']}) — {i['title']}")
    lines.append("")
    return "\n".join(lines)


def _read_snapshot_titles(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")]


def run(argv: Sequence[str]) -> int:
    ap = base_parser("ath issue", "read the system's backlog and mirror it into the repo")
    sub = ap.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="query the tracker")
    p_list.add_argument("--state", default="open", choices=("open", "closed", "all"))
    p_list.add_argument("--label", action="append", default=[], help="filter by label (repeatable)")
    p_list.add_argument("--offline", action="store_true", help="read the snapshot, not the tracker")

    p_show = sub.add_parser("show", help="one issue with its comment trail")
    p_show.add_argument("number", type=int)

    p_sync = sub.add_parser("sync", help="regenerate the in-repo snapshot")
    p_sync.add_argument("--check", action="store_true",
                        help="report whether the snapshot is stale; write nothing")

    args = ap.parse_args(list(argv))
    if not args.cmd:
        print(_USAGE, end="")
        return 0

    try:
        root = resolve_root(args.root)
        tracker = load_tracker(root)
    except ManifestError as e:
        print(f"ath issue: {e}", file=sys.stderr)
        return 2

    if args.cmd == "list":
        if args.offline:
            rows = _read_snapshot_titles(tracker.snapshot)
            if not rows:
                print(f"ath issue: no snapshot at {tracker.snapshot}", file=sys.stderr)
                return 1
            print(f"(offline — {tracker.snapshot.name})")
            print("\n".join(rows))
            return 0
        try:
            issues = fetch_issues(tracker, args.state)
        except TrackerError as e:
            print(f"ath issue: {e}\n  try --offline for the committed snapshot", file=sys.stderr)
            return 1
        for i in issues:
            if _is_tombstone(i):
                continue
            labs = _labels(i)
            if args.label and not set(args.label) <= set(labs):
                continue
            state = " " if i["state"] == "open" else "x"
            print(f"[{state}] #{i['number']:<4} {i['title'][:66]:<66} {','.join(labs)}")
        return 0

    if args.cmd == "show":
        try:
            issue = _get(tracker, f"{tracker.issues_path}/{args.number}")
            comments = _get(tracker, f"{tracker.issues_path}/{args.number}/comments") or []
        except TrackerError as e:
            print(f"ath issue: {e}", file=sys.stderr)
            return 1
        print(f"#{issue['number']} [{issue['state']}] {issue['title']}")
        print(f"  {' '.join(_labels(issue))}")
        print(f"  {issue['html_url']}\n")
        print(issue.get("body") or "(no body)")
        for c in comments:
            print(f"\n--- {c['user']['login']} · {c['created_at']} ---")
            print(c.get("body") or "")
        return 0

    if args.cmd == "sync":
        try:
            issues = fetch_issues(tracker, "all")
        except TrackerError as e:
            print(f"ath issue: {e}", file=sys.stderr)
            return 1
        rendered = _render_snapshot(tracker, issues)
        current = tracker.snapshot.read_text(encoding="utf-8") if tracker.snapshot.is_file() else ""
        if args.check:
            if rendered == current:
                print(f"snapshot current ({tracker.snapshot})")
                return 0
            print(f"snapshot STALE ({tracker.snapshot}) — run `ath issue sync`", file=sys.stderr)
            return 1
        tracker.snapshot.parent.mkdir(parents=True, exist_ok=True)
        tracker.snapshot.write_text(rendered, encoding="utf-8")
        live = [i for i in issues if not _is_tombstone(i)]
        verb = "unchanged" if rendered == current else "written"
        n_open = sum(1 for i in live if i["state"] == "open")
        print(f"{tracker.snapshot} {verb} — {n_open} open, {len(live) - n_open} closed")
        return 0

    return 2
