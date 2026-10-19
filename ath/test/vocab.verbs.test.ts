// vocab.verbs.test.ts — the vocabulary verbs and `tree` end to end (§19.5): writing a term is the owner's, at a
// terminal, after the check; the pins; an artifact's derived tree through its shape, a container's route scopes, and
// the scope a positional or designated address names (§7.6).
import { describe, expect, test } from "bun:test";
import { copyFileSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { byDesignators } from "@ath/engine/structure/designate.ts";
import { emptyVocabulary } from "@ath/engine/vocab/terms.ts";
import { ath, scratch, TESTDATA } from "./harness.ts";

const SYN = join(TESTDATA, "synthetic");
const env = { ATH_ACTOR: "owner-a" };
const owner = { env, tty: true };

async function instance() {
  const root = join(scratch(), "household");
  expect((await ath(["instance", "init", root], { env })).code).toBe(0);
  return root;
}
async function add(root: string, vocab: string, term: string, ...lines: object[]) {
  const words = ["vocab", "add", vocab, term, ...lines.map((l) => JSON.stringify(l))];
  const r = await ath(words, { ...owner, cwd: root, confirm: async () => "vocab add" });
  expect(r.code, r.stderr).toBe(0);
}

describe("vocab", () => {
  test("add, edit, remove at a terminal; the check refuses a write that leaves a finding; the pins move", async () => {
    const root = await instance();
    expect((await ath(["vocab", "add", "forms", "line", '{"pred":"reads","val":"text"}'], { env, cwd: root })).code).toBe(64); // hidden from an agent
    expect((await ath(["--json", "vocab", "add", "forms", "line", '{"pred":"reads","val":"text"}'], { ...owner, cwd: root })).code).toBe(
      77,
    );
    const before = (await ath(["--json", "vocab", "pin"], { env, cwd: root })).json() as { data: { corpus: string; graph: string } };
    await add(root, "forms", "line", { pred: "reads", val: "text" }, { pred: "definition", val: "one line of print" });
    expect(readFileSync(join(root, "corpus/forms/line.jsonl"), "utf8")).toBe(
      '{"pred":"definition","val":"one line of print"}\n{"pred":"reads","val":"text"}\n',
    );
    const after = (await ath(["--json", "vocab", "pin"], { env, cwd: root })).json() as { data: { corpus: string; graph: string } };
    expect(after.data.corpus).not.toBe(before.data.corpus);
    expect(after.data.graph).toBe(before.data.graph);
    // a second line at the same identity is an edit, not an add
    expect(
      (
        await ath(["vocab", "add", "forms", "line", '{"pred":"reads","val":"tex"}'], {
          ...owner,
          cwd: root,
          confirm: async () => "vocab add",
        })
      ).code,
    ).toBe(73);
    const bad = await ath(["vocab", "edit", "forms", "line", '{"pred":"reads","val":"rows"}'], {
      ...owner,
      cwd: root,
      confirm: async () => "vocab edit",
    });
    expect(bad.code).toBe(73);
    expect(bad.stderr).toContain("reads: is one of text, cells, tex, none");
    expect(
      (
        await ath(["vocab", "edit", "forms", "line", '{"pred":"reads","val":"tex"}'], {
          ...owner,
          cwd: root,
          confirm: async () => "vocab edit",
        })
      ).code,
    ).toBe(0);
    expect(readFileSync(join(root, "corpus/forms/line.jsonl"), "utf8")).toContain('{"pred":"reads","val":"tex"}');
    expect((await ath(["vocab", "remove", "forms", "line"], { ...owner, cwd: root, confirm: async () => "vocab remove" })).code).toBe(0);
    expect((await ath(["vocab", "show", "forms", "line"], { env, cwd: root })).code).toBe(66);
    expect((await ath(["vocab", "check"], { env, cwd: root })).code).toBe(0);
    const listed = (await ath(["--json", "vocab", "list", "properties"], { env, cwd: root })).json() as {
      data: { terms: { name: string }[] };
    };
    expect(listed.data.terms.map((t) => t.name)).toEqual(["source"]);
  });
});

describe("tree", () => {
  test("a thread's tree derived through its shape; a zip's route scopes; the scope a position names", async () => {
    const root = await instance();
    await add(root, "forms", "message", { pred: "reads", val: "text" }, { pred: "field", val: { name: "sender", type: "string" } });
    await add(root, "forms", "attachment", { pred: "reads", val: "none" });
    await add(
      root,
      "shapes",
      "messenger-thread",
      { pred: "matches", val: { mime: "application/json", selector: "/participants" } },
      { pred: "select", val: { selector: "/messages/*", form: "message" } },
      { pred: "select", val: { selector: "/messages/*/sender_name", form: "message", field: "sender" } },
      { pred: "select", val: { selector: "/messages/*/content", form: "message", reads: "text" } },
    );
    await add(
      root,
      "shapes",
      "drive-export",
      { pred: "matches", val: { mime: "application/zip", origin: { "/producer/tool": "google-drive-export" } } },
      { pred: "select", val: { selector: "Harbour plans/*.pdf", form: "attachment" } },
    );
    const work = scratch();
    for (const f of ["facebook-thread.json", "drive-folder.zip", "drive-folder.zip.testimony.yaml"])
      copyFileSync(join(SYN, f), join(work, f));
    expect((await ath(["--root", root, "ingest", "facebook-thread.json"], { env, cwd: work })).code).toBe(0);
    expect(
      (await ath(["--root", root, "ingest", "drive-folder.zip", "--testimony", "drive-folder.zip.testimony.yaml"], { env, cwd: work }))
        .code,
    ).toBe(0);
    const t = await ath(["--json", "tree", "b3387f88"], { env, cwd: root });
    expect(t.code, t.stdout).toBe(0);
    const d = (
      t.json() as {
        data: { shape: string; kind: string; scopes: { position: string; form: string; fields: Record<string, unknown>; text: string }[] };
      }
    ).data;
    expect(d).toMatchObject({ shape: "messenger-thread", kind: "derived" });
    expect(d.scopes[0]).toMatchObject({
      position: "1",
      form: "message",
      fields: { sender: "Eli Hale" },
      text: "Green kettle map walked harbour bread while water carried.",
    });
    const pos = (await ath(["--json", "tree", "b3387f88", "2"], { env, cwd: root })).json() as {
      data: { named: { position: string; at: string }[] };
    };
    expect(pos.data.named[0]!.position).toBe("2");
    const zip = (await ath(["--json", "tree", "da7b858a"], { env, cwd: root })).json() as {
      data: { shape: string; scopes: { form: string; at: string }[] };
    };
    expect(zip.data.shape).toBe("drive-export");
    expect(zip.data.scopes.map((s) => [s.form, s.at])).toEqual([["attachment", "path=Harbour plans/Mooring plan 2026.pdf"]]);
    const h = await ath(["--json", "holdings"], { env, cwd: root });
    expect(h.code).toBe(0);
  });

  test("a designated address: a later key narrows to the earlier key's descendants; a capture answers too", () => {
    const v = emptyVocabulary();
    v.forms.set("heading", [
      { pred: "field", val: { name: "num", type: "designator", where: "leading", pattern: "^(\\d+)\\.$", address: "sec" } },
    ]);
    v.forms.set("paragraph", [{ pred: "field", val: { name: "n", type: "designator", where: "leading", address: "para" } }]);
    const tree = [
      { form: "heading", at: "page=1&bbox=0,0,1,0.1", num: "4.", scopes: [{ form: "paragraph", at: "page=1&bbox=0,0.1,1,0.1", n: "1" }] },
      {
        form: "heading",
        at: "page=2&bbox=0,0,1,0.1",
        num: "5.",
        scopes: [
          { form: "paragraph", at: "page=2&bbox=0,0.1,1,0.1", n: "1" },
          { form: "paragraph", at: "page=2&bbox=0,0.3,1,0.1", n: "2" },
        ],
      },
    ];
    expect(byDesignators(v, tree, "sec=5").map((s) => s.at)).toEqual(["page=2&bbox=0,0,1,0.1"]);
    expect(byDesignators(v, tree, "sec=5.").map((s) => s.at)).toEqual(["page=2&bbox=0,0,1,0.1"]);
    expect(byDesignators(v, tree, "sec=5&para=2").map((s) => s.at)).toEqual(["page=2&bbox=0,0.3,1,0.1"]);
    expect(byDesignators(v, tree, "sec=4&para=2")).toEqual([]);
  });
});

describe("propose", () => {
  test("a rendered page's shape proposes a tree, each scope with the hint text at its address; nothing is stored", async () => {
    const root = await instance();
    await add(root, "forms", "heading", { pred: "reads", val: "text" });
    await add(root, "forms", "value", { pred: "reads", val: "text" });
    await add(
      root,
      "shapes",
      "homes-listing",
      { pred: "matches", val: { mime: "text/html", selector: ".listing" } },
      { pred: "select", val: { selector: "h1.listing-title", form: "heading", level: 0 } },
      { pred: "select", val: { selector: ".price .amount", form: "value" } },
    );
    const work = scratch();
    copyFileSync(join(SYN, "cottage-listing.html"), join(work, "listing.html"));
    expect((await ath(["--root", root, "ingest", "listing.html"], { env, cwd: work })).code).toBe(0);
    const p = (await ath(["--json", "propose", "7684234e"], { env, cwd: root })).json() as {
      data: { shape: string; tree: { form: string; at: string; fields: object; hint: string }[] };
    };
    expect(p.data.shape).toBe("homes-listing");
    expect(p.data.tree.map((s) => [s.form, s.at, s.hint])).toEqual([
      ["heading", "bytes=800,967", "12 Quay Street, Port Ellen"],
      ["value", "bytes=985,1022", "£313,000"],
    ]);
    expect(p.data.tree[0]!.fields).toEqual({ level: 0 });
    const rec = (await ath(["--json", "record", "7684234e"], { env, cwd: root })).json() as { data: { stage: string; scopes: number } };
    expect(rec.data).toMatchObject({ stage: "unread", scopes: 0 });
  });
});
