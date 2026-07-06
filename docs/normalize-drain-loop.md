# Normalization drain monitor — the standing queue loop

The operating procedure for running normalization as a **standing loop over the queue**:
one long-lived session that claims whatever's enqueued, hands it to a `normalizer` agent,
and finalizes — record-agnostic, near-zero idle cost. Starting it is a matter of following
§*Start the monitor* below; **which records are enqueued doesn't matter** — the loop drains
whatever is there.

The loop serves **either corpus** — the queue is per-corpus state (`queue/` in each corpus
root), so a monitor drains ONE hub; run one per corpus when both have work. **Boot the
session at the athenaeum workspace root** (where the `normalizer` subagent is defined,
`.claude/agents/normalizer.md`) and run the `corpus` commands with cwd inside the target
corpus (`corpora/corpus` or `corpora/corpus-private`) or with `--corpus-root`.

This is the *how-to for running the loop*. The generic request/claim contract and its two
modes are the tooling's own runbook — read it first, don't restate it:

```bash
corpus workflow normalize-loop            # overview + the enqueue/drain/finalize/release/await cycle
corpus workflow normalize-loop standing   # the mode this monitor runs
corpus workflow normalize-loop results    # the settled-outcome lifecycle + prune
```

Per-*record* normalization guidance is never here either — it rides in the classification
overlays and surfaces per claim via `corpus guidance <id>` / `corpus diagnose <id>`. The
monitor is classification-agnostic; the agent picks up format specifics at runtime. For
iMessage records specifically, those specifics are [`imessage-workflow.md`](imessage-workflow.md) §5.

## When to run this vs. the explicit-set batch

Two ways records get normalized; pick by the *shape of the work*, not the classification:

- **Drain monitor (this file)** — a *standing* loop for whatever trickles into the queue:
  ad-hoc `corpus enqueue`s, re-normalization after an overlay change (stale is
  status-independent — a normalized record re-enqueues), a handful of fresh drafts. One
  claim at a time, dispatched to one `normalizer` agent. You start it and leave it; it
  drains whatever is there and parks when dry.
- **Explicit-set batch** ([`imessage-workflow.md`](imessage-workflow.md) §5) — for a
  *known pile, right now* (a fresh weekly export): the orchestrator partitions the ids up
  front (one batch agent for all the small records + one agent per heavy thread) and
  dispatches on **explicit disjoint hash sets, bypassing the queue**. Better wall-clock on
  a big known backlog because the partition is size-aware; the queue's round-robin claim is
  not.

Both run the same per-record work through the same `normalizer` agent — only the *dispatch*
differs. Don't run both over the same ids at once: `corpus decompose`'s per-id scratch keeps
them from corrupting each other, but it's duplicated work.

## Start the monitor

`SESSION` is any stable identifier for this loop — recorded on claims/results, and what
lets a stale claim (a dead session) be reclaimed after its `--lease`. Use `drain-monitor`.

The standing cycle — one claim → one agent → finalize, repeated:

```bash
SESSION=drain-monitor
corpus queue --prune                                    # sweep aged outcomes first
while id=$(corpus drain --wait --by "$SESSION"); do
    #   >>> hand $id to a `normalizer` agent <<<
    #   it self-guides from `corpus guidance $id`, sets status: normalized, recompiles.
    corpus finalize "$id" || corpus release "$id" --failed "<reason>"
done
```

`corpus drain --wait` **long-polls in the subprocess** (the free layer) and returns the
instant a request is claimable, so the session is engaged only when there is genuinely work
— no model wake-ups on an empty queue. It prints just the id (add `--json` for
`{id, record}`). The wait never holds a claim, so interrupting it mid-wait leaks nothing.

**Realizing the loop in a Claude Code session.** A raw `--wait --timeout 0` blocks a single
Bash call forever, which an agent turn can't host. Run it as a self-paced `/loop`
instead — each tick is one claim attempt with a bounded park:

```bash
corpus drain --wait --timeout <T> --by "$SESSION"       # park up to T s in the free layer
```

- **id returned** → dispatch a `normalizer` **subagent** on it (the decompose/compile churn
  stays in the subagent, so the monitor's own context stays clean), then `corpus finalize`
  (or `release --failed`), then re-arm the loop.
- **exit 1 (timed out, no work)** → re-arm and park again.

Delegating each claim to a subagent is what makes the monitor cheap to run for a long time.
One claim per subagent — or, if several small records are already queued, let one agent take
a same-classification batch (it processes a batch per invocation). Pick `T` for the park you
want: ≤ ~270 s keeps the prompt cache warm; longer trades one cache miss for fewer wake-ups.

**Scheduled fallback.** No long-lived loop available? Run the *scheduled* mode instead
(`corpus workflow normalize-loop scheduled`): a timer wakes the session, it drains to dry
with plain `corpus drain` (no `--wait`; empty → exit 1), then sleeps. Higher pickup latency,
dead simple.

## The `normalizer` dispatch

Each claimed id goes to a `normalizer` agent (subagent type `normalizer`, defined at the
workspace root's `.claude/agents/`). Brief it with only the **corpus root** + the id(s) plus
the finalize contract — it carries **no** format knowledge and pulls
everything from the corpus at runtime (`corpus diagnose` / `guidance` / `overlay` / `atoms`).
It must leave the record at `status: normalized` **and** lint-clean, or `corpus finalize`
refuses (exit 1). The monitor owns claim + finalize/release; the agent owns the
normalization. Do **not** tell the agent to touch the queue.

## Stop, failures, backlog

- **Stop** — a standing loop parks until killed; the scheduled loop ends naturally on an
  empty queue. On a clean shutdown while holding a claim, `corpus release <id>` (bare)
  re-queues it for the next drain.
- **A pass that can't clear** — `corpus release <id> --failed "<reason>"`; the record stays
  a draft and an awaiting requester resolves to failure. Never `finalize` a dirty pass — the
  gate (normalized + lint-clean) refuses it anyway.
- **Heavy thread** — two different limits. A multi-GB export OOMs the drafter/normalizer and
  is deferred pending a streaming parse (`imessage-workflow.md` §3): if the monitor claims
  one, `release --failed "oversize; needs streaming parse"` so the loop doesn't wedge. Separately,
  an *attachment-dense* thread can overflow a single normalizer subagent — accumulated image
  views hit the 32MB API request cap (the binding limit at any context length; ~60 downscaled
  views per agent, and a 200k-context agent token-wedges even earlier at ~30 full-size views —
  see `imessage-workflow.md` §5): past it, don't hand the record to one subagent; use
  the **perception/assembly split** (same §5): parallel read-only describers write
  per-attachment description files, then one assembler applies them and compiles — and
  spot-audit descriptions against bytes afterward (§5's off-by-N failure mode). For a big *normal* backlog, stop the monitor and use the size-aware explicit-set
  batch instead.
- **Prune** — `corpus queue --prune` (settled outcomes older than 7 d; `--older-than 0` for
  all) around each drain session or on a periodic tick, so the queue's footprint stays
  bounded. It never touches live requested/claimed entries.
