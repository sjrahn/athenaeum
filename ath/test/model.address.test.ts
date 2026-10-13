// model.address.test.ts — the intrinsic address: parse, canonical spelling, order, containment.
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
} from "../src/engine/model/address.ts";

describe("address", () => {
  test("parses every axis and keeps the aspect apart", () => {
    expect(parseAddress("whole")).toEqual({ members: [{ kind: "whole" }] });
    expect(parseAddress("page=3&bbox=0.1192,0.6933,0.4851,0.019&text")).toEqual({
      members: [{ kind: "page", page: 3, box: [0.1192, 0.6933, 0.4851, 0.019] }],
      aspect: "text",
    });
    expect(parseAddress("bytes=518950,518985").members[0]).toEqual({ kind: "bytes", start: 518950, end: 518985 });
    expect(parseAddress("row=3&col=10").members[0]).toEqual({ kind: "row", row: 3, col: 10 });
    expect(parseAddress("t=52,80.5").members[0]).toEqual({ kind: "time", start: 52, end: 80.5 });
    expect(parseAddress("path=OEBPS%2Fch02.xhtml").members[0]).toEqual({ kind: "path", path: "OEBPS/ch02.xhtml" });
    expect(parseAddress("page=5&bbox=0.1,0.2,0.3,0.4;page=6&bbox=0.1,0.1,0.3,0.2").members.length).toBe(2);
  });

  test("refuses what is not an address", () => {
    expect(() => parseAddress("page=0")).toThrow();
    expect(() => parseAddress("page=1&row=2")).toThrow();
    expect(() => parseAddress("bytes=5,3")).toThrow();
    expect(() => parseAddress("whole;page=1")).toThrow();
    expect(() => parseAddress("el=3")).toThrow();
  });

  test("canonical spelling: 4 decimals, sorted union members, aspect kept, scope drops the aspect", () => {
    expect(canonicalAt("page=3&bbox=0.11920,0.69330,0.48510,0.01900")).toBe("page=3&bbox=0.1192,0.6933,0.4851,0.019");
    expect(canonicalAt("page=6&bbox=0.1,0.1,0.3,0.2;page=5&bbox=0.1,0.2,0.3,0.4")).toBe(
      "page=5&bbox=0.1,0.2,0.3,0.4;page=6&bbox=0.1,0.1,0.3,0.2",
    );
    expect(canonicalAt("row=3&col=1&cells")).toBe("row=3&col=1&cells");
    expect(scopeAt("row=3&col=1&cells")).toBe("row=3&col=1");
    expect(formatAddress({ members: [{ kind: "bbox", box: [0.123456, 0, 1, 1] }] })).toBe("bbox=0.1235,0,1,1");
  });

  test("order: whole, pages top-down by y then x, then bytes, rows, times", () => {
    const sorted = ["row=1", "page=2", "bytes=10,20", "page=1&bbox=0.5,0.1,0.1,0.1", "whole", "page=1&bbox=0.1,0.1,0.1,0.1", "page=1"].sort(
      compareAt,
    );
    expect(sorted).toEqual([
      "whole",
      "page=1",
      "page=1&bbox=0.1,0.1,0.1,0.1",
      "page=1&bbox=0.5,0.1,0.1,0.1",
      "page=2",
      "bytes=10,20",
      "row=1",
    ]);
  });

  test("containment with slack; pages contain their boxes; unions contain their members", () => {
    expect(contains("whole", "page=4&bbox=0.1,0.1,0.1,0.1")).toBe(true);
    expect(contains("page=4", "page=4&bbox=0.1,0.1,0.1,0.1")).toBe(true);
    expect(contains("page=4", "page=5&bbox=0.1,0.1,0.1,0.1")).toBe(false);
    expect(contains("page=4&bbox=0.1,0.1,0.5,0.5", "page=4&bbox=0.2,0.2,0.1,0.1")).toBe(true);
    expect(contains("page=4&bbox=0.1,0.1,0.5,0.5", "page=4&bbox=0.599,0.2,0.002,0.1")).toBe(true);
    expect(contains("page=4&bbox=0.1,0.1,0.5,0.5", "page=4&bbox=0.7,0.2,0.1,0.1")).toBe(false);
    expect(contains("page=5&bbox=0.1,0.2,0.3,0.4;page=6&bbox=0.1,0.1,0.3,0.2", "page=6&bbox=0.15,0.12,0.1,0.1")).toBe(true);
    expect(contains("bytes=100,200", "bytes=150,160")).toBe(true);
    expect(contains("bytes=100,200", "bytes=150,260")).toBe(false);
    expect(contains("row=3", "row=3&col=4")).toBe(true);
    expect(contains("row=3&col=4", "row=3")).toBe(false);
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
