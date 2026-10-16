# Generators for `testdata/synthetic/`

One script per family; the committed bytes are what the manifest pins (see `../../README.md`, "The synthetic
tier"). Run from the repo root.

| script | makes | tool, version | reproduces byte-for-byte |
| --- | --- | --- | --- |
| `procedure.ts` | `procedure.typ`, `procedure.pdf`, `../passes/<blake3>.p1.jsonl` | typst 0.15.1, bundled fonts; `pdf.words@1` for the pass | yes (typst, `set document(date: none)`) |
| `plain.ts` | `tidewatch-readme.md`, `tidewatch.js`, `address-book.json`, `address-cards.vcf`, `bracket.p21`, `media-manifest.tsv` | the script itself (a seeded LCG for the fabricated rows) | yes |
| `plain.ts` | `window.png`, `garden.jpg` | ImageMagick 7 (`magick`), `-strip`; the Exif APP1 of the JPEG is written by the script | no (encoder) |
| `plain.ts` | `countdown.mp4` | ffmpeg (libx264 + aac) | no (encoder, muxer timestamps) |
| `plain.ts` | `till-receipt.typ`, `till-receipt.pdf` | typst 0.15.1 | yes |
| `thread.ts` | `harbourboard-thread.html` | the script itself | yes |
| `conversation-page.ts` | `quay-messages.html` + `.capture.yaml` | the script itself (`lib/png.ts` for the inlined images) | yes |
| `manual-page.ts` | `pump-service-manual.html` | the script itself | yes |
| `bundles.ts` | `facebook-/instagram-/threads-month-bundle.zip`, `*-thread.json`, `chat-month-bundle.zip`, `chat-space.json`, `messages-week-bundle.zip`, `mail-month-bundle.zip`, each with a `.capture.yaml` | the script itself (`lib/zip.ts`, `lib/png.ts`; the gif and mp4 members are the committed synthetic files) | yes |
| `bundles.ts` | `photos-month-bundle.zip` | heif-enc, ImageMagick, ffmpeg for the originals | no (encoders) |
| `bundles2.ts` | `orders-delivery.zip`, `rides-export.zip`, `health-export.zip`, `host-diagnostics.zip`, `vault-subtree.zip`, `vendor-share.zip`, `agent-session.zip`, `takeout-slice.zip`, `profile-year.zip`, each with a `.capture.yaml` | the script itself (`lib/zip.ts`, `lib/png.ts`; typst for the PDFs inside) | yes |
| `bundles2.ts` | `statements-year.zip`, `drive-folder.zip` | typst 0.15.1 for the PDFs | yes |
| `bundles2.ts` | `card-dump.zip` | hand-written TIFF-shaped ARW; heif-enc and ffmpeg for the HIF and the clip | no (encoders) |
| `media.ts` | `harbour-clip.mov`, `phone-clip.3gp`, `stream.h264`, `stream.h265`, `stream.ivf`, `tone.opus`, `tone.aac`, `tone.mp3`, `animation.gif` | ffmpeg (libx264, libx265, libaom-av1, libopus, aac, lame) | no (encoders) |
| `media.ts` | `scan.tiff`, `still.avif`, `favicon.ico` | ImageMagick 7 | no (encoder) |
| `documents.ts` | `statement-2026-03.pdf`, `tax-slip-2025.pdf`, `policy-schedule.pdf`, `account-confirmation.pdf`, `chart-printout.pdf`, `design-export.pdf` (each with a `.capture.yaml`) | typst 0.15.1 | yes |
| `documents.ts` | `regatta-roles.docx`, `owner-statement.md`, `contact-card.vcf`, `sms-2026-03.ndjson`, `location-history.json`, `tidewatch.css`, `tidewatch.ts`, `tidewatch.py`, `harbour-events.ics`, `walk.gpx` | the script itself | yes |
| `pages.ts` | `harbour-article.html`, `rope-product.html`, `order-detail.html`, `cottage-listing.html` | the script itself | yes |
| `odds.ts` | `reference.zim`, `region.osm.pbf`, `bracket.FCStd`, `notes.txt.gz` | the script itself (`lib/zip.ts`, node zlib) | yes |
| `mailing.ts` | `regatta-mailing.eml` | the script itself (its xlsx attachment through `lib/zip.ts`; the jpeg and pdf are the committed `garden.jpg` and `till-receipt.pdf`) | yes, given those two files |
| `novel.ts` | `lantern-novel.epub` | the script itself (`lib/zip.ts`, `lib/png.ts` for the images) | yes |
| `chat-archive.ts` | `quay-chat.mbox` | the script itself | yes |
| `chat-export.ts` | `quay-chat-export.zip` | the script itself (`lib/zip.ts` with zstd, `lib/png.ts`) | yes |
| `message-audio-heic.py` | `synthetic-message.eml`, `synthetic-audio.m4a`, `synthetic-image.heic` | stdlib; ffmpeg n9.0.1; libheif 1.23.1 `heif-enc` | eml yes; m4a, heic no |
| by hand | `amazon-twin.csv`, `sign.jpg`, `synthetic-image.{gif,webp,svg}`, `synthetic-lines.ndjson` | ImageMagick for gif/webp | — |

`lib/` holds what the twins share: a deterministic zip writer (store, deflate, zstd; fixed DOS stamps), a minimal
PNG encoder, and a seeded generator with a word well for fabricated prose.

A twin keeps the *shape* of its private counterpart (the manifest's `shape` and `note`), never its content:
fictional names, places and numbers only, nothing copied from a real export — and that includes timestamps,
message and thread ids, snowflakes, MIME boundaries, routing headers and capture instants. A value in a
generator is invented, never read off a real file; plainly fictional forms (`1000000000000000001`,
`000000000000twin0001aaaa`, `example.invalid`) are preferred so a leak is obvious.
