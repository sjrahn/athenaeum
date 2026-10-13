# ath — the successor contract's reference implementation

Bun/TypeScript. Implements `spec/successor.md` (unratified draft; v52 stays the law for the current instance) on a
layer of sorted JSONL claim files: `ontology/`, `corpus/`, `ledger/`. One grammar, intrinsic addresses, derived
everything. No network: `ath` ingests bytes already on disk and may shell out to local binaries (tesseract,
pdftotext); producers live outside it.

```
bun install
bun run src/main.ts whoami            # or: bun run build && dist/ath whoami
```

## Layout

- `contracts/` — one declaration per command: args (zod), argv shape, output (zod). Help and `--schema` derive from it.
- `src/kit/` — the dispatcher and nothing Athenaeum-specific: registry (longest-prefix word resolution), caller
  profiles (owner at a terminal · agent under a Claude session or off-terminal · reader), tiers (read · write · admin),
  gates, the `--json` envelope, closed error codes, events, history, locks. Modelled on the `ita` CLI's kit.
- `src/engine/` — the contract: lines, addresses, layers, ontology, derivation ops, trees, lints, L7, verify, harvest,
  export, serve. Never imports the kit except its error type.
- `src/commands/` — thin: parse → engine → data (+ a text renderer).
- `test/` — `bun test`; `test/harness.ts` runs the CLI in-process; regression tests self-skip without the bytes.

## Conventions

Global flags come before the command's words: `ath --json --root PATH --profile P --now ISO <words> [args]`.
Exit codes: 0 ok · 1 a verdict · 64 usage · 66 not found · 70 internal · 71 external tool · 73 refused write ·
75 busy · 77 denied · 78 config. A verdict (lint errors, a failed verify) is an ok envelope with `exit_code: 1`.
An admin command confirms at a terminal and never runs under `--json`.

Gates: `bun run check` (typecheck, biome, tests); `bun run build && dist/ath whoami`.
