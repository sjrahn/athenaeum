# Session Capture — ingesting Claude Code sessions

Operational guide for `corpus session` — bundling a Claude Code session (transcript +
sidecar tree) into the corpus as one content-addressed record, and keeping the more
complete version as a session grows. The design contract lives in `spec/corpus.md`
(§7.2 the `claude-code-session` origin, §12.8 the writer core) and `spec/ledger.md`
(the `supersede` verb); this doc is the how-to.

## What a session is on disk

Claude Code stores each session under a per-project directory keyed by a mangled cwd:

```
~/.claude/projects/<mangled-cwd>/<session-id>.jsonl     # the main transcript (append-only)
~/.claude/projects/<mangled-cwd>/<session-id>/          # sidecar tree
    subagents/agent-<name>-<hash>.jsonl (+ .meta.json)  #   dispatched agents
    tool-results/<id>.txt · pdf-<id>/page-N.jpg         #   overflow tool-result payloads
    workflows/wf_<id>.json                              #   workflow scripts / state
```

`corpus session capture` packs the transcript + the whole `<id>/` subtree into ONE
deterministic zstd-zip (`ZIP_ZSTANDARD` members via the `corpus.assembly` writer core),
ingests it, and drafts it with the `zip-manifest` strategy: **every member becomes a
directly-addressed `path=<member>` embed** (`corpus://<record>?path=<member>` resolves it
byte-faithful) and the content zone stays empty. The transcript is a transport, never
transcribed into prose.

## Tenancy: sessions are private

A session bundle embeds every tool result verbatim — it routinely contains private records,
emails, even medical PDFs the session read. **Always capture into `corpus-private`.** Run
the command from inside `corpora/corpus-private` (auto-discovery) or pass
`--corpus-root corpora/corpus-private`.

## Everyday use

```bash
cd corpora/corpus-private

corpus session list                       # discoverable sessions + stats (records, sub-agents, size)
corpus session capture <session-id>       # bundle → ingest → draft  (accepts an <id>.jsonl path too)
corpus show <hash>                        # origin: [claude-code-session] + session_id; embeds: path=<member>
corpus lint <hash>                        # must be clean
corpus resolve "corpus://<hash>?path=<session-id>.jsonl" | head   # a member round-trips
```

`capture` prints the new record's blake3. Identity is the **bundle's blake3**, so a session
that has grown since the last capture becomes a **new record** — that is expected.

## Recapture & supersession (keep the more complete version)

Re-running `capture` on the same session is safe and idempotent:

- **Nothing changed** → the deterministic bundle hashes identically → an ingest
  **re-encounter** (no duplicate).
- **The session grew** (append-only) → a new record whose content **contains** the prior.
  `capture` proves this with `corpus continuity <old> <new>` (`contains_a: true`) and prints
  the exact follow-up to rewrite any ledger citations and reclaim the old bytes:

  ```bash
  ath ledger supersede <old-hash> <new-hash> --retire
  ```

- **The session was compacted / rewritten** (the new transcript is NOT a superset) →
  `capture` refuses to supersede, keeps **both** records, and warns. This is the case a
  naive turn-counter would get wrong; the continuity check catches it. Decide by hand which
  to keep (the pre-compaction record holds detail the new one dropped).

`corpus continuity <A> <B>` is the standalone check: per `path=<member>` it reports
`identical` / `contained` / `diverged` / `absent`, and the bottom line `contains_a` — the
green light for both supersession and citation rewrite.

## Pulling sessions from another machine (SSH)

```bash
corpus session list --from <host>                 # session ids discoverable on <host>
corpus session capture <session-id> --from <host> # rsync the transcript + <id>/ tree, then bundle
```

`--from [user@]host` uses `ssh` to locate the session and `rsync -a` (mtimes preserved →
the bundle stays deterministic; `scp -rp` fallback) to stage it locally before bundling. The
source machine is recorded as the origin `host` field, so identically-named sessions from
different boxes never collide, and each machine's sessions fold into one corpus.

## Notes & gotchas

- **Determinism depends on member mtimes + a state-only archive comment.** The zip comment
  names the session and its `record_count`/`activity_end` — never the wall-clock capture
  time (that would perturb the bytes every run and defeat the re-encounter). Don't reintroduce
  a capture timestamp into `ccsession.bundle_comment`.
- **`--project`** narrows discovery when a session id (unlikely) collides across project dirs,
  or to disambiguate a `--from` lookup.
- **Citation eligibility.** The ledger only cites `normalized` records. A session record is
  mechanically complete at `draft` (nothing to transcribe); when the first ledger citation of
  a session is authored, resolve how it reaches `normalized` (a trivial confirm or a spec
  carve-out) — see the open point in `spec/corpus.md` §7.2.
