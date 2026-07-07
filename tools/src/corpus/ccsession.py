"""Claude Code session capture — the domain layer behind `corpus session`.

A Claude Code session lives on disk as a transcript plus a sidecar tree:

    ~/.claude/projects/<mangled-cwd>/<session-id>.jsonl        # the main transcript
    ~/.claude/projects/<mangled-cwd>/<session-id>/             # sidecar tree
        subagents/agent-<name>-<hash>.jsonl (+ .meta.json)     #   dispatched agents
        tool-results/<id>.txt · pdf-<id>/page-N.jpg            #   overflow tool payloads
        workflows/wf_<id>.json                                 #   workflow scripts/state

This module gathers those files, stats the transcript, and packs the union into ONE
deterministic zstd-zip (`corpus.assembly.write_bundle` — the reusable writer core spec
§12.8 reserves for a producer-side bundler like this) staged in `capture/`, alongside a
capture sidecar that binds the `claude-code-session` producer-export origin (uri-less,
carrying the session's identity as structured `origin_fields` — the `imessage-export`
pattern, spec §7.2). Ingest → the `zip-manifest` draft turns each member into a
directly-addressed `path=<member>` embed; the transcript is never transcribed.

Identity is the bundle's blake3 (spec §2). A session grows turn-by-turn, so a re-capture
is a genuinely NEW record — supersession keeps the more complete version, proven by
`corpus.continuity` (B may retire A only when B contains all of A). No synthetic URI.

Everything here is pure filesystem + subprocess (ssh/rsync for the `--from` path); it holds
no corpus knowledge beyond the record helpers, and never runs git.
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import assembly, records

log = logging.getLogger("corpus.session")

ORIGIN_SCHEMA = "claude-code-session"
_TRANSCRIPT_SUFFIX = ".jsonl"
# The transcript is already-compact JSON text that zstd shrinks well — let the writer core's
# extension routing compress it (jsonl/json/txt are not in the already-compressed set).


# --------------------------------------------------------------------------- discovery


@dataclass(frozen=True)
class SessionPaths:
    """Where a session's bytes live and how to name it."""

    session_id: str
    transcript: Path  # <id>.jsonl
    sidecar: Path | None  # <id>/ dir, or None when the session spawned no sidecar files
    project_dir: str  # the `~/.claude/projects/<name>` subdir basename (mangled cwd)
    host: str  # source machine label (local hostname, or the --from host)


def home_projects_dir(home: Path | None = None) -> Path:
    """`~/.claude/projects` — the root of Claude Code's per-project session store."""
    return (home or Path.home()) / ".claude" / "projects"


def local_host() -> str:
    """This machine's short hostname — the `host` recorded on a locally-captured session."""
    return socket.gethostname().split(".", 1)[0]


def _session_paths_for(transcript: Path, host: str) -> SessionPaths:
    session_id = transcript.name[: -len(_TRANSCRIPT_SUFFIX)]
    sidecar = transcript.with_suffix("")  # <dir>/<id>
    return SessionPaths(
        session_id=session_id,
        transcript=transcript,
        sidecar=sidecar if sidecar.is_dir() else None,
        project_dir=transcript.parent.name,
        host=host,
    )


def find_session(
    target: str,
    *,
    project: str | None = None,
    projects_dir: Path | None = None,
    host: str | None = None,
) -> SessionPaths:
    """Locate a session by id (or by a direct path to its `<id>.jsonl`).

    `target` is a session id — globbed under `projects_dir` (optionally narrowed to the
    `project` subdir) — or a filesystem path to a transcript. Raises `FileNotFoundError`
    when nothing matches and `ValueError` when an id is ambiguous across projects."""
    host = host or local_host()
    p = Path(target)
    if p.is_file() and p.suffix == _TRANSCRIPT_SUFFIX:
        return _session_paths_for(p.resolve(), host)

    root = projects_dir or home_projects_dir()
    scope = root / project if project else root
    matches = sorted(scope.glob(f"*/{target}{_TRANSCRIPT_SUFFIX}")) if not project \
        else sorted(scope.glob(f"{target}{_TRANSCRIPT_SUFFIX}"))
    if not matches:
        raise FileNotFoundError(
            f"no session {target!r} under {scope} (looked for <project>/{target}.jsonl)"
        )
    if len(matches) > 1:
        locs = ", ".join(m.parent.name for m in matches)
        raise ValueError(
            f"session id {target!r} is ambiguous across projects ({locs}); pass --project"
        )
    return _session_paths_for(matches[0].resolve(), host)


def iter_sessions(
    *, project: str | None = None, projects_dir: Path | None = None, host: str | None = None
) -> list[SessionPaths]:
    """Every discoverable session (optionally within one `project` subdir), newest first."""
    host = host or local_host()
    root = projects_dir or home_projects_dir()
    scope = [root / project] if project else sorted(p for p in root.glob("*") if p.is_dir())
    out: list[SessionPaths] = []
    for proj in scope:
        for tr in proj.glob(f"*{_TRANSCRIPT_SUFFIX}"):
            out.append(_session_paths_for(tr.resolve(), host))
    out.sort(key=lambda sp: sp.transcript.stat().st_mtime, reverse=True)
    return out


# --------------------------------------------------------------------------- stats


@dataclass
class SessionStats:
    session_id: str
    record_count: int  # transcript lines — the monotonic completeness metric
    message_count: int  # user + assistant turns (human-facing)
    subagent_count: int  # dispatched sub-agent transcripts (sidecar files)
    cwd: str  # the session's predominant working directory
    claude_code_version: str  # highest CLI version observed in the transcript
    activity_start: str  # first record timestamp (ISO-8601), or ""
    activity_end: str  # last record timestamp (ISO-8601), or ""


def session_stats(sp: SessionPaths) -> SessionStats:
    """Parse the transcript (tolerantly) for completeness + provenance fields."""
    record_count = 0
    message_count = 0
    cwds: Counter[str] = Counter()
    versions: set[str] = set()
    session_id = sp.session_id
    first_ts = ""
    last_ts = ""
    with sp.transcript.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            record_count += 1
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("type") in ("user", "assistant"):
                message_count += 1
            if cwd := r.get("cwd"):
                cwds[str(cwd)] += 1
            if v := r.get("version"):
                versions.add(str(v))
            if sid := (r.get("sessionId") or r.get("session_id")):
                session_id = str(sid)
            if ts := r.get("timestamp"):
                ts = str(ts)
                first_ts = first_ts or ts
                if ts > last_ts:
                    last_ts = ts

    subagent_count = 0
    if sp.sidecar is not None:
        subdir = sp.sidecar / "subagents"
        if subdir.is_dir():
            subagent_count = sum(1 for _ in subdir.glob("agent-*.jsonl"))

    return SessionStats(
        session_id=session_id,
        record_count=record_count,
        message_count=message_count,
        subagent_count=subagent_count,
        cwd=cwds.most_common(1)[0][0] if cwds else "",
        claude_code_version=max(versions) if versions else "",
        activity_start=first_ts,
        activity_end=last_ts,
    )


# --------------------------------------------------------------------------- bundle


def collect_members(sp: SessionPaths) -> list[tuple[str, Path]]:
    """`(bundle-relpath, source-path)` for every file of the session, mirroring the on-disk
    tree: the transcript at `<id>.jsonl`, sidecar files under `<id>/…`. Sorted, so the
    bundle is deterministic regardless of directory-walk order."""
    members: list[tuple[str, Path]] = [
        (f"{sp.session_id}{_TRANSCRIPT_SUFFIX}", sp.transcript)
    ]
    if sp.sidecar is not None:
        for f in sp.sidecar.rglob("*"):
            if f.is_file():
                rel = f.relative_to(sp.sidecar).as_posix()
                members.append((f"{sp.session_id}/{rel}", f))
    members.sort(key=lambda m: m[0])
    return members


def _file_opener(path: Path):
    """A re-openable byte source for the writer core (called once, streamed)."""
    return lambda: path.open("rb")


def build_bundle(members: list[tuple[str, Path]], out_path: Path, *, comment: str) -> int:
    """Pack `members` into the deterministic zstd-zip at `out_path`; return its byte size.
    Member mtimes come from disk (so an unchanged session re-bundles byte-identically), and
    the writer core stamps the archive `comment` with the session identity."""
    bundle_members = [
        assembly.BundleMember(
            path=rel,
            open_stream=_file_opener(src),
            date_time=assembly.epoch_to_dostuple(src.stat().st_mtime),
            size=src.stat().st_size,
        )
        for rel, src in members
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return assembly.write_bundle(bundle_members, out_path, comment=comment)


def now_iso() -> str:
    """Current instant as ISO-8601 UTC seconds with a `Z` suffix (the capture stamp)."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def origin_fields(sp: SessionPaths, stats: SessionStats, *, captured_at: str) -> dict:
    """The structured provenance stamped on the record's `claude-code-session` origin block."""
    fields = {
        "session_id": stats.session_id,
        "host": sp.host,
        "project_dir": sp.project_dir,
        "cwd": stats.cwd,
        "claude_code_version": stats.claude_code_version,
        "record_count": stats.record_count,
        "message_count": stats.message_count,
        "subagent_count": stats.subagent_count,
        "captured_at": captured_at,
    }
    if stats.activity_start:
        fields["activity_start"] = stats.activity_start
    if stats.activity_end:
        fields["activity_end"] = stats.activity_end
    return {k: v for k, v in fields.items() if v not in ("", None)}


def write_sidecar(zip_path: Path, fields: dict, *, snapshot: str) -> Path:
    """Mint the `<bundle>.capture.yaml` ingest consumes: a uri-less producer-export origin
    (`origin_schema` + `origin_fields`; `fetched_at` → the origin snapshot). No `source_url`
    — a session has nothing to re-fetch (spec §7.2, the imessage-export shape)."""
    import yaml

    sidecar = zip_path.with_suffix(zip_path.suffix + ".capture.yaml")
    payload = {
        "fetched_at": snapshot,
        "origin_schema": ORIGIN_SCHEMA,
        "origin_fields": fields,
    }
    sidecar.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return sidecar


def bundle_comment(sp: SessionPaths, stats: SessionStats) -> str:
    """The archive comment stamped on the zip (surfaces as the record's artifact `comment`).

    Deterministic for a given session STATE — it names the session's identity and shape
    (record count, activity end), never the wall-clock capture time. A capture-time stamp
    here would perturb the bundle bytes on every run, so an unchanged session would mint a
    new record instead of folding as a byte-identical re-encounter. `captured_at` lives on
    the origin block (via the sidecar), which does not reach the zip bytes."""
    return (
        f"claude-code-session {stats.session_id} @{sp.host} · "
        f"{stats.record_count} records · through {stats.activity_end or 'unknown'}"
    )


# --------------------------------------------------------------------------- prior scan


@dataclass(frozen=True)
class PriorSession:
    record_id: str
    record_count: int  # what the prior capture recorded (0 when the field is absent)


def find_prior_sessions(corpus_root: Path, session_id: str, host: str) -> list[PriorSession]:
    """Records already holding this session (same `session_id` + `host` on a
    `claude-code-session` origin block) — the supersession candidates. A structured
    origin-FIELD match, not a URI match (there is no session URI)."""
    out: list[PriorSession] = []
    for _path, post in records.load_all(corpus_root):
        for origin in records.iter_origin_blocks(post):
            if (origin.get("id") or "") != ORIGIN_SCHEMA:
                continue
            fields = origin.get("fields") or {}
            if str(fields.get("session_id") or "") != session_id:
                continue
            if str(fields.get("host") or "") != host:
                continue
            rid = str(post.metadata.get("id") or "")
            try:
                count = int(fields.get("record_count") or 0)
            except (TypeError, ValueError):
                count = 0
            out.append(PriorSession(record_id=rid, record_count=count))
            break
    return out


# --------------------------------------------------------------------------- SSH sourcing


class SessionSourceError(RuntimeError):
    """A session could not be located or fetched from a remote host."""


def _run(cmd: list[str], *, capture: bool = True) -> subprocess.CompletedProcess:
    log.debug("run: %s", " ".join(cmd))
    return subprocess.run(cmd, text=True, capture_output=capture, check=False)


def ssh_find_transcript(host: str, session_id: str, *, project: str | None = None) -> str:
    """The remote path of `<session_id>.jsonl` on `host` (via `ssh … ls`). Raises
    `SessionSourceError` when absent or ambiguous."""
    pattern = (
        f"~/.claude/projects/{project}/{session_id}.jsonl"
        if project
        else f"~/.claude/projects/*/{session_id}.jsonl"
    )
    proc = _run(["ssh", host, f"ls -1d {pattern} 2>/dev/null"])
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        raise SessionSourceError(f"no session {session_id!r} on {host} (looked for {pattern})")
    if len(lines) > 1:
        raise SessionSourceError(
            f"session {session_id!r} is ambiguous on {host} ({len(lines)} matches); pass --project"
        )
    return lines[0]


def ssh_fetch(
    host: str, session_id: str, staging: Path, *, project: str | None = None
) -> SessionPaths:
    """Pull a remote session's transcript + `<id>/` sidecar into `staging` (rsync `-a`,
    preserving mtimes so the bundle stays deterministic; `scp -rp` fallback) and return its
    local `SessionPaths`. `host` is recorded as the source machine."""
    remote_transcript = ssh_find_transcript(host, session_id, project=project)
    project_dir = remote_transcript.rsplit("/", 2)[-2]
    remote_sidecar = remote_transcript[: -len(_TRANSCRIPT_SUFFIX)]

    staging.mkdir(parents=True, exist_ok=True)
    local_transcript = staging / f"{session_id}{_TRANSCRIPT_SUFFIX}"
    local_sidecar = staging / session_id

    if not _rsync(f"{host}:{_shq(remote_transcript)}", local_transcript) and not _scp(
        f"{host}:{_shq(remote_transcript)}", local_transcript, recursive=False
    ):
        raise SessionSourceError(f"failed to fetch transcript from {host}:{remote_transcript}")
    # The sidecar dir may not exist; a fetch failure there is tolerated (a session with no
    # sub-agents/tool-results is legitimate).
    local_sidecar.mkdir(exist_ok=True)
    if not _rsync(f"{host}:{_shq(remote_sidecar)}/", local_sidecar, dir_contents=True):
        _scp(f"{host}:{_shq(remote_sidecar)}", staging, recursive=True)

    host_label = host.split("@", 1)[-1].split(".", 1)[0]
    return SessionPaths(
        session_id=session_id,
        transcript=local_transcript,
        sidecar=local_sidecar if any(local_sidecar.rglob("*")) else None,
        project_dir=project_dir,
        host=host_label,
    )


def ssh_list(host: str) -> list[str]:
    """Session ids discoverable on `host` (one per line from a remote glob)."""
    proc = _run(["ssh", host, "ls -1 ~/.claude/projects/*/*.jsonl 2>/dev/null"])
    ids: list[str] = []
    for ln in (proc.stdout or "").splitlines():
        ln = ln.strip()
        if ln.endswith(_TRANSCRIPT_SUFFIX):
            ids.append(Path(ln).name[: -len(_TRANSCRIPT_SUFFIX)])
    return ids


def _shq(path: str) -> str:
    """Keep a leading `~` shell-expandable while quoting nothing else (paths here are our
    own globs, not user free-text)."""
    return path


def _rsync(src: str, dst: Path, *, dir_contents: bool = False) -> bool:
    src_arg = src if not dir_contents else (src if src.endswith("/") else src + "/")
    proc = _run(["rsync", "-a", src_arg, str(dst) + ("/" if dir_contents else "")])
    return proc.returncode == 0


def _scp(src: str, dst: Path, *, recursive: bool) -> bool:
    cmd = ["scp", "-p"] + (["-r"] if recursive else []) + [src, str(dst)]
    proc = _run(cmd)
    return proc.returncode == 0
