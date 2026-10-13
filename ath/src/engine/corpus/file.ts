// file.ts — a subject's claim file: read the union view, append lines with the identity check (spec §4.2: a write at
// an existing identity is a correction — delete + insert + lineage row, never an edit), refuse a corpus write at an
// identity a lower layer holds (spec §2 shadowing), sort, write.
import { existsSync, readFileSync } from "node:fs";
import { AthError } from "../../kit/errors.ts";
import { canonicalLine, type JsonObject } from "../../lib/jsonl.ts";
import type { Chain } from "../layer/config.ts";
import { appendLineage } from "../layer/lineage.ts";
import { readSubject, type SubjectKind, subjectPath, writeSubject } from "../layer/store.ts";
import { identityKey, type Tree, validateLine } from "../model/line.ts";

export interface AppendReport {
  added: number;
  corrected: number;
  unchanged: number;
  path: string;
}

export interface AppendOptions {
  /** Who is making the change, for the lineage row. */
  by: string;
  date: string;
  why?: string;
  /** Refuse any correction (ops lines at ingest are immutable; a differing attests is a superseding line, not a correction). */
  noCorrect?: boolean;
}

/** Append `lines` to the top layer's file for `id`; same identity + same content is a no-op, same identity +
 * different content is a correction with a lineage row, an identity held by a lower layer is refused. */
export function appendLines(
  chain: Chain,
  kind: SubjectKind,
  id: string,
  lines: JsonObject[],
  o: AppendOptions,
  owner = false,
): AppendReport {
  const tree: Tree = owner ? "owner" : kind;
  for (const l of lines) {
    const bad = validateLine(tree, l);
    if (bad) throw new AthError("CONFLICT", `${id}: ${bad}: ${canonicalLine(l).slice(0, 200)}`);
  }
  const existing = readSubject(chain, kind, id, owner);
  const top = new Map<string, JsonObject>();
  const lower = new Map<string, JsonObject>();
  for (const l of existing) (l.layer === chain.top ? top : lower).set(identityKey(tree, l.line), l.line);
  let added = 0;
  let corrected = 0;
  let unchanged = 0;
  for (const l of lines) {
    const key = identityKey(tree, l);
    const low = lower.get(key);
    if (low !== undefined && kind === "corpus") {
      if (canonicalLine(low) === canonicalLine(l)) {
        unchanged++;
        continue;
      }
      throw new AthError(
        "CONFLICT",
        `${id}: identity ${key} is held by a lower layer; a disagreement with a foundation reading is demand upward, not a write`,
      );
    }
    const prev = top.get(key);
    if (prev !== undefined) {
      if (canonicalLine(prev) === canonicalLine(l)) {
        unchanged++;
        continue;
      }
      if (o.noCorrect)
        throw new AthError("CONFLICT", `${id}: identity ${key} already exists with different content and corrections are not allowed here`);
      appendLineage(chain, kind === "ledger" ? "ledger" : "corpus", {
        op: "correct",
        subject: id,
        identity: key,
        was: prev,
        now: l,
        why: o.why,
        by: o.by,
        date: o.date,
      });
      corrected++;
    } else added++;
    top.set(key, l);
  }
  const path = subjectPath(chain.top, kind, id, owner);
  if (added + corrected > 0) writeSubject(chain, kind, id, [...top.values()], owner);
  return { added, corrected, unchanged, path };
}

/** Remove the lines whose identities match; each removal leaves a lineage row. */
export function deleteLines(
  chain: Chain,
  kind: SubjectKind,
  id: string,
  identities: readonly string[],
  o: AppendOptions,
  owner = false,
): number {
  const tree: Tree = owner ? "owner" : kind;
  const existing = readSubject(chain, kind, id, owner).filter((l) => l.layer === chain.top);
  const keep: JsonObject[] = [];
  let removed = 0;
  for (const l of existing) {
    const key = identityKey(tree, l.line);
    if (identities.includes(key)) {
      appendLineage(chain, kind === "ledger" ? "ledger" : "corpus", {
        op: "delete",
        subject: id,
        identity: key,
        was: l.line,
        now: null,
        why: o.why,
        by: o.by,
        date: o.date,
      });
      removed++;
    } else keep.push(l.line);
  }
  writeSubject(chain, kind, id, keep, owner);
  return removed;
}

/** Rewrite the top layer's file in canonical order; reports whether anything changed. */
export function sortSubject(chain: Chain, kind: SubjectKind, id: string, owner = false): { path: string; changed: boolean } {
  const existing = readSubject(chain, kind, id, owner).filter((l) => l.layer === chain.top);
  const p = subjectPath(chain.top, kind, id, owner);
  const before = existsSync(p) ? readFileSync(p, "utf8") : "";
  const path = writeSubject(
    chain,
    kind,
    id,
    existing.map((l) => l.line),
    owner,
  );
  return { path, changed: readFileSync(path, "utf8") !== before };
}
