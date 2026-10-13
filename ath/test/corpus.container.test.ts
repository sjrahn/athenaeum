// corpus.container.test.ts — a container's members are subjects; a route through the container canonicalises to the
// member (spec §5.1): a claim anchored at corpus://<zip>?path=… binds on the member's own surface.
import { describe, expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { readJsonl } from "../src/lib/jsonl.ts";
import { ath } from "./harness.ts";
import { foundation } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");
const env = { ATH_ACTOR: "tester" };

describe("containers", () => {
  test("zip members are subjects; the path route binds on the member", async () => {
    const f = foundation();
    const ing = await ath(["--json", "ingest", join(FIX, "small.zip"), "--received", "2026-10-13"], { cwd: f, env });
    const rows = (ing.json() as { data: { ingested: { blake3: string; mime: string; members: number }[] } }).data.ingested;
    expect(rows.map((r) => r.mime)).toEqual(["application/zip", "text/plain", "text/csv"]);
    const zip = rows[0]!.blake3;
    const csv = rows[2]!.blake3;
    const tree = await ath(["--json", "tree", zip], { cwd: f, env });
    expect((tree.json() as { data: { root: string; tree: string } }).data).toMatchObject({ root: "zip", tree: "derived" });
    const member = readJsonl(join(f, "corpus", `${csv}.claims.jsonl`));
    expect(member[1]!.value).toEqual({ container: `corpus://${zip}`, path: "data/rows.csv" });
    writeFileSync(
      join(f, "ledger", "t.claims.jsonl"),
      [
        '{"subject":"t","predicate":"term","value":"concept"}',
        `{"subject":"t","predicate":"via-route","value":"1","evidence":[{"anchor":"corpus://${zip}?path=data%2Frows.csv;row=1&col=0","quote":"1","kind":"direct","mode":"stated","reading":"derived:csv.parse@1"}],"by":"ath.test@1"}`,
        `{"subject":"t","predicate":"direct","value":"2","evidence":[{"anchor":"corpus://${csv}?row=1&col=1","quote":"2","kind":"direct","mode":"stated","reading":"derived:csv.parse@1"}],"by":"ath.test@1"}`,
        `{"subject":"t","predicate":"bad-route","value":"x","evidence":[{"anchor":"corpus://${zip}?path=nope.txt","quote":"x","kind":"direct","mode":"stated","reading":"derived:csv.parse@1"}],"by":"ath.test@1"}`,
      ]
        .map((l) => `${l}\n`)
        .join(""),
    );
    const v = await ath(["--json", "verify", "t"], { cwd: f, env });
    const claims = (v.json() as { data: { claims: { predicate: string; bindings: { state: string; at: string; why?: string }[] }[] } }).data
      .claims;
    expect(claims.find((c) => c.predicate === "via-route")!.bindings[0]).toMatchObject({ state: "bound", at: "row=1&col=0" });
    expect(claims.find((c) => c.predicate === "direct")!.bindings[0]!.state).toBe("bound");
    expect(claims.find((c) => c.predicate === "bad-route")!.bindings[0]).toMatchObject({
      state: "flagged",
      why: "container has no member at path nope.txt",
    });
  });
});
