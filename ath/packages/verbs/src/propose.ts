// propose.ts — `ath propose <subject> [<at>]` (spec §19.5): the hints at an address — the text each hint op of the
// artifact's format guesses there, with its units (§10.6) — for a reader to stage, correct and sign. Nothing proposed
// is derived, stored or cited unsigned.
import { defineContract, z } from "@ath/contracts";
import { parseAddress } from "@ath/engine/address/address.ts";
import { formatOf, hintAt, Parses } from "@ath/engine/formats/index.ts";
import { containersIndex, holdings, recordView, resolvePrefix } from "@ath/engine/instance/instance.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { bindHost, resolver } from "./artifacts.ts";
import { custodyIndex, instanceOf, localStore } from "./context.ts";

export const proposeCommand = defineCommand({
  meta: { summary: "the hints at an address: the text a hint op guesses there, with its units", tier: "read", mutating: false },
  contract: defineContract({
    key: "propose",
    args: z.object({ subject: z.string(), at: z.string().default("whole") }),
    argv: {
      positionals: [
        { name: "subject", required: true },
        { name: "at", help: "an intrinsic address (default whole)" },
      ],
    },
    data: z.object({
      hash: z.string(),
      at: z.string(),
      hints: z.array(z.object({ op: z.string(), text: z.string(), units: z.array(z.object({ text: z.string(), at: z.string() })) })),
    }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    bindHost(ctx);
    const hash = resolvePrefix(a.subject, new Set([...holdings(inst).keys(), ...containersIndex(inst).keys()]));
    const mime = recordView(inst, hash)?.record.intrinsics?.mime;
    if (typeof mime !== "string") throw new AthError("NOT_FOUND", `${hash} has no record of its own to say what it is`);
    const format = formatOf(mime);
    if (format.class !== "rendered")
      throw new AthError("USAGE", `${mime} is ${format.class ?? "unregistered"}: its parse is its reading, and nothing is proposed`);
    const index = custodyIndex(ctx);
    try {
      const { bytes } = await resolver(inst, localStore(ctx), index).resolve(hash);
      const parses = new Parses(bytes);
      const regions = parseAddress(a.at).regions;
      const hints = [];
      for (const op of format.ops) {
        const h = await hintAt(parses, op, regions);
        if (h) hints.push({ op, ...h });
      }
      return { data: { hash, at: a.at, hints } };
    } finally {
      index.close();
    }
  },
  text(d, io) {
    for (const h of d.hints) io.out(`── ${h.op} at ${d.at}\n${h.text}\n`);
    if (!d.hints.length) io.out(`no hint at ${d.at}\n`);
  },
});
