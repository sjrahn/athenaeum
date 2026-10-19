// tree.ts — `ath tree <subject> [<address>]` (spec §19.5): the tree, derived (a structured artifact through its shape),
// stored (a formed record) or proposed (a rendered artifact's shape over its hints), each scope with its positional
// address, and the chrome the declared rules find. With an address — positional (`2/1`), designated (`sec=5&para=6`)
// or intrinsic — the scope it names and its intrinsic `at`.
import { defineContract, z } from "@ath/contracts";
import { canonicalAt } from "@ath/engine/address/address.ts";
import { holdings, resolvePrefix } from "@ath/engine/instance/instance.ts";
import type { Scope } from "@ath/engine/record/document.ts";
import { type DScope, positional } from "@ath/engine/structure/derive.ts";
import { byDesignators, byPosition, type TreeScope } from "@ath/engine/structure/designate.ts";
import { defineCommand } from "@ath/kit/define.ts";
import { AthError } from "@ath/kit/errors.ts";
import { resolver } from "./artifacts.ts";
import { custodyIndex, instanceOf } from "./context.ts";
import { viewer } from "./view.ts";

const row = z.object({
  position: z.string(),
  form: z.union([z.string(), z.array(z.string())]),
  at: z.string(),
  fields: z.record(z.string(), z.unknown()),
  text: z.string().nullable(),
  depth: z.number(),
});

/** A derived scope as a tree scope: its fields flat beside its form and address, as a stored scope carries them. */
const flat = (s: DScope): TreeScope => ({
  ...s.fields,
  form: s.form,
  at: s.at,
  ...(s.reads ? { reads: s.reads } : { text: s.text }),
  scopes: s.scopes.map(flat),
});

export const treeCommand = defineCommand({
  meta: {
    summary: "an artifact's tree — derived, stored or proposed — with positional addresses and chrome; or the scope an address names",
    tier: "read",
    mutating: false,
  },
  contract: defineContract({
    key: "tree",
    args: z.object({ subject: z.string(), address: z.string().optional() }),
    argv: {
      positionals: [
        { name: "subject", required: true },
        { name: "address", help: "positional 2/1, designated sec=5&para=6, or intrinsic" },
      ],
    },
    data: z.object({
      hash: z.string(),
      mime: z.string(),
      shape: z.string().nullable(),
      kind: z.string(),
      scopes: z.array(row),
      chrome: z.array(z.object({ at: z.string(), text: z.string(), role: z.string().optional() })),
      named: z.array(row).optional(),
    }),
  }),
  async run(ctx, a) {
    const inst = instanceOf(ctx);
    const index = custodyIndex(ctx);
    try {
      const vw = viewer(inst, resolver(ctx, inst, index).resolve);
      const hash = resolvePrefix(a.subject, new Set([...holdings(inst).keys(), ...vw.containers.keys()]));
      const view = await vw.view(hash);
      const tree: TreeScope[] = view.tree.kind === "stored" ? (view.tree.scopes as Scope[]) : (view.tree.scopes as DScope[]).map(flat);
      const rowOf = (s: TreeScope, path: number[]) => {
        const { form, at, scopes: _s, text, cells, tex, reads, ...fields } = s as TreeScope & { reads?: { text: string } };
        const body =
          typeof text === "string"
            ? text
            : Array.isArray(cells)
              ? (cells as string[]).join("\t")
              : typeof tex === "string"
                ? tex
                : (reads?.text ?? null);
        return { position: path.join("/"), form, at, fields, text: body, depth: path.length - 1 };
      };
      const scopes = [...positional(tree)].map(({ scope, path }) => rowOf(scope, path));
      const data: z.input<typeof row>[] | undefined = a.address
        ? (() => {
            const addr = a.address!;
            if (/^\d+(\/\d+)*$/.test(addr)) {
              const s = byPosition(tree, addr);
              if (!s) throw new AthError("NOT_FOUND", `no scope at position ${addr}`);
              return [rowOf(s, addr.split("/").map(Number))];
            }
            let want: string | null = null;
            try {
              want = canonicalAt(addr);
            } catch {
              want = null;
            }
            const hit = want ? scopes.filter((r) => canonicalAt(r.at) === want) : [];
            if (hit.length) return hit;
            const named = byDesignators(vw.vocab.vocab, tree, addr);
            if (!named.length) throw new AthError("NOT_FOUND", `no scope answers to ${addr}`);
            return named.map((s) => scopes.find((r) => r.at === s.at)!);
          })()
        : undefined;
      return {
        data: {
          hash,
          mime: view.mime,
          shape: view.shape.shape,
          kind: view.tree.kind,
          scopes,
          chrome: view.chrome,
          ...(data ? { named: data } : {}),
        },
      };
    } finally {
      index.close();
    }
  },
  text(d, io) {
    io.out(`${d.hash}  ${d.mime}  shape ${d.shape ?? "(none)"}  tree ${d.kind}\n`);
    for (const s of d.named ?? d.scopes) {
      const f = Object.keys(s.fields).length ? ` ${JSON.stringify(s.fields)}` : "";
      io.out(
        `${"  ".repeat(d.named ? 0 : s.depth)}${s.position.padEnd(6)} ${[s.form].flat().join(",")} ${s.at}${f}${s.text ? `  ${s.text.split("\n")[0]!.slice(0, 60)}` : ""}\n`,
      );
    }
    for (const c of d.chrome) io.out(`chrome ${c.role ?? ""} ${c.at}  ${c.text}\n`);
  },
});
