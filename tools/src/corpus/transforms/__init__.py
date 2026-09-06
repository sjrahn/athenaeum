"""Functional URI transformation registry (spec §6).

Each transformation is a handler function `(working_value, param_value, ctx) →
next_working_value`. Handlers are tagged with their input and output "kind" so the
resolver can dispatch and validate the pipeline at each step.

Kinds:

- `"pdf"`     — `pypdfium2.PdfDocument`
- `"pdfpage"` — `transforms.pdf.PdfPageRef` (a selected page; renders to image on demand)
- `"html"`    — `bs4.BeautifulSoup`
- `"image"`   — `PIL.Image.Image`
- `"video"`   — `pathlib.Path` (P5)
- `"audio"`   — `pathlib.Path` (P5)
- `"text"`    — `str` (P5)
- `"json"`    — `str` (a pre-serialized JSON document, cached as `.json`)
- `"zip"`     — `pathlib.Path` (the artifact `.zip`)
- `"tar"`     — `pathlib.Path` (the artifact `.tar` / `.tgz`; `tarfile` auto-detects gzip)
- `"mbox"`    — `pathlib.Path` (the artifact `.mbox`; `msg=<N>` streams one message out)
- `"vcard"`   — `pathlib.Path` (the artifact `.vcf`; `card=<N>` extracts one card's bytes)
- `"message"` — `pathlib.Path` (the artifact `.eml`; `part=<N>` decodes one MIME part)
- `"csv"`     — `pathlib.Path` (the artifact `.csv`; `row=<N>` selects one data row)
- `"csvrow"`  — `transforms.csv.CsvRowRef` (a selected row; renders to raw text on demand,
  like `pdfpage`; `col=<name-or-index>` narrows to one field)
- `"bytes"`   — `bytes` (a raw member, cached verbatim)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict


class RenderContext(TypedDict, total=False):
    dpi: int
    # The source artifact on disk. PDF text/probe ops read it via pypdf (the working
    # value is a pypdfium2 document); the resolver sets it for every resolve.
    artifact_path: object  # pathlib.Path
    # Audio transforms consume `transcriber` to call out to the configured
    # TranscriptionAdapter. P3 wires the injection seam; the resolver defaults it.
    transcriber: object  # corpus.transcription.TranscriptionAdapter
    # The audio `transcribe` transform stashes the adapter's raw payload here so a
    # future resolver enhancement can persist it next to the rendered cache file.
    transcription_payload: object  # dict
    # The video `frame` transform range-checks the requested timecode against this
    # when the resolver plumbs the source record's duration through.
    video_duration_seconds: float
    # Muxing-contract config (§6.2): `cut=precise|copy` (default "precise") and the
    # `stream_id=<id>[,<id>…]` selection list. Position-independent, like `dpi` — the
    # resolver extracts them once before the transform chain runs, and `time_range=`/
    # `format=`/`scenes=` read them to compose ffmpeg `-map` selection and cut semantics.
    cut_mode: str
    stream_ids: list
    # The mime schema's declared `csv_dialect:` (§7.1, `text_csv.yaml`), plumbed in once
    # by the resolver for every `csv`-working-kind resolve so `row=`/`col=` never hardcode
    # delimiter/quoting/header-presence knowledge (`transforms.csv`).
    csv_dialect: dict
    # The record's attested `addressing:` stamp (§7.1 — `{parser, elements}`), plumbed in
    # by the resolver from the artifact block. Its PRESENCE is the el= grammar dispatch
    # (3.6 path space vs the frozen legacy filtered index — `transforms.html.extract_el`);
    # its fields are the drift check (parser identity + element count).
    el_addressing: dict
    # A member-extraction transform's DECLARED facts about the member it just yielded
    # (§6.2 "Member re-chaining") — set by the handler, consumed (popped) by the resolver's
    # `_rechain_member` immediately after, never carried past that step. `member_mime` is the
    # container's own declaration of the member's type (a MIME part's Content-Type, refined
    # the way its embed is), used when the byte sniff finds nothing — a plain-text part has
    # no magic and no filename to guess from; `member_name` feeds the sniff's extension
    # refinement; `member_charset` decodes a terminal textual member faithfully.
    member_mime: str
    member_name: str
    member_charset: str
    # The ENCLOSING MESSAGE's bytes on disk (the `.eml` a `part=` was cut from), set by the
    # `part=` handler and read by the HTML transforms to materialize a `cid:` carrier —
    # an RFC 2392 reference to a sibling MIME part by Content-ID (§6.2 intra-container
    # references). Stays for the rest of the chain: the nearest enclosing message wins
    # (a nested message's own `part=` re-sets it).
    cid_source: object  # pathlib.Path


class NotMaterializable(ValueError):
    """The address names something REAL that has no byte surface to materialize.

    The distinction this type exists to make: `el=99` on a 12-element artifact names
    nothing and is a defect, while `el=3` naming a `<table>` names exactly what it says
    — the element is there, its content is text, and there is simply no file to render.
    A `text/data-table` segment citing that element is correct and complete; only the
    byte-materialization step has nothing to do.

    A ValueError subclass so every existing `except ValueError` / `except Exception`
    caller (the resolver's error surface, the ledger's tolerant anchor check) behaves
    exactly as before. Callers that need to tell a naming failure from a
    materialization gap — `corpus lint --resolve`, which would otherwise report a
    perfectly good text citation as broken provenance — catch this type instead of
    matching on message text."""


HandlerFunc = Callable[[Any, str | None, RenderContext], Any]


# ---------- op classes (spec §6.2 "Op classes", v43) ---------- #
#
# Every op — registry transform, record-level op, or bare address axis — belongs to exactly
# one class, declared ONCE here by param name (a class is a property of what the op NAMES,
# never of the working kind it runs on: `text` reads on a PDF page and on HTML alike; `bbox`
# addresses an image and a worksheet alike). The class decides where an op may appear:
#
#   address    — names a place in the bytes: the selectors, plus the frame-fixers and
#                region-subtractors a region is expressed with. Stored addresses and
#                evidence anchors are made of these.
#   reading    — the mechanical textual reading of an already-addressed place (the text
#                layer, the markup's text, the derived body, the attested roster). May end an
#                evidence anchor; never stored in an address (the segment IS the reading).
#   view       — a rendering for eyes, or its configuration. Never an anchor, never stored.
#   instrument — a measurement or proposal ABOUT the artifact, for the normalizer or the
#                querier. Never an anchor, never stored: citing one cites the tool.
#   engine     — model output (transcription). Citable only once a pass has consumed it into
#                the record with provenance (§6.4); never a live anchor.
#
# `register` refuses an unclassified param, so a new op cannot exist without its class —
# which is what makes `corpus inspect`'s per-mime op list ("what is available, and its place")
# complete by construction.
OP_CLASS_ADDRESS = "address"
OP_CLASS_READING = "reading"
OP_CLASS_VIEW = "view"
OP_CLASS_INSTRUMENT = "instrument"
OP_CLASS_ENGINE = "engine"
OP_CLASSES_ALL: frozenset[str] = frozenset(
    {OP_CLASS_ADDRESS, OP_CLASS_READING, OP_CLASS_VIEW, OP_CLASS_INSTRUMENT, OP_CLASS_ENGINE}
)

OP_CLASSES: dict[str, str] = {
    # address — selectors (§12.11 axes) …
    "el": OP_CLASS_ADDRESS, "page": OP_CLASS_ADDRESS, "block": OP_CLASS_ADDRESS,
    "sheet": OP_CLASS_ADDRESS, "row": OP_CLASS_ADDRESS, "col": OP_CLASS_ADDRESS,
    "line": OP_CLASS_ADDRESS, "time": OP_CLASS_ADDRESS, "time_range": OP_CLASS_ADDRESS,
    "frame": OP_CLASS_ADDRESS, "bbox": OP_CLASS_ADDRESS, "crop": OP_CLASS_ADDRESS,
    "region": OP_CLASS_ADDRESS, "turn": OP_CLASS_ADDRESS, "att": OP_CLASS_ADDRESS,
    "stream_id": OP_CLASS_ADDRESS, "extract_audio": OP_CLASS_ADDRESS,
    "card": OP_CLASS_ADDRESS, "prop": OP_CLASS_ADDRESS, "entry": OP_CLASS_ADDRESS,
    "item": OP_CLASS_ADDRESS, "attachment": OP_CLASS_ADDRESS, "path": OP_CLASS_ADDRESS,
    "msg": OP_CLASS_ADDRESS, "part": OP_CLASS_ADDRESS, "header": OP_CLASS_ADDRESS,
    "spine": OP_CLASS_ADDRESS,
    "selector": OP_CLASS_ADDRESS, "xpath": OP_CLASS_ADDRESS,
    # … the frame a region is measured in (lossless), and the disclosed region subtraction
    "rotate": OP_CLASS_ADDRESS, "auto_orient": OP_CLASS_ADDRESS, "cover": OP_CLASS_ADDRESS,
    # reading
    "text": OP_CLASS_READING, "body": OP_CLASS_READING, "members": OP_CLASS_READING,
    "outline": OP_CLASS_READING,
    # view — renderings and their configuration, delivery forms
    "render": OP_CLASS_VIEW, "fit": OP_CLASS_VIEW, "resize": OP_CLASS_VIEW,
    "mark": OP_CLASS_VIEW, "autocontrast": OP_CLASS_VIEW, "contrast": OP_CLASS_VIEW,
    "grayscale": OP_CLASS_VIEW, "format": OP_CLASS_VIEW, "dpi": OP_CLASS_VIEW,
    "cut": OP_CLASS_VIEW, "annotated": OP_CLASS_VIEW, "raw": OP_CLASS_VIEW,
    # instrument — measurements and proposals about the artifact
    "probe": OP_CLASS_INSTRUMENT, "words": OP_CLASS_INSTRUMENT,
    "geometry": OP_CLASS_INSTRUMENT, "scene": OP_CLASS_INSTRUMENT,
    "scenes": OP_CLASS_INSTRUMENT,
    # engine — model output
    "transcribe": OP_CLASS_ENGINE,
}


def op_class(param: str) -> str | None:
    """The declared class of an op / address axis by param name, or None for a name the
    system does not know (a `#fragment`, a typo) — callers decide what an unknown means."""
    return OP_CLASSES.get(param)


def anchor_class_defects(params) -> list[tuple[str, str]]:
    """The `(param, class)` pairs in an evidence anchor that may NOT appear there (spec
    §6.2 op classes; ledger.md §6.2/§13.2): a view, an instrument, or an engine op. An
    anchor is address-class ops, optionally ending in one reading; anything else cites a
    tool, not the source. Unknown params are not this function's finding."""
    out = []
    for key, _ in params:
        cls = OP_CLASSES.get(key)
        if cls in (OP_CLASS_VIEW, OP_CLASS_INSTRUMENT, OP_CLASS_ENGINE):
            out.append((key, cls))
    return out


@dataclass(frozen=True)
class Handler:
    input_kind: str
    output_kind: str
    func: HandlerFunc
    op_class: str


REGISTRY: dict[tuple[str, str], Handler] = {}


def register(input_kind: str, param_name: str, output_kind: str):
    """Decorator that registers a handler for `(input_kind, param_name)`. The param must
    be classified in `OP_CLASSES` (spec §6.2 op classes) — an op with no declared place
    cannot register, so the per-mime op list is complete by construction."""
    cls = OP_CLASSES.get(param_name)
    if cls is None:
        raise ValueError(
            f"transform param {param_name!r} has no op class — declare it in "
            f"`transforms.OP_CLASSES` (spec §6.2 op classes) before registering it"
        )

    def decorator(func: HandlerFunc) -> HandlerFunc:
        key = (input_kind, param_name)
        if key in REGISTRY:
            raise ValueError(f"handler already registered for {key}")
        REGISTRY[key] = Handler(
            input_kind=input_kind, output_kind=output_kind, func=func, op_class=cls
        )
        return func

    return decorator


def lookup(input_kind: str, param_name: str) -> Handler | None:
    return REGISTRY.get((input_kind, param_name))


# Importing the per-kind submodules registers their handlers.
from . import audio as _audio  # noqa: E402, F401
from . import csv as _csv  # noqa: E402, F401
from . import epub as _epub  # noqa: E402, F401
from . import html as _html  # noqa: E402, F401
from . import image as _image  # noqa: E402, F401
from . import mbox as _mbox  # noqa: E402, F401
from . import message as _message  # noqa: E402, F401
from . import pdf as _pdf  # noqa: E402, F401
from . import tar as _tar  # noqa: E402, F401
from . import vcard as _vcard  # noqa: E402, F401
from . import video as _video  # noqa: E402, F401
from . import zip as _zip  # noqa: E402, F401
