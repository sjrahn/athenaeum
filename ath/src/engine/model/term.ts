// term.ts — what a term's lines may say (spec §7.2). Each predicate's value shape, loosely: the ontology is open
// vocabulary, and an extension may add predicates the foundation never used; what is checked is what the engine reads.
import { z } from "../../../contracts/index.ts";

export const FIELD_KINDS = ["int", "enum", "datetime", "string", "col", "designator", "list", "string | col"] as const;

export const FieldDecl = z
  .object({
    name: z.string().min(1),
    kind: z.enum(FIELD_KINDS),
    required: z.boolean().optional(),
    /** The value is a function of the address or another stored thing and is never written (D-D2). */
    derived: z.boolean().optional(),
    options: z.array(z.string()).optional(),
    where: z.string().optional(),
    pattern: z.string().optional(),
    /** The derived-address key this designator feeds (`sec`, `para`, `eq`, `table`, `post`, `col`, `page`). */
    address: z.string().optional(),
  })
  .passthrough();
export type FieldDecl = z.infer<typeof FieldDecl>;

export const SelectDecl = z
  .object({
    selector: z.string().min(1),
    term: z.string().min(1),
    in: z.string().optional(),
    /** A field on the derived manifests line, filled from `attr` (default: the attribute of the same name). */
    field: z.string().optional(),
    attr: z.string().optional(),
    ord: z.string().optional(),
    level: z.number().int().optional(),
  })
  .passthrough();
export type SelectDecl = z.infer<typeof SelectDecl>;

export const ShapeDecl = z.object({ col: z.string().min(1), term: z.string().min(1) }).passthrough();
export type ShapeDecl = z.infer<typeof ShapeDecl>;

export const MatchesDecl = z
  .object({
    mime: z.string().optional(),
    header: z.array(z.string()).optional(),
    selector: z.string().optional(),
    magic: z.string().optional(),
  })
  .passthrough();
export type MatchesDecl = z.infer<typeof MatchesDecl>;

/** The harvest rule (spec §9.4). `key` names the value that identifies the concept; absent, the concept is the one the
 * enclosing document manifests. A claims value names a scope by term (`author`), a field (`post.position`, `captured_from.uri`),
 * an attribute of the scope's own element (`@data-site`), an edge (`author → member`), a cell by index (definition lists)
 * or `*` (every row). Never a selector (D-F7): selectors live on `select` lines. */
export const ConceptDecl = z
  .object({
    term: z.string().min(1),
    key: z.string().min(1).optional(),
    claims: z.record(z.string(), z.union([z.string(), z.number()])),
    group: z.string().optional(),
  })
  .passthrough();
export type ConceptDecl = z.infer<typeof ConceptDecl>;

export const READS = ["text", "cells", "tex", "none"] as const;

/** The term predicates the engine interprets; anything else is carried through unchecked. */
export const KNOWN_PREDICATES = [
  "refines",
  "definition",
  "aligns",
  "matches",
  "axes",
  "physical",
  "tree",
  "derivation",
  "reads",
  "field",
  "expects",
  "owes",
  "convention",
  "renders",
  "select",
  "shape",
  "spine",
  "sentinel",
  "keys",
  "chrome",
  "concept",
  "lint",
  "cells",
  "origin",
  "functional",
] as const;

/** Repeatable predicates key on the value's name; the rest are single-valued per term. */
export const REPEATABLE = new Set(["field", "select", "shape", "convention", "concept", "lint", "matches"]);
