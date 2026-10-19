// ops.pdf.test.ts — pdf.words@1: words with boxes, lines, words-in-box in reading order, chrome by repetition.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { allPages, readingOrder, wordsInBox, wordsText } from "@ath/engine/formats/pdf/words.ts";

const PY = join(import.meta.dir, "fixtures");
const read = async (p: string) => new Uint8Array(await Bun.file(p).arrayBuffer());

describe("pdf.words@1", () => {
  test("words carry 4-decimal boxes in the page frame, origin top-left", async () => {
    const pages = await allPages(await read(join(PY, "born_text.pdf")));
    expect(pages.length).toBe(2);
    const p1 = pages[0]!;
    expect(p1.width_pt).toBe(612);
    expect(p1.words[0]!.text).toBe("Hello");
    const b = p1.words[0]!.bbox;
    expect(b.every((n) => Number.isFinite(n) && n >= 0 && n <= 1)).toBe(true);
    expect(b.every((n) => String(n).split(".")[1]?.length ?? 0 <= 4)).toBe(true);
    expect(b[1]).toBeLessThan(0.2); // near the top
    expect(wordsText(p1.words)).toContain("Hello born-digital");
    expect(p1.lines[0]!.text).toContain("Hello");
  });

  test("words in a box, in reading order; a two-column box splits by the gutter", async () => {
    const pages = await allPages(await read(join(PY, "geometry_pages.pdf")));
    const p1 = pages[0]!;
    const intro = p1.lines.find((l) => l.text.startsWith("1. Introduction"))!;
    const ws = wordsInBox(p1.words, [intro.x0, intro.y, intro.x1 - intro.x0, intro.h]);
    expect(wordsText(ws)).toBe("1. Introduction");
    // synthetic two columns: left column lines y=0.1..0.3 at x 0.1..0.4, right column at x 0.55..0.9
    const w = (text: string, x: number, y: number) => ({ text, bbox: [x, y, 0.08, 0.01] as const });
    const left = ["L1", "L2", "L3", "L4"].map((t, i) => w(t, 0.1, 0.1 + i * 0.05));
    const right = ["R1", "R2", "R3", "R4"].map((t, i) => w(t, 0.6, 0.1 + i * 0.05));
    const mixed = [...right, ...left].sort(() => 0);
    expect(wordsText(readingOrder(mixed, [0, 0, 1, 1]))).toBe("L1 L2 L3 L4 R1 R2 R3 R4");
  });

  test("the displayed frame: a rotated page, a crop box; text drawn invisible contributes nothing (§7.3.1, §10.6.3)", async () => {
    const pages = await allPages(
      new Uint8Array(await Bun.file(join(import.meta.dir, "..", "..", "testdata", "synthetic", "frames.pdf")).arrayBuffer()),
    );
    expect(pages.map((p) => [p.width_pt, p.height_pt])).toEqual([
      [600, 800],
      [800, 600],
      [400, 600],
      [600, 800],
    ]);
    expect(pages[0]!.words).toEqual([{ text: "Plain", bbox: [0.1701, 0.1035, 0.0829, 0.022] }]);
    // rotated 90° clockwise: the page's left edge is the top, its top the right; the word runs down the frame
    expect(pages[1]!.words).toEqual([{ text: "Turned", bbox: [0.8746, 0.1672, 0.022, 0.1239] }]);
    // cropped to [100 100 500 700]: x from the crop box's left, y from its top
    expect(pages[2]!.words).toEqual([{ text: "Cropped", bbox: [0.2526, 0.1372, 0.224, 0.0377] }]);
    expect(pages[3]!.words.map((w) => w.text)).toEqual(["Shown"]);
  });
});
