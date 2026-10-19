// attest.ts — what an HTML file is: encoding, title, the standard `<meta>` names (§10.2). A field a capturing tool
// inserts under a name of its own is text in the bytes, not part of the format (§10.2.3).
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
  for (const name of ["generator", "description", "author"]) {
    const v = selectFirst(d, `meta[name="${name}"]`)?.attribs.content;
    if (v) value[name] = v;
  }
  return { value };
}

registerAttester("text/html", attestHtml);
registerAttester("application/xhtml+xml", attestHtml);
