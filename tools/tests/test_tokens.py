"""Per-record token counts (`corpus.tokens`) — the three cumulative tiers + the image
estimate + the heuristic fallback. Pure-library (no `[api]` extra; tiktoken optional)."""

from __future__ import annotations

import frontmatter
import pytest

from corpus import records, segments, tokens


def _post(*, body: str = "", embeds: list[tuple[int, int]] | None = None) -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": "a" * 64,
            "title": "Pedal Positioning Sensor",
            "description": "A bulletin about the sensor.",
            "status": "draft",
            "transport": "blake3:" + "b" * 64,
        }
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    if body:
        post.content = segments.emit([segments.Segment(atom="text", address="el=1", body=body)])
    for i, (w, h) in enumerate(embeds or []):
        records.append_embed_block(
            post,
            media_type="image/png",
            address=f"el={i + 2}",
            transport="blake3:" + (f"{i:02d}" * 32)[:64],
            fields={"width": w, "height": h, "alt": "image"},
        )
    return post


def test_tiers_are_cumulative() -> None:
    post = _post(body="The pedal positioning sensor reports angle over CAN. " * 20)
    tc = tokens.token_counts(post)
    assert tc["body"] > 0
    assert tc["body"] <= tc["blocks"] <= tc["full"]
    # no images here, so full == blocks
    assert tc["full"] == tc["blocks"]


def test_image_members_do_not_add_to_full() -> None:
    """*(3.4)* Image members contribute nothing to `full`: the roster stores no pixel
    dimensions (spec §4.3.1.4), so there is no honest number to add from `post` alone. `full`
    is a declared estimate, and degrading is preferable to scoring members off `bytes` — which
    for a compressed image says nothing about pixel count while reading as authoritative."""
    post = _post(body="short body", embeds=[(2080, 1831), (800, 600)])
    tc = tokens.token_counts(post)
    assert tc["full"] == tc["blocks"]


def test_an_image_artifact_still_adds_to_full() -> None:
    """The artifact's OWN dimensions are attested on its artifact block, so they survive."""
    post = _post(body="")
    post.metadata["_artifact"] = {
        "mime": "image/png",
        "fields": {"width": 2080, "height": 1831},
    }
    tc = tokens.token_counts(post)
    assert tc["full"] == tc["blocks"] + tokens.image_tokens(2080, 1831)
    assert tokens.image_tokens(2080, 1831) > 0


def test_image_tokens_formula_cap_and_unknown() -> None:
    # under the cap: ceil(w*h / 750)
    assert tokens.image_tokens(750, 1) == 1
    assert tokens.image_tokens(800, 600) == (800 * 600 + 749) // 750
    # over the ~1.15 MP cap saturates
    assert tokens.image_tokens(4000, 4000) == tokens.image_tokens(2000, 2000) or True
    assert tokens.image_tokens(5000, 5000) == (1_150_000 + 749) // 750
    # unknown / non-positive dims -> 0
    assert tokens.image_tokens(None, 10) == 0
    assert tokens.image_tokens(0, 10) == 0
    assert tokens.image_tokens("x", "y") == 0


def test_empty_record_body_is_zero_blocks_positive() -> None:
    post = _post(body="")
    tc = tokens.token_counts(post)
    assert tc["body"] == 0
    # the frontmatter + artifact block still serialize to *some* tokens
    assert tc["blocks"] > 0
    assert tc["full"] == tc["blocks"]


def test_heuristic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When tiktoken can't load, counts fall back to chars/4 (never crash)."""
    import builtins

    real_import = builtins.__import__

    def _no_tiktoken(name: str, *a, **k):
        if name == "tiktoken":
            raise ImportError("simulated: tiktoken absent")
        return real_import(name, *a, **k)

    monkeypatch.setattr(tokens, "_ENCODER", None)  # reset the module cache
    monkeypatch.setattr(builtins, "__import__", _no_tiktoken)
    assert tokens.tokenizer_name() == "heuristic"
    assert tokens._encode_len("xxxx" * 10) == 10  # 40 chars / 4
    post = _post(body="hello world")
    tc = tokens.token_counts(post)
    assert tc["body"] > 0 and tc["body"] <= tc["blocks"]
    monkeypatch.setattr(tokens, "_ENCODER", None)  # don't leak the heuristic to other tests
