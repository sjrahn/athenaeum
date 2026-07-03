"""The build — resolve · raster · link · leak-check · certify (`spec/codex.md` §5, §6).

Compiles the generated vault into a renderer-ready content tree: every
`corpus://` footnote resolves to a human citation, every functional-URI embed
rasters through the corpus resolver into a static asset, the public-profile
leak check walks the OUTPUT, and the build certificate freezes the
reproducibility tuple. The site renderer (Quartz, the reference deployment)
consumes the content tree; rendering is presentation, these obligations are
the contract.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from codex.manifest import CodexManifest
from codex.notes import fact_private, generate
from codex.scope import materialize
from ledger.corpora import CorpusJoin, _read_frontmatter
from ledger.model import CORPUS_URI_RE

_EMBED_RE = re.compile(r"!\[\[(corpus://[^\]|]+)(?:\|([^\]]*))?\]\]")
_FOOTNOTE_URI_RE = re.compile(r"`(corpus://[0-9a-f]{64}[^`]*)`")
_HASH_RE = re.compile(r"[0-9a-f]{64}")


class BuildError(RuntimeError):
    pass


@dataclass
class BuildResult:
    profile: str
    notes: int = 0
    citations: int = 0
    rastered: int = 0
    certificate: Path | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _human_citation(join: CorpusJoin, uri: str) -> str | None:
    m = CORPUS_URI_RE.match(uri)
    if not m:
        return None
    holders = join.holders(m.group(1))
    if not holders:
        return None
    fm = _read_frontmatter(join.record_path(holders[0].root, m.group(1)))
    title = str(fm.get("title") or "").strip() or f"record {m.group(1)[:12]}…"
    return title


def _git_commit(path: Path) -> str:
    res = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                         capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else "unversioned"


def build(
    manifest: CodexManifest,
    ledger_root: Path,
    join: CorpusJoin,
    *,
    profile: str = "private",
    out_dir: Path | None = None,
    today: str = "",
) -> BuildResult:
    if profile != "private" and profile not in manifest.profiles:
        raise BuildError(f"profile {profile!r} not declared in codex.yaml")
    if not join.complete:
        # with a registered corpus absent, every hash it holds resolves nowhere
        # and sensitivity cannot be derived — the wall would fail open (§6.4)
        raise BuildError(
            f"corpus join incomplete — missing on disk: {', '.join(join.missing)}; "
            "sensitivity is underivable, refusing to build (run `ath sync`)")
    redact = str((manifest.profiles.get(profile) or {}).get("redact", "exclude"))
    res = BuildResult(profile=profile)

    scoped, riding, problems = materialize(ledger_root, manifest)
    res.problems += [p for p in problems if "scope root" in p]
    vault = generate(scoped, riding, join, profile=profile, redact=redact, today=today)
    out = out_dir or (manifest.root / "build" / profile)
    content = out / "content"
    if content.exists():
        shutil.rmtree(content)
    (content / "assets").mkdir(parents=True)

    cited: dict[str, str] = {}  # hash -> latest touch (for the certificate)

    def raster(match: re.Match) -> str:
        uri = match.group(1)
        alt = match.group(2) or "embed"
        m = CORPUS_URI_RE.match(uri)
        if not m:
            res.problems.append(f"embed {uri!r}: not a corpus URI")
            return match.group(0)
        h = m.group(1)
        holders = join.holders(h)
        if not holders:
            res.problems.append(f"embed corpus://{h[:12]}…: resolves in no corpus")
            return match.group(0)
        if profile != "private" and join.is_private(h):
            res.problems.append(f"embed corpus://{h[:12]}…: private asset in a "
                                f"{profile} build")
            return match.group(0)
        from corpus import functional_uri, resolver

        try:
            src = resolver.resolve(uri, holders[0].root)
        except Exception as e:
            res.problems.append(f"embed corpus://{h[:12]}…: raster failed — {e}")
            return match.group(0)
        cited[h] = join.touch(h)
        name = functional_uri.urihash(functional_uri.canonical(
            functional_uri.parse(uri))) + src.suffix
        shutil.copyfile(src, content / "assets" / name)
        res.rastered += 1
        return f"![{alt}](assets/{name})"

    def cite(match: re.Match) -> str:
        uri = match.group(1)
        m = CORPUS_URI_RE.match(uri)
        if m:
            cited[m.group(1)] = join.touch(m.group(1))
        title = _human_citation(join, uri)
        if title is None:
            res.problems.append(f"citation {uri[:60]}… resolves in no corpus")
            return match.group(0)
        res.citations += 1
        return f"{title} — `{uri}`"

    for relpath, text in vault.items():
        text = _EMBED_RE.sub(raster, text)
        text = _FOOTNOTE_URI_RE.sub(cite, text)
        dest = content / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        res.notes += 1

    (content / "index.md").write_text(
        f"---\ntitle: {manifest.display_name}\n---\n\n"
        f"{manifest.description}\n\n"
        f"*Built from the ledger — profile: {profile}. Every assertion traces "
        "to captured evidence.*\n",
        encoding="utf-8",
    )

    # ---------------------------------------------------- leak check (§6)
    if profile != "private":
        private_ids = {fid for fid, o in scoped.items() if fact_private(o, join)}
        for f in sorted(content.rglob("*.md")):
            text = f.read_text(encoding="utf-8")
            for h in set(_HASH_RE.findall(text)):
                private = join.is_private(h)
                if private is not False:  # unresolvable fails closed
                    res.problems.append(
                        f"LEAK {f.relative_to(content)}: "
                        f"{'private' if private else 'unresolvable'} hash {h[:12]}…")
            for fid in private_ids:
                if fid in text:
                    res.problems.append(
                        f"LEAK {f.relative_to(content)}: id of fully-private "
                        f"fact {fid!r}")

    # ------------------------------------------------ certificate (§5.6)
    ledger_commit = _git_commit(ledger_root)
    codex_commit = _git_commit(manifest.root)
    try:
        from importlib.metadata import version

        tool = f"athenaeum@{version('athenaeum')}"
    except Exception:
        tool = "athenaeum@unknown"
    cert = {
        "codex": manifest.name,
        "profile": profile,
        "codex_commit": codex_commit,
        "ledger_commit": ledger_commit,
        "corpus_touches": dict(sorted(cited.items())),
        "reference_snapshots": {},
        "tool": tool,
        "built": today,
        "notes": res.notes,
        "rastered": res.rastered,
    }
    certs = manifest.root / "certificates"
    certs.mkdir(exist_ok=True)
    cert_path = certs / f"{profile}-{ledger_commit[:8]}-{codex_commit[:8]}.json"
    cert_path.write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8")
    res.certificate = cert_path
    return res
