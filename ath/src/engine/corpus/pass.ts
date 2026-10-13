// pass.ts — a pass (spec §10.1, D-staging): one author and one verifier over one artifact. Its lines stage in
// <layer>/.ath/passes/<blake3>/<id>.jsonl until `pass sign` lints the stored ∪ staged tree and merges them into the
// claim file (corrections with lineage). Nothing under corpus/ exists unsigned.
import { existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { AthError } from "../../kit/errors.ts";
import { stateDir } from "../../kit/root.ts";
import { writeAtomic } from "../../lib/fs.ts";
import { type JsonObject, readJsonl, serializeJsonl } from "../../lib/jsonl.ts";
import type { Chain } from "../layer/config.ts";
import { readSubject, unionView } from "../layer/store.ts";
import { identityKey, PASS_REF, validateLine } from "../model/line.ts";
import { appendLines } from "./file.ts";
import { stampRevisions } from "./readings.ts";

export interface PassFile {
  id: string;
  blake3: string;
  path: string;
  pass: JsonObject;
  lines: JsonObject[];
}

const passDir = (chain: Chain, blake3: string) => join(stateDir(chain.top.root), "passes", blake3);
const passPath = (chain: Chain, blake3: string, id: string) => join(passDir(chain, blake3), `${id}.jsonl`);

export function listPasses(chain: Chain, blake3: string): PassFile[] {
  const dir = passDir(chain, blake3);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith(".jsonl"))
    .sort()
    .map((f) => readPass(chain, blake3, f.replace(/\.jsonl$/, "")));
}

export function readPass(chain: Chain, blake3: string, id: string): PassFile {
  const path = passPath(chain, blake3, id);
  if (!existsSync(path)) throw new AthError("NOT_FOUND", `no open pass ${id} on ${blake3.slice(0, 12)}…`);
  const lines = readJsonl(path);
  const pass = lines.find((l) => l.predicate === "pass");
  if (!pass) throw new AthError("CONFIG", `${path}: no pass line`);
  return { id, blake3, path, pass, lines: lines.filter((l) => l !== pass) };
}

/** The next free pass id on an artifact: after every signed and open one. */
export function nextPassId(chain: Chain, blake3: string): string {
  const used = new Set<string>();
  for (const l of readSubject(chain, "corpus", blake3)) if (l.line.predicate === "pass") used.add(String((l.line.value as JsonObject).id));
  for (const p of listPasses(chain, blake3)) used.add(p.id);
  let n = 1;
  while (used.has(`p${n}`)) n++;
  return `p${n}`;
}

export function openPass(
  chain: Chain,
  blake3: string,
  o: { by: string; verify: string; ontology: string; date: string; note?: string; with?: string },
): PassFile {
  if (!readSubject(chain, "corpus", blake3).length)
    throw new AthError("NOT_FOUND", `${blake3}: no artifact subject in the chain (ingest it first)`);
  const id = nextPassId(chain, blake3);
  const value: JsonObject = { id, by: o.by, verify: o.verify, ontology: o.ontology, date: o.date };
  if (o.note) value.note = o.note;
  if (o.with) value.with = o.with;
  const pass: JsonObject = { at: "whole", predicate: "pass", value };
  mkdirSync(passDir(chain, blake3), { recursive: true });
  const path = passPath(chain, blake3, id);
  writeAtomic(path, serializeJsonl([pass]));
  return { id, blake3, path, pass, lines: [] };
}

/** Stage lines on an open pass: each must be a pass-attested artifact line naming this pass (or carry no attestation,
 * which is filled in); revs are stamped or checked; identities within the staging replace earlier staged ones. */
export async function stageLines(
  chain: Chain,
  blake3: string,
  id: string,
  lines: JsonObject[],
): Promise<{ staged: number; replaced: number; mismatched: { at: string; given: string; computed: string }[] }> {
  const p = readPass(chain, blake3, id);
  for (const l of lines) {
    if (l.predicate === "attests" || l.predicate === "captured_from")
      throw new AthError("CONFLICT", `${String(l.predicate)} is an op line; ingest writes it`);
    if (l.predicate === "pass") throw new AthError("CONFLICT", "a pass line is opened with `pass open`, never staged");
    if (l.pass === undefined && l.by === undefined) l.pass = id;
    if (l.pass !== id) throw new AthError("CONFLICT", `a staged line names pass ${String(l.pass)}, not ${id}`);
    if (typeof l.pass === "string" && !PASS_REF.test(l.pass)) throw new AthError("CONFLICT", `bad pass ref ${String(l.pass)}`);
  }
  const { mismatched } = await stampRevisions(lines);
  if (mismatched.length)
    throw new AthError(
      "CONFLICT",
      `${mismatched.length} reading revision${mismatched.length === 1 ? "" : "s"} do not match the body (D-rev): first at ${mismatched[0]!.at}: given ${mismatched[0]!.given}, computed ${mismatched[0]!.computed}`,
    );
  for (const l of lines) {
    const bad = validateLine("corpus", l);
    if (bad) throw new AthError("CONFLICT", `${bad}: ${JSON.stringify(l).slice(0, 160)}`);
  }
  const byId = new Map<string, JsonObject>();
  for (const l of p.lines) byId.set(identityKey("corpus", l), l);
  let replaced = 0;
  for (const l of lines) {
    const k = identityKey("corpus", l);
    if (byId.has(k)) replaced++;
    byId.set(k, l);
  }
  writeAtomic(p.path, serializeJsonl([p.pass, ...byId.values()]));
  return { staged: lines.length, replaced, mismatched };
}

/** Merge a signed pass into the claim file; the caller has run the lints over stored ∪ staged. */
export function commitPass(
  chain: Chain,
  blake3: string,
  id: string,
  o: { date: string; walked?: boolean },
): { added: number; corrected: number; unchanged: number } {
  const p = readPass(chain, blake3, id);
  const lines = [p.pass, ...p.lines];
  if (o.walked) lines.push({ at: "whole", predicate: "walked", pass: id });
  const r = appendLines(chain, "corpus", blake3, lines, { by: `pass:${id}`, date: o.date, why: `pass ${id} signed` });
  rmSync(p.path, { force: true });
  return { added: r.added, corrected: r.corrected, unchanged: r.unchanged };
}

export function abandonPass(chain: Chain, blake3: string, id: string): void {
  const p = readPass(chain, blake3, id);
  rmSync(p.path, { force: true });
}

/** The stored lines with a pass's staged lines laid over (by identity), for linting before signing. */
export function storedWithStaged(chain: Chain, blake3: string, p: PassFile): JsonObject[] {
  const byId = new Map<string, JsonObject>();
  for (const l of unionView("corpus", readSubject(chain, "corpus", blake3))) byId.set(identityKey("corpus", l.line), l.line);
  byId.set(identityKey("corpus", p.pass), p.pass);
  for (const l of p.lines) byId.set(identityKey("corpus", l), l);
  return [...byId.values()];
}
