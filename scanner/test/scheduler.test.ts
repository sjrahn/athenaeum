// Disk-aware element scheduling (scheduler.ts): least-active-element preference, the null
// (unresolved-element) bucket, and the degenerate single-element case.

import { test, expect } from "bun:test";
import { groupByElement, runElementAwarePool, ElementAwareQueue } from "../src/scheduler.ts";

// ── groupByElement ────────────────────────────────────────────────────────────────────────

test("groupByElement buckets items by resolved element, preserving per-bucket order", () => {
  const items = ["a1", "b1", "a2", "c1", "a3"];
  const grouped = groupByElement(items, (i) => i[0] as string);
  expect(grouped.get("a")).toEqual(["a1", "a2", "a3"]);
  expect(grouped.get("b")).toEqual(["b1"]);
  expect(grouped.get("c")).toEqual(["c1"]);
});

test("groupByElement supports a null bucket for unresolved elements", () => {
  const items = [1, 2, 3, 4];
  const grouped = groupByElement(items, (i) => (i % 2 === 0 ? "even" : null));
  expect(grouped.get(null)).toEqual([1, 3]);
  expect(grouped.get("even")).toEqual([2, 4]);
});

// ── ElementAwareQueue: least-active-element preference ───────────────────────────────────────

test("acquire() prefers the element with fewest active checkouts among elements with queued work", () => {
  const q = new ElementAwareQueue(
    new Map([
      ["disk1", ["a", "b"]],
      ["disk2", ["c", "d"]],
    ]),
  );
  const first = q.acquire()!; // both at 0 active — either is fine, but exactly one is picked
  expect(first.element === "disk1" || first.element === "disk2").toBe(true);
  const second = q.acquire()!; // the OTHER element now has fewer active (0 vs 1)
  expect(second.element).not.toBe(first.element);
  // both elements now have 1 active each; a third acquire drains whichever still has queue
  const third = q.acquire()!;
  expect(third.element === "disk1" || third.element === "disk2").toBe(true);
});

test("release() frees up an element so it's preferred again on the next acquire", () => {
  const q = new ElementAwareQueue(
    new Map([
      ["disk1", ["a1", "a2", "a3"]],
      ["disk2", ["b1"]],
    ]),
  );
  const d1a = q.acquire()!; // disk1 (tie, first seen)
  expect(d1a.element).toBe("disk1");
  const d2 = q.acquire()!; // disk2 has fewer active (0 vs 1) now
  expect(d2.element).toBe("disk2");
  q.release("disk1"); // disk1 back to 0 active, disk2 still at 1
  const d1b = q.acquire()!;
  expect(d1b.element).toBe("disk1"); // preferred again over disk2's 1-active
});

test("the null bucket participates in scheduling exactly like a named element", () => {
  const q = new ElementAwareQueue(
    new Map<string | null, string[]>([
      [null, ["u1", "u2"]],
      ["disk1", ["d1"]],
    ]),
  );
  const first = q.acquire()!;
  expect(first.element === null || first.element === "disk1").toBe(true);
  const second = q.acquire()!;
  expect(second.element).not.toBe(first.element);
});

test("single-element degenerate case: acquire just drains it in order, no partitioning needed", () => {
  const q = new ElementAwareQueue(new Map([["disk1", ["a", "b", "c"]]]));
  const seen: string[] = [];
  for (let i = 0; i < 3; i++) {
    const next = q.acquire()!;
    seen.push(next.item);
    // no release() between acquires — simulates every worker piling onto the one element
  }
  expect(seen).toEqual(["a", "b", "c"]);
  expect(q.acquire()).toBeNull();
});

test("acquire() returns null once every element's queue is empty", () => {
  const q = new ElementAwareQueue(new Map([["disk1", ["a"]]]));
  const got = q.acquire()!;
  expect(got.item).toBe("a");
  expect(q.acquire()).toBeNull();
  q.release(got.element);
  expect(q.acquire()).toBeNull(); // releasing doesn't resurrect a drained queue
});

// ── runElementAwarePool: end-to-end drain, correctness under concurrency ────────────────────

test("runElementAwarePool drains every item across multiple elements exactly once", async () => {
  const grouped = new Map([
    ["disk1", ["a", "b", "c"]],
    ["disk2", ["d", "e"]],
    [null, ["f"]],
  ]);
  const processed: string[] = [];
  await runElementAwarePool(grouped, 3, async (item) => {
    await new Promise((r) => setTimeout(r, 1));
    processed.push(item);
  });
  expect(processed.sort()).toEqual(["a", "b", "c", "d", "e", "f"]);
});

test("runElementAwarePool fans workers out across elements: no single element sees more concurrent workers than it has queued items, until others are drained", async () => {
  const grouped = new Map([
    ["disk1", Array.from({ length: 4 }, (_, i) => `d1-${i}`)],
    ["disk2", Array.from({ length: 4 }, (_, i) => `d2-${i}`)],
  ]);
  const activeByElement = new Map<string, number>();
  const maxActiveByElement = new Map<string, number>();
  const worker = async (item: string) => {
    const element = item.startsWith("d1") ? "disk1" : "disk2";
    activeByElement.set(element, (activeByElement.get(element) ?? 0) + 1);
    maxActiveByElement.set(element, Math.max(maxActiveByElement.get(element) ?? 0, activeByElement.get(element)!));
    await new Promise((r) => setTimeout(r, 20));
    activeByElement.set(element, activeByElement.get(element)! - 1);
  };
  await runElementAwarePool(grouped, 4, worker);
  // With 4 workers and 2 elements of equal queue depth, the least-active preference should
  // split them ~evenly — neither element should see all 4 workers pile on while the other sits idle.
  expect(maxActiveByElement.get("disk1")).toBeLessThanOrEqual(3);
  expect(maxActiveByElement.get("disk2")).toBeLessThanOrEqual(3);
});

test("runElementAwarePool with only one element having remaining work: all workers may pile onto it (no hard cap)", async () => {
  const grouped = new Map([
    ["disk1", ["a"]],
    ["disk2", Array.from({ length: 5 }, (_, i) => `d2-${i}`)],
  ]);
  let maxDisk2Active = 0;
  let disk2Active = 0;
  await runElementAwarePool(grouped, 4, async (item) => {
    if (item.startsWith("d2")) {
      disk2Active++;
      maxDisk2Active = Math.max(maxDisk2Active, disk2Active);
      await new Promise((r) => setTimeout(r, 15));
      disk2Active--;
    } else {
      await new Promise((r) => setTimeout(r, 1));
    }
  });
  // Once disk1's single item is done, all remaining workers pile onto disk2 — no per-element cap.
  expect(maxDisk2Active).toBeGreaterThan(1);
});

test("runElementAwarePool respects the concurrency cap k even with plenty of queued work", async () => {
  const grouped = new Map([["disk1", Array.from({ length: 20 }, (_, i) => `${i}`)]]);
  let active = 0;
  let maxActive = 0;
  await runElementAwarePool(grouped, 3, async () => {
    active++;
    maxActive = Math.max(maxActive, active);
    await new Promise((r) => setTimeout(r, 5));
    active--;
  });
  expect(maxActive).toBeLessThanOrEqual(3);
});

test("runElementAwarePool propagates a worker's rejection", async () => {
  const grouped = new Map([["disk1", ["a", "b"]]]);
  await expect(
    runElementAwarePool(grouped, 2, async (item) => {
      if (item === "b") throw new Error("boom");
    }),
  ).rejects.toThrow("boom");
});
