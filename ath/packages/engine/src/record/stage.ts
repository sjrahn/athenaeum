// stage.ts — a record's stage, derived and never stored (spec §8.5.3): unread (the projection only), read (readings at
// some addresses), transcribed (readings attested complete by the latest pass), formed (a tree, attested structure).
// A structured artifact is at no stage: its parse is its reading and its shape its structure (§8.5.5).
import { formatOf } from "../formats/index.ts";
import { passOrder, type RecordDoc } from "./document.ts";

export type Stage = "unread" | "read" | "transcribed" | "formed";

/** The highest-numbered pass, whose attestations stand (§8.5.2). */
export function latestPass(r: RecordDoc): string | null {
  const ids = Object.keys(r.passes ?? {}).sort(passOrder);
  return ids.at(-1) ?? null;
}

export function stageOf(r: RecordDoc): Stage | null {
  const mime = r.intrinsics?.mime;
  if (typeof mime === "string" && formatOf(mime).class === "structured") return null;
  const latest = latestPass(r);
  const attests = latest ? (r.passes![latest]!.attests ?? []) : [];
  if (r.scopes) return attests.includes("structure") ? "formed" : "read";
  if (r.readings && Object.keys(r.readings).length) return attests.includes("readings") ? "transcribed" : "read";
  return "unread";
}

/** What the next stage needs, in one sentence (§19.5 `record`). */
export function nextNeeds(r: RecordDoc): string {
  switch (stageOf(r)) {
    case null:
      return "nothing: a structured artifact's parse is its reading and its shape its structure";
    case "unread":
      return "a reading of the region a claim needs, by a pass with an author and a verifier";
    case "read":
      return r.scopes
        ? "a forming pass that attests structure"
        : "readings of every region that carries transcribable content, attested `readings` by the latest pass; or a forming pass";
    case "transcribed":
      return "a forming pass: a tree over the readings, signed whole and attested `structure`";
    case "formed":
      return "nothing further; a later pass re-attests or the attestations lapse";
  }
}
