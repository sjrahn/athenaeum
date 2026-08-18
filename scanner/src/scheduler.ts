// Disk-aware scheduling for the native hash pool, used when a byte-path resolver is active
// (unRAID: each file lives wholly on one physical disk). A plain worker pool draining a single
// shared queue doesn't know that "file A" and "file B" might be on the same spindle — this
// scheduler groups queued work by storage element and always hands a free worker the next item
// from whichever element currently has the FEWEST active readers (among elements that still
// have queued work), so K workers fan out across up to K distinct disks instead of piling onto
// whichever one happened to be shuffled first. Files whose element couldn't be resolved land in
// the `null` bucket, same as any other element as far as scheduling is concerned.

/** `null` element key = "couldn't resolve a storage element for this file" (read via the share
 * path). Grouping still works normally for it; it's just not a real disk for fan-out purposes. */
export type ElementKey = string | null;

/** Group `items` by the element `resolveElement` reports for each. Insertion order within each
 * element's queue is preserved (FIFO drain). */
export function groupByElement<T>(items: readonly T[], resolveElement: (item: T) => ElementKey): Map<ElementKey, T[]> {
  const grouped = new Map<ElementKey, T[]>();
  for (const item of items) {
    const element = resolveElement(item);
    let queue = grouped.get(element);
    if (!queue) {
      queue = [];
      grouped.set(element, queue);
    }
    queue.push(item);
  }
  return grouped;
}

/**
 * Least-active-element work queue. `acquire()` picks the element with the fewest currently
 * "checked out" items among elements that still have queued work (ties broken by iteration
 * order, i.e. whichever was seen first) and pops its next item; the caller MUST call
 * `release(element)` exactly once when done with that item (success or failure) so the active
 * count is accurate for the next `acquire()`. When only one element has remaining work, every
 * worker piles onto it — there is no hard per-element cap, matching the non-direct shuffle
 * pool's behavior of letting all K workers run once only one segment of work is left.
 */
export class ElementAwareQueue<T> {
  private readonly queues: Map<ElementKey, T[]>;
  private readonly active = new Map<ElementKey, number>();

  constructor(grouped: Map<ElementKey, readonly T[]>) {
    this.queues = new Map(Array.from(grouped, ([element, items]) => [element, [...items]] as const));
  }

  acquire(): { element: ElementKey; item: T } | null {
    let best: ElementKey | undefined;
    let bestActive = Infinity;
    let found = false;
    for (const [element, queue] of this.queues) {
      if (queue.length === 0) continue;
      const activeCount = this.active.get(element) ?? 0;
      if (activeCount < bestActive) {
        bestActive = activeCount;
        best = element;
        found = true;
      }
    }
    if (!found) return null;
    const queue = this.queues.get(best as ElementKey)!;
    const item = queue.shift()!;
    this.active.set(best as ElementKey, bestActive + 1);
    return { element: best as ElementKey, item };
  }

  release(element: ElementKey): void {
    this.active.set(element, Math.max(0, (this.active.get(element) ?? 1) - 1));
  }

  /** Distinct elements with at least one queued (not-yet-acquired) item, right now. */
  get pendingElementCount(): number {
    let n = 0;
    for (const queue of this.queues.values()) if (queue.length > 0) n++;
    return n;
  }
}

/** Run `worker` over every item in `grouped`, at most `k` in flight, each worker always
 * pulling from the least-active element with remaining work (see ElementAwareQueue). */
export async function runElementAwarePool<T>(grouped: Map<ElementKey, readonly T[]>, k: number, worker: (item: T) => Promise<void>): Promise<void> {
  const queue = new ElementAwareQueue(grouped);
  const total = Array.from(grouped.values()).reduce((sum, items) => sum + items.length, 0);
  const runner = async (): Promise<void> => {
    for (;;) {
      const next = queue.acquire();
      if (!next) return;
      try {
        await worker(next.item);
      } finally {
        queue.release(next.element);
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(Math.max(1, k), total || 1) }, runner));
}
