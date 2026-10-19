// serve.ts — `ath serve [--port N] [--host H]` (spec §16): the instance and everything it builds on, whole, over HTTP,
// read-only — every read verb at `GET /v1/<verb>` (its arguments as query parameters, positionals by name), answered
// with the envelope `--json` prints and the status §19.4.2 gives it. A server holds no state: every request re-reads
// the instances. What is shared is decided by which instance is served, and by nothing else.
import { defineContract, type FlagSpec, z } from "@ath/contracts";
import { defineCommand } from "@ath/kit/define.ts";
import { httpStatus, invoke } from "@ath/kit/invoke.ts";
import type { Registry } from "@ath/kit/registry.ts";
import type { Caller } from "@ath/kit/types.ts";

const READER: Caller = {
  profile: "reader",
  kind: "script",
  session: null,
  basis: ["served over HTTP: read-only"],
  actor: null,
  tty: false,
};

/** A request's query as an args object, typed by the verb's argv: numbers and booleans as they are declared, a
 * repeated flag or a variadic positional as a list. */
function argsFrom(registry: Registry, verb: string, q: URLSearchParams): Record<string, unknown> {
  const def = registry.resolve([verb])?.def;
  if (!def) return {};
  const flags = (def.contract.argv.flags ?? {}) as Record<string, FlagSpec>;
  const variadic = new Set((def.contract.argv.positionals ?? []).filter((p) => p.variadic).map((p) => p.name));
  const out: Record<string, unknown> = {};
  for (const key of new Set(q.keys())) {
    const vals = q.getAll(key);
    const f = flags[key];
    if (f?.type === "number") out[key] = Number(vals[0]);
    else if (f?.type === "boolean") out[key] = vals[0] !== "false" && vals[0] !== "0";
    else if (f?.repeat || variadic.has(key)) out[key] = vals;
    else out[key] = vals[0];
  }
  return out;
}

export interface Served {
  url: string;
  stop(): void;
}

export function startServer(o: {
  registry: Registry;
  root: string;
  env: Record<string, string | undefined>;
  cwd: string;
  port: number;
  hostname: string;
}): Served {
  const server = Bun.serve({
    port: o.port,
    hostname: o.hostname,
    async fetch(req) {
      const url = new URL(req.url);
      if (req.method !== "GET" && req.method !== "HEAD")
        return Response.json({ ok: false, error: { code: "DENIED", message: "a served instance is read-only" } }, { status: 405 });
      if (url.pathname === "/" || url.pathname === "/v1") {
        const verbs = o.registry
          .list()
          .filter((d) => d.meta.tier === "read" && d.contract.key !== "serve")
          .map((d) => ({ verb: d.contract.key, path: `/v1/${d.contract.key}`, summary: d.meta.summary }));
        return Response.json({ instance: o.root, verbs });
      }
      const m = /^\/v1\/([a-z][a-z0-9-]*)$/.exec(url.pathname);
      if (!m || m[1] === "serve")
        return Response.json({ ok: false, error: { code: "NOT_FOUND", message: `no route ${url.pathname}` } }, { status: 404 });
      const { envelope } = await invoke({
        registry: o.registry,
        verb: m[1]!,
        args: argsFrom(o.registry, m[1]!, url.searchParams),
        caller: READER,
        root: o.root,
        env: o.env,
        cwd: o.cwd,
        history: false,
        via: "over HTTP",
      });
      return new Response(`${JSON.stringify(envelope)}\n`, {
        status: httpStatus(envelope),
        headers: { "content-type": "application/json; charset=utf-8", "cache-control": "private, no-store" },
      });
    },
  });
  return { url: `http://${server.hostname}:${server.port}`, stop: () => server.stop(true) };
}

export function serveCommand(registry: Registry) {
  return defineCommand({
    meta: {
      summary: "serve the instance and its chain, whole and read-only, over HTTP",
      tier: "read",
      mutating: false,
      examples: ["ath serve --port 8641"],
    },
    contract: defineContract({
      key: "serve",
      args: z.object({ port: z.number().int().min(0).max(65535).default(8641), host: z.string().default("127.0.0.1") }),
      argv: { flags: { port: { type: "number" }, host: { type: "string", help: "the address to listen on (default loopback)" } } },
      data: z.object({ url: z.string() }),
    }),
    async run(ctx, a) {
      if (!ctx.root) throw new Error("no instance to serve");
      const s = startServer({ registry, root: ctx.root, env: ctx.env, cwd: ctx.cwd, port: a.port, hostname: a.host });
      ctx.events.emit({ kind: "serve.listening", level: "info", msg: `serving ${ctx.root} at ${s.url}` });
      await new Promise<void>((resolve) => {
        for (const sig of ["SIGINT", "SIGTERM"] as const) process.once(sig, () => resolve());
      });
      s.stop();
      return { data: { url: s.url } };
    },
  });
}
