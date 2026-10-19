// derive.ts — structure from a shape (spec §11.7). Every `select`, `columns` and `spine` line along the artifact's shape
// chain mints scopes from the parse: a selected node is a scope of `form` at its span (or its route); its parent is
// the nearest enclosing scope of the form `in` names, else it is top-level; siblings in byte order; a line with
// `field` fills that field of the nearest enclosing scope of `form` (with `attr`, from the node's source); a line with
// `reads` makes the node that scope's reading; `level` sets a heading's level. A sheet's declared header row and its
// rows; a container's route scopes. On a structured artifact this is its structure, derived and never stored; on a
// rendered one it is a proposal (§11.7.5). Chrome is what the shape's and the record's declared rules say (§8.4.6).
import { canonicalAt, contains, encodePath, parseAddress } from "../address/address.ts";
import { delimiterFor, parseCsv } from "../formats/csv/parse.ts";
import { formatOf } from "../formats/index.ts";
import type { PageWords } from "../formats/pdf/words.ts";
import { type Selected, type SelectParse, select } from "../select/select.ts";
import { all, refinesChain } from "../vocab/load.ts";
import type { Vocabulary } from "../vocab/terms.ts";

type J = Record<string, unknown>;

export interface DScope {
  form: string | string[];
  at: string;
  fields: J;
  /** The node the scope reads, where its shape names one, and the aspect (§11.7.1). */
  reads?: { at: string; aspect: string; text: string };
  /** The selected node's text: the scope's surface where it reads no other node. */
  text: string;
  scopes: DScope[];
}

export interface ChromeRun {
  at: string;
  text: string;
  role?: string;
}

const spanOf = (at: string): [number, number] | null => {
  const r = parseAddress(at).regions[0]!;
  return r.bytes ? [r.bytes[0], r.bytes[1]] : null;
};
const enclosing = (outer: string, inner: string) => outer === inner || contains(outer, inner);

/** The shape chain's lines of a predicate, the shape's own first. */
const chainLines = (v: Vocabulary, shape: string, pred: string): J[] =>
  refinesChain(v, "shapes", shape).flatMap((s) => all(v.shapes.get(s), pred) as J[]);

/** A form's field declaration, along its refines chain. */
function fieldDecl(v: Vocabulary, form: string, name: string): J | undefined {
  for (const f of refinesChain(v, "forms", form)) {
    const d = (all(v.forms.get(f), "field") as J[]).find((x) => x.name === name);
    if (d) return d;
  }
  return undefined;
}

/** A value filled from a source (§10.7.4): verbatim; where the field declares a pattern, its first capture. */
function fill(v: Vocabulary, form: string, field: string, raw: string): string {
  const d = fieldDecl(v, form, field);
  if (!d || typeof d.pattern !== "string") return raw;
  const m = new RegExp(d.pattern).exec(raw);
  return m ? (m[1] ?? m[0]) : raw;
}

/** The scopes the chain's select lines mint from a parse. */
export function deriveSelect(v: Vocabulary, shape: string, parse: SelectParse): DScope[] {
  const lines = chainLines(v, shape, "select");
  const minted: (DScope & { _in?: string })[] = [];
  const byAt = new Map<string, DScope & { _in?: string }>();
  for (const l of lines.filter((x) => x.field === undefined && x.reads === undefined)) {
    for (const n of select(parse, l.selector)) {
      const at = canonicalAt(n.at);
      const have = byAt.get(at);
      if (have) {
        const forms = [have.form].flat();
        if (!forms.includes(String(l.form))) have.form = [...forms, String(l.form)].sort();
        continue;
      }
      const s: DScope & { _in?: string } = {
        form: String(l.form),
        at,
        fields: {},
        text: n.text,
        scopes: [],
        ...(typeof l.in === "string" ? { _in: l.in } : {}),
      };
      if (typeof l.level === "number") s.fields.level = l.level;
      else if (n.level !== undefined && l.form) s.fields.level = n.level;
      byAt.set(at, s);
      minted.push(s);
    }
  }
  const hasForm = (s: DScope, f: string) => [s.form].flat().some((x) => refinesChain(v, "forms", x).includes(f));
  /** The smallest minted scope of `form` that encloses `at`. */
  const nearest = (form: string, at: string, not?: DScope): DScope | null => {
    let best: DScope | null = null;
    for (const s of minted) {
      if (s === not || !hasForm(s, form) || !enclosing(s.at, at)) continue;
      const sp = spanOf(s.at);
      const bp = best ? spanOf(best.at) : null;
      if (!best || (sp && bp && sp[1] - sp[0] < bp[1] - bp[0])) best = s;
    }
    return best;
  };
  // fields and readings
  for (const l of lines.filter((x) => x.field !== undefined || x.reads !== undefined))
    for (const n of select(parse, l.selector)) {
      const s = nearest(String(l.form), canonicalAt(n.at));
      if (!s) continue;
      if (l.field !== undefined) {
        const raw = typeof l.attr === "string" ? n.attr(l.attr) : n.text;
        if (raw !== null && s.fields[String(l.field)] === undefined)
          s.fields[String(l.field)] = fill(v, [s.form].flat()[0]!, String(l.field), raw);
      } else if (!s.reads) s.reads = { at: canonicalAt(n.at), aspect: String(l.reads), text: n.text };
    }
  // the tree: a scope with `in` hangs from the nearest enclosing scope of that form
  const top: DScope[] = [];
  for (const s of minted) {
    const parent = s._in ? nearest(s._in, s.at, s) : null;
    delete s._in;
    (parent ? parent.scopes : top).push(s);
  }
  const order = (xs: DScope[]) => {
    xs.sort((a, b) => (spanOf(a.at)?.[0] ?? 0) - (spanOf(b.at)?.[0] ?? 0));
    for (const x of xs) order(x.scopes);
  };
  order(top);
  return top;
}

/** A sheet (§11.7.2): the declared header row of its `columns` form first, then every other row of the `rows` form. */
export function deriveSheet(
  v: Vocabulary,
  shape: string,
  bytes: Uint8Array,
  mime: string,
): { scopes: DScope[]; names: Map<number, string> } {
  const cols = chainLines(v, shape, "columns");
  const header = cols.find((c) => typeof c.header === "number");
  const rows = cols.find((c) => typeof c.rows === "string");
  const p = parseCsv(bytes, delimiterFor(mime));
  const scopes: DScope[] = [];
  const names = new Map<number, string>();
  for (const [i, r] of p.rows.entries()) {
    const cells = r.cells.map((c) => c.value);
    if (header && i === header.header) {
      for (const [k, c] of cells.entries()) names.set(k, c);
      scopes.push({ form: String(header.form), at: `row=${i}`, fields: {}, text: cells.join("\t"), scopes: [] });
    } else if (rows) scopes.push({ form: String(rows.rows), at: `row=${i}`, fields: {}, text: cells.join("\t"), scopes: [] });
  }
  return { scopes, names };
}

/** A structured artifact's structure, or a rendered artifact's proposed tree, from its shape: a sheet's rows, a
 * package's spine, the scopes its select lines name. */
export function deriveTree(
  v: Vocabulary,
  shape: string,
  mime: string,
  bytes: Uint8Array,
  parse: SelectParse | null,
  intrinsics: J,
): DScope[] {
  if (formatOf(mime).name === "csv") return deriveSheet(v, shape, bytes, mime).scopes;
  return [...deriveSpine(v, shape, intrinsics), ...(parse ? deriveSelect(v, shape, parse) : [])];
}

/** A package's spine as route scopes in spine order (§11.7.3), from its intrinsics. */
export function deriveSpine(v: Vocabulary, shape: string, intrinsics: J): DScope[] {
  const spine = chainLines(v, shape, "spine")[0];
  if (!spine || !Array.isArray(intrinsics.spine)) return [];
  return (intrinsics.spine as string[]).map((p) => ({
    form: String(spine.form),
    at: canonicalAt(`path=${encodePath(p)}`),
    fields: {},
    text: "",
    scopes: [],
  }));
}

// ── chrome ──────────────────────────────────────────────────────────────────────────────────────────────────────────

/** Chrome by the declared rules (§11.2.3, §8.4.6): selector rules over the parse; repetition rules over a PDF's lines. */
export function chromeOf(rules: readonly J[], parse: SelectParse | null, pages: readonly PageWords[] | null): ChromeRun[] {
  const out: ChromeRun[] = [];
  for (const r of rules) {
    if (r.selector !== undefined && parse)
      for (const n of select(parse, r.selector) as Selected[]) out.push({ at: canonicalAt(n.at), text: n.text });
    const rep = r.repeats as { pages?: number; share?: number } | undefined;
    if (rep && pages) {
      const places = Number(r.box ?? 3);
      const round = (x: number) => Math.round(x * 10 ** places) / 10 ** places;
      const mask = (t: string) => (r.mask === "digits" ? t.replace(/\d+/g, "#") : t);
      const seen = new Map<string, { pages: Set<number>; runs: { page: number; line: PageWords["lines"][number] }[] }>();
      for (const p of pages)
        for (const l of p.lines) {
          const key = `${mask(l.text)}|${round(l.y)}|${round(l.x0)}|${round(l.h)}`;
          const e = seen.get(key) ?? { pages: new Set(), runs: [] };
          e.pages.add(p.page);
          e.runs.push({ page: p.page, line: l });
          seen.set(key, e);
        }
      const roles = (r.roles as Record<string, string> | undefined) ?? {};
      for (const [key, e] of seen) {
        if (e.pages.size < Number(rep.pages ?? 1) || e.pages.size / pages.length < Number(rep.share ?? 0)) continue;
        const masked = key.split("|")[0]!;
        // a role's pattern is a masked run the line holds: a page number banded with other footer text keeps its role
        const role = Object.entries(roles).find(([, pat]) => masked.includes(pat))?.[0];
        for (const { page, line } of e.runs)
          out.push({
            at: canonicalAt(`page=${page}&bbox=${line.x0},${line.y},${Math.max(0, line.x1 - line.x0)},${line.h}`),
            text: line.text,
            role: role ?? (line.y < 0.5 ? "running-header" : "running-footer"),
          });
      }
    }
  }
  return out;
}

/** Every scope, depth first, with its positional address (§7.6.1): its positions from the root, 1-based. */
export function* positional<S extends { scopes?: S[] }>(
  scopes: readonly S[] | undefined,
  prefix: number[] = [],
): Generator<{ scope: S; path: number[] }> {
  for (const [i, s] of (scopes ?? []).entries()) {
    const path = [...prefix, i + 1];
    yield { scope: s, path };
    yield* positional(s.scopes, path);
  }
}
