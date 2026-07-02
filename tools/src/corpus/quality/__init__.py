"""Quality-signal catalogs for capture / ingest / drafter detectors.

`signatures` holds the static regex tables and thresholds; the detector functions
that consume them live with the code that runs them (`corpus.capture`, the
drafters). Kept as a separate package so the catalogs can be imported without
pulling in Playwright / yt-dlp.
"""
