"""The normalization queue (spec §8.5) — request/claim contract + the CLI verbs.

The queue is external, untracked state under `queue/`; it never writes records.
A claim is an atomic rename, `finalize` gates on `status: normalized` + lint-clean,
and the verbs are exit-code-meaningful so a `/loop` session can drive them.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import frontmatter

from corpus import paths, queue, records, schemas, segments
from corpus._cli import dispatch

RID = "a1" * 32
RID2 = "b2" * 32


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _put(
    root: Path, rid: str, *, status: str, description: str = "", entry: str | None = "Intro"
) -> None:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/plain")
    records.append_origin_block(post, uri="file:///x.txt", snapshot="2026-06-05T00:00:00Z")
    post.content = segments.emit(
        [segments.Segment(atom="text", address="el=1", body="hello", entry=entry)]
    )
    post.metadata["status"] = status
    if status == "normalized":
        post.metadata["title"] = "T"
        post.metadata["description"] = description
    records.dump(post, paths.record_path(root, rid))


# ---------- library: request / claim / settle ---------- #


def test_enqueue_is_idempotent_and_status_aware(tmp_path):
    root = _corpus(tmp_path)
    assert queue.enqueue(root, RID) == "requested"
    assert queue.enqueue(root, RID) == "already-requested"  # joins the pending request
    assert queue.drain(root) == RID  # claim it
    assert queue.enqueue(root, RID) == "in-flight"  # a request during a pass joins it


def test_drain_hands_out_each_request_once_then_empty(tmp_path):
    root = _corpus(tmp_path)
    queue.enqueue(root, RID)
    queue.enqueue(root, RID2)
    claimed = {queue.drain(root), queue.drain(root)}
    assert claimed == {RID, RID2}
    assert queue.drain(root) is None  # empty queue — the loop's stop signal


def test_drain_does_not_rehand_a_live_claim(tmp_path):
    root = _corpus(tmp_path)
    queue.enqueue(root, RID)
    assert queue.drain(root) == RID
    # The claim is live (lease not lapsed): a second drain must not re-hand it out.
    assert queue.drain(root, lease=10_000) is None


def test_drain_reclaims_a_stale_claim(tmp_path):
    root = _corpus(tmp_path)
    queue.enqueue(root, RID)
    assert queue.drain(root) == RID
    # Backdate the claim so its lease has lapsed (a dead loop session).
    stale = "2000-01-01T00:00:00+00:00"
    queue._write_json(
        queue._claim(root, RID),
        {"id": RID, "requested_at": stale, "claimed_at": stale},
    )
    assert queue.drain(root, lease=60) == RID  # reclaimed


def test_complete_fail_requeue_transitions(tmp_path):
    root = _corpus(tmp_path)
    queue.enqueue(root, RID)
    queue.drain(root)
    queue.complete(root, RID)
    st = queue.state(root, RID)
    assert st["state"] == "idle" and st["result"]["outcome"] == "completed"

    queue.enqueue(root, RID)
    queue.drain(root)
    queue.fail(root, RID, reason="gave up")
    st = queue.state(root, RID)
    assert st["state"] == "idle" and st["result"]["outcome"] == "failed"

    queue.enqueue(root, RID)
    queue.drain(root)
    queue.requeue(root, RID)
    assert queue.state(root, RID)["state"] == "requested"


def test_queue_never_writes_records(tmp_path):
    root = _corpus(tmp_path)
    _put(root, RID, status="draft")
    before = paths.record_path(root, RID).read_text(encoding="utf-8")
    queue.enqueue(root, RID)
    queue.drain(root)
    queue.complete(root, RID)
    assert paths.record_path(root, RID).read_text(encoding="utf-8") == before


# ---------- CLI verbs ---------- #


def test_enqueue_then_drain_cli(tmp_path, capsys):
    root = _corpus(tmp_path)
    _put(root, RID, status="draft")
    assert dispatch(["enqueue", RID, "--corpus-root", str(root)]) == 0
    capsys.readouterr()
    assert dispatch(["drain", "--corpus-root", str(root)]) == 0
    assert capsys.readouterr().out.strip() == RID
    # Queue now empty → drain exits 1 with no stdout (the /loop stop signal).
    assert dispatch(["drain", "--corpus-root", str(root)]) == 1
    assert capsys.readouterr().out.strip() == ""


def test_drain_wait_claims_an_already_pending_request(tmp_path, capsys):
    root = _corpus(tmp_path)
    _put(root, RID, status="draft")
    queue.enqueue(root, RID)
    # A claimable request is returned immediately — --wait never sleeps when there's work.
    rc = dispatch(
        ["drain", "--wait", "--timeout", "2", "--interval", "0.05", "--corpus-root", str(root)]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == RID


def test_drain_wait_times_out_on_empty_queue(tmp_path, capsys):
    root = _corpus(tmp_path)
    # Empty queue + a bounded --timeout → exit 1 (an empty result), nothing on stdout.
    rc = dispatch(
        ["drain", "--wait", "--timeout", "0.2", "--interval", "0.05", "--corpus-root", str(root)]
    )
    assert rc == 1
    assert capsys.readouterr().out.strip() == ""


def test_drain_wait_picks_up_a_late_arrival(tmp_path, capsys):
    root = _corpus(tmp_path)
    _put(root, RID, status="draft")

    def _enqueue_soon() -> None:
        time.sleep(0.15)
        queue.enqueue(root, RID)

    t = threading.Thread(target=_enqueue_soon)
    t.start()
    try:
        # The long-poll wakes within an interval of the request appearing — no model in the loop.
        rc = dispatch(
            ["drain", "--wait", "--timeout", "3", "--interval", "0.03", "--corpus-root", str(root)]
        )
    finally:
        t.join()
    assert rc == 0
    assert capsys.readouterr().out.strip() == RID


def test_finalize_requires_a_claim(tmp_path):
    root = _corpus(tmp_path)
    _put(root, RID, status="normalized", description="A summary.")
    rc = dispatch(["finalize", RID, "--corpus-root", str(root)])
    assert rc != 0  # not claimed


def test_finalize_refuses_unnormalized(tmp_path):
    root = _corpus(tmp_path)
    _put(root, RID, status="draft")
    queue.enqueue(root, RID)
    queue.drain(root)
    rc = dispatch(["finalize", RID, "--corpus-root", str(root)])
    assert rc != 0
    assert queue.state(root, RID)["state"] == "claimed"  # claim left intact


def test_finalize_refuses_on_blocking_lint(tmp_path):
    root = _corpus(tmp_path)
    _put(root, RID, status="normalized", description="")  # empty desc → description-empty error
    queue.enqueue(root, RID)
    queue.drain(root)
    rc = dispatch(["finalize", RID, "--corpus-root", str(root)])
    assert rc != 0
    assert queue.state(root, RID)["state"] == "claimed"  # not closed on a dirty pass


def test_finalize_completes_a_clean_pass(tmp_path):
    root = _corpus(tmp_path)
    _put(root, RID, status="normalized", description="A faithful summary.")
    # Self-check: the fixture genuinely lints clean (no error-severity findings).
    post = records.load(paths.record_path(root, RID))
    blocks = segments.iter_blocks(post.content or "")
    from corpus import lint as _lint

    assert not [f for f in _lint.lint(post, blocks, root) if f.severity == "error"]

    queue.enqueue(root, RID)
    queue.drain(root)
    assert dispatch(["finalize", RID, "--corpus-root", str(root)]) == 0
    st = queue.state(root, RID)
    assert st["state"] == "idle" and st["result"]["outcome"] == "completed"


def test_await_resolves_completed_then_failed(tmp_path):
    root = _corpus(tmp_path)
    _put(root, RID, status="normalized", description="A summary.")
    queue.enqueue(root, RID)
    queue.drain(root)
    queue.complete(root, RID)
    assert dispatch(["await", RID, "--timeout", "5", "--corpus-root", str(root)]) == 0

    queue.enqueue(root, RID)
    queue.drain(root)
    queue.fail(root, RID, reason="nope")
    assert dispatch(["await", RID, "--timeout", "5", "--corpus-root", str(root)]) != 0


def test_await_times_out_while_pending(tmp_path):
    root = _corpus(tmp_path)
    _put(root, RID, status="draft")
    queue.enqueue(root, RID)  # requested → pending, never settles
    rc = dispatch(
        ["await", RID, "--timeout", "0.2", "--interval", "0.05", "--corpus-root", str(root)]
    )
    assert rc != 0


def test_prune_removes_aged_results_keeps_fresh(tmp_path):
    root = _corpus(tmp_path)
    # A settled (completed) entry leaves a .result marker; backdate it past the grace window.
    queue.enqueue(root, RID)
    queue.drain(root)
    queue.complete(root, RID)
    queue._write_json(
        queue._result(root, RID),
        {"id": RID, "outcome": "completed", "finished_at": "2000-01-01T00:00:00+00:00"},
    )
    # A second, freshly-settled result stays inside the grace window.
    queue.enqueue(root, RID2)
    queue.drain(root)
    queue.complete(root, RID2)

    removed = queue.prune(root)  # default grace (7 days)
    assert removed["results"] == [RID]
    assert queue.state(root, RID)["result"] is None  # aged result gone
    assert queue.state(root, RID2)["result"] is not None  # fresh result kept
    # Idempotent: a second prune removes nothing more.
    assert queue.prune(root)["results"] == []


def test_prune_never_touches_live_entries(tmp_path):
    root = _corpus(tmp_path)
    queue.enqueue(root, RID)  # requested (live)
    queue.enqueue(root, RID2)
    queue.drain(root)  # one claimed (live)
    removed = queue.prune(root, older_than_days=0)  # prune everything prunable
    assert removed == {"results": [], "temp": []}  # nothing settled → nothing removed
    states = {e["state"] for e in queue.entries(root)}
    assert states == {"requested", "claimed"}  # live entries untouched


def test_prune_sweeps_orphan_temp_scratch(tmp_path):
    root = _corpus(tmp_path)
    qd = queue.queue_dir(root)
    qd.mkdir(parents=True, exist_ok=True)
    orphan = qd / f"{RID}.result.tmp.99999"  # crash-orphaned atomic-write scratch
    orphan.write_text("{}\n", encoding="utf-8")
    removed = queue.prune(root, older_than_days=0)
    assert removed["temp"] == [orphan.name]
    assert not orphan.exists()


def test_queue_prune_cli(tmp_path, capsys):
    root = _corpus(tmp_path)
    queue.enqueue(root, RID)
    queue.drain(root)
    queue.complete(root, RID)
    assert dispatch(["queue", "--prune", "--older-than", "0", "--corpus-root", str(root)]) == 0
    assert "pruned 1 result" in capsys.readouterr().out
    assert queue.state(root, RID)["result"] is None


def test_queue_listing(tmp_path, capsys):
    root = _corpus(tmp_path)
    queue.enqueue(root, RID)
    queue.enqueue(root, RID2)
    queue.drain(root)  # one claimed, one requested
    assert dispatch(["queue", "--corpus-root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "claimed" in out and "requested" in out
    assert RID[:12] in out and RID2[:12] in out
