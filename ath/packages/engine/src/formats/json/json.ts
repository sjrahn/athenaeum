// json.ts — JSON and NDJSON as the format defines them (RFC 8259), parsed with every value's byte span: a value's span
// covers its source text, a string's quotes included (spec §10.5.4). `json.text@1 [lines]` is the surface: the scalar
// values inside a span in document order, strings unescaped, one per line; `lines` parses one document per line.
import { AthError } from "@ath/kit/errors.ts";
import { byteMap } from "../html/dom.ts";
import { registerOp } from "../ops.ts";

export type JsonKind = "object" | "array" | "string" | "number" | "true" | "false" | "null";

export interface JsonNode {
  kind: JsonKind;
  /** Byte span of the value's source text. */
  start: number;
  end: number;
  /** A scalar's value as the surface gives it: a string unescaped, anything else its source text. */
  text?: string;
  /** An object's members (with their keys) or an array's items, in source order. */
  children?: { key?: string; node: JsonNode }[];
}

export interface JsonDoc {
  /** One root, or one per line under `lines`. */
  roots: JsonNode[];
}

export const JSON_TEXT_OP = "json.text@1";

/** Parse JSON text into nodes with byte spans. Throws CONFLICT on bytes that are not JSON. */
export function parseJson(bytes: Uint8Array, lines = false): JsonDoc {
  let src = new TextDecoder("utf-8").decode(bytes);
  let bom = 0;
  if (src.charCodeAt(0) === 0xfeff) {
    src = src.slice(1);
    bom = 3;
  }
  const map = byteMap(src);
  const B = (i: number) => map[i]! + bom;
  let i = 0;
  const bad = (m: string): never => {
    throw new AthError("CONFLICT", `json: ${m} at byte ${B(Math.min(i, src.length))}`);
  };
  const ws = () => {
    while (i < src.length && (src[i] === " " || src[i] === "\t" || src[i] === "\n" || src[i] === "\r")) i++;
  };
  const str = (): string => {
    i++;
    let out = "";
    for (;;) {
      if (i >= src.length) bad("unterminated string");
      const c = src[i]!;
      if (c === '"') {
        i++;
        return out;
      }
      if (c === "\\") {
        const e = src[i + 1];
        const simple: Record<string, string> = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
        if (e === "u") {
          const hex = src.slice(i + 2, i + 6);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) bad("bad \\u escape");
          out += String.fromCharCode(Number.parseInt(hex, 16));
          i += 6;
        } else if (e !== undefined && e in simple) {
          out += simple[e];
          i += 2;
        } else bad("bad escape");
      } else {
        out += c;
        i++;
      }
    }
  };
  const value = (): JsonNode => {
    ws();
    const start = i;
    const c = src[i];
    if (c === "{") {
      i++;
      const children: { key?: string; node: JsonNode }[] = [];
      ws();
      if (src[i] === "}") i++;
      else
        for (;;) {
          ws();
          if (src[i] !== '"') bad("expected a key");
          const key = str();
          ws();
          if (src[i++] !== ":") bad("expected ':'");
          children.push({ key, node: value() });
          ws();
          if (src[i] === ",") {
            i++;
            continue;
          }
          if (src[i] === "}") {
            i++;
            break;
          }
          bad("expected ',' or '}'");
        }
      return { kind: "object", start: B(start), end: B(i), children };
    }
    if (c === "[") {
      i++;
      const children: { node: JsonNode }[] = [];
      ws();
      if (src[i] === "]") i++;
      else
        for (;;) {
          children.push({ node: value() });
          ws();
          if (src[i] === ",") {
            i++;
            continue;
          }
          if (src[i] === "]") {
            i++;
            break;
          }
          bad("expected ',' or ']'");
        }
      return { kind: "array", start: B(start), end: B(i), children };
    }
    if (c === '"') {
      const text = str();
      return { kind: "string", start: B(start), end: B(i), text };
    }
    for (const [lit, kind] of [
      ["true", "true"],
      ["false", "false"],
      ["null", "null"],
    ] as const)
      if (src.startsWith(lit, i)) {
        i += lit.length;
        return { kind, start: B(start), end: B(i), text: lit };
      }
    const m = /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?/.exec(src.slice(i, i + 64));
    if (!m) return bad("expected a value");
    i += m[0].length;
    return { kind: "number", start: B(start), end: B(i), text: m[0] };
  };
  const roots: JsonNode[] = [];
  if (lines) {
    for (;;) {
      ws();
      if (i >= src.length) break;
      roots.push(value());
      while (i < src.length && (src[i] === " " || src[i] === "\t" || src[i] === "\r")) i++;
      if (i < src.length && src[i] !== "\n") bad("one document per line");
    }
  } else {
    roots.push(value());
    ws();
    if (i < src.length) bad("text after the document");
  }
  return { roots };
}

/** The scalars whose spans lie inside [a, b), in document order. */
export function scalarsIn(nodes: readonly JsonNode[], a: number, b: number): string[] {
  const out: string[] = [];
  const walk = (n: JsonNode) => {
    if (n.end <= a || n.start >= b) return;
    if (n.children) for (const c of n.children) walk(c.node);
    else if (n.start >= a && n.end <= b) out.push(n.text!);
  };
  for (const r of nodes) walk(r);
  return out;
}

registerOp<JsonDoc>({
  name: JSON_TEXT_OP,
  kind: "surface",
  family: "json",
  parseArg: true,
  arg: (a) => (a === undefined || a === "lines" ? null : `${JSON_TEXT_OP} takes \`lines\` or nothing, not '${a}'`),
  parse: (bytes, arg) => parseJson(bytes, arg === "lines"),
  surface: (d, r) => {
    if (r.path !== undefined) return null;
    if (r.whole) return scalarsIn(d.roots, 0, Number.MAX_SAFE_INTEGER).join("\n");
    return r.bytes ? scalarsIn(d.roots, r.bytes[0], r.bytes[1]).join("\n") : null;
  },
});
