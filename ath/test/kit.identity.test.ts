// kit.identity.test.ts — Claude ancestry from a fake process tree and session files.
import { describe, expect, test } from "bun:test";
import { claudeSession, type IdentityDeps, parsePsTable, walkAncestors } from "../src/kit/identity.ts";

function deps(tree: Record<number, number>, sessions: Record<string, string>): IdentityDeps {
  return {
    pid: 100,
    ppid: (p) => tree[p] ?? null,
    sessionsDir: "/s",
    exists: (p) => p in sessions,
    read: (p) => sessions[p]!,
  };
}

describe("identity", () => {
  test("walks ancestors nearest first and stops at init or a cycle", () => {
    expect(walkAncestors(deps({ 100: 50, 50: 7, 7: 1 }, {}))).toEqual([100, 50, 7]);
    expect(walkAncestors(deps({ 100: 50, 50: 100 }, {}))).toEqual([100, 50]);
  });
  test("the nearest session file wins; a broken file is still a session", () => {
    const d = deps({ 100: 50, 50: 7, 7: 1 }, { "/s/50.json": '{"sessionId":"abc","name":"arbre"}', "/s/7.json": "{}" });
    expect(claudeSession(d)).toEqual({ id: "abc", pid: 50, name: "arbre" });
    expect(claudeSession(deps({ 100: 50, 50: 1 }, { "/s/50.json": "not json" }))).toEqual({ id: "", pid: 50, name: null });
    expect(claudeSession(deps({ 100: 50, 50: 1 }, {}))).toBeNull();
  });
  test("parsePsTable", () => {
    expect(parsePsTable("  1   0\n 50   1\n100  50\n")).toEqual(
      new Map([
        [1, 0],
        [50, 1],
        [100, 50],
      ]),
    );
  });
});
