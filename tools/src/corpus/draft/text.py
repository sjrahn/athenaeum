"""text/* — the verbatim-passthrough drafter for a textual type no specialized drafter serves.

spec/corpus.md §6.2 / the per-format inventory: a markdown or plain-text record's `body` is
its own text (passthrough). The same holds for any `text/*` type the corpus has no richer
drafter or declared strategy for — code (`text/javascript`), delimited data
(`text/tab-separated-values`, `text/csv`), prose (`text/markdown`, `text/plain`). It is the
family default, never an override: an id-keyed drafter (`text/text_html`) or a schema's
`draft.strategy:` (`vcard-manifest`) always wins (`corpus.derive.resolve_drafter`).

The drafter emits ONE `text/code` segment spanning every line, exactly as the JSON drafter
does. The fence keeps the text inert inside the content zone, so a markdown file's own
`<!--…-->` or headings are carried, never parsed as record structure. It attests nothing:
what a given text MEANS is overlay guidance plus ledger knowledge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from corpus import recordbuild
from corpus.draft import DrafterResult
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.segments import Segment

# the `language:` a `text/code` segment carries — the subtype, where it is not itself one
_LANGUAGE = {
    "plain": "text",
    "tab-separated-values": "tsv",
    "x-python": "python",
    "x-shellscript": "sh",
}


def language_for(media_type: str) -> str:
    subtype = media_type.partition("/")[2].partition(";")[0].strip().lower()
    return _LANGUAGE.get(subtype, subtype or "text")


def draft_for(media_type: str):
    """The verbatim drafter bound to `media_type`'s language."""

    def draft(
        text_path: Path,
        *,
        build: recordbuild.Build,
        corpus_root: Path | None = None,
        record_id: str | None = None,
        record_metadata: dict[str, Any] | None = None,
        canonical_algo: str | None = None,
        fingerprint: bool | str | list[str] = False,
    ) -> DrafterResult:
        text = text_path.read_bytes().decode("utf-8-sig", errors="replace")
        n_lines = max(1, text.count("\n") + (0 if text.endswith("\n") else 1))
        recordbuild.add_blocks(
            build,
            [
                Segment(
                    atom="text",
                    overlay="text/code",
                    address=f"line=1-{n_lines}" if n_lines > 1 else "line=1",
                    perceptual=text_fingerprints(text, algos_for_atom("text", fingerprint)),
                    body=text,
                    extra={"language": language_for(media_type)},
                )
            ],
        )
        return {
            "fields": {},
            "embeds": [],
            "issues": [],
            "canonical": None,
            "origin_uri_aliases": [],
        }

    return draft
