// index.ts — the formats the tooling registers (spec §10.4.3), each with its class, its axes and which are physical,
// its surface or hint ops, its container role and its intrinsics op; importing it registers them and the surface
// and hint ops. `intrinsicsOf` is a record's `intrinsics` (§8.2.1): the op, mime, size, encoding for text, the
// format's facts, then its constituents.
import { csvIntrinsics } from "./csv/intrinsics.ts";
import "./csv/parse.ts";
import { epubIntrinsics } from "./epub/intrinsics.ts";
import { type Constituent, constituentEntry, type Format, formatOf, intrinsicsOp, type J, registerFormat, textEncoding } from "./format.ts";
import { htmlIntrinsics } from "./html/intrinsics.ts";
import "./html/text.ts";
import { rasterIntrinsics } from "./image/image.ts";
import { mboxIntrinsics, messageIntrinsics } from "./mail/intrinsics.ts";
import "./mail/text.ts";
import { mediaIntrinsics } from "./media/media.ts";
import { pdfIntrinsics } from "./pdf/intrinsics.ts";
import "./json/json.ts";
import "./markdown/markdown.ts";
import "./media/hints.ts";
import "./package/text.ts";
import "./pdf/words.ts";
import "./text/text.ts";
import "./vcard/vcard.ts";
import "./yaml/yaml.ts";
import { ooxmlIntrinsics, zipIntrinsics } from "./zip/intrinsics.ts";

export { type Hint, hintAt, type Op, opNamed, opNames, opProblem, Parses, parseOpRef, surfaceAt, type Unit } from "./ops.ts";

const text = (b: Uint8Array) => ({ facts: {}, encoding: textEncoding(b) });
const OOXML = [
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
];
const RASTERS = [
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
  "image/tiff",
  "image/heic",
  "image/avif",
  "image/x-icon",
  "image/x-sony-arw",
  "image/x-adobe-dng",
];
const MEDIA = [
  "video/mp4",
  "video/quicktime",
  "video/3gpp",
  "audio/mp4",
  "audio/mpeg",
  "audio/aac",
  "audio/opus",
  "video/av1",
  "video/x-ivf",
  "video/h264",
  "video/hevc",
];

const FORMATS: Format[] = [
  {
    name: "pdf",
    mimes: ["application/pdf"],
    class: "rendered",
    axes: ["page", "bbox"],
    physical: ["page"],
    ops: ["pdf.words@1"],
    container: null,
    version: 1,
    intrinsics: pdfIntrinsics,
  },
  {
    name: "html",
    mimes: ["text/html", "application/xhtml+xml"],
    class: "rendered",
    axes: ["bytes"],
    physical: [],
    ops: ["html.text@1", "html.attr@1"],
    container: "assets",
    version: 1,
    intrinsics: htmlIntrinsics,
  },
  {
    name: "image",
    mimes: RASTERS,
    class: "rendered",
    axes: ["bbox"],
    physical: [],
    ops: [],
    container: null,
    version: 1,
    intrinsics: rasterIntrinsics,
  },
  {
    name: "media",
    mimes: MEDIA,
    class: "rendered",
    axes: ["t", "bbox"],
    physical: [],
    ops: ["audio.speech@1", "media.subtitles@1"],
    container: "parts",
    version: 1,
    intrinsics: mediaIntrinsics,
  },
  {
    name: "epub",
    mimes: ["application/epub+zip"],
    class: "rendered",
    axes: ["path", "bytes"],
    physical: [],
    ops: ["epub.text@1"],
    container: "both",
    version: 1,
    intrinsics: epubIntrinsics,
  },
  {
    name: "ooxml",
    mimes: OOXML,
    class: "rendered",
    axes: ["path", "bytes"],
    physical: [],
    ops: ["ooxml.text@1"],
    container: "both",
    version: 1,
    intrinsics: ooxmlIntrinsics,
  },
  {
    name: "rfc822",
    mimes: ["message/rfc822"],
    class: "rendered",
    axes: ["path", "bytes"],
    physical: [],
    ops: ["eml.text@1"],
    container: "both",
    version: 1,
    intrinsics: messageIntrinsics,
  },
  {
    name: "csv",
    mimes: ["text/csv", "text/tab-separated-values"],
    class: "structured",
    axes: ["row", "col"],
    physical: ["col"],
    ops: ["csv.parse@1"],
    container: null,
    version: 1,
    intrinsics: csvIntrinsics,
  },
  {
    name: "json",
    mimes: ["application/json", "application/x-ndjson"],
    class: "structured",
    axes: ["bytes"],
    physical: [],
    ops: ["json.text@1"],
    container: null,
    version: 1,
    intrinsics: text,
  },
  {
    name: "yaml",
    mimes: ["application/yaml"],
    class: "structured",
    axes: ["bytes"],
    physical: [],
    ops: ["yaml.text@1"],
    container: null,
    version: 1,
    intrinsics: text,
  },
  {
    name: "vcard",
    mimes: ["text/vcard"],
    class: "structured",
    axes: ["bytes"],
    physical: [],
    ops: ["vcard.text@1"],
    container: null,
    version: 1,
    intrinsics: text,
  },
  {
    name: "markdown",
    mimes: ["text/markdown"],
    class: "structured",
    axes: ["bytes"],
    physical: [],
    ops: ["markdown.text@1"],
    container: null,
    version: 1,
    intrinsics: text,
  },
  {
    name: "text",
    mimes: ["text/plain"],
    class: "structured",
    axes: ["bytes"],
    physical: [],
    ops: [],
    container: null,
    version: 1,
    intrinsics: text,
  },
  {
    name: "mbox",
    mimes: ["application/mbox"],
    class: "structured",
    axes: ["path"],
    physical: [],
    ops: [],
    container: "assets",
    version: 1,
    intrinsics: mboxIntrinsics,
  },
  {
    name: "zip",
    mimes: ["application/zip"],
    class: "structured",
    axes: ["path"],
    physical: [],
    ops: [],
    container: "assets",
    version: 1,
    intrinsics: zipIntrinsics,
  },
  { name: "bytes", mimes: [], axes: [], physical: [], ops: [], container: null, version: 1, intrinsics: () => ({ facts: {} }) },
];
for (const f of FORMATS) registerFormat(f);

export interface Projection {
  /** The record's `intrinsics` value. */
  value: J;
  constituents: Constituent[];
  format: Format;
}

/** What the format defines about these bytes (§8.2.1, §10.2): the record's `intrinsics` and the constituents. */
export async function intrinsicsOf(bytes: Uint8Array, mime: string): Promise<Projection> {
  const format = formatOf(mime);
  const r = await format.intrinsics(bytes, mime);
  const constituents = r.constituents ?? [];
  const value: J = { op: intrinsicsOp(format), mime, bytes: bytes.length };
  if (r.encoding) value.encoding = r.encoding;
  Object.assign(value, r.facts);
  if (constituents.length) value.constituents = constituents.map(constituentEntry);
  return { value, constituents, format };
}

export { type Format, formatNamed, formatOf, formats, intrinsicsOp, parseIntrinsicsOp } from "./format.ts";
