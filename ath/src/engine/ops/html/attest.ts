// attest.ts — what an HTML file is: encoding, title, generator; and the provenance a v52 capture banner carries
// (`corpus-capture-url`, `corpus-fetched-at`, `corpus-fidelity` meta tags) as `captured_from` fields.
import { type AttestResult, registerAttester } from "../registry.ts";
import { parseHtml, selectFirst } from "./dom.ts";

function textOf(n: { children?: { type: string; data?: string }[] } | null): string {
  if (!n) return "";
  return (n.children ?? [])
    .filter((c) => c.type === "text")
    .map((c) => c.data ?? "")
    .join("")
    .trim();
}

export async function attestHtml(bytes: Uint8Array, mime: string): Promise<AttestResult> {
  const d = parseHtml(bytes);
  const value: Record<string, unknown> = { mime, bytes: bytes.length, encoding: d.encoding };
  const title = textOf(selectFirst(d, "title") as never);
  if (title) value.title = title;
  const gen = selectFirst(d, 'meta[name="generator"]')?.attribs.content;
  const html = selectFirst(d, "html");
  if (gen) value.generator = gen;
  else if (html?.attribs["data-app"] && html.attribs["data-version"])
    value.generator = `${html.attribs.id ?? "app"} (data-app ${html.attribs["data-app"]}, data-version ${html.attribs["data-version"]})`;
  const capturedFrom: Record<string, unknown> = {};
  const url = selectFirst(d, 'meta[name="corpus-capture-url"]')?.attribs.content;
  const at = selectFirst(d, 'meta[name="corpus-fetched-at"]')?.attribs.content;
  const fidelity = selectFirst(d, 'meta[name="corpus-fidelity"]')?.attribs.content;
  if (url) {
    try {
      capturedFrom.origin = new URL(url).hostname.replace(/^www\./, "");
    } catch {
      // not a URL
    }
    capturedFrom.uri = url;
    capturedFrom.via = "capture";
  }
  if (at) capturedFrom.snapshot = at;
  if (fidelity) capturedFrom.fidelity = fidelity;
  return Object.keys(capturedFrom).length ? { value, capturedFrom } : { value };
}

registerAttester("text/html", attestHtml);
registerAttester("application/xhtml+xml", attestHtml);
