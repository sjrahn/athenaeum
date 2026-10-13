// status.ts — status, derived (spec §9.3, D-status): confirmed ⇔ a bound authoritative entry or two bound direct
// entries from distinct artifacts, and no standing challenge; disputed ⇔ a challenge stands; conflicting ⇔ a bound
// sibling disagrees on a functional predicate; else the mode of the best bound entry; else unsupported; refuted ⇔
// unsupported with an upheld challenge.
import type { EvidenceEntry } from "../model/evidence.ts";
import type { BindResult } from "./bind.ts";
import type { Claim } from "./file.ts";

export type Status = "confirmed" | "provisional" | "inferred" | "reported" | "disputed" | "conflicting" | "unsupported" | "refuted";

export interface Judged {
  claim: Claim;
  bindings: BindResult[];
  status: Status;
  why: string;
}

const MODE_RUNG: Record<EvidenceEntry["mode"], Status> = { stated: "provisional", inferred: "inferred", reported: "reported" };
const MODE_RANK: Record<EvidenceEntry["mode"], number> = { stated: 0, inferred: 1, reported: 2 };

export interface Challenge {
  /** The claim identity it challenges. */
  target: string;
  upheld: boolean;
}

export function judge(
  claim: Claim,
  bindings: BindResult[],
  o: { challenges?: Challenge[]; siblings?: Judged[]; functional?: string[] } = {},
): Judged {
  const bound = claim.evidence.map((e, i) => ({ e, b: bindings[i]! })).filter((x) => x.b.state === "bound");
  const challenge = (o.challenges ?? []).find((c) => c.target === claim.identity);
  if (challenge?.upheld && !bound.length) return { claim, bindings, status: "refuted", why: "no bound entry and an upheld challenge" };
  if (challenge) return { claim, bindings, status: "disputed", why: "a challenge stands" };
  if (!bound.length) return { claim, bindings, status: "unsupported", why: claim.evidence.length ? "no entry binds" : "no evidence" };
  const functional = o.functional ?? [];
  if (functional.includes(claim.predicate)) {
    const other = (o.siblings ?? []).find(
      (s) => s.claim.predicate === claim.predicate && s.claim.identity !== claim.identity && s.bindings.some((b) => b.state === "bound"),
    );
    if (other)
      return { claim, bindings, status: "conflicting", why: `a bound sibling disagrees on functional predicate ${claim.predicate}` };
  }
  const authoritative = bound.some((x) => x.e.kind === "authoritative" && x.e.mode === "stated");
  const directArtifacts = new Set(bound.filter((x) => x.e.kind === "direct").map((x) => x.b.blake3));
  if (authoritative || directArtifacts.size >= 2)
    return {
      claim,
      bindings,
      status: "confirmed",
      why: authoritative ? "a bound authoritative entry" : "two bound direct entries from distinct artifacts",
    };
  const best = bound.map((x) => x.e.mode).sort((a, b) => MODE_RANK[a] - MODE_RANK[b])[0]!;
  return { claim, bindings, status: MODE_RUNG[best], why: `bar not met; best bound entry is ${best} ${bound[0]!.e.kind}` };
}
