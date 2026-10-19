// formats.exemplars.test.ts — every exemplar in testdata/exemplars.yaml: sniffed by its bytes to its listed mime, and
// its intrinsics (§10.2) and constituents (§10.3) equal to the reviewed golden in test/fixtures/intrinsics.jsonl, one
// canonical line per exemplar. A change to any intrinsics op shows here as a diff; regenerate the golden with
// ATH_UPDATE_GOLDEN=1 and review it before committing.
import { describe, expect, test } from "bun:test";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { formatOf, intrinsicsOf } from "@ath/engine/formats/index.ts";
import { sniffMime } from "@ath/engine/formats/sniff.ts";
import { canonicalLine } from "@ath/kit/canonical.ts";
import { blake3Hex } from "@ath/kit/hash.ts";
import { TESTDATA } from "./harness.ts";

const GOLDEN = join(import.meta.dir, "fixtures", "intrinsics.jsonl");
const exemplars = Bun.YAML.parse(readFileSync(join(TESTDATA, "exemplars.yaml"), "utf8")) as {
  file: string;
  blake3: string;
  mime: string;
}[];
const pathOf = (f: string) => join(TESTDATA, f.includes("/") ? f : `synthetic/${f}`);

describe("exemplars", () => {
  test("each is sniffed by its bytes to its listed mime, and hashes to its listed BLAKE3", async () => {
    const wrong: string[] = [];
    for (const e of exemplars) {
      const b = new Uint8Array(readFileSync(pathOf(e.file)));
      const m = sniffMime(b, e.file.split("/").pop());
      if (m !== e.mime) wrong.push(`${e.file}: ${m}, listed ${e.mime}`);
      if ((await blake3Hex(b)) !== e.blake3) wrong.push(`${e.file}: BLAKE3 differs from the listed one`);
    }
    expect(wrong).toEqual([]);
  });

  test("intrinsics and constituents equal the reviewed golden", async () => {
    const lines: string[] = [];
    for (const e of exemplars) {
      const b = new Uint8Array(readFileSync(pathOf(e.file)));
      const p = await intrinsicsOf(b, e.mime);
      expect(String(p.value.op).split(".")[0]).toBe(formatOf(e.mime).name);
      for (const c of p.constituents) expect(await blake3Hex(c.read()), `${e.file} ${c.path}`).toBe(c.blake3);
      lines.push(canonicalLine({ file: e.file, intrinsics: p.value }));
    }
    const text = `${lines.join("\n")}\n`;
    if (process.env.ATH_UPDATE_GOLDEN === "1") writeFileSync(GOLDEN, text);
    expect(text).toBe(readFileSync(GOLDEN, "utf8"));
  });
});
