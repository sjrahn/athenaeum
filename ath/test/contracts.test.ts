// contracts.test.ts — defineContract's declaration checks and parseArgv's token rules.
import { describe, expect, test } from "bun:test";
import { ContractUsageError, defineContract, parseArgv, usageText, z } from "../contracts/index.ts";

const c = defineContract({
  key: "t-cmd",
  args: z.object({
    file: z.string(),
    rest: z.array(z.string()).default([]),
    n: z.number().default(1),
    tag: z.array(z.string()).default([]),
    dryRun: z.boolean().default(false),
  }),
  argv: {
    positionals: [
      { name: "file", required: true },
      { name: "rest", variadic: true },
    ],
    flags: { n: { type: "number", short: "n" }, tag: { type: "string", repeat: true }, dryRun: { type: "boolean" } },
  },
  data: z.object({}),
});

describe("contracts", () => {
  test("parseArgv: positionals, variadic, repeat, number, boolean, --no-, --, =", () => {
    expect(parseArgv(c, ["a.pdf"])).toEqual({ file: "a.pdf", rest: [], n: 1, tag: [], dryRun: false });
    expect(parseArgv(c, ["a", "b", "c", "-n", "3", "--tag", "x", "--tag=y", "--dry-run"])).toEqual({
      file: "a",
      rest: ["b", "c"],
      n: 3,
      tag: ["x", "y"],
      dryRun: true,
    });
    expect(parseArgv(c, ["--dry-run", "--no-dry-run", "a"]).dryRun).toBe(false);
    expect(parseArgv(c, ["a", "--", "--not-a-flag"]).rest).toEqual(["--not-a-flag"]);
    expect(parseArgv(c, ["a", "-n", "-2"]).n).toBe(-2);
  });

  test("parseArgv refuses what it does not know", () => {
    expect(() => parseArgv(c, [])).toThrow(ContractUsageError);
    expect(() => parseArgv(c, ["a", "--zzz"])).toThrow("unrecognized argument: --zzz");
    expect(() => parseArgv(c, ["a", "-n", "x"])).toThrow("invalid number value");
    expect(() => parseArgv(c, ["a", "--n"])).toThrow("expected one argument");
    expect(() => parseArgv(c, ["a", "--dry-run=1"])).toThrow("takes no value");
  });

  test("defineContract checks the argv spec against the args keys", () => {
    expect(() => defineContract({ key: "Bad", args: z.object({}), argv: {}, data: z.object({}) })).toThrow("kebab-case");
    expect(() => defineContract({ key: "x", args: z.object({ a: z.string() }), argv: {}, data: z.object({}) })).toThrow(
      "no positional or flag",
    );
    expect(() => defineContract({ key: "x", args: z.object({}), argv: { positionals: [{ name: "a" }] }, data: z.object({}) })).toThrow(
      "not a key of args",
    );
    expect(() =>
      defineContract({
        key: "x",
        args: z.object({ a: z.string(), b: z.string() }),
        argv: { flags: { a: { type: "string", short: "a" }, b: { type: "string", short: "a" } } },
        data: z.object({}),
      }),
    ).toThrow("used twice");
  });

  test("usageText", () => {
    const u = usageText("ath", c, "a test");
    expect(u).toContain("usage: ath t cmd <file> [rest]… [flags]");
    expect(u).toContain("-n, --n NUMBER");
    expect(u).toContain("--dry-run");
  });
});
