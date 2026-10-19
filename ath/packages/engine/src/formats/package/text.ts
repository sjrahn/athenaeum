// text.ts — `epub.text@1` and `ooxml.text@1`, hints (spec §10.6.2): the text of a content document's or package
// part's span, at `path=<entry>&bytes=a,b`, as `html.text@1` over its markup; an element's namespace prefix is set
// aside, so a package's own paragraph and break elements end their lines.
import { parseHtml } from "../html/dom.ts";
import { HTML_TEXT_OP } from "../html/text.ts";
import { type Hint, opNamed, registerOp } from "../ops.ts";
import { zipEntries } from "../zip/roster.ts";

type Entries = Map<string, () => Uint8Array>;

const parse = async (bytes: Uint8Array): Promise<Entries> => new Map((await zipEntries(bytes)).map((e) => [e.path, e.read]));

async function partHint(entries: Entries, path: string | undefined, bytes: readonly [number, number] | undefined): Promise<Hint | null> {
  if (path === undefined) return null;
  const read = entries.get(path);
  if (!read) return null;
  const body = read();
  const h = await opNamed(HTML_TEXT_OP)!.hint!(parseHtml(body), bytes ? { bytes } : { whole: true }, undefined);
  return h ? { text: h.text, units: h.units.map((u) => ({ text: u.text, at: `path=${path}&${u.at}` })) } : null;
}

for (const [name, family] of [
  ["epub.text@1", "epub"],
  ["ooxml.text@1", "ooxml"],
] as const)
  registerOp<Entries>({ name, kind: "hint", family, parse, hint: (e, r) => partHint(e, r.path, r.bytes) });
