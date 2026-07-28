"""The `adopt_flat` ADOPT shaper (spec §7.8, §12.19 step 4): wraps an ALREADY-RENDERED, flat
(section-less) conversation content zone in a whole-record `<!--section conversation-->`
opener, deriving `participants:` from the record's own stored sender field — no
re-transcription, no re-addressing. Proves the codebook derivation (distinct senders,
first-appearance order), the opener emission (whole-record: no `address`), the two refusal
guards (empty content zone; already-sectioned record), and the `el=` address axis's
lint-clean status (the imessage-conversation-adopt-32 finding: an HTML-drafted chat export
addresses at `el=`, a third axis alongside `turn=`/`time_range=`)."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from corpus import lint, recordbuild, records, segments
from corpus.shape import conversation, get_shaper

_FLAT_BODY = """\
<!--segment text/message
address: el=1
sender: Me
timestamp: '2011-11-08T11:31:10'
-->

You get COD yet?

<!--segment text/message
address: el=2
sender: Jason Cummings
timestamp: '2011-11-08T11:32:36'
-->

No, not yet.

<!--segment image
address: el=3
-->

<!--segment text/message
address: el=4
sender: Jason Cummings
timestamp: '2011-11-08T11:34:12'
-->

Elder scrolls.

<!--segment text/message
address: el=5
sender: Me
timestamp: '2011-11-08T11:35:19'
-->

Wanna come?
"""


_FAKE_ID = "a" * 64


def _post(body: str, embeds: list | None = None) -> frontmatter.Post:
    post = frontmatter.Post(body)
    post.metadata.update({"id": _FAKE_ID, "transport": "sha256:" + "b" * 64})
    post.metadata["_embeds"] = embeds or []
    return post


def _root(tmp_path: Path) -> Path:
    (tmp_path / "records").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _adopt(post: frontmatter.Post, root: Path) -> frontmatter.Post:
    build = recordbuild.begin_from_post(post, root)
    conversation.adopt_flat(build, post, root, {})
    return recordbuild.finish(build)


def _lint_findings(post: frontmatter.Post, root: Path) -> list:
    blocks = segments.iter_blocks(post.content or "")
    return list(lint.lint(post, blocks, root))


# The form-coherence rule ids (§4.3.2.1/§7.8) this suite actually exercises — the fixtures
# above are minimal (no touch chain, no embed descriptions) and deliberately don't chase every
# unrelated universal lint rule (`touch-empty`, embed-description warnings); what matters here
# is that adopting `el=` addressing raises none of the form's own coherence findings.
_FORM_COHERENCE_RULES = {
    "form-overlay-unknown",
    "form-envelope-missing",
    "form-codebook-index-out-of-range",
    "form-address-axis",
    "form-address-nonmonotonic",
}


def _form_coherence_findings(post: frontmatter.Post, root: Path) -> list:
    return [f for f in _lint_findings(post, root) if f.rule_id in _FORM_COHERENCE_RULES]


def test_adopt_flat_wraps_whole_record_with_codebook(tmp_path):
    root = _root(tmp_path)
    post = _post(_FLAT_BODY)
    # The bare `image` marker at el=3 needs its matching embed — a real drafted record only
    # ever emits an attachment marker when a real embed backs it (§4.3.2.2).
    records.append_embed_block(
        post, media_type="image/gif", address="el=3", transport="blake3:" + "c" * 64
    )
    post = _adopt(post, root)

    blocks = segments.iter_blocks(post.content or "")
    assert len(blocks) == 1
    sec = blocks[0]
    assert isinstance(sec, segments.Section)
    assert sec.form == "conversation"
    # *(3.7)* The envelope is derived from the children rather than omitted (§12.29); these
    # five root-level siblings cross subtree boundaries, so it is an ordered address list.
    assert sec.address == ["el=1", "el=2", "el=3", "el=4", "el=5"]
    # First-appearance order: Me (turn 1), Jason Cummings (turn 2) — no duplicates.
    assert sec.extra["participants"] == ["Me", "Jason Cummings"]

    # Every original segment survives, in order, fields untouched.
    assert [s.address for s in sec.segments] == ["el=1", "el=2", "el=3", "el=4", "el=5"]
    assert [s.atom for s in sec.segments] == ["text", "text", "image", "text", "text"]
    assert sec.segments[0].body.strip() == "You get COD yet?"
    assert sec.segments[0].extra["sender"] == "Me"
    assert sec.segments[0].extra["timestamp"] == "2011-11-08T11:31:10"
    assert sec.segments[2].body == ""  # the bare image marker stays body-empty
    assert "sender" not in sec.segments[2].extra  # no sender on the attachment marker

    # Zero form-coherence findings — in particular, `el=` raises no `form-address-axis`
    # warning (the imessage-conversation-adopt-32 schema fix) and the strictly-increasing
    # el=1..5 sequence raises no `form-address-nonmonotonic` warning.
    assert not _form_coherence_findings(post, root)


def test_adopt_flat_ignores_segments_without_sender(tmp_path):
    root = _root(tmp_path)
    body = _FLAT_BODY + """
<!--segment image
address: el=6
-->
"""
    post = _adopt(_post(body), root)
    sec = segments.iter_blocks(post.content or "")[0]
    # The trailing sender-less image marker adds nothing to the codebook.
    assert sec.extra["participants"] == ["Me", "Jason Cummings"]
    assert sec.segments[-1].address == "el=6"


def test_adopt_flat_configurable_sender_field(tmp_path):
    root = _root(tmp_path)
    body = _FLAT_BODY.replace("sender:", "author:")
    build = recordbuild.begin_from_post(_post(body), root)
    conversation.adopt_flat(build, build.post, root, {"sender_field": "author"})
    post = recordbuild.finish(build)
    sec = segments.iter_blocks(post.content or "")[0]
    assert sec.extra["participants"] == ["Me", "Jason Cummings"]


def test_adopt_flat_raises_on_empty_content_zone(tmp_path):
    root = _root(tmp_path)
    post = _post("")
    build = recordbuild.begin_from_post(post, root)
    with pytest.raises(ValueError, match="nothing to adopt"):
        conversation.adopt_flat(build, post, root, {})


def test_adopt_flat_raises_on_already_sectioned_record(tmp_path):
    root = _root(tmp_path)
    already = """\
<!--section conversation
participants:
- Me
-->

<!--segment text/message
address: el=1
sender: Me
-->

hi
"""
    post = _post(already)
    build = recordbuild.begin_from_post(post, root)
    with pytest.raises(ValueError, match="already carries a form section"):
        conversation.adopt_flat(build, post, root, {})


def test_adopt_flat_registered_under_origin_id_wins_over_form_id():
    """The dispatch preference (`shape_record`: `get_shaper(origin_id) or
    get_shaper(form_id)`) is what lets a corpus-local `shapers/*.py` register `adopt_flat`
    under its own origin id (e.g. `imessage-export`) without colliding with the universal
    `conversation`-form-id-keyed mapping-driven shaper — this only checks the registry
    supports both keys existing simultaneously without `adopt_flat` being registered under
    `conversation` itself (that key belongs to the generic mapping-driven shaper)."""
    assert get_shaper("conversation") is not None
    assert get_shaper("conversation") is not conversation.adopt_flat
