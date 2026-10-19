// registry.ts — derivation ops by `name@version`. An op is a pure function of bytes (and an address) that yields a
// byte-fact: the attestation of what the bytes are, or the quote surface a term's `derivation` names. Ops never read
// a layer and never touch the network.
export interface AttestResult {
  /** The `attests` value: mime, bytes, and the format's own facts. */
  value: Record<string, unknown>;
  /** A container's members: each becomes its own subject. */
  members?: { path: string; bytes: Uint8Array; blake3?: string /** A file name to sniff by, when the path is not one. */; name?: string }[];
}

export type Attester = (bytes: Uint8Array, mime: string) => Promise<AttestResult>;

const attesters = new Map<string, Attester>();

/** Register the attester for a mime (exact) or a family (`image/*`). */
export function registerAttester(mime: string, fn: Attester): void {
  attesters.set(mime, fn);
}

export function attesterFor(mime: string): Attester | null {
  return attesters.get(mime) ?? attesters.get(`${mime.split("/")[0]}/*`) ?? attesters.get("*/*") ?? null;
}

// ── derivation ops (D-derivation) ───────────────────────────────────────────────────────────────────────────────────
// The ontology names the op (`derivation: <op>@<v>[ <arg>]`); the registry is the only place an op exists. An op of
// one family shares one parse of the bytes with the other ops of that family (html.text, html.attr and html.title all
// read one DOM); the parse is cached on the artifact by family (and by arg where the arg shapes the parse).

import type { Aspect, Region } from "../address/address.ts";

export type Family = "html" | "csv" | "pdf" | "mail";

export interface DerivationOp<F = unknown> {
  /** `name@version`, the string the ontology and every binding name. */
  name: string;
  /** The parsed form this op reads; one parse per family per artifact. */
  family: Family;
  /** Whether the arg shapes the parse (csv.parse@1 tab) rather than the surface (html.attr@1 datetime). */
  parseArg?: boolean;
  parse: (bytes: Uint8Array, arg: string | undefined) => F | Promise<F>;
  /** Why the arg is not one this op takes, or null when it is (the ontology lint and the resolver both ask). */
  arg?: (arg: string | undefined) => string | null;
  /** The surface at one address member, or null when the op does not serve that kind of address there. */
  surface: (form: F, region: Region, arg: string | undefined, aspect: Aspect) => string | null;
}

const ops = new Map<string, DerivationOp>();

export function registerOp<F>(op: DerivationOp<F>): void {
  ops.set(op.name, op as DerivationOp);
}

export function opFor(name: string): DerivationOp | null {
  return ops.get(name) ?? null;
}

export function opNames(): string[] {
  return [...ops.keys()].sort();
}

/** Why `arg` is not acceptable to `op`, or null; an op that declares no check takes no arg at all. */
export function argProblem(op: DerivationOp, arg: string | undefined): string | null {
  if (op.arg) return op.arg(arg);
  return arg === undefined ? null : `${op.name} takes no argument, got '${arg}'`;
}

/** The cache key of an op's form on an artifact. */
export function formKey(op: DerivationOp, arg: string | undefined): string {
  return op.parseArg && arg ? `${op.family}|${arg}` : op.family;
}
