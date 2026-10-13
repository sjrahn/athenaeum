// ledger.test.ts — harvest from concept lines, bindings, derived status, demand, slugs; through the CLI where it
// matters.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import type { BindResult } from "../src/engine/ledger/bind.ts";
import type { Claim } from "../src/engine/ledger/file.ts";
import { mintSlug } from "../src/engine/ledger/file.ts";
import { judge } from "../src/engine/ledger/status.ts";
import { readJsonl } from "../src/lib/jsonl.ts";
import { ath } from "./harness.ts";
import { foundation, TESTDATA } from "./layers.ts";

const FIX = join(import.meta.dir, "fixtures");
const env = { ATH_ACTOR: "tester" };

describe("slugs", () => {
  test("default, template, extract, case", () => {
    expect(mintSlug("order", "702-9818878-7129055")).toBe("order-702-9818878-7129055");
    expect(mintSlug("product", "B005OVCJN6", { slug: "asin-{key}", case: "keep" })).toBe("asin-B005OVCJN6");
    expect(mintSlug("marketplace", "Amazon.ca", { slug: "{key}" })).toBe("amazon-ca");
    expect(
      mintSlug("forum-thread", "https://www.g8board.com/threads/idle-stall.292301/", {
        slug: "g8board-thread-{1}",
        extract: "\\.(\\d+)/?$",
      }),
    ).toBe("g8board-thread-292301");
    expect(mintSlug("member", "Davisb1983", { slug: "member-{key}" })).toBe("member-davisb1983");
    expect(() => mintSlug("x", "nodigits", { extract: "(\\d+)" })).toThrow("does not match");
  });
});

describe("status (D-status)", () => {
  const claim = (predicate: string, evidence: Claim["evidence"]): Claim => ({
    line: {},
    identity: `s|${predicate}`,
    predicate,
    evidence,
    attestation: "by:x@1",
    layer: "f",
  });
  const e = (kind: "authoritative" | "direct" | "incidental", mode: "stated" | "inferred" | "reported" = "stated") => ({
    anchor: `corpus://${"0".repeat(64)}?whole`,
    quote: "q",
    kind,
    mode,
    reading: "derived:x@1",
    ...(mode !== "stated" ? { reasoning: "r" } : {}),
  });
  const b = (state: BindResult["state"], blake3 = "a"): BindResult => ({ state, blake3, at: "whole", tight: true });
  test("the rungs", () => {
    expect(judge(claim("p", [e("authoritative")]), [b("bound")]).status).toBe("confirmed");
    expect(judge(claim("p", [e("direct")]), [b("bound")]).status).toBe("provisional");
    expect(judge(claim("p", [e("direct"), e("direct")]), [b("bound", "a"), b("bound", "b")]).status).toBe("confirmed");
    expect(judge(claim("p", [e("direct"), e("direct")]), [b("bound", "a"), b("bound", "a")]).status).toBe("provisional");
    expect(judge(claim("p", [e("direct", "inferred")]), [b("bound")]).status).toBe("inferred");
    expect(judge(claim("p", [e("direct", "reported"), e("direct", "inferred")]), [b("bound"), b("bound")]).status).toBe("inferred");
    expect(judge(claim("p", [e("authoritative")]), [b("held")]).status).toBe("unsupported");
    expect(judge(claim("p", []), []).status).toBe("unsupported");
    expect(judge(claim("p", [e("authoritative")]), [b("bound")], { challenges: [{ target: "s|p", upheld: false }] }).status).toBe(
      "disputed",
    );
    expect(judge(claim("p", [e("authoritative")]), [b("flagged")], { challenges: [{ target: "s|p", upheld: true }] }).status).toBe(
      "refuted",
    );
    const a1 = judge(claim("born", [e("authoritative")]), [b("bound")]);
    const a2 = judge({ ...claim("born", [e("authoritative")]), identity: "s|born|2" }, [b("bound")], {
      functional: ["born"],
      siblings: [a1],
    });
    expect(a2.status).toBe("conflicting");
  });
});

describe("harvest + verify over the fixtures", () => {
  test("markup: a thread, its post, the member; every entry binds; owes drive status and demand", async () => {
    const f = foundation();
    const ing = await ath(["--json", "ingest", join(FIX, "small.html"), "--received", "2026-10-13"], { cwd: f, env });
    const id = (ing.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const dry = await ath(["--json", "harvest", id, "--dry-run"], { cwd: f, env });
    expect((dry.json() as { data: { concepts: number; written: string[] } }).data).toMatchObject({ concepts: 3, written: [] });
    const h = await ath(["--json", "harvest", id], { cwd: f, env });
    const d = (h.json() as { data: { concepts: number; claims: number; written: string[] } }).data;
    expect(d.concepts).toBe(3);
    expect(d.written.sort()).toEqual(["g8board-post-1", "g8board-thread-123", "member-alice"]);
    const post = readJsonl(join(f, "ledger", "g8board-post-1.claims.jsonl"));
    expect(post.map((l) => l.predicate)).toEqual(["term", "manifested_by", "author", "body", "position", "posted"]);
    const author = post.find((l) => l.predicate === "author")!;
    expect(author).toMatchObject({
      object: "member-alice",
      qualifiers: { as: "alice" },
      by: expect.stringMatching(/^harvest:xenforo-thread@[0-9a-f]{6}$/),
    });
    expect((author.evidence as { kind: string; reading: string; anchor: string }[])[0]).toMatchObject({
      kind: "authoritative",
      reading: "derived:html.text@1",
    });
    const posted = post.find((l) => l.predicate === "posted")!;
    expect(posted.value).toBe("2026-04-03T23:48:07Z");
    expect((posted.evidence as { reading: string; quote: string }[])[0]).toMatchObject({
      reading: "line:manifests datetime",
      quote: "2026-04-03T23:48:07Z",
    });
    const thread = readJsonl(join(f, "ledger", "g8board-thread-123.claims.jsonl"));
    expect(thread.find((l) => l.predicate === "url")!.evidence).toEqual([
      {
        anchor: `corpus://${id}?whole`,
        quote: "https://www.example.com/threads/test-thread.123/",
        kind: "authoritative",
        mode: "stated",
        reading: "line:captured_from uri",
      },
    ]);
    expect(thread.find((l) => l.predicate === "post")).toMatchObject({ object: "g8board-post-1" });
    const member = readJsonl(join(f, "ledger", "member-alice.claims.jsonl"));
    expect(member.find((l) => l.predicate === "user_id")!.value).toBe("42");
    // again: nothing changes
    const again = await ath(["--json", "harvest", id], { cwd: f, env });
    expect((again.json() as { data: { written: string[]; skipped: string[] } }).data).toMatchObject({
      written: [],
      skipped: expect.arrayContaining(["member-alice"]),
    });
    // verify
    const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
    expect(v.code).toBe(0);
    const vd = (
      v.json() as {
        data: {
          counts: Record<string, unknown>;
          claims: { subject: string; predicate: string; status: string }[];
          demand: { detail: string }[];
        };
      }
    ).data;
    expect(vd.counts).toMatchObject({ concepts: 3, flagged: 0, held: 0 });
    expect(vd.claims.find((c) => c.predicate === "author")!.status).toBe("confirmed");
    expect(vd.claims.find((c) => c.predicate === "user_id")!.status).toBe("provisional"); // member does not owe user_id
    expect(vd.demand.map((x) => x.detail)).toEqual(["forum-thread owes site"]);
    const lint = await ath(["lint", "--all"], { cwd: f, env });
    expect(lint.code).toBe(0);
  });

  test("tabular: the twin CSV mints orders, products and a marketplace; rows sharing a key accrue; sentinels become demand", async () => {
    const f = foundation();
    const ing = await ath(["--json", "ingest", join(TESTDATA, "synthetic", "amazon-twin.csv"), "--received", "2026-10-13"], {
      cwd: f,
      env,
    });
    const id = (ing.json() as { data: { ingested: { blake3: string }[] } }).data.ingested[0]!.blake3;
    const h = await ath(["--json", "harvest", id], { cwd: f, env });
    const d = (h.json() as { data: { concepts: number; written: string[] } }).data;
    expect(d.written.sort()).toEqual([
      "amazon-ca",
      "amazon-com",
      "asin-B000TWIN01",
      "asin-B000TWIN02",
      "asin-B000TWIN03",
      "order-700-0000001-0000001",
      "order-700-0000002-0000002",
      "order-700-0000003-0000003",
    ]);
    const o2 = readJsonl(join(f, "ledger", "order-700-0000002-0000002.claims.jsonl"));
    expect(o2.filter((l) => l.predicate === "line_item").length).toBe(2);
    expect(o2.filter((l) => l.predicate === "manifested_by").map((l) => l.value)).toEqual([`corpus://${id}?row=2`, `corpus://${id}?row=3`]);
    const placed = o2.find((l) => l.predicate === "placed")!;
    expect((placed.evidence as unknown[]).length).toBe(2); // two rows, one claim
    const li = o2.find((l) => l.predicate === "line_item" && (l.value as { asin: string }).asin === "B000TWIN02")!;
    expect(li.value).toMatchObject({
      asin: "B000TWIN02",
      asin_concept: "asin-B000TWIN02",
      product_name: "Example Gadget",
      original_quantity: 2,
      unit_price: 25,
      total_discounts: -2,
    });
    expect(o2.find((l) => l.predicate === "marketplace")).toMatchObject({ object: "amazon-ca" });
    const p2 = readJsonl(join(f, "ledger", "asin-B000TWIN02.claims.jsonl"));
    expect(p2.map((l) => l.predicate)).toEqual(["term", "manifested_by", "asin", "name"]); // department was a sentinel
    const v = await ath(["--json", "verify", "--all"], { cwd: f, env });
    const vd = (
      v.json() as {
        data: {
          counts: { flagged: number; bound: number; byStatus: Record<string, number> };
          demand: { kind: string; subject: string; detail: string }[];
        };
      }
    ).data;
    expect(vd.counts.flagged).toBe(0);
    expect(vd.counts.byStatus.confirmed).toBeGreaterThan(10);
    expect(vd.demand).toContainEqual({ kind: "search", subject: "asin-B000TWIN02", detail: "product owes department" });
    const anchorCheck = await ath(["resolve", `corpus://${id}?row=2&col=10`], { cwd: f, env });
    expect(anchorCheck.stdout.trim()).toBe("700-0000002-0000002");
  });
});
