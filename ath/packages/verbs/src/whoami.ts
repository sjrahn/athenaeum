// whoami.ts — `ath whoami`: the caller's profile and actor and how they were chosen, the instance root and its host
// state, the external tools found on PATH (§19.5).
import { defineContract, z } from "@ath/contracts";
import { defineCommand } from "@ath/kit/define.ts";
import { probeBinaries } from "@ath/kit/spawn.ts";
import { ATH_VERSION } from "@ath/kit/version.ts";

const contract = defineContract({
  key: "whoami",
  args: z.object({}),
  argv: {},
  data: z.object({
    version: z.string(),
    profile: z.enum(["owner", "agent", "reader"]),
    kind: z.enum(["human", "session", "script"]),
    actor: z.string().nullable(),
    tty: z.boolean(),
    session: z.object({ id: z.string(), pid: z.number(), name: z.string().nullable() }).nullable(),
    basis: z.array(z.string()),
    root: z.string().nullable(),
    instance: z.string().nullable(),
    state: z.string().nullable(),
    now: z.string(),
    tools: z.record(z.string(), z.string().nullable()),
  }),
});

export const whoamiCommand = defineCommand({
  meta: {
    summary: "the caller's profile and how it was chosen, the instance root, the local tools found",
    tier: "read",
    mutating: false,
    examples: ["ath whoami", "ath --json whoami"],
  },
  contract,
  run(ctx) {
    const c = ctx.caller;
    return {
      data: {
        version: ATH_VERSION,
        profile: c.profile,
        kind: c.kind,
        actor: c.actor,
        tty: c.tty,
        session: c.session,
        basis: c.basis,
        root: ctx.root,
        instance: ctx.instance?.id ?? null,
        state: ctx.instance?.state ?? null,
        now: ctx.clock.iso(),
        tools: probeBinaries(["git", "rclone", "ffprobe", "ffmpeg"]),
      },
    };
  },
  text(d, io) {
    io.out(`ath ${d.version}\n`);
    io.out(`profile  ${d.profile} (${d.kind})\n`);
    for (const b of d.basis) io.out(`         ${b}\n`);
    io.out(`actor    ${d.actor ?? "(none)"}\n`);
    io.out(`root     ${d.root ?? "(no athenaeum.yaml found)"}\n`);
    if (d.instance) io.out(`instance ${d.instance}  state ${d.state}\n`);
    io.out(`now      ${d.now}\n`);
    for (const [k, v] of Object.entries(d.tools)) io.out(`tool     ${k.padEnd(9)} ${v ?? "not found"}\n`);
  },
});
