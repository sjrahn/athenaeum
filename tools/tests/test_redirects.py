"""Redirect-following short-link resolution (`corpus.redirects`).

Pure units for the short-link heuristic + the redirect-chain walk. The network is mocked at
the `_one_hop` seam (the only function that touches urllib), so no real request is made — the
suite stays offline.
"""

from __future__ import annotations

from corpus import redirects

# ---------- is_probably_short_link ---------- #


def test_short_link_known_shortener_host():
    assert redirects.is_probably_short_link("https://bit.ly/abc")
    assert redirects.is_probably_short_link("https://t.co/XyZ")
    assert redirects.is_probably_short_link("https://youtu.be/dQw4w9WgXcQ")


def test_short_link_shortener_subdomain():
    # TikTok's short-link surfaces share the apex but live under vt./vm.
    assert redirects.is_probably_short_link("https://vt.tiktok.com/ZSQdnsm4M/")
    assert redirects.is_probably_short_link("https://vm.tiktok.com/ZSQdWDhqp/")


def test_short_link_single_opaque_path_segment():
    assert redirects.is_probably_short_link("https://example.test/Ab3Xy")  # short opaque token
    assert not redirects.is_probably_short_link("https://example.test/")  # bare host, no path
    assert not redirects.is_probably_short_link("https://example.test")  # no path at all


def test_short_link_rejects_content_shaped_urls():
    # A real canonical URL is never probed: multi-segment path, slug, or file extension.
    assert not redirects.is_probably_short_link(
        "https://www.tiktok.com/@user/video/7616385236439485709"
    )
    assert not redirects.is_probably_short_link("https://example.test/blog/some-post")
    assert not redirects.is_probably_short_link("https://example.test/page.html")
    assert not redirects.is_probably_short_link("https://example.test/this-is-a-long-opaque-token")


def test_short_link_handles_junk_gracefully():
    assert not redirects.is_probably_short_link("")
    assert not redirects.is_probably_short_link("not a url")
    assert not redirects.is_probably_short_link("mailto:x@y.test")


# ---------- resolve_final_url (network mocked at _one_hop) ---------- #


def _hop_chain(*locations):
    """Return a `_one_hop` stub that yields the given Location values in order, then None
    (terminal). A None in the list means that hop is terminal (no redirect)."""
    seq = list(locations)

    def stub(_opener, _url, *, timeout_s):
        return seq.pop(0) if seq else None

    return stub


def test_resolve_follows_redirect_chain(monkeypatch):
    monkeypatch.setattr(
        redirects,
        "_one_hop",
        _hop_chain(
            "https://www.tiktok.com/@user/video/7616385236439485709?_r=1&_t=abc",
            None,  # final URL is terminal
        ),
    )
    out = redirects.resolve_final_url("https://vt.tiktok.com/ZSQdnsm4M/")
    assert out == "https://www.tiktok.com/@user/video/7616385236439485709?_r=1&_t=abc"


def test_resolve_terminal_returns_input(monkeypatch):
    # No redirect (immediately terminal) → the URL is its own final form.
    monkeypatch.setattr(redirects, "_one_hop", _hop_chain(None))
    url = "https://www.tiktok.com/@user/video/123"
    assert redirects.resolve_final_url(url) == url


def test_resolve_relative_location(monkeypatch):
    monkeypatch.setattr(redirects, "_one_hop", _hop_chain("/final/path", None))
    out = redirects.resolve_final_url("https://h.test/short")
    assert out == "https://h.test/final/path"


def test_resolve_hop_cap(monkeypatch):
    # Every hop redirects to a NEW url — the walk must stop at max_hops, not loop forever.
    counter = {"n": 0}

    def stub(_opener, _url, *, timeout_s):
        counter["n"] += 1
        return f"https://h.test/hop{counter['n']}"

    monkeypatch.setattr(redirects, "_one_hop", stub)
    out = redirects.resolve_final_url("https://h.test/start", max_hops=3)
    # Capped: stops after max_hops without raising; result is the last hop reached.
    assert counter["n"] == 3
    assert out == "https://h.test/hop3"


def test_resolve_redirect_loop_returns_input(monkeypatch):
    # A 2-cycle loop is detected via the `seen` set and bails to the original URL.
    monkeypatch.setattr(
        redirects, "_one_hop", _hop_chain("https://h.test/b", "https://h.test/a")
    )
    assert redirects.resolve_final_url("https://h.test/a") == "https://h.test/a"


def test_resolve_non_web_location_ends_walk(monkeypatch):
    # A Location to a non-http scheme is not followed — the current URL is final.
    monkeypatch.setattr(redirects, "_one_hop", _hop_chain("ftp://h.test/file"))
    assert redirects.resolve_final_url("https://h.test/short") == "https://h.test/short"


def test_join_location_rejects_non_web():
    assert redirects._join_location("https://h.test/x", "mailto:a@b.test") == ""
    assert redirects._join_location("https://h.test/x", "/y") == "https://h.test/y"
