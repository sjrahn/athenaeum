// text.ts — plain text (spec §10.4.4): every text format with no row of its own. `text.text@1` is its surface: the
// text itself — the bytes of a span decoded in the file's encoding, nothing removed.
import { textEncoding } from "../format.ts";
import { registerOp } from "../ops.ts";

export const TEXT_OP = "text.text@1";

registerOp<{ bytes: Uint8Array; encoding: string }>({
  name: TEXT_OP,
  kind: "surface",
  family: "text",
  parse: (bytes) => ({ bytes, encoding: textEncoding(bytes) }),
  surface: (d, r) => {
    if (r.path !== undefined) return null;
    const [a, b] = r.whole ? [0, d.bytes.length] : (r.bytes ?? [-1, -1]);
    if (a < 0 || b > d.bytes.length) return null;
    return new TextDecoder(d.encoding as ConstructorParameters<typeof TextDecoder>[0]).decode(d.bytes.subarray(a, b));
  },
});
