// check.ts — the vocabulary check (spec §17.4): over the vocabularies as loaded, every line in the grammar its
// predicate takes (§11.2), and the refusals §17.4 lists — a term refining another vocabulary's, a predicate its
// vocabulary does not carry, a form naming a format, a shape or a family, a `reads`, `where` or `convention` outside
// its set, a `surface` op that does not parse, is unregistered, refuses its argument or reaches a rendered format, a
// selector its format's language rejects, a `matches` without `mime`, an `origin` pointer that does not parse, an
// `owes` naming no property, a `range` naming neither a type, `artifact` nor a kind, a name an entity and a kind
// share, a write at an identity the base holds, a `refines` cycle. Names follow §5.3.
import { formats } from "../formats/index.ts";
import { opProblem, parseOpRef } from "../formats/ops.ts";
import { selectorFamily as familyOfMime, selectorProblem } from "../select/select.ts";
import { all, type LoadedVocabulary, one } from "./load.ts";
import { PREDICATES, termIdentity, VOCABS, type Vocab } from "./terms.ts";

export interface VocabFinding {
  vocab: Vocab;
  term: string;
  problem: string;
}

const NAME = /^[a-z0-9][a-z0-9-]*$/;
const READS = new Set(["text", "cells", "tex", "none"]);
const TYPES = new Set(["int", "enum", "datetime", "string", "col", "designator", "list"]);
const WHERE = new Set(["leading", "trailing", "margin"]);
const RANGES = new Set(["string", "int", "decimal", "amount", "date", "datetime", "uri", "bool", "artifact"]);
const MATCH_KEYS = new Set(["mime", "first_row", "selector", "magic", "container", "constituent", "path", "origin"]);
const SELECT_KEYS = new Set(["selector", "form", "in", "field", "attr", "reads", "ord", "level"]);
type J = Record<string, unknown>;
const isObj = (v: unknown): v is J => !!v && typeof v === "object" && !Array.isArray(v);
const strList = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === "string");

export function vocabularyCheck(lv: LoadedVocabulary, own: string, entities: Iterable<string> = []): VocabFinding[] {
  const { vocab: v, holders } = lv;
  const out: VocabFinding[] = [];
  const find = (vocab: Vocab, term: string, problem: string) => out.push({ vocab, term, problem });
  const formatNames = new Set(
    formats().flatMap((f) => [f.name, ...f.mimes.map((m) => m.split("/")[1]!.replace(/^x-/, "").split("+")[0]!)]),
  );
  for (const vocab of VOCABS)
    for (const [term, lines] of v[vocab]) {
      if (!NAME.test(term) || /^[0-9a-f]+$/.test(term))
        find(vocab, term, "a name is lowercase letters, digits and hyphens, and not hex digits alone (§5.3)");
      // identity: a line the base holds, written again here with different content
      const ids = new Map<string, J[]>();
      for (const l of lines) ids.set(termIdentity(l), [...(ids.get(termIdentity(l)) ?? []), l]);
      for (const [id, ls] of ids)
        if (ls.length > 1 && new Set(ls.map((l) => JSON.stringify(l))).size > 1)
          find(
            vocab,
            term,
            `writes at an identity ${holders[vocab].get(term)?.get(id) === own ? "twice" : `the base ${holders[vocab].get(term)?.get(id)} holds`}: ${id.split("\u0000")[0]}`,
          );
      for (const l of lines) {
        const pred = String(l.pred);
        const val = l.val;
        if (!PREDICATES[vocab].includes(pred)) {
          find(vocab, term, `\`${pred}\` is not a predicate of ${vocab}`);
          continue;
        }
        const bad = (m: string) => find(vocab, term, `${pred}: ${m}`);
        switch (pred) {
          case "refines":
            if (typeof val !== "string") bad("names one term");
            else if (!v[vocab].has(val))
              bad(
                `'${val}' is not a term of ${vocab}${VOCABS.some((o) => o !== vocab && v[o].has(val)) ? " (it is another vocabulary's)" : ""}`,
              );
            break;
          case "definition":
          case "aligns":
            if (typeof val !== "string" || !val.trim()) bad("is one non-empty string");
            break;
          case "reads":
            if (!READS.has(val as string)) bad("is one of text, cells, tex, none");
            break;
          case "field": {
            if (!isObj(val) || typeof val.name !== "string" || !TYPES.has(val.type as string)) {
              bad(`is {name, type} with type one of ${[...TYPES].join(", ")}`);
              break;
            }
            if (val.where !== undefined && !(WHERE.has(val.where as string) || v.forms.has(val.where as string)))
              bad("`where` is leading, trailing, margin or a form");
            if (val.pattern !== undefined)
              try {
                new RegExp(String(val.pattern));
              } catch {
                bad("`pattern` is not a regular expression");
              }
            break;
          }
          case "expects":
            if (!strList(val)) bad("lists forms");
            else for (const f of val) if (!v.forms.has(f)) bad(`'${f}' is not a form`);
            break;
          case "convention": {
            const keys = isObj(val) ? Object.keys(val) : [];
            const ok =
              keys.length === 1 &&
              ((keys[0] === "footnotes" && typeof (val as J).footnotes === "string") ||
                (val as J).hyphens === "rejoin" ||
                (val as J).scripts === "flatten-outside-math" ||
                (val as J).bullets === "drop");
            if (!ok) bad("is one of {footnotes: <pattern>}, {hyphens: rejoin}, {scripts: flatten-outside-math}, {bullets: drop}");
            break;
          }
          case "renders":
            if (!isObj(val) || typeof val.md !== "string") bad("is {md: <template>}");
            break;
          case "check": {
            const ok =
              isObj(val) &&
              ((typeof val.every === "string" && typeof val.names === "string") ||
                (typeof val.contains === "string" && typeof val.at_least === "number") ||
                (typeof val.field === "string" && typeof val.agrees === "string" && String(val.agrees).startsWith("intrinsics.")));
            if (!ok) bad("is {every, names}, {contains, at_least} or {field, agrees: intrinsics.<key>}");
            break;
          }
          case "matches": {
            if (!isObj(val) || typeof val.mime !== "string") {
              bad("has a `mime`");
              break;
            }
            for (const k of Object.keys(val)) if (!MATCH_KEYS.has(k)) bad(`\`${k}\` is not a condition`);
            const fam = familyOfMime(val.mime);
            if (val.selector !== undefined) {
              const p = fam ? selectorProblem(fam, val.selector) : `${val.mime} has no selector language`;
              if (p) bad(`selector: ${p}`);
            }
            if (val.origin !== undefined) {
              if (!isObj(val.origin)) bad("origin is {<pointer>: <pattern> | true}");
              else
                for (const [ptr, pat] of Object.entries(val.origin))
                  if (!ptr.startsWith("/") || !(pat === true || typeof pat === "string"))
                    bad(`origin: '${ptr}' is not a JSON pointer to a pattern or true`);
            }
            if (val.first_row !== undefined && !strList(val.first_row)) bad("first_row lists cells");
            break;
          }
          case "select":
            if (!isObj(val) || val.selector === undefined || typeof val.form !== "string") bad("is {selector, form, …}");
            else {
              for (const k of Object.keys(val)) if (!SELECT_KEYS.has(k)) bad(`\`${k}\` is not a key of select`);
              if (!v.forms.has(val.form as string)) bad(`'${val.form}' is not a form`);
              if (val.in !== undefined && !v.forms.has(val.in as string)) bad(`in: '${val.in}' is not a form`);
              if (val.reads !== undefined && !READS.has(val.reads as string)) bad("reads is text, cells or tex");
              for (const m of all(lines, "matches") as J[]) {
                const fam = isObj(m) && typeof m.mime === "string" ? familyOfMime(m.mime) : null;
                const p = fam ? selectorProblem(fam, val.selector) : null;
                if (p) bad(`selector: ${p}`);
              }
            }
            break;
          case "columns":
            if (
              !isObj(val) ||
              !(
                (val.col !== undefined && typeof val.form === "string") ||
                (typeof val.header === "number" && typeof val.form === "string") ||
                typeof val.rows === "string"
              )
            )
              bad("is {col, form, …}, {header: <row>, form} or {rows: <form>}");
            else
              for (const f of [val.form, val.rows].filter((x) => x !== undefined))
                if (!v.forms.has(f as string)) bad(`'${f}' is not a form`);
            break;
          case "spine":
            if (!isObj(val) || !v.forms.has(val.form as string)) bad("is {form} naming a form");
            break;
          case "chrome":
            if (!isObj(val) || !(val.selector !== undefined || isObj(val.repeats)))
              bad("is {selector} or {repeats: {pages, share}, mask, box, roles}");
            break;
          case "surface": {
            if (!isObj(val) || typeof val.form !== "string" || typeof val.op !== "string") {
              bad("is {form, op}");
              break;
            }
            const p = opProblem(val.op);
            if (p) bad(p);
            else {
              const op = parseOpRef(val.op).name;
              for (const m of all(lines, "matches") as J[]) {
                const f = isObj(m) ? formats().find((x) => x.mimes.includes(String(m.mime))) : undefined;
                if (f?.class === "rendered") bad(`${op} reaches ${m.mime}, a rendered format, which gives no surface`);
              }
            }
            break;
          }
          case "owes":
            if (!strList(val)) bad("lists properties");
            else for (const p of val) if (!v.properties.has(p)) bad(`'${p}' is not a property`);
            break;
          case "range":
            if (typeof val !== "string" || !(RANGES.has(val) || v.kinds.has(val))) bad("names a type, `artifact` or a kind");
            break;
          case "functional":
          case "authority":
            if (typeof val !== "boolean") bad("is true or false");
            break;
        }
      }
      if (vocab === "forms" && (formatNames.has(term) || v.shapes.has(term)))
        find(vocab, term, "a form names structure, never a format, a shape or a family (§11.1.2)");
    }
  // refines cycles
  for (const vocab of VOCABS)
    for (const term of v[vocab].keys()) {
      const seen: string[] = [];
      for (let n: string | undefined = term; n; n = one(v[vocab].get(n), "refines") as string | undefined) {
        if (seen.includes(n)) {
          if (n === term) find(vocab, term, `refines in a cycle: ${[...seen, n].join(" → ")}`);
          break;
        }
        seen.push(n);
      }
    }
  for (const e of entities) if (v.kinds.has(e)) find("kinds", e, "an entity and a kind share the name");
  return out;
}
