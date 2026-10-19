// artifacts.ts — reaching an artifact's bytes from a verb: custody's resolution (§18.8) over the host's stores, with
// the engine handing it the containers of a hash and the extraction of a constituent; and the host's bindings
// (`host.yaml`, §5.6) for the hints that consult the host.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { type CustodyIndex, type LocalStore, type Readable, type ResolveDeps, type Resolved, resolveHash } from "@ath/custody";
import { intrinsicsOf } from "@ath/engine/formats/index.ts";
import { bindRecogniser } from "@ath/engine/formats/media/hints.ts";
import { containersIndex, type Instance, recordView } from "@ath/engine/instance/instance.ts";
import { AthError } from "@ath/kit/errors.ts";
import type { KitCtx } from "@ath/kit/types.ts";

export function resolver(
  inst: Instance,
  store: LocalStore,
  index?: CustodyIndex,
): { deps: ResolveDeps; resolve: (hash: string) => Promise<Resolved> } {
  const containers = containersIndex(inst);
  const local: Readable = { id: store.id, name: "local", tags: ["local"], get: (t, h) => store.get(t, h) };
  const deps: ResolveDeps = {
    stores: [local],
    containersOf: (h) => containers.get(h) ?? [],
    async extract(bytes, hash, path) {
      const mime = recordView(inst, hash)?.record.intrinsics?.mime;
      if (typeof mime !== "string") return null;
      const c = (await intrinsicsOf(bytes, mime)).constituents.find((x) => x.path === path);
      return c ? c.read() : null;
    },
    ...(index ? { index } : {}),
  };
  return { deps, resolve: (h) => resolveHash(h, deps) };
}

/** Bind what `host.yaml` names: `speech: {command: [argv…]}`, a recogniser that reads the recording on stdin and
 * prints the regions it heard as JSON, `[{"start": s, "end": e, "text": "…"}]`. */
export function bindHost(ctx: KitCtx): void {
  const p = join(ctx.host.config, "host.yaml");
  if (!existsSync(p)) {
    bindRecogniser(null);
    return;
  }
  let doc: { speech?: { command?: unknown } } | null;
  try {
    doc = Bun.YAML.parse(readFileSync(p, "utf8")) as typeof doc;
  } catch (e) {
    throw new AthError("CONFIG", `${p}: ${(e as Error).message}`);
  }
  const argv = doc?.speech?.command;
  if (argv === undefined) {
    bindRecogniser(null);
    return;
  }
  if (!Array.isArray(argv) || !argv.every((a) => typeof a === "string") || !argv.length)
    throw new AthError("CONFIG", `${p}: speech.command is a list of strings`);
  bindRecogniser(async (bytes) => {
    const r = Bun.spawnSync(argv as string[], { stdin: new Blob([bytes as unknown as ArrayBuffer]), stdout: "pipe", stderr: "pipe" });
    if (r.exitCode !== 0)
      throw new AthError("EXTERNAL", `the recogniser exited ${r.exitCode}: ${r.stderr.toString().trim().split("\n").pop()}`);
    const out = JSON.parse(r.stdout.toString()) as { start: number; end: number; text: string }[];
    if (!Array.isArray(out)) throw new AthError("EXTERNAL", "the recogniser printed no list of regions");
    return out;
  });
}
