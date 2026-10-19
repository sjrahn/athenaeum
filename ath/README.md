# ath — the specification's reference implementation

A Bun/TypeScript workspace implementing `spec/athenaeum.md` (what conforms and what is owed: `CONFORMANCE.md`). The
`ath` CLI, the `athd` host daemon and the residence scanner share one registry of verbs, one envelope and one set of
gates, on the foundations of the `ita` CLI. Nothing here acquires: artifacts and testimony are handed in from disk.

```
bun install
bin/ath whoami                        # or: bun run build && dist/ath whoami
```

## Packages

| package | holds | may import |
|---|---|---|
| `contracts` | `defineContract` (zod args, argv shape, zod data); help and `--schema` derive from it | zod |
| `kit` | the dispatcher, registry, callers and profiles (from the process tree), tiers and gates, the envelope and exit codes, events, locks, history and the journal in host state, XDG host paths, the canonical line, BLAKE3, atomic writes | contracts |
| `engine` | what an instance is: formats (sniffing, intrinsics, constituents, surfaces, hints), addresses, records, testimony, vocabularies, passes, the graph, checks, export | kit, contracts |
| `custody` | stores and drivers, the host index, policies, reconcile, resolution | kit, contracts |
| `scanner` | the residence scanner (`ath-scan`): an observed tree's manifest, its own versioned contract (`MANIFEST-SCHEMA.md`) | kit |
| `verbs` | every verb of §19.5: a contract over engine and custody functions | kit, contracts, engine, custody |
| `daemon` | `athd`: the verbs over a unix socket, the custody schedule; handed the registry | kit, contracts |
| `cli` | `main.ts`: the registry and the real environment | kit, contracts, verbs, daemon |

`test/workspace.lint.test.ts` pins the graph. Imports between packages go through `@ath/<package>/<path>`.

## Host state

Nothing the tool keeps for itself is in a repository (§5.6): the local store under `$XDG_DATA_HOME/athenaeum/`, the
custody index and each instance's staging, locks, journal and history under `$XDG_STATE_HOME/athenaeum/`, the access
and host files under `$XDG_CONFIG_HOME/athenaeum/`, the daemon's socket under `$XDG_RUNTIME_DIR/athenaeum/`.

## The host daemon

`athd` (`ath daemon run`; `ath daemon install` writes and starts a systemd user unit) answers every read and write
verb at `POST /v1/<verb>` on its socket, and keeps custody for the instances `host.yaml` names:

```yaml
daemon:
  instances: [~/athenaeum]
  every: {inventory: 1d, verify: 30d, reconcile: 1h}   # a job left out runs on events and on demand only
  poll: 5m                                              # look for a store come back or a new observed generation
```

While it runs, a verb that writes the custody index (`ingest`, `custody inventory|verify|reconcile`) is handed to it;
without it, the verb runs in the calling process under the index lock. A store's bandwidth on this host is its
`bwlimit` in `access.yaml` (`bwlimit: 10MB/s`).

## Conventions

Global flags come before the verb's words: `ath --json --root PATH --profile P --now ISO <words> [args]`. Exit codes:
0 ok · 1 a verdict · 64 usage · 66 not found · 69 the daemon is not running · 70 internal · 71 external tool · 73 a
refused write · 75 busy · 77 denied · 78 config. A verdict is an ok envelope with `exit_code: 1`. An admin verb is
confirmed at a terminal and never runs under `--json`. Every instant is whole-second UTC; `--now` moves only what a
verb reports, never a receipt, a pass, a ruling or a removal.

Gates: `bun run check` (tsc, biome, tests; run with `TMPDIR` off a small tmpfs); `bun run build && dist/ath whoami`.
