// reading-check.ts — the reading check (spec §13.4): every reading's body against the hint at its address, after the
// scope's conventions and designators are applied, per aspect; a divergence is an advisory for the verifier, never
// a block, and an `accept` ruling marks it known. A reading with no hint — of an image — is listed for inspection.
// Beside an attestation of `readings`, the hint's units outside every reading and every chrome run (§8.5.2).
import { short } from "@ath/kit/hash.ts";
import { canonicalAt, contains, parseAddress } from "../address/address.ts";
import type { Format } from "../formats/format.ts";
import { hintAt, type Parses, type Unit } from "../formats/ops.ts";
import { normalize } from "../norm/text.ts";
import type { RecordDoc, Scope } from "../record/document.ts";
import { effectiveRules } from "../vocab/rules.ts";
import type { Vocabulary } from "../vocab/terms.ts";
import { compareCells, compareTex, compareText } from "./compare.ts";

type J = Record<string, unknown>;

export interface Advisory {
  at: string;
  aspect: "text" | "cells" | "tex";
  rev: string;
  state: "agrees" | "diverges" | "accepted" | "no hint";
  detail?: string;
  hint?: string;
}

/** Remove a leading or trailing designator's printed value from the hint's head or tail (§13.4.3). */
function stripDesignators(hint: string, s: Scope | null, v: Vocabulary): { hint: string; labels: string[] } {
  if (!s) return { hint, labels: [] };
  let h = hint;
  const labels: string[] = [];
  for (const d of effectiveRules(v, s.form).fields) {
    if (d.type !== "designator") continue;
    const val = s[String(d.name)];
    if (typeof val !== "string" || !val) continue;
    labels.push(val);
    const n = normalize(val);
    const nh = normalize(h);
    if (d.where === "leading" && nh.startsWith(n)) h = nh.slice(n.length).trim();
    else if (d.where === "trailing" && nh.endsWith(n)) h = nh.slice(0, nh.length - n.length).trim();
  }
  return { hint: h, labels };
}

export async function readingCheck(
  r: RecordDoc,
  format: Format,
  parses: Parses,
  v: Vocabulary,
  accepted: ReadonlySet<string> = new Set(),
): Promise<Advisory[]> {
  const op = format.ops.find((o) => !o.startsWith("audio.") && !o.startsWith("media.")) ?? null;
  const out: Advisory[] = [];
  const one = async (at: string, body: Partial<Record<"text" | "cells" | "tex", unknown>>, scope: Scope | null, conventions: J[]) => {
    const hint = op ? await hintAt(parses, op, parseAddress(at).regions) : null;
    for (const aspect of ["text", "cells", "tex"] as const) {
      const b = body[aspect];
      if (b === undefined) continue;
      const rev = await short(b);
      if (!hint) {
        out.push({ at, aspect, rev, state: "no hint" });
        continue;
      }
      const { hint: h, labels } = stripDesignators(hint.text, scope, v);
      const detail =
        aspect === "text"
          ? compareText(String(b), h, conventions)
          : aspect === "cells"
            ? compareCells(b, hint.text, conventions)
            : compareTex(String(b), h, labels);
      const known = accepted.has(`${canonicalAt(at)}|${rev}`);
      out.push({
        at,
        aspect,
        rev,
        state: detail === null ? "agrees" : known ? "accepted" : "diverges",
        ...(detail ? { detail, hint: h.slice(0, 400) } : {}),
      });
    }
  };
  for (const [at, b] of Object.entries(r.readings ?? {})) await one(at, b, null, []);
  const walk = async (scopes: readonly Scope[] | undefined, inherited: J[]) => {
    for (const s of scopes ?? []) {
      const rules = effectiveRules(v, s.form, inherited);
      if (s.text !== undefined || s.cells !== undefined || s.tex !== undefined) await one(s.at, s, s, rules.conventions);
      await walk(s.scopes, rules.conventions);
    }
  };
  await walk(r.scopes, []);
  return out;
}

/** The hint's units outside every reading (or every scope) and every chrome run: what an attestation may have missed. */
export async function unreadUnits(r: RecordDoc, format: Format, parses: Parses, chrome: readonly string[]): Promise<Unit[]> {
  const op = format.ops.find((o) => !o.startsWith("audio.") && !o.startsWith("media.")) ?? null;
  if (!op) return [];
  const hint = await hintAt(parses, op, [{ whole: true }]);
  if (!hint) return [];
  const read: string[] = [...Object.keys(r.readings ?? {})];
  const walk = (ss: readonly Scope[] | undefined) => {
    for (const s of ss ?? []) {
      read.push(s.at);
      walk(s.scopes);
    }
  };
  walk(r.scopes);
  const inside = (u: Unit) =>
    [...read, ...chrome].some((at) => {
      try {
        return contains(at, u.at);
      } catch {
        return false;
      }
    });
  return hint.units.filter((u) => !inside(u));
}
