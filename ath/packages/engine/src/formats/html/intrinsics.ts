// intrinsics.ts — what an HTML document defines about itself (spec §10.2, §10.3): its declared encoding, its
// `<title>`, the standard `<meta>` names; and every `data:` URI in its bytes, wherever it stands — an attribute, a
// `srcset` candidate, a CSS `url()` — base64- or percent-decoded, as an asset whose path is the URI's byte span. An
// empty payload is skipped. A field a capturing tool inserts under a name of its own is not the format's (§10.2.3).
import { blake3Hex } from "@ath/kit/hash.ts";
import type { Constituent, IntrinsicsResult, J } from "../format.ts";
import { parseHtml, selectFirst } from "./dom.ts";

const DATA_URI = /data:([a-z0-9!#$&^_.+-]+\/[a-z0-9!#$&^_.+-]+)?((?:;[a-z0-9!#$&^_.+-]+=[^;,"'()\s]*)*)(;base64)?,([^"'()\s<>]*)/gi;

export async function dataUris(bytes: Uint8Array): Promise<Constituent[]> {
  const text = new TextDecoder("latin1").decode(bytes);
  const out: Constituent[] = [];
  for (const m of text.matchAll(DATA_URI)) {
    const raw = m[4]!;
    let payload: Uint8Array;
    try {
      payload = m[3] ? Uint8Array.from(Buffer.from(raw, "base64")) : new Uint8Array(Buffer.from(decodeURIComponent(raw), "latin1"));
    } catch {
      continue;
    }
    if (!payload.length) continue;
    const a = m.index!;
    const mediatype = (m[1] ?? "text/plain").toLowerCase();
    out.push({
      path: `${a}-${a + m[0].length}`,
      blake3: await blake3Hex(payload),
      kind: "asset",
      fields: { mime: mediatype },
      read: () => payload,
    });
  }
  return out;
}

const textOf = (n: { children?: { type: string; data?: string }[] } | null): string =>
  (n?.children ?? [])
    .filter((c) => c.type === "text")
    .map((c) => c.data ?? "")
    .join("")
    .trim();

export async function htmlIntrinsics(bytes: Uint8Array): Promise<IntrinsicsResult> {
  const d = parseHtml(bytes);
  const facts: J = {};
  const title = textOf(selectFirst(d, "title") as never);
  if (title) facts.title = title;
  for (const name of ["generator", "description", "author"]) {
    const v = selectFirst(d, `meta[name="${name}"]`)?.attribs.content;
    if (v) facts[name] = v;
  }
  return { encoding: d.encoding, facts, constituents: await dataUris(bytes) };
}
