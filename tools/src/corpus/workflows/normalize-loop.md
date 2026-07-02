# Normalize loop

Run the interpretive normalize stage as an external loop session over the queue's request/claim contract.

`normalize` (spec §8.1, §8.5) is the one stage the tooling does not run itself — it is interpretive, performed by an external **loop session** (a scheduled agent). The tooling provides only the request/claim contract; it never invokes a normalizer. One generic loop serves every domain: the per-domain knowledge rides in overlays (`corpus guidance <id>`), so the loop never needs domain code — a codex contributes by authoring overlays and enqueuing, not by supplying a normalizer.

The verb cycle each iteration:

    enqueue   request a (re-)normalization pass for a record (the requester side)
    drain     claim the next pending record — prints its id (the consumer/loop side)
    guidance  read the merged overlay guidance for the claimed record
    finalize  close the pass — gated on status: normalized AND lint-clean
    release   return the claim — bare re-queues it; --failed records a failure
    await     (requester side) block until a record's pass settles, resolve by exit code

The loop runs in one of two operating **modes** — `scheduled` or `standing` — and leaves behind outcomes that are GC'd by age (`results`). Narrow into each below.

## Scheduled

A timer (e.g. cron) wakes the loop; it drains until the queue is empty, then sleeps until the next tick.

    while id=$(corpus drain --by "$SESSION"); do
        corpus guidance "$id"
        # ...normalize $id in-session: title, description, segment/embed descriptions,
        #    re-segmentation; set status: normalized; recompile...
        corpus finalize "$id" || corpus release "$id" --failed "<reason>"
    done

An empty queue makes `drain` exit 1 with no output — the loop's natural stop signal. Simple and stateless, but the **model is the poller**: every tick wakes the loop session just to ask "any work?", and the session is the expensive layer, so most ticks find nothing. Pickup latency is the tick interval. Good for low, predictable volume, or when no long-lived process is available to host a standing loop.

## Standing

The loop blocks on `corpus drain --wait`, which long-polls the claim **in the subprocess** (the free layer) and returns the instant a request is claimable — so the wait lives in the tooling, and the loop session is engaged only when there is genuinely work.

    corpus drain --wait --json --by "$SESSION"   # blocks; emits one {id, record} when work arrives

Run it under a persistent runner that re-invokes per claim (a `while` loop, a process supervisor, or an event runner), normalizing each emitted id then finalizing as in the scheduled cycle. `--timeout 0` (the default) waits indefinitely; `--timeout S` gives up after S seconds (exit 1); `--interval` sets the poll cadence (default 2 s). The wait **never holds a claim** — `drain` claims atomically only at the instant it succeeds, then returns — so interrupting it mid-wait (exit 130) leaks nothing.

Prefer this mode whenever a long-lived process or event runner is available: near-zero idle cost (no model wake-ups on an empty queue) and faster pickup (within one poll interval). `--wait` is purely additive — without it, `drain` behaves exactly as in the scheduled loop (empty → exit 1), so the same verb drives both modes.

## Results

A request and its claim are transient — each transition supersedes the prior state. A **settled** pass records an outcome so a requester's `corpus await <id>` can resolve completed-vs-failed, and tell a *re-normalization* apart from an earlier pass (`status` alone cannot — a re-normalized record is still `status: normalized`). That outcome is **coordination state, not history**: the record's own `status` and `touch[]` are the durable trail.

Outcomes are **never discarded at loop end**. The loop (consumer) and a requester (`enqueue` → `await`) are decoupled and asynchronous; a requester may `await` after a loop iteration ends, and deleting on loop end would race it — dropping the awaiter to the `status` fallback that cannot distinguish a re-normalization. Instead, GC by **age**:

    corpus queue --prune                 # remove settled outcomes older than the grace window (default 7 d)
    corpus queue --prune --older-than 0  # remove all settled outcomes now
    corpus queue                         # list live entries (requested + claimed)

`--prune` also sweeps orphaned write scratch, never touches live requested/claimed entries, and is idempotent. Run it on a periodic tick, or around a drain session, so the queue's footprint stays bounded without ever dropping an outcome a requester still needs.
