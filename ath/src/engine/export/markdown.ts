// markdown.ts — the proxy as an output (spec §11): walk the tree in ord, emit each scope through its term's renders
// rule with designators re-emitted from fields, every block prefixed by its address, and a header that names the
// authority (the bytes), the passes and their ontology pins, the inspected divergences, the chrome and the remainder.
import type { JsonObject } from "../../lib/jsonl.ts";
import type { Artifact } from "../corpus/derive.ts";
import type { Scope } from "../corpus/tree.ts";
import { coverageHtml } from "../lint/generic.ts";
import { effectiveRules } from "../ontology/effective.ts";

function render(a: Artifact, s: Scope, reading: { aspect: string; body: unknown } | undefined): string | null {
  const rules = effectiveRules(a.ontology, s.terms);
  const body = reading ? (typeof reading.body === "string" ? reading.body : cellsMd(reading.body)) : null;
  const tpl = rules.renders?.md;
  if (typeof tpl === "string" && body !== null) {
    return collapse(
      tpl.replace(/\{([a-z_]+)(\+1)?\}/g, (_m, k: string, plus: string | undefined) => {
        if (k === "body") return body;
        if (k === "at") return s.at;
        const v = s.fields[k];
        if (v === undefined) return "";
        if (plus && typeof v === "number") return "#".repeat(v + 1);
        return String(v);
      }),
    );
  }
  if (body !== null) return body;
  return null;
}

/** A render template with empty fields leaves double spaces behind; one space, trimmed per line. */
const collapse = (s: string) =>
  s
    .split("\n")
    .map((l) => l.replace(/ {2,}/g, " ").trim())
    .join("\n");

function cellsMd(body: unknown): string {
  if (!Array.isArray(body)) return String(body);
  if (body.every((r) => Array.isArray(r))) {
    const rows = body as unknown[][];
    const head = rows[0] ?? [];
    const line = (r: unknown[]) => `| ${r.map((c) => String(c).replace(/\|/g, "\\|").replace(/\n/g, "<br>")).join(" | ")} |`;
    return [line(head), `|${head.map(() => "---").join("|")}|`, ...rows.slice(1).map(line)].join("\n");
  }
  return `| ${body.map((c) => String(c).replace(/\|/g, "\\|").replace(/\n/g, "<br>")).join(" | ")} |`;
}

export function exportMarkdown(a: Artifact, o: { inspected?: JsonObject[]; pin?: string | null } = {}): string {
  const head: string[] = [];
  head.push("athenaeum export · derived from the claim file, walked in ord · do not edit");
  head.push(`artifact   corpus://${a.blake3}`);
  head.push(`           ${a.mime}${a.root ? ` · manifests ${a.root}` : ""} · tree ${a.tree ?? "none"}`);
  if (a.capturedFrom) {
    const v = a.capturedFrom.value as JsonObject;
    head.push(`origin     ${[v.origin, v.uri, v.container].filter(Boolean).join(" ")}`);
  }
  head.push("authority  the bytes — this export is a derivation and never stands in for them");
  const passes = [...a.passes.values()].map((p) => `${(p.value as JsonObject).id}@${(p.value as JsonObject).ontology}`);
  if (passes.length) head.push(`passes     ${passes.join(" ")}`);
  if (o.pin) head.push(`ontology   ${o.pin}`);
  const inspected = o.inspected ?? [];
  if (inspected.length) head.push(`inspected  ${inspected.length} divergence${inspected.length === 1 ? "" : "s"} accepted by the owner`);
  const cov = coverageHtml(a);
  if (cov)
    head.push(
      `remainder  ${cov.remainder} of ${cov.total} text characters outside every reading scope and declared chrome (${(cov.ratio * 100).toFixed(1)}%)`,
    );
  if (a.chromeSpans.length) head.push(`chrome     ${a.chromeSpans.length} regions by declared selectors, never read`);
  const out: string[] = [`<!--\n${head.join("\n")}\n-->`, ""];
  for (const s of a.table.walk()) {
    if (s.at === "whole") continue;
    const reading = s.readings.find((r) => r.aspect === "text") ?? s.readings[0];
    const text = render(a, s, reading);
    if (text === null) continue;
    out.push(`<!-- ${s.at} -->`, text, "");
  }
  return `${out.join("\n").trimEnd()}\n`;
}
