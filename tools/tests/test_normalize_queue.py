"""The normalization queue (spec §8.5) — request/claim contract + the CLI verbs.

The queue is external, untracked state under `queue/`; it never writes records or inspects
them at enqueue time. `finalize` gates on the **pass gate** (3.1, re-keyed 3.2, §8.5):
formed-where-declared (§4.4.6) + lint-clean. The 3.1 gate's authored half dissolved into the
form layer (§4.1) — a record staying formless owes no vouch. The verbs are exit-code-
meaningful so a `/loop` session can drive them.
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

_FORM_OVERLAY = (
    "applies_to:\n  schemes: [convtest]\nkind: interpretive\nform:\n  id: conversation\n"
)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _declare_form_overlay(root: Path, schema_id: str = "conv-test") -> None:
    """Author an origin overlay declaring `form: {id: conversation}` (no mapping — the
    `declared_form_unmet` half of the pass gate only needs the id)."""
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True, exist_ok=True)
    (odir / f"{schema_id}.yaml").write_text(_FORM_OVERLAY, encoding="utf-8")
    schemas.cache_clear()


def _put(
    root: Path, rid: str, *,
    title: str = "",
    description: str = "",
    entry: str | None = "Intro",
    origin: bool = True,
    schema_id: str | None = None,
    section_form: str | None = None,
    section_fields: dict | None = None,
) -> None:
    """Build a fixture record. `title`/`description` set together is a full frontmatter
    editorial override (spec §4.2.1) — optional under 3.2, never required by the pass gate;
    `schema_id` (paired with `_declare_form_overlay`) declares a form; `section_form` stamps
    a matching (or deliberately mismatched) form section so the "formed-where-declared" half
    of the pass gate can be exercised in isolation. `section_fields` supplies the form
    overlay's required envelope fields (e.g. `conversation`'s `participants:`) so a stamped
    section can lint clean."""
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/plain")
    if origin:
        records.append_origin_block(
            post, uri="file:///x.txt", snapshot="2026-06-05T00:00:00Z", schema_id=schema_id
        )
    if section_form:
        seg = segments.Segment(atom="text", address="turn=1", body="hello")
        post.content = segments.emit(
            [segments.Section(form=section_form, segments=[seg], extra=section_fields or {})]
        )
    else:
        seg = segments.Segment(atom="text", address="el=1", body="hello", entry=entry)
        post.content = segments.emit([seg])
    if title:
        post.metadata["title"] = title
    if description:
        post.metadata["description"] = description
    records.dump(post, paths.record_path(root, rid))


# ---------- library: request / claim / settle ---------- #


def test_enqueue_is_idempotent(tmp_path):
    """Enqueue never inspects the record (§8.5) — no record even exists at this path."""
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
    _put(root, RID)
    before = paths.record_path(root, RID).read_text(encoding="utf-8")
    queue.enqueue(root, RID)
    queue.drain(root)
    queue.complete(root, RID)
    assert paths.record_path(root, RID).read_text(encoding="utf-8") == before


# ---------- CLI verbs ---------- #


def test_enqueue_then_drain_cli(tmp_path, capsys):
    root = _corpus(tmp_path)
    _put(root, RID)
    assert dispatch(["enqueue", RID, "--corpus-root", str(root)]) == 0
    capsys.readouterr()
    assert dispatch(["drain", "--corpus-root", str(root)]) == 0
    assert capsys.readouterr().out.strip() == RID
    # Queue now empty → drain exits 1 with no stdout (the /loop stop signal).
    assert dispatch(["drain", "--corpus-root", str(root)]) == 1
    assert capsys.readouterr().out.strip() == ""


def test_drain_wait_claims_an_already_pending_request(tmp_path, capsys):
    root = _corpus(tmp_path)
    _put(root, RID)
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
    _put(root, RID)

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
    _put(root, RID, title="T", description="A summary.")
    rc = dispatch(["finalize", RID, "--corpus-root", str(root)])
    assert rc != 0  # not claimed


def test_finalize_passes_unauthored_formless_lint_clean(tmp_path):
    """*(3.2)* The retired authored half of the pass gate no longer blocks finalize — a
    formless, lint-clean record with no vouch anywhere (no frontmatter override, no
    section) completes cleanly: "a record staying formless owes no vouch — its derived
    title/description are already honest" (spec §8.5)."""
    root = _corpus(tmp_path)
    _put(root, RID)  # no title/description, no declared form
    post = records.load(paths.record_path(root, RID))
    assert records.derived_editorial_field(post, root, "title").value == ""
    queue.enqueue(root, RID)
    queue.drain(root)
    rc = dispatch(["finalize", RID, "--corpus-root", str(root)])
    assert rc == 0
    st = queue.state(root, RID)
    assert st["state"] == "idle" and st["result"]["outcome"] == "completed"


def test_finalize_passes_formed_without_vouch(tmp_path):
    """*(3.2)* A formed record whose section header carries no title/description still
    passes finalize — the vouch is optional, not required, now that "authored" dissolves
    into the form layer (spec §4.1, §8.5)."""
    root = _corpus(tmp_path)
    _declare_form_overlay(root)
    _put(
        root, RID, schema_id="conv-test",
        section_form="conversation", section_fields={"participants": ["Andy <a1>"]},
    )
    post = records.load(paths.record_path(root, RID))
    assert records.derived_state(post) == "formed"
    assert records.derived_editorial_field(post, root, "title").value == ""
    queue.enqueue(root, RID)
    queue.drain(root)
    rc = dispatch(["finalize", RID, "--corpus-root", str(root)])
    assert rc == 0
    assert queue.state(root, RID)["result"]["outcome"] == "completed"


def test_finalize_refuses_declared_form_without_section(tmp_path):
    """Authored, lint-clean, but the origin declares a form (§4.4.6) that no section in the
    content zone carries — the "formed-where-declared" half of the pass gate (§8.5)."""
    root = _corpus(tmp_path)
    _declare_form_overlay(root)
    _put(root, RID, title="T", description="A summary.", schema_id="conv-test")
    queue.enqueue(root, RID)
    queue.drain(root)
    rc = dispatch(["finalize", RID, "--corpus-root", str(root)])
    assert rc != 0
    assert queue.state(root, RID)["state"] == "claimed"


def test_finalize_refuses_on_blocking_lint(tmp_path):
    root = _corpus(tmp_path)
    # Authored, and no form declared (formed-where-declared is vacuous) — but no origin block
    # at all, an `origins-empty` lint ERROR (spec §4.3.1.2), so only the lint gate refuses.
    _put(root, RID, title="T", description="A summary.", origin=False)
    queue.enqueue(root, RID)
    queue.drain(root)
    rc = dispatch(["finalize", RID, "--corpus-root", str(root)])
    assert rc != 0
    assert queue.state(root, RID)["state"] == "claimed"  # not closed on a dirty pass


def test_finalize_completes_a_clean_pass(tmp_path):
    root = _corpus(tmp_path)
    _put(root, RID, title="T", description="A faithful summary.")
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


def test_finalize_passes_formed_authored_clean(tmp_path):
    """The full pass gate (§8.5): authored + formed-where-declared + lint-clean, together."""
    root = _corpus(tmp_path)
    _declare_form_overlay(root)
    _put(
        root, RID, title="T", description="A conversation record.", schema_id="conv-test",
        section_form="conversation", section_fields={"participants": ["Andy <a1>"]},
    )
    post = records.load(paths.record_path(root, RID))
    assert records.derived_state(post) == "formed"
    queue.enqueue(root, RID)
    queue.drain(root)
    assert dispatch(["finalize", RID, "--corpus-root", str(root)]) == 0
    assert queue.state(root, RID)["result"]["outcome"] == "completed"


def test_await_resolves_completed_then_failed(tmp_path):
    root = _corpus(tmp_path)
    _put(root, RID, title="T", description="A summary.")
    queue.enqueue(root, RID)
    queue.drain(root)
    queue.complete(root, RID)
    assert dispatch(["await", RID, "--timeout", "5", "--corpus-root", str(root)]) == 0

    queue.enqueue(root, RID)
    queue.drain(root)
    queue.fail(root, RID, reason="nope")
    assert dispatch(["await", RID, "--timeout", "5", "--corpus-root", str(root)]) != 0


def test_await_record_state_fallback_uses_pass_gate(tmp_path):
    """Absent a recorded outcome, `await` falls back to the record-state predicate:
    formed-where-declared (no lint in the poll loop, §8.5, re-keyed 3.2 — the authored half
    dissolved into the form layer, so a bare formless record needs no vouch to settle)."""
    root = _corpus(tmp_path)
    _put(root, RID, title="T", description="A summary.")
    assert dispatch(["await", RID, "--timeout", "1", "--corpus-root", str(root)]) == 0

    # A bare, override-less, formless record ALSO settles now — no vouch required.
    untitled = "d4" * 32
    _put(root, untitled)
    assert dispatch(["await", untitled, "--timeout", "1", "--corpus-root", str(root)]) == 0

    # A record whose origin declares a form the content zone doesn't carry still fails —
    # the "formed-where-declared" half of the gate still applies.
    _declare_form_overlay(root, schema_id="conv-test")
    unmet = "c3" * 32
    _put(root, unmet, schema_id="conv-test")
    rc = dispatch(["await", unmet, "--timeout", "0.2", "--interval", "0.05",
                   "--corpus-root", str(root)])
    assert rc != 0


def test_await_times_out_while_pending(tmp_path):
    root = _corpus(tmp_path)
    _put(root, RID)
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
