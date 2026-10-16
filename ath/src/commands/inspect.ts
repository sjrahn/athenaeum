// inspect.ts — `ath inspect <blake3>` (L7: every stored reading against the derivation at its address) and
// `ath inspect accept|revoke` (the owner's `inspected` lines in <blake3>.owner.jsonl; admin tier).
import { defineContract, z } from "../../contracts/index.ts";
import { openChain, openOntology, requireBlake3 } from "../engine/context.ts";
import { loadArtifact } from "../engine/corpus/derive.ts";
import { appendLines, deleteLines } from "../engine/corpus/file.ts";
import { readSubject, unionView } from "../engine/layer/store.ts";
import { l7 } from "../engine/lint/l7.ts";
import { canonicalAt } from "../engine/model/address.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";

const row = z.object({
  at: z.string(),
  aspect: z.string(),
  rev: z.string(),
  terms: z.array(z.string()),
  state: z.string(),
  detail: z.string().optional(),
  derivation: z.string().optional(),
});

export const inspect = defineCommand({
  meta: {
    summary: "L7: every stored reading against the derivation at its address, per aspect; divergences listed, accepted ones marked",
    tier: "read",
    mutating: false,
    examples: ["ath inspect 5e6e497d…", "ath inspect 5e6e497d… --at 'page=4&bbox=0.3154,0.7134,0.5408,0.0178'"],
  },
  contract: defineContract({
    key: "inspect",
    args: z.object({ subject: z.string(), at: z.string().optional(), aspect: z.string().optional(), all: z.boolean().default(false) }),
    argv: {
      positionals: [{ name: "subject", required: true }],
      flags: { at: { type: "string" }, aspect: { type: "string" }, all: { type: "boolean", help: "list readings that agree too" } },
    },
    data: z.object({ subject: z.string(), rows: z.array(row), counts: z.record(z.string(), z.number()) }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const id = requireBlake3(a.subject);
    const art = await loadArtifact(chain, o, id);
    const owner = unionView("corpus", readSubject(chain, "corpus", id, true)).map((l) => l.line);
    let rows = l7(art, owner);
    if (a.at) rows = rows.filter((r) => r.at === canonicalAt(a.at!));
    if (a.aspect) rows = rows.filter((r) => r.aspect === a.aspect);
    const counts: Record<string, number> = {};
    for (const r of rows) counts[r.state] = (counts[r.state] ?? 0) + 1;
    if (!a.all) rows = rows.filter((r) => r.state !== "ok");
    return { data: { subject: id, rows, counts }, exitCode: rows.some((r) => r.state === "diverges") ? 1 : 0 };
  },
  text(d, io) {
    io.out(
      `${
        Object.entries(d.counts)
          .map(([k, v]) => `${v} ${k}`)
          .join(", ") || "no stored readings"
      }\n`,
    );
    for (const r of d.rows) {
      io.out(`${r.state.padEnd(14)} ${r.aspect.padEnd(5)} ${r.terms.join("+").padEnd(18)} ${r.at}  ${r.rev}\n`);
      if (r.detail) io.out(`               ${r.detail}\n`);
      if (r.state === "diverges" && r.derivation) io.out(`               derivation: ${r.derivation.replace(/\n/g, " ⏎ ")}\n`);
    }
  },
});

export const inspectAccept = defineCommand({
  meta: {
    summary: "the owner accepts a divergence: an inspected line in the owner file, by reading revision, with a reason",
    tier: "admin",
    mutating: true,
    locks: ["corpus"],
    examples: ["ath inspect accept 5e6e497d… --at 'page=3&bbox=…' --rev b3:… --why '2-D math; the TeX is the bytes'"],
  },
  contract: defineContract({
    key: "inspect-accept",
    args: z.object({ subject: z.string(), at: z.string(), rev: z.string(), why: z.string() }),
    argv: {
      positionals: [{ name: "subject", required: true }],
      flags: { at: { type: "string" }, rev: { type: "string" }, why: { type: "string" } },
    },
    data: z.object({ subject: z.string(), at: z.string(), rev: z.string(), path: z.string() }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const o = openOntology(chain);
    const id = requireBlake3(a.subject);
    const art = await loadArtifact(chain, o, id, { bytes: false });
    const at = canonicalAt(a.at);
    const s = art.table.get(at);
    if (!s?.readings.some((r) => r.stored && r.rev === a.rev)) throw new AthError("NOT_FOUND", `no stored reading ${a.rev} at ${at}`);
    const line = {
      at,
      predicate: "inspected",
      value: { rev: a.rev, diverges: "accepted", why: a.why },
      by: "owner",
      date: ctx.clock.iso().slice(0, 10),
    };
    const r = appendLines(chain, "corpus", id, [line], { by: "owner", date: ctx.clock.iso().slice(0, 10) }, true);
    return { data: { subject: id, at, rev: a.rev, path: r.path } };
  },
  text(d, io) {
    io.out(`accepted ${d.rev} at ${d.at} → ${d.path}\n`);
  },
});

export const inspectRevoke = defineCommand({
  meta: { summary: "the owner withdraws an acceptance (a lineage row records it)", tier: "admin", mutating: true, locks: ["corpus"] },
  contract: defineContract({
    key: "inspect-revoke",
    args: z.object({ subject: z.string(), at: z.string(), rev: z.string() }),
    argv: { positionals: [{ name: "subject", required: true }], flags: { at: { type: "string" }, rev: { type: "string" } } },
    data: z.object({ subject: z.string(), removed: z.number() }),
  }),
  run(ctx, a) {
    const chain = openChain(ctx);
    const id = requireBlake3(a.subject);
    const removed = deleteLines(
      chain,
      "corpus",
      id,
      [`${canonicalAt(a.at)}|inspected|${a.rev}`],
      { by: "owner", date: ctx.clock.iso().slice(0, 10) },
      true,
    );
    if (!removed) throw new AthError("NOT_FOUND", `no inspected line for ${a.rev} at ${a.at}`);
    return { data: { subject: id, removed } };
  },
  text(d, io) {
    io.out(`${d.removed} acceptance revoked\n`);
  },
});
