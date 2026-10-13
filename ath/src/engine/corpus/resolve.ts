// resolve.ts — what is at an address: the bytes, the derivation surface the root term's op yields there, or the
// stored reading. The quote surface a binding names (spec §9.2) is computed here and nowhere else.
import { AthError } from "../../kit/errors.ts";
import type { JsonObject } from "../../lib/jsonl.ts";
import { type Aspect, parseAddress, scopeAt } from "../model/address.ts";
import type { Binding } from "../model/evidence.ts";
import { cellsSurface } from "../norm/text.ts";
import { CSV_OP, csvSurface } from "../ops/csv/parse.ts";
import { attrAt, HTML_ATTR_OP, HTML_TEXT_OP, HTML_TITLE_OP, rootAttr, textAt, titleOf } from "../ops/html/text.ts";
import { EML_TEXT_OP, textAt as mailTextAt } from "../ops/mail/text.ts";
import { PDF_WORDS_OP, wordsInBox, wordsText } from "../ops/pdf/words.ts";
import type { Artifact } from "./derive.ts";

export interface Surface {
  /** The op or line that produced it. */
  source: string;
  text: string;
}

/** The bytes at an address (whole or a byte range; other axes need their op). */
export function bytesAt(a: Artifact, at: string): Uint8Array {
  if (!a.bytes) throw new AthError("NOT_FOUND", `${a.blake3}: bytes are not resident in this chain`);
  const m = parseAddress(at).members[0]!;
  if (m.kind === "whole") return a.bytes;
  if (m.kind === "bytes") return a.bytes.subarray(m.start, m.end);
  throw new AthError("USAGE", `bytes at ${at}: only whole and bytes= slice the bytes; use --derivation for ${m.kind}`);
}

/** The derivation surface at an address under the root term's op (text for markup/tabular), or null when none. */
export function derivationAt(a: Artifact, at: string, aspect: Aspect = "text"): Surface | null {
  const m = parseAddress(scopeAt(at)).members[0]!;
  if (a.html) {
    if (m.kind === "whole") {
      const t = titleOf(a.html);
      return t !== null ? { source: HTML_TITLE_OP, text: t } : null;
    }
    if (m.kind !== "bytes") return null;
    const t = textAt(a.html, m.start, m.end);
    return t === null ? null : { source: HTML_TEXT_OP, text: t };
  }
  if (a.pdf) {
    const members = parseAddress(scopeAt(at)).members;
    const parts: string[] = [];
    for (const mm of members) {
      if (mm.kind === "whole") parts.push(...a.pdf.pages.map((p) => wordsText(p.words)));
      else if (mm.kind === "page") {
        const page = a.pdf.pages[mm.page - 1];
        if (!page) return null;
        parts.push(mm.box ? wordsText(wordsInBox(page.words, mm.box)) : wordsText(page.words));
      } else return null;
    }
    return { source: PDF_WORDS_OP, text: parts.join("\n") };
  }
  if (a.csv) {
    if (m.kind !== "row") return null;
    const t = csvSurface(a.csv, m.row, m.col);
    return t === null ? null : { source: CSV_OP, text: aspect === "cells" ? t : t };
  }
  if (a.mail) {
    if (m.kind !== "bytes") return null;
    const t = mailTextAt(a.mail, m.start, m.end);
    return t === null ? null : { source: EML_TEXT_OP, text: t };
  }
  return null;
}

/** The surface a binding names for an anchor; null = cannot be produced (held or flagged by the caller's rule). */
export function surfaceFor(a: Artifact, at: string, b: Binding, aspect?: Aspect): Surface | null {
  const scope = scopeAt(at);
  switch (b.kind) {
    case "held":
      return null;
    case "rev": {
      const s = a.table.get(scope);
      const r = s?.readings.find((x) => x.stored && x.rev === b.rev && (!aspect || x.aspect === aspect));
      return r ? { source: r.rev, text: typeof r.body === "string" ? r.body : cellsSurface(r.body) } : null;
    }
    case "derived": {
      const m = parseAddress(scope).members[0]!;
      if (b.op === HTML_ATTR_OP) {
        if (!a.html || !b.arg) return null;
        const v = m.kind === "whole" ? rootAttr(a.html, b.arg) : m.kind === "bytes" ? attrAt(a.html, m.start, m.end, b.arg) : null;
        return v === null ? null : { source: `${HTML_ATTR_OP} ${b.arg}`, text: v };
      }
      if (b.op === HTML_TITLE_OP) {
        const t = a.html ? titleOf(a.html) : null;
        return t === null ? null : { source: HTML_TITLE_OP, text: t };
      }
      const d = derivationAt(a, scope, aspect);
      if (!d) return null;
      if (d.source !== b.op) return null;
      return d;
    }
    case "line": {
      const line =
        b.predicate === "attests"
          ? a.attests
          : b.predicate === "captured_from"
            ? a.capturedFrom
            : b.predicate === "manifests"
              ? manifestsLine(a, scope)
              : null;
      if (!line) return null;
      if (!b.field) return { source: `line:${b.predicate}`, text: JSON.stringify(line.value ?? line) };
      const holder = b.predicate === "manifests" ? line : (line.value as JsonObject);
      const v = holder?.[b.field];
      return v === undefined ? null : { source: `line:${b.predicate} ${b.field}`, text: typeof v === "string" ? v : JSON.stringify(v) };
    }
  }
}

function manifestsLine(a: Artifact, scope: string): JsonObject | null {
  const s = a.table.get(scope);
  if (!s) return null;
  // stored first; else a derived manifests carries the fields in the scope
  const stored = s.stored.find((l) => l.predicate === "manifests");
  if (stored) return stored;
  return { at: s.at, predicate: "manifests", term: s.terms[0], ...s.fields };
}
