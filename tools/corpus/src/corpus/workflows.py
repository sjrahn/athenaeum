"""Operating-mode runbooks for the corpus tooling (surfaced by `corpus workflow`).

These document how to *run* the tooling — the normalize loop's operating modes, the
queue's result lifecycle — as distinct from a record's `normalization.guidance`
(§7.4), which is about interpreting one artifact. They ship with the package as
markdown under `corpus/workflows/`, so they version with the tooling and are
maintained **once, centrally** — never copied into each corpus repo (the tooling
stays agnostic to any particular corpus). Updating a runbook is a tooling change,
out of band of the corpora.

A runbook file is plain markdown: an `# H1` title, a one-line summary paragraph,
free-form intro prose, then `## ` sections (the narrowable sub-topics — e.g. the
individual operating modes). `corpus workflow` lists the runbooks; `corpus workflow
<name>` shows the intro + its section index; `corpus workflow <name> <section>`
prints one section in full.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable

__all__ = ["Section", "Workflow", "get", "intro", "list_workflows", "sections", "slugify"]

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Workflow:
    name: str
    title: str
    summary: str
    body: str  # the full markdown


@dataclass(frozen=True)
class Section:
    slug: str
    title: str
    text: str  # the section, heading included


def _dir() -> Traversable:
    return files("corpus") / "workflows"


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s:
            break
    return fallback


def _summary(body: str) -> str:
    """First non-empty, non-heading line — the one-liner shown in the index."""
    for line in body.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    return ""


def _make(name: str, body: str) -> Workflow:
    return Workflow(name=name, title=_title(body, name), summary=_summary(body), body=body)


def list_workflows() -> list[Workflow]:
    """All packaged runbooks, by name."""
    d = _dir()
    if not d.is_dir():
        return []
    out: list[Workflow] = []
    for entry in sorted(d.iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".md") and entry.is_file():
            out.append(_make(entry.name[:-3], entry.read_text(encoding="utf-8")))
    return out


def get(name: str) -> Workflow | None:
    """One runbook by name, or None if there's no such file."""
    try:
        body = (_dir() / f"{name}.md").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    return _make(name, body)


def sections(body: str) -> list[Section]:
    """The `## ` sections of a runbook, in order (heading included in each `text`)."""
    matches = list(_SECTION_RE.finditer(body))
    out: list[Section] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        title = m.group(1)
        out.append(Section(slug=slugify(title), title=title, text=body[m.start() : end].rstrip()))
    return out


def intro(body: str) -> str:
    """The prose before the first `## ` section (title + summary + overview)."""
    m = _SECTION_RE.search(body)
    return body[: m.start()].rstrip() if m else body.rstrip()
