// index.ts — ath's command contracts: one declaration per command of its arguments (zod), its argv shape and its
// output (zod). The CLI parser, the generated help and `--schema` all derive from it. The one physical copy of zod;
// everything in ath imports `z` from here.
import { z } from "zod";

export { z };

/** One positional argument, in order. A variadic one must be last and collects the rest. */
export interface PositionalSpec {
  name: string;
  required?: boolean;
  variadic?: boolean;
  help?: string;
}

/** One `--flag`. `repeat` collects every occurrence into an array. `short` is a single letter (`-v`). */
export interface FlagSpec {
  type: "string" | "boolean" | "number";
  short?: string;
  repeat?: boolean;
  help?: string;
  /** The value's name in help (`--root PATH`). */
  metavar?: string;
}

/** How argv maps onto the args object: positionals by name, flags by their camelCased name (`--dry-run` → `dryRun`). */
export interface ArgvSpec {
  positionals?: PositionalSpec[];
  flags?: Record<string, FlagSpec>;
}

export interface Contract<A extends z.ZodType = z.ZodType, D extends z.ZodType = z.ZodType> {
  /** The command key, kebab-case words joined by dashes: `layer-init`, `pass-sign`. */
  key: string;
  args: A;
  argv: ArgvSpec;
  data: D;
}

export type AnyContract = Contract<z.ZodType, z.ZodType>;
export type ArgsOf<C extends AnyContract> = z.output<C["args"]>;
export type DataOf<C extends AnyContract> = z.input<C["data"]>;

/** A bad invocation, found while parsing or validating argv. The kit maps it to USAGE (64). */
export class ContractUsageError extends Error {
  constructor(
    message: string,
    readonly key: string,
  ) {
    super(message);
  }
}

const KEBAB = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/;
const camel = (s: string): string => s.replace(/-([a-z0-9])/g, (_, c: string) => c.toUpperCase());
const kebab = (s: string): string => s.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

function objectKeys(a: z.ZodType): string[] | undefined {
  return a instanceof z.ZodObject ? Object.keys(a.shape) : undefined;
}

/** Every flag with its option name (`--dry-run`) and args key (`dryRun`). */
function flagList(argv: ArgvSpec): { name: string; key: string; spec: FlagSpec }[] {
  return Object.entries(argv.flags ?? {}).map(([k, spec]) => ({ name: kebab(k), key: camel(kebab(k)), spec }));
}

/** Declare a contract. Checks the argv spec against the args schema's keys at declaration time (a mismatch throws). */
export function defineContract<A extends z.ZodType, D extends z.ZodType>(c: Contract<A, D>): Contract<A, D> {
  const fail = (msg: string): never => {
    throw new Error(`contract ${c.key}: ${msg}`);
  };
  if (!KEBAB.test(c.key)) fail("key must be kebab-case");
  const positionals = c.argv.positionals ?? [];
  const flags = flagList(c.argv);
  const keys = objectKeys(c.args);
  if (!keys) return fail("args must be a z.object");
  const covered = new Set<string>();
  positionals.forEach((p, i) => {
    if (!keys.includes(p.name)) fail(`positional \`${p.name}\` is not a key of args`);
    if (covered.has(p.name)) fail(`positional \`${p.name}\` is declared twice`);
    covered.add(p.name);
    if (p.variadic && i !== positionals.length - 1) fail(`variadic positional \`${p.name}\` must be last`);
  });
  const shorts = new Set<string>();
  for (const f of flags) {
    if (!keys.includes(f.key)) fail(`flag --${f.name} has no \`${f.key}\` key in args`);
    if (covered.has(f.key)) fail(`flag --${f.name} collides with another argument named \`${f.key}\``);
    covered.add(f.key);
    const s = f.spec.short;
    if (s !== undefined) {
      if (!/^[a-zA-Z]$/.test(s)) fail(`short flag for --${f.name} must be one letter`);
      if (shorts.has(s)) fail(`short flag -${s} is used twice`);
      shorts.add(s);
    }
  }
  for (const k of keys) if (!covered.has(k)) fail(`args key \`${k}\` has no positional or flag`);
  return c;
}

function zodMessage(key: string, error: z.ZodError): ContractUsageError {
  const lines = error.issues.map((i) => `${i.path.length ? i.path.map(String).join(".") : "(root)"}: ${i.message}`);
  return new ContractUsageError(lines.join("\n"), key);
}

function validate<C extends AnyContract>(contract: C, raw: unknown): ArgsOf<C> {
  const r = contract.args.safeParse(raw);
  if (!r.success) throw zodMessage(contract.key, r.error);
  return r.data as ArgsOf<C>;
}

const isValueToken = (t: string): boolean => !t.startsWith("-") || t === "-" || /^-\d/.test(t) || /^-\.\d/.test(t);

/** argv (the tokens after the command's words) → validated args. Throws ContractUsageError. */
export function parseArgv<C extends AnyContract>(contract: C, argv: readonly string[]): ArgsOf<C> {
  const usage = (m: string) => new ContractUsageError(m, contract.key);
  const positionals = contract.argv.positionals ?? [];
  const flags = flagList(contract.argv);
  const byName = new Map(flags.map((f) => [f.name, f]));
  const byShort = new Map(flags.filter((f) => f.spec.short).map((f) => [f.spec.short as string, f]));
  const raw: Record<string, unknown> = {};
  const pos: string[] = [];

  const store = (f: (typeof flags)[number], label: string, value: string | boolean) => {
    let v: string | number | boolean = value;
    if (f.spec.type === "number") {
      if (!/^-?\d+(\.\d+)?$/.test(String(value))) throw usage(`argument ${label}: invalid number value: '${value}'`);
      v = Number(value);
    }
    if (f.spec.repeat) {
      const arr = (raw[f.key] as unknown[] | undefined) ?? [];
      arr.push(v);
      raw[f.key] = arr;
    } else raw[f.key] = v;
  };
  const needValue = (label: string, next: string | undefined): string => {
    if (next === undefined || !isValueToken(next)) throw usage(`argument ${label}: expected one argument`);
    return next;
  };

  let i = 0;
  for (; i < argv.length; i++) {
    const t = argv[i] as string;
    if (t === "--") {
      pos.push(...argv.slice(i + 1));
      break;
    }
    if (t.startsWith("--") && t.length > 2) {
      const eq = t.indexOf("=");
      const name = eq === -1 ? t.slice(2) : t.slice(2, eq);
      const inline = eq === -1 ? undefined : t.slice(eq + 1);
      const f = byName.get(name);
      if (!f) {
        if (name.startsWith("no-") && byName.get(name.slice(3))?.spec.type === "boolean") {
          store(byName.get(name.slice(3))!, `--${name}`, false);
          continue;
        }
        throw usage(`unrecognized argument: --${name}`);
      }
      if (f.spec.type === "boolean") {
        if (inline !== undefined) throw usage(`argument --${name}: takes no value`);
        store(f, `--${name}`, true);
      } else store(f, `--${name}`, inline ?? needValue(`--${name}`, argv[++i]));
      continue;
    }
    if (t.startsWith("-") && t.length > 1 && !isValueToken(t)) {
      const s = t.slice(1);
      const f = byShort.get(s);
      if (!f) throw usage(`unrecognized argument: ${t}`);
      if (f.spec.type === "boolean") store(f, t, true);
      else store(f, t, needValue(t, argv[++i]));
      continue;
    }
    pos.push(t);
  }

  let pi = 0;
  for (const p of positionals) {
    if (p.variadic) {
      raw[p.name] = pos.slice(pi);
      pi = pos.length;
      break;
    }
    const v = pos[pi];
    if (v === undefined) {
      if (p.required) throw usage(`missing required argument: ${p.name}`);
      continue;
    }
    raw[p.name] = v;
    pi++;
  }
  if (pi < pos.length) throw usage(`unexpected arguments: ${pos.slice(pi).join(" ")}`);
  return validate(contract, raw);
}

/** An args object (over a socket or HTTP) → validated args. Keys the contract does not declare are refused, so a
 * caller never passes what a terminal could not. Throws ContractUsageError. */
export function parseArgs<C extends AnyContract>(contract: C, raw: unknown): ArgsOf<C> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw))
    throw new ContractUsageError("the arguments are one JSON object", contract.key);
  const keys = objectKeys(contract.args) ?? [];
  for (const k of Object.keys(raw)) if (!keys.includes(k)) throw new ContractUsageError(`unrecognized argument: ${k}`, contract.key);
  return validate(contract, raw);
}

/** The usage line and the argument table for one contract. */
export function usageText(prog: string, c: AnyContract, summary?: string): string {
  const words = c.key.replaceAll("-", " ");
  const positionals = c.argv.positionals ?? [];
  const flags = flagList(c.argv);
  const posPart = positionals.map((p) => (p.required ? `<${p.name}>` : `[${p.name}]`) + (p.variadic ? "…" : "")).join(" ");
  const head = `usage: ${prog} ${words}${posPart ? ` ${posPart}` : ""}${flags.length ? " [flags]" : ""}`;
  const rows: [string, string][] = [];
  for (const p of positionals) rows.push([p.name, p.help ?? ""]);
  for (const f of flags) {
    const short = f.spec.short ? `-${f.spec.short}, ` : "";
    const val = f.spec.type === "boolean" ? "" : ` ${f.spec.metavar ?? f.spec.type.toUpperCase()}`;
    rows.push([`${short}--${f.name}${val}`, f.spec.help ?? ""]);
  }
  const w = Math.max(0, ...rows.map(([a]) => a.length));
  const table = rows.map(([a, b]) => `  ${a.padEnd(w)}  ${b}`.trimEnd()).join("\n");
  return `${head}\n${summary ? `\n${summary}\n` : ""}${table ? `\n${table}\n` : ""}`;
}

/** The JSON Schema of a contract's args and data, for `--schema`. */
export function contractJsonSchema(c: AnyContract): { key: string; args: unknown; data: unknown } {
  return { key: c.key, args: z.toJSONSchema(c.args), data: z.toJSONSchema(c.data) };
}
