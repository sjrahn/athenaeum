"""Capture a Claude Code session into the corpus, or list discoverable sessions.

    corpus session capture <session-id | path/to/<id>.jsonl> [--project P] [--from HOST]
    corpus session list [--project P] [--from HOST]

`capture` bundles a session (the `<id>.jsonl` transcript + its `<id>/` sidecar tree of
sub-agent transcripts, tool results, and workflow state) into ONE deterministic zstd-zip
staged in `capture/`, mints the `claude-code-session` producer-export sidecar, then ingests
and drafts it — the transcript members land as directly-addressed `path=<member>` embeds
(never transcribed). Sessions are personal by nature (a transcript embeds every tool result
verbatim), so this belongs in **corpus-private**.

Identity is the bundle's blake3, so a re-capture after more turns is a NEW record. When a
prior capture of the same session exists, `capture` proves continuity (`corpus.continuity`):
if the new bundle CONTAINS the old (the append-only case), it reports the supersession and
the exact `ath ledger supersede` command to rewrite any citations; if the old capture is NOT
contained (a compacted / truncated session), it keeps both and warns rather than clobber the
fuller copy.

`--from HOST` pulls the session off another machine over ssh/rsync first (recording HOST as
the source), so sessions from every box fold into one corpus.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from corpus import ccsession, continuity, hashing, paths
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_cap = sub.add_parser("capture", help="Bundle a session → ingest → draft (with supersession).")
    p_cap.add_argument("target", help="session id, or a path to its <id>.jsonl transcript")
    p_cap.add_argument("--project", help="narrow discovery to one ~/.claude/projects/<dir> subdir")
    p_cap.add_argument("--from", dest="from_host", metavar="HOST",
                       help="pull the session from another machine via ssh ([user@]host)")
    p_cap.add_argument("--no-draft", action="store_true",
                       help="stop after ingest (leave the record a stub)")
    add_corpus_root_arg(p_cap)

    p_list = sub.add_parser("list", help="List discoverable sessions with stats.")
    p_list.add_argument("--project", help="narrow to one ~/.claude/projects/<dir> subdir")
    p_list.add_argument("--from", dest="from_host", metavar="HOST",
                        help="list sessions on another machine via ssh ([user@]host)")
    add_corpus_root_arg(p_list)


def run(args: argparse.Namespace) -> int:
    if args.action == "list":
        return _list(args)
    if args.action == "capture":
        return _capture(args)
    print(f"unknown action: {args.action}", file=sys.stderr)
    return 2


# --------------------------------------------------------------------------- capture


def _capture(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    staging: Path | None = None

    # 1. Locate the session — locally, or fetched from a remote host first.
    try:
        if args.from_host:
            staging = corpus_root / "capture" / ".session-staging" / _sanitize(args.from_host) / args.target
            sp = ccsession.ssh_fetch(args.from_host, args.target, staging, project=args.project)
        else:
            sp = ccsession.find_session(args.target, project=args.project)
    except (FileNotFoundError, ValueError, ccsession.SessionSourceError) as e:
        sys.exit(str(e))

    stats = ccsession.session_stats(sp)
    captured_at = ccsession.now_iso()
    snapshot = stats.activity_end or captured_at
    priors = ccsession.find_prior_sessions(corpus_root, stats.session_id, sp.host)

    # 2. Pack the deterministic bundle + mint the capture sidecar.
    zip_path = corpus_root / "capture" / f"{stats.session_id}.zip"
    members = ccsession.collect_members(sp)
    size = ccsession.build_bundle(
        members, zip_path, comment=ccsession.bundle_comment(sp, stats)
    )
    record_id = hashing.hash_file(zip_path, also=())["blake3"]
    already = paths.record_path(corpus_root, record_id).is_file()
    fields = ccsession.origin_fields(sp, stats, captured_at=captured_at)
    ccsession.write_sidecar(zip_path, fields, snapshot=snapshot)

    print(
        f"session {stats.session_id} @{sp.host}: {len(members)} files, "
        f"{stats.record_count} records, {size:,} bundle bytes → {record_id[:12]}…",
        file=sys.stderr,
    )

    # 3. Ingest through the real command (dedup, grammar validation, dump). 3.0: ingest
    # attests the session bundle's byte-facts (its members as `path=` embeds) at stub time —
    # there is no separate draft stage; the transcript body is a derivation op (§6.2). The
    # `--no-draft` flag is retained as a no-op for caller compatibility.
    from corpus._cli import dispatch

    rc = dispatch(["ingest", str(zip_path), "--corpus-root", str(corpus_root)])
    if rc != 0:
        _cleanup_staging(staging)
        sys.exit("session capture: ingest failed")

    _cleanup_staging(staging)

    # 4. Supersession — prove continuity against any prior capture of this session.
    _report_supersession(corpus_root, record_id, priors, already=already, new_count=stats.record_count)

    print(paths.record_path(corpus_root, record_id))
    return 0


def _report_supersession(
    corpus_root: Path, new_id: str, priors, *, already: bool, new_count: int
) -> None:
    if already:
        print("re-encounter: byte-identical to an existing record — nothing new captured.")
        return
    for p in priors:
        if p.record_id == new_id:
            continue
        cont = continuity.continuity(corpus_root, p.record_id, new_id)
        if cont.contains_a:
            print(
                f"supersedes {p.record_id[:12]}… ({p.record_count} → {new_count} records; "
                f"new capture contains all of the prior)."
            )
            print("  → rewrite citations + retire the old bytes:")
            print(f"    ath ledger supersede {p.record_id} {new_id} --retire")
        else:
            addrs = len(cont.diverged)
            print(
                f"WARNING: prior {p.record_id[:12]}… is NOT contained in this capture "
                f"({addrs} address(es) diverged) — a compacted or truncated session. "
                f"Keeping both; not superseding."
            )


# --------------------------------------------------------------------------- list


def _list(args: argparse.Namespace) -> int:
    if args.from_host:
        try:
            ids = ccsession.ssh_list(args.from_host)
        except ccsession.SessionSourceError as e:
            sys.exit(str(e))
        for sid in ids:
            print(sid)
        if not ids:
            print(f"(no sessions found on {args.from_host})", file=sys.stderr)
        return 0

    sessions = ccsession.iter_sessions(project=args.project)
    if not sessions:
        print("(no sessions discoverable under ~/.claude/projects)", file=sys.stderr)
        return 0
    for sp in sessions:
        st = sp.transcript.stat()
        records_n = _line_count(sp.transcript)
        mtime = datetime.fromtimestamp(st.st_mtime, UTC).strftime("%Y-%m-%d %H:%M")
        subs = 0
        if sp.sidecar is not None and (sp.sidecar / "subagents").is_dir():
            subs = sum(1 for _ in (sp.sidecar / "subagents").glob("agent-*.jsonl"))
        print(
            f"{sp.session_id}  {records_n:>6} rec  {subs:>3} sub  "
            f"{st.st_size / 1_048_576:>7.1f} MB  {mtime}  {sp.project_dir}"
        )
    return 0


# --------------------------------------------------------------------------- helpers


def _line_count(path: Path) -> int:
    """Fast transcript line count (records) without JSON parsing."""
    n = 0
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            n += chunk.count(b"\n")
    return n


def _sanitize(host: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in host)


def _cleanup_staging(staging: Path | None) -> None:
    if staging is not None and staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
