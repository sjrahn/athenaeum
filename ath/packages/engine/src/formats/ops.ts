// ops.ts — the surface ops and hint ops by `name@version` (spec §10.5, §10.6). A surface op decodes the text at a
// scope of a structured artifact — a function of the bytes, the region and its argument, versioned by its behaviour
// — and a claim may bind to it. A hint op guesses at what a rendered artifact shows: its text and its units, each
// unit with its own intrinsic address, never bound and never stored. The bytes are parsed once per family per
// artifact (§10.5.2); an op says which arguments it takes and refuses every other.
import { AthError } from "@ath/kit/errors.ts";
import type { Region } from "../address/address.ts";

/** One unit of a hint — a word on a page, a run of text, a candidate region of speech — at its own address. */
export interface Unit {
  text: string;
  at: string;
}

export interface Hint {
  text: string;
  units: Unit[];
}

export interface Op<F = unknown> {
  /** `name@version`. */
  name: string;
  kind: "surface" | "hint";
  /** The format whose parse it reads (`csv`, `html`, …). */
  family: string;
  /** Whether the argument shapes the parse itself (`csv.parse@1 tab`), so parses are cached by it. */
  parseArg?: boolean;
  /** Why an argument is refused, or null; an op that declares none takes no argument. */
  arg?: (arg: string | undefined) => string | null;
  parse(bytes: Uint8Array, arg: string | undefined): F | Promise<F>;
  surface?(form: F, region: Region, arg: string | undefined): string | null;
  hint?(form: F, region: Region, arg: string | undefined): Hint | null | Promise<Hint | null>;
}

const ops = new Map<string, Op>();

export function registerOp<F>(op: Op<F>): void {
  if (ops.has(op.name)) throw new AthError("INTERNAL", `op ${op.name} is registered twice`);
  ops.set(op.name, op as Op);
}

export const opNamed = (name: string): Op | null => ops.get(name) ?? null;
export const opNames = (): string[] => [...ops.keys()].sort();

/** `<op>@<version>[ <argument>]` → its parts (§11.2.3 `surface`, §14.4.1 `derived:`). */
export function parseOpRef(ref: string): { name: string; arg?: string } {
  const m = /^([a-z0-9]+\.[a-z0-9]+@[1-9]\d*)(?: (\S.*))?$/.exec(ref.trim());
  if (!m) throw new AthError("USAGE", `'${ref}' is not an op reference: <name>@<version>[ <argument>]`);
  return m[2] === undefined ? { name: m[1]! } : { name: m[1]!, arg: m[2] };
}

/** Why an op reference cannot be used, or null: the op is unregistered, or refuses its argument. */
export function opProblem(ref: string): string | null {
  let r: { name: string; arg?: string };
  try {
    r = parseOpRef(ref);
  } catch (e) {
    return (e as Error).message;
  }
  const op = ops.get(r.name);
  if (!op) return `${r.name} is not an op this tool registers`;
  if (op.arg) return op.arg(r.arg);
  return r.arg === undefined ? null : `${op.name} takes no argument, got '${r.arg}'`;
}

/** One artifact's parses, by family and, where the argument shapes the parse, by argument. */
export class Parses {
  private cache = new Map<string, Promise<unknown>>();
  constructor(readonly bytes: Uint8Array) {}
  get<F>(op: Op<F>, arg: string | undefined): Promise<F> {
    const key = op.parseArg && arg !== undefined ? `${op.family}|${arg}` : op.family;
    let p = this.cache.get(key) as Promise<F> | undefined;
    if (!p) {
      p = Promise.resolve(op.parse(this.bytes, arg));
      this.cache.set(key, p);
    }
    return p;
  }
}

/** The surface an op yields at an address: a union's regions joined by a newline (§10.5.1); null where it yields none. */
export async function surfaceAt(parses: Parses, ref: string, regions: readonly Region[]): Promise<string | null> {
  const problem = opProblem(ref);
  if (problem) throw new AthError("CONFIG", problem);
  const { name, arg } = parseOpRef(ref);
  const op = ops.get(name)!;
  if (op.kind !== "surface" || !op.surface) throw new AthError("CONFIG", `${name} is a hint; nothing binds to it`);
  const form = await parses.get(op, arg);
  const parts: string[] = [];
  for (const r of regions) {
    const s = op.surface(form, r, arg);
    if (s === null) return null;
    parts.push(s);
  }
  return parts.join("\n");
}

/** What a hint op guesses at an address: the regions' texts joined by a newline, their units together. */
export async function hintAt(parses: Parses, ref: string, regions: readonly Region[]): Promise<Hint | null> {
  const { name, arg } = parseOpRef(ref);
  const op = ops.get(name);
  if (!op?.hint) return null;
  const form = await parses.get(op, arg);
  const texts: string[] = [];
  const units: Unit[] = [];
  for (const r of regions) {
    const h = await op.hint(form, r, arg);
    if (!h) return null;
    texts.push(h.text);
    units.push(...h.units);
  }
  return { text: texts.join("\n"), units };
}
