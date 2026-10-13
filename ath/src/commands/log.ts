// log.ts — `ath log`: the history lines of this instance (<root>/.ath/history.jsonl), newest last.
import { defineContract, z } from "../../contracts/index.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";
import { readHistory } from "../kit/history.ts";

const line = z.object({
  v: z.literal(1),
  ts: z.string(),
  cmd: z.string(),
  argv: z.array(z.string()),
  profile: z.string(),
  actor: z.string().nullable(),
  exit: z.number(),
  elapsed_ms: z.number(),
  error: z.string().optional(),
  reason: z.string().optional(),
});

const contract = defineContract({
  key: "log",
  args: z.object({ cmd: z.string().optional(), limit: z.number().int().positive().default(50) }),
  argv: {
    flags: {
      cmd: { type: "string", help: "only lines for this command key (e.g. pass-sign)" },
      limit: { type: "number", help: "at most this many lines, newest (default 50)" },
    },
  },
  data: z.object({ lines: z.array(line) }),
});

export const logCommand = defineCommand({
  meta: { summary: "this instance's command history (who ran what, how it ended)", tier: "read", mutating: false },
  contract,
  run(ctx, a) {
    if (!ctx.root) throw new AthError("CONFIG", "no instance root (--root, $ATHENAEUM_ROOT, or an athenaeum.yaml above the cwd)");
    let lines = readHistory(ctx.root);
    if (a.cmd) lines = lines.filter((l) => l.cmd === a.cmd);
    return { data: { lines: lines.slice(-a.limit) } };
  },
  text(d, io) {
    for (const l of d.lines) {
      const tail = l.error ? ` ${l.error}${l.reason ? ` (${l.reason})` : ""}` : "";
      io.out(
        `${l.ts}  ${String(l.exit).padStart(3)}  ${l.profile.padEnd(6)} ${(l.actor ?? "-").padEnd(12)} ${l.cmd} ${l.argv.join(" ")}${tail}\n`,
      );
    }
  },
});
