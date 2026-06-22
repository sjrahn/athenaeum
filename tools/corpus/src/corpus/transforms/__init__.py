"""Functional URI transformation registry (spec §6).

Each transformation is a handler function `(working_value, param_value, ctx) →
next_working_value`. Handlers are tagged with their input and output "kind" so the
resolver can dispatch and validate the pipeline at each step.

Kinds:

- `"pdf"`   — `pypdfium2.PdfDocument`
- `"html"`  — `bs4.BeautifulSoup`
- `"image"` — `PIL.Image.Image`
- `"video"` — `pathlib.Path` (P5)
- `"audio"` — `pathlib.Path` (P5)
- `"text"`  — `str` (P5)
- `"zip"`   — `pathlib.Path` (the artifact `.zip`)
- `"bytes"` — `bytes` (a raw member, cached verbatim)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict


class RenderContext(TypedDict, total=False):
    dpi: int
    # Audio transforms consume `transcriber` to call out to the configured
    # TranscriptionAdapter. P3 wires the injection seam; the resolver defaults it.
    transcriber: object  # corpus.transcription.TranscriptionAdapter
    # The audio `transcribe` transform stashes the adapter's raw payload here so a
    # future resolver enhancement can persist it next to the rendered cache file.
    transcription_payload: object  # dict
    # The video `frame` transform range-checks the requested timecode against this
    # when the resolver plumbs the source record's duration through.
    video_duration_seconds: float


HandlerFunc = Callable[[Any, str | None, RenderContext], Any]


@dataclass(frozen=True)
class Handler:
    input_kind: str
    output_kind: str
    func: HandlerFunc


REGISTRY: dict[tuple[str, str], Handler] = {}


def register(input_kind: str, param_name: str, output_kind: str):
    """Decorator that registers a handler for `(input_kind, param_name)`."""

    def decorator(func: HandlerFunc) -> HandlerFunc:
        key = (input_kind, param_name)
        if key in REGISTRY:
            raise ValueError(f"handler already registered for {key}")
        REGISTRY[key] = Handler(input_kind=input_kind, output_kind=output_kind, func=func)
        return func

    return decorator


def lookup(input_kind: str, param_name: str) -> Handler | None:
    return REGISTRY.get((input_kind, param_name))


# Importing the per-kind submodules registers their handlers.
from . import audio as _audio  # noqa: E402, F401
from . import epub as _epub  # noqa: E402, F401
from . import html as _html  # noqa: E402, F401
from . import image as _image  # noqa: E402, F401
from . import pdf as _pdf  # noqa: E402, F401
from . import video as _video  # noqa: E402, F401
from . import zip as _zip  # noqa: E402, F401
