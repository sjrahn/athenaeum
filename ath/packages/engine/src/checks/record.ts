// record.ts — the checks over a record (spec §17.1–§17.3). Record checks: class (a structured artifact holds no
// reading and no scope), unit (a scope whose form reads an aspect has its reading under it, and one that reads none
// has none), tree (every `at` an address the format has, no two scopes at one, every form a form). Vocabulary use:
// sorts. Per form: `reads`, required fields, field types, designators where `pattern` says, `expects` (soft), the
// form's `check` lines, a stored shape one that matches. Per file: no undeclared field, no derived field stored,
// every reading and scope covered by a pass, pins well-formed. A blocking finding refuses a signature.
import { canonicalAt, parseAddress } from "../address/address.ts";
import { regionProblem } from "../address/anchor.ts";
import type { Format } from "../formats/format.ts";
import { uncovered } from "../pass/coverage.ts";
import { isField, type RecordDoc, type Scope } from "../record/document.ts";
import { scopesOf } from "../record/tree.ts";
import { refinesChain } from "../vocab/load.ts";
import { effectiveRules } from "../vocab/rules.ts";
import type { Vocabulary } from "../vocab/terms.ts";

type J = Record<string, unknown>;

export interface Finding {
  check: "class" | "unit" | "tree" | "coverage" | "sorts" | "per form" | "per file" | "per testimony" | "citation" | "standing";
  level: "block" | "soft" | "advisory";
  at?: string;
  message: string;
}

const AXIS_OF: Record<string, string> = { path: "path", page: "page", row: "row", t: "t", bbox: "bbox", bytes: "bytes", col: "col" };

function typeProblem(d: J, v: unknown): string | null {
  switch (d.type) {
    case "int":
    case "col":
      return typeof v === "number" && Number.isInteger(v) ? null : "is an integer";
    case "enum":
      return Array.isArray(d.options) && d.options.includes(v) ? null : `is one of ${JSON.stringify(d.options)}`;
    case "list":
      return Array.isArray(v) ? null : "is a list";
    default:
      return typeof v === "string" ? null : "is a string";
  }
}

export interface RecordContext {
  vocab: Vocabulary;
  format: Format;
  intrinsics: J;
  /** The shapes that match the artifact, for a stored shape's check. */
  matched: string[];
}

export function recordChecks(r: RecordDoc, c: RecordContext): Finding[] {
  const out: Finding[] = [];
  const add = (f: Finding) => out.push(f);
  const v = c.vocab;
  if (c.format.class === "structured" && (r.readings || r.scopes))
    add({
      check: "class",
      level: "block",
      message: "a structured artifact's parse is its reading: its record holds no reading and no scope",
    });
  if (r.shape !== undefined) {
    if (!v.shapes.has(r.shape)) add({ check: "sorts", level: "block", message: `the stored shape ${r.shape} is not a shape` });
    else if (!c.matched.includes(r.shape))
      add({ check: "per form", level: "block", message: `the stored shape ${r.shape} does not match the artifact` });
  }
  // readings: addresses the format has
  for (const at of Object.keys(r.readings ?? {})) addressChecks(at, c, add);
  // the tree
  const seen = new Set<string>();
  const walk = (scopes: readonly Scope[] | undefined, inherited: J[]) => {
    for (const s of scopes ?? []) {
      const at = s.at;
      addressChecks(at, c, add);
      let key = at;
      try {
        key = canonicalAt(at);
      } catch {
        // reported above
      }
      if (seen.has(key)) add({ check: "tree", level: "block", at, message: "two scopes share this address" });
      seen.add(key);
      const forms = [s.form].flat();
      const unknown = forms.filter((f) => !v.forms.has(f));
      for (const f of unknown) add({ check: "sorts", level: "block", at, message: `${f} is not a form` });
      if (unknown.length) {
        walk(s.scopes, inherited);
        continue;
      }
      const rules = effectiveRules(v, forms, inherited);
      const reads = rules.reads ?? "none";
      const bodies = (["text", "cells", "tex"] as const).filter((a) => s[a] !== undefined);
      if (reads === "none" && bodies.length)
        add({ check: "unit", level: "block", at, message: `${forms.join(", ")} reads none, but the scope carries ${bodies.join(", ")}` });
      if (reads !== "none" && !bodies.includes(reads as "text"))
        add({ check: "unit", level: "block", at, message: `${forms.join(", ")} reads ${reads}, but the scope has no reading under it` });
      for (const b of bodies)
        if (reads !== "none" && b !== reads)
          add({ check: "unit", level: "block", at, message: `a reading under ${b}, where ${forms.join(", ")} reads ${reads}` });
      // fields: declared, typed, required present, none derived stored, designators as their pattern says
      const declared = new Map(rules.fields.map((d) => [String(d.name), d]));
      for (const k of Object.keys(s).filter(isField)) {
        const d = declared.get(k);
        if (!d) {
          add({ check: "per file", level: "block", at, message: `\`${k}\` is not a field ${forms.join(", ")} declares` });
          continue;
        }
        if (d.derived) add({ check: "per file", level: "block", at, message: `\`${k}\` is derived from the address and is never stored` });
        const p = typeProblem(d, s[k]);
        if (p) add({ check: "per form", level: "block", at, message: `\`${k}\` ${p}` });
        if (
          d.type === "designator" &&
          typeof d.pattern === "string" &&
          typeof s[k] === "string" &&
          !new RegExp(d.pattern).test(s[k] as string)
        )
          add({ check: "per form", level: "block", at, message: `the designator \`${k}\` '${s[k]}' is not as its pattern says` });
      }
      for (const d of rules.fields)
        if (d.required && !d.derived && s[String(d.name)] === undefined)
          add({ check: "per form", level: "block", at, message: `the required field \`${d.name}\` is missing` });
      if (
        rules.expects.length &&
        !(s.scopes ?? []).some((ch) => [ch.form].flat().some((f) => rules.expects.some((e) => refinesChain(v, "forms", f).includes(e))))
      )
        add({ check: "per form", level: "soft", at, message: `${forms.join(", ")} expects ${rules.expects.join(" or ")} within it` });
      for (const ck of rules.checks) formCheck(ck, s, c, v, add, r.scopes ?? []);
      walk(s.scopes, rules.conventions);
    }
  };
  walk(r.scopes, []);
  for (const g of uncovered(r))
    add({
      check: "per file",
      level: "block",
      at: g === "tree" || g === "shape" || g === "chrome" ? undefined : g,
      message: `${g === "tree" || g === "shape" || g === "chrome" ? `the ${g}` : "this reading"} is covered by no pass`,
    });
  for (const [id, p] of Object.entries(r.passes ?? {})) {
    if (!/^b3:[0-9a-f]{16}$/.test(p.vocab))
      add({ check: "per file", level: "block", message: `${id}'s vocabulary pin is not b3: and 16 hex digits` });
    if (p.by === p.verify) add({ check: "per file", level: "block", message: `${id}'s author is its verifier` });
  }
  return out;
}

function addressChecks(at: string, c: RecordContext, add: (f: Finding) => void): void {
  let regions: ReturnType<typeof parseAddress>["regions"];
  try {
    const a = parseAddress(at);
    if (a.aspect) throw new Error("an address stored in a record carries no aspect");
    regions = a.regions;
  } catch (e) {
    add({ check: "tree", level: "block", at, message: (e as Error).message });
    return;
  }
  for (const r of regions) {
    const p = regionProblem(c.intrinsics, r);
    if (p) add({ check: "tree", level: "block", at, message: p });
    if (r.whole) continue;
    const axes = Object.keys(r)
      .map((k) => AXIS_OF[k])
      .filter((x): x is string => !!x);
    for (const a of axes)
      if (a !== "col" && !c.format.axes.includes(a as never))
        add({ check: "tree", level: "block", at, message: `${c.format.name} has no ${a} axis` });
  }
}

function formCheck(ck: J, s: Scope, c: RecordContext, v: Vocabulary, add: (f: Finding) => void, root: readonly Scope[]): void {
  if (typeof ck.contains === "string") {
    let n = 0;
    for (const { scope } of scopesOf(s.scopes))
      if ([scope.form].flat().some((f) => refinesChain(v, "forms", f).includes(String(ck.contains)))) n++;
    if (n < Number(ck.at_least))
      add({ check: "per form", level: "block", at: s.at, message: `contains ${n} ${ck.contains}, at least ${ck.at_least} expected` });
  }
  if (typeof ck.field === "string" && typeof ck.agrees === "string") {
    const key = ck.agrees.replace(/^intrinsics\./, "");
    const want = c.intrinsics[key];
    if (s[ck.field] !== undefined && String(s[ck.field]) !== String(want))
      add({
        check: "per form",
        level: "block",
        at: s.at,
        message: `\`${ck.field}\` ${JSON.stringify(s[ck.field])} disagrees with intrinsics ${key} ${JSON.stringify(want)}`,
      });
  }
  if (typeof ck.every === "string" && typeof ck.names === "string") {
    // every value of the field names a scope of the form by a designator it prints (a contents row names a heading)
    const raw = s[ck.every];
    if (raw === undefined) return;
    const keys = effectiveRules(v, String(ck.names))
      .fields.filter((d) => d.type === "designator")
      .map((d) => String(d.name));
    const named = new Set<string>();
    for (const { scope } of scopesOf(root)) {
      if (![scope.form].flat().some((f) => refinesChain(v, "forms", f).includes(String(ck.names)))) continue;
      for (const k of keys) {
        const val = scope[k];
        if (typeof val !== "string") continue;
        named.add(val);
        const d = effectiveRules(v, scope.form).fields.find((x) => x.name === k);
        const m = typeof d?.pattern === "string" ? new RegExp(d.pattern).exec(val) : null;
        if (m?.[1] !== undefined) named.add(m[1]);
      }
    }
    for (const x of [raw].flat())
      if (!named.has(String(x)))
        add({ check: "per form", level: "block", at: s.at, message: `\`${ck.every}\` ${JSON.stringify(x)} names no ${ck.names}` });
  }
}
