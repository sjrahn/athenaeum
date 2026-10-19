// model.address.test.ts — the intrinsic address (§7.3, §7.4): parse, canonical form, order, containment.
import { describe, expect, test } from "bun:test";
import {
  canonicalAt,
  compareAt,
  contains,
  formatAddress,
  isPageAt,
  pagesOf,
  parseAddress,
  scopeAt,
  unionBox,
} from "@ath/engine/address/address.ts";

describe("address", () => {
  test("parses every axis, a route anywhere in a region, and keeps the aspect apart", () => {
    expect(parseAddress("whole")).toEqual({ regions: [{ whole: true }] });
    expect(parseAddress("page=3&bbox=0.1192,0.6933,0.4851,0.019&text")).toEqual({
      regions: [{ page: 3, bbox: [0.1192, 0.6933, 0.4851, 0.019] }],
      aspect: "text",
    });
    expect(parseAddress("bytes=518950,518985").regions[0]).toEqual({ bytes: [518950, 518985] });
    expect(parseAddress("row=3&col=10").regions[0]).toEqual({ row: 3, col: 10 });
    expect(parseAddress("t=52,80.5&bbox=0.1,0.1,0.5,0.5").regions[0]).toEqual({ t: [52, 80.5], bbox: [0.1, 0.1, 0.5, 0.5] });
    expect(parseAddress("col=4").regions[0]).toEqual({ col: 4 });
    expect(parseAddress("page=2&bbox=0.1,0.1,0.5,0.1&col=1").regions[0]).toEqual({ page: 2, bbox: [0.1, 0.1, 0.5, 0.1], col: 1 });
    expect(parseAddress("bytes=10,20&path=OEBPS%2Fch02.xhtml").regions[0]).toEqual({ path: "OEBPS/ch02.xhtml", bytes: [10, 20] });
    expect(parseAddress("page=5&bbox=0.1,0.2,0.3,0.4;page=6&bbox=0.1,0.1,0.3,0.2").regions.length).toBe(2);
  });

  test("refuses what is not an address", () => {
    for (const bad of [
      "page=0",
      "page=1&row=2",
      "bytes=5,3",
      "whole;page=1",
      "el=3",
      "bytes=1,2&col=3",
      "t=1,2&col=1",
      "page=1&page=2",
      "bbox=0.9,0,0.5,1",
      "row=-1",
      "page=1.5",
      "path=%zz",
    ])
      expect(() => parseAddress(bad), bad).toThrow();
  });

  test("canonical form (§7.4): shortest numbers, axes in order, regions sorted and once, paths escaped", () => {
    expect(canonicalAt("page=3&bbox=0.11920,0.69330,0.48510,0.01900")).toBe("page=3&bbox=0.1192,0.6933,0.4851,0.019");
    expect(canonicalAt("bbox=0.1,0.1,0.3,0.2&page=6;page=5&bbox=0.1,0.2,0.3,0.4;page=6&bbox=0.1,0.1,0.3,0.2")).toBe(
      "page=5&bbox=0.1,0.2,0.3,0.4;page=6&bbox=0.1,0.1,0.3,0.2",
    );
    expect(canonicalAt("col=1&row=3&cells")).toBe("row=3&col=1&cells");
    expect(canonicalAt("bbox=0.1,0.1,0.5,0.5&t=1.50,2")).toBe("t=1.5,2&bbox=0.1,0.1,0.5,0.5");
    expect(canonicalAt("bytes=1,2&path=a b/c%3bd%3De%25.html")).toBe("path=a b/c%3Bd%3De%25.html&bytes=1,2");
    expect(canonicalAt("path=caf%C3%A9.txt")).toBe("path=caf%C3%A9.txt");
    expect(canonicalAt("path=café.txt")).toBe("path=caf%C3%A9.txt");
    expect(scopeAt("row=3&col=1&cells")).toBe("row=3&col=1");
    expect(formatAddress({ regions: [{ bbox: [0.123456, 0, 1, 1] }] })).toBe("bbox=0.1235,0,1,1");
  });

  test("order (§7.4.2): page, row, time, y, x, byte start; routes last", () => {
    const sorted = [
      "path=b",
      "row=1",
      "bytes=10,20",
      "page=1&bbox=0.5,0.1,0.1,0.1",
      "path=a&bytes=0,1",
      "whole",
      "page=1&bbox=0.1,0.1,0.1,0.1",
      "page=1",
      "page=2",
      "t=1,2",
      "bytes=3,9",
    ].sort(compareAt);
    expect(sorted).toEqual([
      "whole",
      "bytes=3,9",
      "bytes=10,20",
      "t=1,2",
      "row=1",
      "page=1",
      "page=1&bbox=0.1,0.1,0.1,0.1",
      "page=1&bbox=0.5,0.1,0.1,0.1",
      "page=2",
      "path=a&bytes=0,1",
      "path=b",
    ]);
  });

  test("containment with slack; pages contain their boxes; unions contain their regions; routes stay in their constituent", () => {
    expect(contains("whole", "page=4&bbox=0.1,0.1,0.1,0.1")).toBe(true);
    expect(contains("page=4", "page=4&bbox=0.1,0.1,0.1,0.1")).toBe(true);
    expect(contains("page=4&bbox=0,0,1,1", "page=4")).toBe(false);
    expect(contains("page=4", "page=5&bbox=0.1,0.1,0.1,0.1")).toBe(false);
    expect(contains("page=4&bbox=0.1,0.1,0.5,0.5", "page=4&bbox=0.599,0.2,0.002,0.1")).toBe(true);
    expect(contains("page=4&bbox=0.1,0.1,0.5,0.5", "page=4&bbox=0.7,0.2,0.1,0.1")).toBe(false);
    expect(contains("page=5&bbox=0.1,0.2,0.3,0.4;page=6&bbox=0.1,0.1,0.3,0.2", "page=6&bbox=0.15,0.12,0.1,0.1")).toBe(true);
    expect(contains("bytes=100,200", "bytes=150,160")).toBe(true);
    expect(contains("bytes=100,200", "bytes=150,260")).toBe(false);
    expect(contains("row=3", "row=3&col=4")).toBe(true);
    expect(contains("row=3&col=4", "row=3")).toBe(false);
    expect(contains("col=4", "row=3&col=4")).toBe(true);
    expect(contains("path=a", "path=a&bytes=1,2")).toBe(true);
    expect(contains("bytes=0,9", "path=a&bytes=1,2")).toBe(false);
  });

  test("helpers", () => {
    expect(isPageAt("page=2")).toBe(true);
    expect(isPageAt("page=2&bbox=0,0,1,1")).toBe(false);
    expect(pagesOf(parseAddress("page=5&bbox=0.1,0.2,0.3,0.4;page=6&bbox=0.1,0.1,0.3,0.2"))).toEqual([5, 6]);
    expect(
      unionBox([
        [0.1, 0.1, 0.2, 0.2],
        [0.2, 0.3, 0.3, 0.1],
      ]),
    ).toEqual([0.1, 0.1, 0.4, 0.3]);
  });
});
