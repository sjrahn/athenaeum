// ops.pdf.test.ts — pdf.words@1: words with boxes, lines, words-in-box in reading order, chrome by repetition.
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { allPages, detectChrome, readingOrder, wordsInBox, wordsText } from "../src/engine/ops/pdf/words.ts";

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

  test("chrome by repetition: the running header on every page, never the one-off heading", async () => {
    const pages = await allPages(await read(join(PY, "geometry_pages.pdf")));
    const chrome = detectChrome(pages);
    expect(chrome.length).toBe(3);
    expect(chrome.every((c) => c.text === "RUNNING HEADER" && c.role === "running-header")).toBe(true);
    expect(chrome.map((c) => c.page)).toEqual([1, 2, 3]);
  });
});
