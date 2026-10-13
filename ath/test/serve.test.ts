// serve.test.ts — the read surface by plane: public sees the foundation and confirmed claims; owner sees everything;
// an audience sees the extension layers its grant names.
import { afterAll, describe, expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { loadChain, serializeConfig } from "../src/engine/layer/config.ts";
import { createServer } from "../src/engine/serve/server.ts";
import { ath } from "./harness.ts";
import { extension, foundation } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");
const env = { ATH_ACTOR: "tester" };
const servers: ReturnType<typeof createServer>[] = [];
afterAll(() => {
  for (const s of servers) s.stop(true);
});

describe("serve", () => {
  test("public, owner and audience planes", async () => {
    const f = foundation();
    const ing = await ath(["--json", "ingest", join(FIX, "small.html"), "--received", "2026-10-13"], { cwd: f, env });
    const id = (ing.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    await ath(["harvest", id], { cwd: f, env });
    const e = extension(f);
    writeFileSync(
      join(e, "athenaeum.yaml"),
      serializeConfig({ successor: true, name: "mine", layer: "extension", extends: f, tier: "family", audiences: { kin: ["family"] } }),
    );
    writeFileSync(
      join(e, "ledger", "member-alice.claims.jsonl"),
      '{"subject":"member-alice","predicate":"nickname","value":"al","evidence":[],"by":"ath.test@1"}\n',
    );
    const chain = loadChain(e);
    const pub = createServer({ chain, plane: { kind: "public" } });
    const own = createServer({ chain, plane: { kind: "owner" } });
    const kin = createServer({ chain, plane: { kind: "audience", name: "kin" } });
    const other = createServer({ chain, plane: { kind: "audience", name: "nobody" } });
    servers.push(pub, own, kin, other);
    const get = async (s: ReturnType<typeof createServer>, path: string) => {
      const r = await fetch(`http://127.0.0.1:${s.port}${path}`);
      return { status: r.status, body: (await r.json()) as Record<string, unknown> };
    };
    const inst = await get(pub, "/instance");
    expect(inst.status).toBe(200);
    expect((inst.body.layers as unknown[]).length).toBe(1);
    expect((await get(own, "/instance")).body.layers).toHaveLength(2);
    expect((await get(kin, "/instance")).body.layers).toHaveLength(2);
    expect((await get(other, "/instance")).body.layers).toHaveLength(1);
    const tree = await get(pub, `/corpus/${id}/tree`);
    expect(tree.status).toBe(200);
    expect((tree.body.scopes as unknown[]).length).toBe(8);
    const post = await get(pub, "/ledger/g8board-post-1");
    expect(post.status).toBe(200);
    expect((post.body.claims as { status: string }[]).every((c) => c.status === "confirmed")).toBe(true);
    expect(post.body.demand).toBeUndefined();
    const ownerPost = await get(own, "/ledger/member-alice");
    expect((ownerPost.body.claims as { predicate: string; status: string }[]).map((c) => c.predicate)).toEqual([
      "name",
      "user_id",
      "nickname",
    ]);
    expect(ownerPost.body.demand).toBeDefined();
    const pubMember = await get(pub, "/ledger/member-alice");
    expect((pubMember.body.claims as { predicate: string }[]).map((c) => c.predicate)).toEqual(["name"]); // only confirmed; the extension's line is unseen
    const kinMember = await get(kin, "/ledger/member-alice");
    expect((kinMember.body.claims as { predicate: string }[]).map((c) => c.predicate)).toEqual(["name"]); // nickname is unsupported, not confirmed
    const res = await get(pub, `/resolve/corpus/${id}?at=${encodeURIComponent((tree.body.scopes as { at: string }[])[1]!.at)}`);
    expect(res.body.text).toBe("Idle/stall — ✓ 𝑃𝐸");
    expect((await get(pub, `/corpus/${"0".repeat(64)}`)).status).toBe(404);
    expect((await get(pub, `/corpus/${id}/owner`)).status).toBe(404);
    expect((await get(own, `/corpus/${id}/owner`)).status).toBe(200);
    const bytes = await fetch(`http://127.0.0.1:${pub.port}/bytes/${id}`);
    expect(bytes.status).toBe(200);
    expect((await bytes.arrayBuffer()).byteLength).toBe((await Bun.file(join(FIX, "small.html")).arrayBuffer()).byteLength);
    const cli = await ath(["--json", "serve", "--plane", "owner", "--port", "0"], { cwd: e, env, tty: true });
    expect(cli.code).toBe(0);
    expect((await ath(["serve", "--plane", "owner", "--port", "0"], { cwd: e, env })).code).toBe(77);
    expect((await ath(["serve", "--plane", "nope"], { cwd: e, env })).code).toBe(64);
  });
});
