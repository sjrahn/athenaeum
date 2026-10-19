// yaml.ts — YAML as the format defines it (YAML 1.2), parsed with every node's byte span by the `yaml` package's
// source ranges. `yaml.text@1` is the surface: as `json.text@1`, over the YAML parse — the scalars inside a span in
// document order, strings as their value, anything else as its source text, one per line (spec §10.5.3).
import { AthError } from "@ath/kit/errors.ts";
import { isAlias, isMap, isPair, isScalar, isSeq, type Node, parseAllDocuments } from "yaml";
import { byteMap } from "../html/dom.ts";
import { type JsonDoc, type JsonNode, scalarsIn } from "../json/json.ts";
import { registerOp } from "../ops.ts";

export const YAML_TEXT_OP = "yaml.text@1";

export function parseYaml(bytes: Uint8Array): JsonDoc {
  const src = new TextDecoder("utf-8").decode(bytes);
  const map = byteMap(src);
  const B = (i: number) => map[Math.min(i, src.length)]!;
  const roots: JsonNode[] = [];
  const conv = (n: Node | null | undefined): JsonNode | null => {
    if (!n || isAlias(n)) return null;
    const [a, , end] = n.range ?? [0, 0, 0];
    if (isScalar(n)) {
      const v = n.value;
      const kind = v === null ? "null" : typeof v === "boolean" ? (v ? "true" : "false") : typeof v === "number" ? "number" : "string";
      return { kind, start: B(a), end: B(n.range![1]), text: kind === "string" ? String(v) : src.slice(a, n.range![1]).trim() };
    }
    if (isMap(n))
      return {
        kind: "object",
        start: B(a),
        end: B(end),
        children: n.items.filter(isPair).flatMap((p) => {
          const val = conv(p.value as Node);
          return val ? [{ key: isScalar(p.key) ? String(p.key.value) : undefined, node: val }] : [];
        }),
      };
    if (isSeq(n))
      return {
        kind: "array",
        start: B(a),
        end: B(end),
        children: n.items.flatMap((x) => (conv(x as Node) ? [{ node: conv(x as Node)! }] : [])),
      };
    return null;
  };
  for (const d of parseAllDocuments(src)) {
    if ("errors" in d && d.errors.length) throw new AthError("CONFLICT", `yaml: ${d.errors[0]!.message}`);
    const r = conv(d.contents as Node);
    if (r) roots.push(r);
  }
  return { roots };
}

registerOp<JsonDoc>({
  name: YAML_TEXT_OP,
  kind: "surface",
  family: "yaml",
  parse: parseYaml,
  surface: (d, r) => {
    if (r.path !== undefined) return null;
    if (r.whole) return scalarsIn(d.roots, 0, Number.MAX_SAFE_INTEGER).join("\n");
    return r.bytes ? scalarsIn(d.roots, r.bytes[0], r.bytes[1]).join("\n") : null;
  },
});
