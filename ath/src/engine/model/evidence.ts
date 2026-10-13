// evidence.ts — an evidence entry (spec §9.2) and the binding grammar (Appendix D-F3): `rev` | `derived:<op>@<v>[ <arg>]`
// | `line:<predicate>[ <field>]` | null (held).
import { z } from "../../../contracts/index.ts";
import { OP_REF, REV } from "./line.ts";

export type Binding =
  | { kind: "rev"; rev: string }
  | { kind: "derived"; op: string; arg?: string }
  | { kind: "line"; predicate: string; field?: string }
  | { kind: "held" };

export function parseBinding(s: string | null | undefined): Binding | { kind: "invalid"; why: string } {
  if (s === null || s === undefined) return { kind: "held" };
  if (REV.test(s)) return { kind: "rev", rev: s };
  let m = /^derived:(\S+)(?: (.+))?$/.exec(s);
  if (m) {
    if (!OP_REF.test(m[1]!)) return { kind: "invalid", why: `derived op must be <name>@<version>: '${m[1]}'` };
    return m[2] ? { kind: "derived", op: m[1]!, arg: m[2] } : { kind: "derived", op: m[1]! };
  }
  m = /^line:([a-z_]+)(?: (\S+))?$/.exec(s);
  if (m) return m[2] ? { kind: "line", predicate: m[1]!, field: m[2] } : { kind: "line", predicate: m[1]! };
  return { kind: "invalid", why: `not a binding: '${s}' (rev, derived:<op>@<v>[ <arg>], line:<predicate>[ <field>], or null)` };
}

export const KINDS = ["authoritative", "direct", "incidental"] as const;
export const MODES = ["stated", "inferred", "reported"] as const;

export const EvidenceEntry = z
  .object({
    anchor: z.string().regex(/^corpus:\/\/[0-9a-f]{64}\?.+$/, "anchor must be corpus://<blake3>?<at>[&aspect]"),
    quote: z.string().refine((q) => !q.includes("…") && !q.endsWith("..."), "a quote is never elided; use prefix/suffix"),
    prefix: z.string().optional(),
    suffix: z.string().optional(),
    kind: z.enum(KINDS),
    mode: z.enum(MODES),
    reasoning: z.string().optional(),
    reading: z.string().nullable(),
  })
  .strict()
  .superRefine((e, ctx) => {
    const b = parseBinding(e.reading);
    if (b.kind === "invalid") ctx.addIssue({ code: "custom", path: ["reading"], message: b.why });
    if (e.mode !== "stated" && !e.reasoning)
      ctx.addIssue({ code: "custom", path: ["reasoning"], message: `mode ${e.mode} needs reasoning` });
  });
export type EvidenceEntry = z.infer<typeof EvidenceEntry>;

export interface Anchor {
  blake3: string;
  at: string;
  aspect?: "text" | "cells" | "tex";
}

export function parseAnchor(anchor: string): Anchor {
  const m = /^corpus:\/\/([0-9a-f]{64})\?(.+)$/.exec(anchor);
  if (!m) throw new Error(`not an anchor: ${anchor}`);
  let at = m[2]!;
  let aspect: Anchor["aspect"];
  const a = /&(text|cells|tex)$/.exec(at);
  if (a) {
    aspect = a[1] as Anchor["aspect"];
    at = at.slice(0, -a[0].length);
  }
  return aspect ? { blake3: m[1]!, at, aspect } : { blake3: m[1]!, at };
}
