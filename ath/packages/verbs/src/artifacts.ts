// artifacts.ts — reaching an artifact's bytes from a verb: custody's resolution (§18.8) over every store the chain
// declares that this host reaches — the local store, the other managed stores by declared cost, observed trees, the
// constituent route, then the bases' stores — trying a store only where the index believes it holds the hash, with
// the engine handing it the containers of a hash and the extraction of a constituent; and the host's bindings
// (`host.yaml`, §5.6) for the hints that consult the host.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { type CustodyIndex, type Readable, type ResolveDeps, type Resolved, resolveHash, type Site, type Tree } from "@ath/custody";
import { intrinsicsOf } from "@ath/engine/formats/index.ts";
import { bindRecogniser } from "@ath/engine/formats/media/hints.ts";
import { containersIndex, type Instance, recordView } from "@ath/engine/instance/instance.ts";
import { AthError } from "@ath/kit/errors.ts";
import type { KitCtx } from "@ath/kit/types.ts";
import { openSites } from "./sites.ts";

/** A site as a route: the local store always looked in; another only where the index believes it holds the hash; an
 * observed tree by the paths the index has for the hash. */
function readable(site: Site, index: CustodyIndex): Readable | null {
  const d = site.driver;
  if (!d) return null;
  const { id, name, tags } = site.decl;
  const held = (h: string) => index.copies(h).some((c) => c.store === id && c.state !== "missing");
  if (d.root && site.decl.role === "observed") {
    const root = d.root;
    return {
      id,
      name,
      tags,
      async get(t, h) {
        if (t !== "artifacts") return null;
        for (const o of index.observed({ store: id, hash: h })) {
          const p = join(root, o.path);
          if (existsSync(p)) return new Uint8Array(readFileSync(p));
        }
        return null;
      },
    };
  }
  return { id, name, tags, get: (t, h) => (tags.includes("local") || held(h) ? d.get(t, h) : Promise.resolve(null)) };
}

export function resolver(
  ctx: KitCtx,
  inst: Instance,
  index: CustodyIndex,
): { deps: ResolveDeps; resolve: (hash: string, tree?: Tree, avoid?: string) => Promise<Resolved>; sites: Site[] } {
  const containers = containersIndex(inst);
  const { sites } = openSites(ctx, inst, index);
  const rank = (s: Site) => (s.decl.role === "observed" ? 1 : 0);
  const order = (xs: Site[]) => xs.sort((a, b) => rank(a) - rank(b) || a.decl.cost - b.decl.cost || (a.decl.name < b.decl.name ? -1 : 1));
  const own = new Set([undefined, inst.config.name]);
  const routes = (xs: Site[]) =>
    order(xs)
      .map((s) => readable(s, index))
      .filter((r): r is Readable => r !== null);
  const before = routes(sites.filter((s) => own.has(s.decl.instance)));
  const later = routes(sites.filter((s) => !own.has(s.decl.instance)));
  const deps: ResolveDeps = {
    stores: before,
    later,
    containersOf: (h) => containers.get(h) ?? [],
    async extract(bytes, hash, path) {
      const mime = recordView(inst, hash)?.record.intrinsics?.mime;
      if (typeof mime !== "string") return null;
      const c = (await intrinsicsOf(bytes, mime)).constituents.find((x) => x.path === path);
      return c ? c.read() : null;
    },
    index,
  };
  return {
    deps,
    sites,
    resolve: (h, tree = "artifacts", avoid) =>
      resolveHash(
        h,
        avoid ? { ...deps, stores: deps.stores.filter((s) => s.id !== avoid), later: later.filter((s) => s.id !== avoid) } : deps,
        tree,
      ),
  };
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
