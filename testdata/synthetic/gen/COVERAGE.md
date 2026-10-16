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
| product / order / listing / article page captures | web | text/html | 600 | c | harbour-article.html, rope-product.html, order-detail.html, cottage-listing.html | pages.ts | done (four roots told by their markup) |
| Meta conversation (`message_N.json`, photos/ gifs/ videos/ audio/) | facebook-, instagram-, threads-conversation | application/json | 2,900 | a (+b via bundle) | facebook-/instagram-/threads-thread.json; inside the month bundles | bundles.ts | done (classified by container and name; tree is a later ruling) |
| Google Chat conversation (`messages.json` + `group_info.json`) | google-chat-conversation | application/json | 1,200 | a | chat-space.json; inside chat-month-bundle.zip | bundles.ts | done |
| Discord channel export (DCE json) | discord-conversation | application/json | 70 | a | (inside quay-chat-export.zip) | chat-export.ts | done |
| Google Timeline export (`location-history.json`) | google-timeline-export | application/json | 1 | a | location-history.json (+ sidecar) | documents.ts | done |
| address book | — | application/json | — | a | address-book.json | plain.ts | done |
| order history export | amazon-export (csv member) | text/csv | 1 | c | amazon-twin.csv | by hand | done |
| media manifest | — | text/tab-separated-values | 2 | c | media-manifest.tsv | plain.ts | done |
| SMS backup (one NDJSON per peer per month, MMS inlined) | sms-backup | application/x-ndjson | 1 | a | sms-2026-03.ndjson (+ sidecar) | documents.ts | done |
| contact card / contacts export | icloud-contacts-card, -export | text/vcard | 150 | a | address-cards.vcf; contact-card.vcf (+ sidecar) | plain.ts, documents.ts | done |
| owner statement | owner-statement | text/markdown | 90 | a | owner-statement.md (+ sidecar); tidewatch-readme.md | documents.ts, plain.ts | done |
| single-file script, sources, stylesheet | web | text/javascript, typescript, x-python, css | 1 (+ members) | a | tidewatch.js, tidewatch.ts, tidewatch.py, tidewatch.css | plain.ts, documents.ts | done |
| mail message with attachments | gmail / proton (eml) | message/rfc822 | 100 | c | regatta-mailing.eml | mailing.ts | done |
| mailbox slice (chat folded into mail) | google-takeout | application/mbox | 30 | b | quay-chat.mbox | chat-archive.ts | done |
| Proton mail export bucket (`<id>.eml` + `<id>.metadata.json` pairs) | proton-mail-export | application/zip | 38 | b | mail-month-bundle.zip | bundles.ts | done |
| Meta export bundle (month slice: inbox threads, media, activity indexes) | facebook-, instagram-, threads-export-bundle | application/zip | 360 | b | facebook-/instagram-/threads-month-bundle.zip | bundles.ts | done |
| Meta account export (size-split parts) | facebook-, instagram-, threads-export | application/zip | — | b | (the month bundles carry the same layout) | bundles.ts | covered by the month slices |
| Facebook profile harvest (our layout, per person / per year) | facebook-profile-export, -year | application/zip | 2 | b | profile-year.zip | bundles2.ts | done |
| Google Chat export bundle (month slice) | google-chat-export-bundle | application/zip | 160 | b | chat-month-bundle.zip | bundles.ts | done |
| iMessage export bundle (period of conversation pages) | imessage-export-bundle | application/zip | 180 | b | messages-week-bundle.zip | bundles.ts | done |
| Google Takeout slice (`Takeout/<Service>/…`: fit tcx, contacts, maps, keep html+json, calendar ics) | google-takeout | application/zip (tgz in the wild) | 6 | b | takeout-slice.zip; notes.txt.gz for the gzip wrapper | bundles2.ts, odds.ts | done (a tar reader is a later ruling) |
| Google Drive download job | google-drive-export | application/zip | 2 | b | drive-folder.zip | bundles2.ts | done (classifies as zip: a flat folder has no layout to be told by) |
| photo-library period batch (originals, sidecar JSON, edited renders, videos) | osxphotos-export | application/zip | 76 | b | photos-month-bundle.zip | bundles.ts | done |
| camera SD-card dump (ARW + HIF pairs, MP4 with XML sidecars) | camera-sd-dump | application/zip | — | b | card-dump.zip | bundles2.ts | done |
| Discord guild export (DCE json + assets/) | discord-export | application/zip | 36 | b | quay-chat-export.zip | chat-export.ts | done |
| Amazon data delivery (category zip: csv, pdf invoices, jpeg proofs) | amazon-export | application/zip | 1 | b | orders-delivery.zip | bundles2.ts | done |
| Uber DSAR export (category CSVs + readme) | uber-export | application/zip | 1 | b | rides-export.zip | bundles2.ts | done |
| Apple Health export (export.xml, CDA, ECG csv, GPX routes, clinical json) | apple-health-export | application/zip | 1 | b | health-export.zip | bundles2.ts | done |
| host diagnostics (Unraid: smart/, system/, config/, logs/) | host-diagnostic | application/zip (vnd.unraid.diagnostics+zip) | 4 | b | host-diagnostics.zip | bundles2.ts | done |
| Obsidian vault subtree | obsidian-vault | application/zip | — | b | vault-subtree.zip | bundles2.ts | done |
| vendor download tree (datasheet pdfs, dxf, nested zips) | vendor-download | application/zip | 3 | b | vendor-share.zip | bundles2.ts | done (rar, 7z, exe as magic-only stubs) |
| Claude Code session (JSONL transcript + sidecar tree, zstd) | claude-code-session | application/zip | — | b | agent-session.zip | bundles2.ts | done |
| bank statement series (year zip of monthly PDFs) | bank-statement | application/zip | 14 | b | statements-year.zip | bundles2.ts | done |
| novel | (asset) | application/epub+zip | 1 | b/c | lantern-novel.epub | novel.ts | done |
| methodological-tool document (asserted tree) | web | application/pdf | 1 | c | procedure.pdf | procedure.ts | done |
| till receipt (print-to-PDF) | receipt | application/pdf | 80 | a | till-receipt.pdf | plain.ts | done |
| monthly statement | bank-statement | application/pdf | 50 | a | statement-2026-03.pdf (+ sidecar); inside statements-year.zip | documents.ts, bundles2.ts | done |
| tax slip (portal render) | tax-slip | application/pdf | 8 | a | tax-slip-2025.pdf (+ sidecar) | documents.ts | done |
| insurance policy document | insurance-document | application/pdf | 5 | a | policy-schedule.pdf (+ sidecar) | documents.ts | done |
| banking document (void cheque, confirmation) | banking-document | application/pdf | — | a | account-confirmation.pdf (+ sidecar) | documents.ts | done |
| health-care print-out | health-record | application/pdf | — | a | chart-printout.pdf (+ sidecar) | documents.ts | done |
| datasheet / manual | vendor-download, web | application/pdf | 40 | a | inside vendor-share.zip | bundles2.ts | done |
| Claude app export | claude-export | application/pdf | — | a | design-export.pdf (+ sidecar) | documents.ts | done |
| word / spreadsheet documents | mail attachments | docx, xlsx | 6 | a | regatta-roles.docx; xlsx inside regatta-mailing.eml | documents.ts, mailing.ts | done |
| photograph with Exif | owner-share, osxphotos | image/jpeg | 9,200 | a | garden.jpg | plain.ts | done |
| screenshot | owner-share | image/png | 4,500 | a | window.png | plain.ts | done |
| animated gif, webp, svg, heic | web, osxphotos | image/* | 1,200 | a | synthetic-image.* | by hand / message-audio-heic.py | done |
| tiff, avif, heif, dng, arw | osxphotos, camera-sd-dump | image/* | 70 (+ members) | a | scan.tiff, still.avif; ARW and HIF inside card-dump.zip | media.ts, bundles2.ts | done; two mimes have a root but no twin reaches it: `image/heif` (every HEIF brand sniffs as heic) and `image/x-adobe-dng` (by extension over the TIFF magic) |
| icon, dxf | web, vendor-download | image/x-icon, image/vnd.dxf | members | a | favicon.ico; DXF inside vendor-share.zip | media.ts, bundles2.ts | done |
| video clip, multi-track | web, osxphotos | video/mp4, video/quicktime, video/3gpp | 500 | a | countdown.mp4, harbour-clip.mov, phone-clip.3gp | plain.ts, media.ts | done |
| raw elementary streams | web | video/hevc, video/h264, video/av1 | 80 | a | stream.h264, stream.h265, stream.ivf | media.ts | done (told by NAL headers and the IVF signature) |
| audio | web, members | audio/opus, aac, mpeg, mp4 | 15 (+ members) | a | synthetic-audio.m4a, tone.opus, tone.aac, tone.mp3 | message-audio-heic.py, media.ts | done |
| reference archives | kiwix, geofabrik | application/x-openzim, application/x-osm+pbf | 48 | a | reference.zim, region.osm.pbf | odds.ts | done as signature stubs |
| calendar, routes, tracks | google-takeout, apple-health | text/calendar, gpx, tcx | members | a | harbour-events.ics, walk.gpx; inside takeout-slice.zip and health-export.zip | documents.ts, bundles2.ts | done |
| compressed and binary odds | vendor-download | rar, 7z, exe, FCStd, octet-stream | members | a | inside vendor-share.zip | bundles2.ts | rar, 7z, exe, ELF done as magic-only stubs; bracket.FCStd (odds.ts); `application/octet-stream` has a root but no twin (every stub carries a magic) |

Rules: a twin keeps the shape, never the content — fictional names, places, numbers; no hostname, institution or
person from the owner's corpus appears in a tracked file. Each generator says in its header what it reproduces
byte-for-byte and what a tool pins by commit (see README.md here).
