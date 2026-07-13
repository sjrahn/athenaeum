import { test, expect } from "bun:test";
import { blake3Factory, countingFactory } from "../src/hasher.ts";

// Official BLAKE3 test vectors — pin the algorithm identity so a wrong hash can't slip in.
const EMPTY = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262";
const ABC = "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85";

test("blake3 known vectors (empty, abc)", async () => {
  const enc = new TextEncoder();

  const h1 = await blake3Factory.create();
  h1.update(enc.encode(""));
  expect(h1.digest()).toBe(EMPTY);

  const h2 = await blake3Factory.create();
  h2.update(enc.encode("ab"));
  h2.update(enc.encode("c")); // streamed in two chunks
  expect(h2.digest()).toBe(ABC);
});

test("counting factory tracks hasher creation", async () => {
  const f = countingFactory(blake3Factory);
  expect(f.count).toBe(0);
  await f.create();
  await f.create();
  expect(f.count).toBe(2);
});
