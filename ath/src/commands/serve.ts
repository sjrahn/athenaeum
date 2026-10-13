// serve.ts — `ath serve [--plane public|audience:<name>|owner] [--port N]`: the read surface over the chain.
import { defineContract, z } from "../../contracts/index.ts";
import { openChain } from "../engine/context.ts";
import { createServer, type Plane } from "../engine/serve/server.ts";
import { defineCommand } from "../kit/define.ts";
import { AthError } from "../kit/errors.ts";

export function parsePlane(s: string): Plane {
  if (s === "public") return { kind: "public" };
  if (s === "owner") return { kind: "owner" };
  const m = /^audience:(.+)$/.exec(s);
  if (m) return { kind: "audience", name: m[1]! };
  throw new AthError("USAGE", `--plane is public, owner, or audience:<name> (got '${s}')`);
}

export const serve = defineCommand({
  meta: {
    summary:
      "the read surface over HTTP: /instance /ontology/<term> /corpus/<blake3>[/tree] /ledger/<slug> /resolve/corpus/<blake3>?at= /bytes/<blake3>",
    tier: "read",
    mutating: false,
    examples: ["ath serve", "ath serve --plane owner --port 8787", "ath serve --plane audience:family"],
  },
  contract: defineContract({
    key: "serve",
    args: z.object({ plane: z.string().default("public"), port: z.number().int().default(8787), host: z.string().default("127.0.0.1") }),
    argv: {
      flags: {
        plane: { type: "string", help: "public (default) · owner · audience:<name>" },
        port: { type: "number" },
        host: { type: "string" },
      },
    },
    data: z.object({ url: z.string(), plane: z.string() }),
  }),
  async run(ctx, a) {
    const chain = openChain(ctx);
    const plane = parsePlane(a.plane);
    if (plane.kind === "owner" && ctx.caller.profile !== "owner") throw new AthError("DENIED", "the owner plane needs the owner profile");
    const server = createServer({ chain, plane, port: a.port, hostname: a.host });
    const url = `http://${a.host}:${server.port}`;
    ctx.events.emit({ kind: "serve.up", level: "info", msg: `${plane.kind} plane at ${url} (ctrl-c to stop)` });
    if (ctx.env.ATH_TEST === "1") {
      server.stop(true);
      return { data: { url, plane: plane.kind } };
    }
    await new Promise<void>((resolve) => {
      process.on("SIGINT", () => {
        server.stop(true);
        resolve();
      });
      process.on("SIGTERM", () => {
        server.stop(true);
        resolve();
      });
    });
    return { data: { url, plane: plane.kind } };
  },
  text(d, io) {
    io.out(`${d.plane} plane served at ${d.url}\n`);
  },
});
