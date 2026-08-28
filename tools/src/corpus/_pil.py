"""Optional Pillow codec plugins, registered once for every `Image.open` in the package.

`pillow-heif` (the `media` extra, v41) teaches Pillow HEIC/HEIF — the iPhone still format,
the bulk of a 2026 photo-library export. Guard-imported: a base install simply cannot open a
HEIC (the image drafter reports it and `corpus reattest` skips the record) rather than
failing at import time. Every module that opens images imports this one for its side
effect, so the opener is registered before any `Image.open` can run.
"""

from __future__ import annotations

try:
    import pillow_heif
except ImportError:  # the `media` extra is not installed
    HEIF_AVAILABLE = False
else:
    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
