# Synthetic coverage of the corpus's byte shapes

The owner's instance holds ~31,600 artifacts across the shapes below (surveyed 2026-10-16 from the v52 records:
artifact mime, origin schema, member media types — no content). Every shape gets a generated twin here, with its
generator kept beside it and, where the shape warrants it, a `<file>.capture.yaml` sidecar in the origin's shape
(D-sidecar) so provenance folding is exercised across all of them. The suite never needs a real file.

**Level** is what the engine can test today: **a** sniff + attest + lint; **b** container roster, member minting,
`path=` routing; **c** derived tree, readings, harvest (markup via `select`, tabular via `shape`, mail, epub; JSON,
markdown, vCard and media trees are later rulings, D-roots). A twin is pinned at its level; the leg says what it will
test once the derivation lands.

| shape (bytes) | corpus origins | mime | ≈count | level | twin | generator | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| forum thread capture (XenForo) | web | text/html | 800 | c | harbourboard-thread.html | thread.ts | done |
| iMessage conversation page (imessage-exporter, attachments inlined) | imessage-export | text/html | 5,900 | c | quay-messages.html (+ .capture.yaml) | conversation-page.ts | done |
| service-manual page (procedures, data tables, figures) | web | text/html | 7,000 | c | pump-service-manual.html | manual-page.ts | done |
| product / order / listing / article page captures | web | text/html | 600 | c | — | — | planned (one generator, a page kind per call) |
| Meta conversation (`message_N.json`, photos/ gifs/ videos/ audio/) | facebook-, instagram-, threads-conversation | application/json | 2,900 | a (+b via bundle) | — | — | planned |
| Google Chat conversation (`messages.json` + `group_info.json`) | google-chat-conversation | application/json | 1,200 | a | — | — | planned |
| Discord channel export (DCE json) | discord-conversation | application/json | 70 | a | (inside quay-chat-export.zip) | chat-export.ts | done |
| Google Timeline export (`location-history.json`) | google-timeline-export | application/json | 1 | a | — | — | planned |
| address book | — | application/json | — | a | address-book.json | plain.ts | done |
| order history export | amazon-export (csv member) | text/csv | 1 | c | amazon-twin.csv | by hand | done |
| media manifest | — | text/tab-separated-values | 2 | c | media-manifest.tsv | plain.ts | done |
| SMS backup (one NDJSON per peer per month, MMS inlined) | sms-backup | application/x-ndjson | 1 | a | — | — | planned |
| contact card / contacts export | icloud-contacts-card, -export | text/vcard | 150 | a | address-cards.vcf | plain.ts | done (collection); single card planned |
| owner statement | owner-statement | text/markdown | 90 | a | tidewatch-readme.md | plain.ts | done (readme); statement shape planned |
| single-file script | web | text/javascript | 1 | a | tidewatch.js | plain.ts | done |
| mail message with attachments | gmail / proton (eml) | message/rfc822 | 100 | c | regatta-mailing.eml | mailing.ts | done |
| mailbox slice (chat folded into mail) | google-takeout | application/mbox | 30 | b | quay-chat.mbox | chat-archive.ts | done |
| Proton mail export bucket (`<id>.eml` + `<id>.metadata.json` pairs) | proton-mail-export | application/zip | 38 | b | — | — | planned |
| Meta export bundle (month slice: inbox threads, media, activity indexes) | facebook-, instagram-, threads-export-bundle | application/zip | 360 | b | — | — | planned |
| Meta account export (size-split parts) | facebook-, instagram-, threads-export | application/zip | — | b | — | — | planned (same layout, whole) |
| Facebook profile harvest (our layout, per person / per year) | facebook-profile-export, -year | application/zip | 2 | b | — | — | planned |
| Google Chat export bundle (month slice) | google-chat-export-bundle | application/zip | 160 | b | — | — | planned |
| iMessage export bundle (period of conversation pages) | imessage-export-bundle | application/zip | 180 | b | — | — | planned |
| Google Takeout slice (`Takeout/<Service>/…`: fit tcx, contacts, maps, keep html+json, calendar ics) | google-takeout | application/zip (tgz in the wild) | 6 | b | — | — | planned |
| Google Drive download job | google-drive-export | application/zip | 2 | b | — | — | planned |
| photo-library period batch (originals, sidecar JSON, edited renders, videos) | osxphotos-export | application/zip | 76 | b | — | — | planned |
| camera SD-card dump (ARW + HIF pairs, MP4 with XML sidecars) | camera-sd-dump | application/zip | — | b | — | — | planned |
| Discord guild export (DCE json + assets/) | discord-export | application/zip | 36 | b | quay-chat-export.zip | chat-export.ts | done |
| Amazon data delivery (category zip: csv, pdf invoices, jpeg proofs) | amazon-export | application/zip | 1 | b | — | — | planned |
| Uber DSAR export (category CSVs + readme) | uber-export | application/zip | 1 | b | — | — | planned |
| Apple Health export (export.xml, CDA, ECG csv, GPX routes, clinical json) | apple-health-export | application/zip | 1 | b | — | — | planned |
| host diagnostics (Unraid: smart/, system/, config/, logs/) | host-diagnostic | application/zip (vnd.unraid.diagnostics+zip) | 4 | b | — | — | planned |
| Obsidian vault subtree | obsidian-vault | application/zip | — | b | — | — | planned |
| vendor download tree (datasheet pdfs, dxf, nested zips) | vendor-download | application/zip | 3 | b | — | — | planned |
| Claude Code session (JSONL transcript + sidecar tree, zstd) | claude-code-session | application/zip | — | b | — | — | planned |
| bank statement series (year zip of monthly PDFs) | bank-statement | application/zip | 14 | b | — | — | planned |
| novel | (asset) | application/epub+zip | 1 | b/c | lantern-novel.epub | novel.ts | done |
| methodological-tool document (asserted tree) | web | application/pdf | 1 | c | procedure.pdf | procedure.ts | done |
| till receipt (print-to-PDF) | receipt | application/pdf | 80 | a | till-receipt.pdf | plain.ts | done |
| monthly statement | bank-statement | application/pdf | 50 | a | — | — | planned (typst) |
| tax slip (portal render) | tax-slip | application/pdf | 8 | a | — | — | planned (typst) |
| insurance policy document | insurance-document | application/pdf | 5 | a | — | — | planned (typst) |
| banking document (void cheque, confirmation) | banking-document | application/pdf | — | a | — | — | planned (typst) |
| health-care print-out | health-record | application/pdf | — | a | — | — | planned (typst) |
| datasheet / manual | vendor-download, web | application/pdf | 40 | a | — | — | planned (typst) |
| Claude app export | claude-export | application/pdf | — | a | — | — | planned (typst) |
| word / spreadsheet documents | mail attachments | docx, xlsx | 6 | a | (xlsx inside regatta-mailing.eml) | mailing.ts | xlsx done; docx planned |
| photograph with Exif | owner-share, osxphotos | image/jpeg | 9,200 | a | garden.jpg | plain.ts | done |
| screenshot | owner-share | image/png | 4,500 | a | window.png | plain.ts | done |
| animated gif, webp, svg, heic | web, osxphotos | image/* | 1,200 | a | synthetic-image.* | by hand / message-audio-heic.py | done |
| tiff, avif, heif, dng, arw | osxphotos, camera-sd-dump | image/* | 70 (+ members) | a | — | — | planned (magick / heif-enc / hand-written headers) |
| icon, dxf | web, vendor-download | image/x-icon, image/vnd.dxf | members | a | — | — | planned (hand-written) |
| video clip, multi-track | web, osxphotos | video/mp4, video/quicktime | 500 | a | countdown.mp4 | plain.ts | mp4 done; quicktime, 3gpp planned (ffmpeg) |
| raw elementary streams | web | video/hevc, video/h264, video/av1 | 80 | a | — | — | planned (ffmpeg, annex-b / ivf) |
| audio | web, members | audio/opus, aac, mpeg, mp4 | 15 (+ members) | a | synthetic-audio.m4a | message-audio-heic.py | m4a done; opus, aac, mpeg planned (ffmpeg) |
| reference archives | kiwix, geofabrik | application/x-openzim, application/x-osm+pbf | 48 | a | — | — | planned (minimal valid headers, marked stub) |
| calendar, routes, tracks | google-takeout, apple-health | text/calendar, gpx, tcx | members | a | — | — | planned |
| compressed and binary odds | vendor-download | rar, 7z, exe, FCStd, octet-stream | members | a | — | — | planned (magic-only stubs) |

Rules: a twin keeps the shape, never the content — fictional names, places, numbers; no hostname, institution or
person from the owner's corpus appears in a tracked file. Each generator says in its header what it reproduces
byte-for-byte and what a tool pins by commit (see README.md here).
