// store.ts — `ath store add <name>` and `ath store list` (spec §18.2, §19.5). Declaring a store writes
// `stores/<name>.yaml` in the instance and how this host reaches it in `access.yaml`, and writes the store's id into the
// store itself, so the store is recognised wherever it is mounted: a store that already carries an id keeps it.
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { defineContract, z } from "@ath/contracts";
import { emitAccess, emitStore, loadAccess, parseStore, type StoreDecl } from "@ath/custody";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { writeAtomic } from "@ath/kit/fs.ts";
import { UUID } from "@ath/kit/root.ts";
import { runLocal } from "@ath/kit/spawn.ts";
import { custodyIndex, instanceOf } from "./context.ts";
import { openSites } from "./sites.ts";

const NAME = /^[a-z0-9][a-z0-9-]*$/;

/** Where a store keeps its id: a managed directory at its root, an observed tree beside its scanner's manifest. */
const markerOf = (role: string, path: string) => (role === "observed" ? join(path, ".athenaeum", "store.yaml") : join(path, "store.yaml"));

const idIn = (text: string | null): string | null => {
  if (!text) return null;
  const id = (Bun.YAML.parse(text) as { id?: unknown } | null)?.id;
  return typeof id === "string" && UUID.test(id) ? id : null;
};

export const storeAdd = defineCommand({
  meta: {
    summary: "declare a store, record how this host reaches it, and write its id into it",
    tier: "write",
    mutating: true,
    locks: ["repository"],
    examples: [
      "ath store add nas --path /mnt/nas/athenaeum --tag hdd --tag city:winnipeg",
      "ath store add offsite --driver rclone --remote b2:athenaeum --tag object --tag city:toronto --encryption driver",
      "ath store add photos --role observed --path /mnt/photos --link reflink --link hardlink",
    ],
  },
  contract: defineContract({
    key: "store-add",
    args: z.object({
      name: z.string(),
      driver: z.enum(["local", "rclone"]).default("local"),
      role: z.enum(["managed", "observed"]).default("managed"),
      tag: z.array(z.string()).default([]),
      path: z.string().optional(),
      remote: z.string().optional(),
      credentials: z.string().optional(),
      encryption: z.enum(["none", "client", "driver"]).default("none"),
      capacity: z.string().optional(),
      evict: z.string().optional(),
      link: z.array(z.enum(["reflink", "hardlink"])).default([]),
      cost: z.number().min(0).optional(),
    }),
    argv: {
      positionals: [{ name: "name", required: true, help: "the store's name in this instance" }],
      flags: {
        driver: { type: "string", help: "local (a directory on this host) or rclone (any backend rclone reaches)" },
        role: { type: "string", help: "managed (content-addressed, custody's alone) or observed (keeps its own names)" },
        tag: { type: "string", repeat: true, help: "a tag policies select on; key:value counts as a distinct value" },
        path: { type: "string", help: "the directory on this host (local driver)" },
        remote: { type: "string", help: "the rclone remote and path (rclone driver)" },
        credentials: { type: "string", help: "a reference to credentials, kept in access.yaml only" },
        encryption: { type: "string" },
        capacity: { type: "string", help: "the size to plan against where the driver cannot report one: 4TB" },
        evict: { type: "string", help: "the fill level above which the store sheds copies: 90%" },
        link: { type: "string", repeat: true, help: "on an observed tree, the link methods ingest tries, in order" },
        cost: { type: "number", help: "the relative cost of a transfer (default 1)" },
      },
    },
    data: z.object({ name: z.string(), id: z.string(), adopted: z.boolean(), declaration: z.string(), access: z.string() }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    if (!NAME.test(a.name) || a.name === "local")
      throw new AthError("USAGE", `'${a.name}' is no store name: lowercase letters, digits, dashes; not local`);
    const file = join(inst.root, "stores", `${a.name}.yaml`);
    if (existsSync(file)) throw new AthError("CONFLICT", `the instance already declares a store ${a.name}`);
    if (a.driver === "local" && !a.path) throw new AthError("USAGE", "a local store names its --path");
    if (a.driver === "rclone" && !a.remote) throw new AthError("USAGE", "an rclone store names its --remote");
    if (a.driver === "rclone" && a.role === "observed") throw new AthError("USAGE", "an observed tree is read on its own host, by path");
    const path = a.path ? resolve(ctx.cwd, a.path) : undefined;
    // the store's id: the one written in it, or a new one written there now
    let existing: string | null;
    if (path) {
      const m = markerOf(a.role, path);
      existing = idIn(existsSync(m) ? readFileSync(m, "utf8") : null);
    } else {
      const r = runLocal(["rclone", "cat", `${a.remote!.replace(/\/$/, "")}/store.yaml`], { allowFail: true });
      existing = r.code === 0 ? idIn(new TextDecoder().decode(r.stdout)) : null;
    }
    const id = existing ?? crypto.randomUUID();
    const decl: StoreDecl = {
      name: a.name,
      id,
      driver: a.driver,
      role: a.role,
      tags: a.tag,
      encryption: a.encryption,
      cost: a.cost ?? 1,
      ...(a.link.length ? { links: a.link } : {}),
    };
    let text = emitStore(decl);
    if (a.capacity) text += `capacity: ${a.capacity}\n`;
    if (a.evict) text += `evict: {above: ${a.evict}}\n`;
    parseStore(a.name, text, `stores/${a.name}.yaml`); // the declaration as written must load
    const sites = openSites(ctx, inst, custodyIndex(ctx));
    try {
      if (sites.sites.some((s) => s.decl.id === id && s.decl.instance === inst.config.name))
        throw new AthError(
          "CONFLICT",
          `the store at ${path ?? a.remote} is already declared, as ${sites.sites.find((s) => s.decl.id === id)!.decl.name}`,
        );
    } finally {
      sites.close();
    }
    if (!existing) {
      const marker = `id: ${id}\nrole: ${a.role}\n`;
      if (path) {
        mkdirSync(path, { recursive: true });
        writeAtomic(markerOf(a.role, path), marker);
      } else runLocal(["rclone", "rcat", `${a.remote!.replace(/\/$/, "")}/store.yaml`], { stdin: new TextEncoder().encode(marker) });
    }
    writeAtomic(file, text);
    const access = loadAccess(ctx.host.config);
    access.stores.set(id, { ...(path ? { path } : { remote: a.remote! }), ...(a.credentials ? { credentials: a.credentials } : {}) });
    const accessPath = join(ctx.host.config, "access.yaml");
    writeAtomic(accessPath, emitAccess(access.local, access.stores));
    return { data: { name: a.name, id, adopted: existing !== null, declaration: `stores/${a.name}.yaml`, access: accessPath } };
  },
  text(d, io) {
    io.out(`${d.adopted ? "adopted" : "declared"}  ${d.name}  ${d.id}\n`);
  },
});

const storeRow = z.object({
  name: z.string(),
  id: z.string(),
  instance: z.string().nullable(),
  driver: z.string(),
  role: z.string(),
  tags: z.array(z.string()),
  cost: z.number(),
  reachable: z.boolean(),
  copies: z.number(),
  bytes: z.number(),
  /** An observed tree's latest finished scan. */
  generation: z.number().optional(),
});

export const storeList = defineCommand({
  meta: {
    summary: "the stores the instance and its bases declare, whether this host reaches each, what each holds",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({ key: "store-list", args: z.object({}), argv: {}, data: z.object({ stores: z.array(storeRow) }) }),
  async run(ctx) {
    const s = openSites(ctx, instanceOf(ctx));
    try {
      const stores = [];
      for (const x of s.sites) {
        const held = s.index.copiesOn(x.decl.id).filter((c) => c.state !== "missing");
        const generation = x.driver?.manifest?.()?.generation;
        stores.push({
          name: x.decl.name,
          id: x.decl.id,
          instance: x.decl.instance ?? null,
          driver: x.decl.driver,
          role: x.decl.role,
          tags: x.decl.tags,
          cost: x.decl.cost,
          reachable: x.driver ? await x.driver.available() : false,
          copies: held.length,
          bytes: held.reduce((n, c) => n + c.size, 0),
          ...(generation !== undefined ? { generation } : {}),
        });
      }
      return { data: { stores } };
    } finally {
      s.close();
    }
  },
  text(d, io) {
    for (const s of d.stores)
      io.out(
        `${s.name.padEnd(12)} ${s.role.padEnd(8)} ${s.reachable ? "reachable  " : "unreachable"}  ${String(s.copies).padStart(6)} copies  [${s.tags.join(", ")}]${s.instance ? `  (${s.instance})` : ""}\n`,
      );
  },
});
