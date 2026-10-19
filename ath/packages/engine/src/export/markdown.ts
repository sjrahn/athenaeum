// markdown.ts — the markdown proxy (spec §15.1): an output, never a record and never a citation target. It walks the
// tree in order and emits each scope through its form's `renders` template — `{text}`, `{cells}`, `{tex}` or
// `{reading}` for its reading, `{<field>}` for a field, `{level+1}` for a run of `#` one deeper than its level — every
// block prefixed by its `at`; a scope whose forms declare no template renders its reading. An unformed record exports
// its readings in address order, under no form. The header names the authority (the bytes), every pass and its pin,
// the accepted divergences, the chrome, and the remainder. Every character it emits is a reading's.
import { compareAt } from "../address/address.ts";
import type { RecordDoc, Scope } from "../record/document.ts";
import { effectiveRules } from "../vocab/rules.ts";
import type { Vocabulary } from "../vocab/terms.ts";

type J = Record<string, unknown>;

export interface ProxyInput {
  hash: string;
  record: RecordDoc;
  vocab: Vocabulary;
  /** Divergences an `accept` ruling marks known: their scope addresses. */
  accepted: string[];
  chrome: { at: string; text: string; role?: string }[];
  /** For a rendered artifact: hint units outside every reading or scope and chrome; for a structured one, the
   * characters outside every unit and chrome, of the total. */
  remainder: { units?: number; characters?: [number, number] };
}

const bodyText = (s: { text?: unknown; cells?: unknown; tex?: unknown }): string =>
  typeof s.text === "string"
    ? s.text
    : Array.isArray(s.cells)
      ? `| ${(s.cells as string[]).join(" | ")} |`
      : typeof s.tex === "string"
        ? `$$${s.tex}$$`
        : "";

/** Apply a `renders` template to a scope. */
export function render(template: string, s: Scope): string {
  return template.replace(/\{([a-z0-9_+-]+)\}/gi, (_, k: string) => {
    if (k === "level+1") return "#".repeat(Number(s.level ?? 0) + 1);
    if (k === "reading") return bodyText(s);
    if (k === "cells") return Array.isArray(s.cells) ? `| ${(s.cells as string[]).join(" | ")} |` : "";
    if (k === "tex") return typeof s.tex === "string" ? s.tex : "";
    const v = (s as J)[k];
    return v === undefined || v === null ? "" : typeof v === "string" ? v : JSON.stringify(v);
  });
}

export function proxy(p: ProxyInput): string {
  const r = p.record;
  const out: string[] = [];
  out.push("---");
  out.push(`authority: ath://${p.hash}`);
  for (const [id, pass] of Object.entries(r.passes ?? {}))
    out.push(
      `pass: ${id} by ${pass.by}, verified by ${pass.verify}, ${pass.date}, vocabulary ${pass.vocab}${pass.attests ? `, attests ${pass.attests.join(" and ")}` : ""}`,
    );
  for (const a of p.accepted) out.push(`accepted: ${a}`);
  for (const c of p.chrome) out.push(`chrome: ${c.role ? `${c.role} ` : ""}${c.at} ${JSON.stringify(c.text)}`);
  if (p.remainder.units !== undefined) out.push(`remainder: ${p.remainder.units} hint units outside every reading and chrome`);
  if (p.remainder.characters)
    out.push(`remainder: ${p.remainder.characters[0]} of ${p.remainder.characters[1]} characters outside every unit and chrome`);
  out.push("---", "");
  if (r.scopes) {
    const walk = (scopes: readonly Scope[], inherited: J[]) => {
      for (const s of scopes) {
        const rules = effectiveRules(p.vocab, s.form, inherited);
        const md = typeof rules.renders?.md === "string" ? render(rules.renders.md, s) : bodyText(s);
        out.push(`<!-- at ${s.at} -->`);
        if (md) out.push(md, "");
        if (s.scopes) walk(s.scopes, rules.conventions);
      }
    };
    walk(r.scopes, []);
  } else
    for (const at of Object.keys(r.readings ?? {}).sort(compareAt)) {
      out.push(`<!-- at ${at} -->`);
      out.push(bodyText(r.readings![at]!), "");
    }
  return `${out.join("\n").trimEnd()}\n`;
}
