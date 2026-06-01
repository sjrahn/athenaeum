"""Static signature catalogs + thresholds for capture/ingest/drafter quality
detectors.

Each catalog is a tuple of `(name, regex)` or `(name, title_regex, body_regex)`
entries. All regexes are pre-compiled, case-insensitive. Catalogs are kept
NARROW — we'd rather miss a real issue than misflag a legitimate page whose
text happens to contain a signature word.

Detector functions live with the code that runs them (`corpus.capture`,
the drafters); this module is signatures only. These are domain-neutral
web-quality patterns — nothing here is corpus-specific.
"""

from __future__ import annotations

import re
from typing import Final

# ---------- HTTP-error-with-200-body ---------- #
#
# Server returned status 200 but the body matches a known error-template
# signature. Each entry is (name, body_regex). Body match alone is enough;
# many servers also serve the error template at status 200 (a common Apache
# ErrorDocument misconfiguration is exactly this — error page with HTTP 200).

HTTP_ERROR_BODY_SIGNATURES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "apache-errordocument",
        re.compile(
            r"<title>\s*\d{3}\s+(?:not\s+found|forbidden|internal\s+server\s+error)\s*</title>"
            r".*?(?:was\s+not\s+found\s+on\s+this\s+server|ErrorDocument)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "nginx-default-error",
        re.compile(
            r"<title>\s*\d{3}\s+(?:not\s+found|forbidden|bad\s+gateway|service\s+unavailable)\s*</title>"
            r".*?<center>\s*<h1>\s*\d{3}",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "iis-default-error",
        re.compile(
            r"<title>IIS\s+Windows\s+Server</title>",
            re.IGNORECASE,
        ),
    ),
    (
        "wikimedia-error",
        re.compile(
            r"<title>\s*Wikimedia\s+Error\s*</title>",
            re.IGNORECASE,
        ),
    ),
    (
        "generic-page-not-found",
        # Conservative: title says some flavor of "not found" / "404" AND
        # body is small enough that there's no real article content.
        re.compile(
            r"<title>[^<]*?(?:page\s+not\s+found|404\s*[-:|]|404\s+error|"
            r"oops!?\s*page\s+not\s+found|not\s+found\s*[-:|])[^<]*?</title>",
            re.IGNORECASE,
        ),
    ),
)

# ---------- Final-URL drift ---------- #
#
# After navigation, page.url settles at a path/host that suggests the request
# didn't reach the intended content. Two checks: (a) path drift to known
# landing/error patterns; (b) hostname change (cross-domain redirect — caller
# compares host separately).

REDIRECT_DRIFT_PATH_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("root-redirect", re.compile(r"^/?$")),
    ("login-redirect", re.compile(r"^/?(?:login|sign[-_]?in|auth|account/login)/?$", re.IGNORECASE)),
    ("subscribe-redirect", re.compile(r"^/?subscribe/?$", re.IGNORECASE)),
    ("cookie-wall", re.compile(r"^/?(?:cookies?|consent|gdpr|privacy/consent)/?$", re.IGNORECASE)),
    ("error-redirect", re.compile(r"^/?(?:404|500|error|not[-_]?found|page[-_]?not[-_]?found)/?$", re.IGNORECASE)),
    ("captcha-redirect", re.compile(r"^/?(?:captcha|challenge|verify)/?$", re.IGNORECASE)),
)

# ---------- Login-wall ---------- #
#
# Page served a login wall instead of the requested content. Distinct from
# paywall: login means "create or use an account"; paywall means "pay".
# Catch via title or visible-text signature; keep narrow.

LOGIN_WALL_SIGNATURES: Final[tuple[tuple[tuple[str, re.Pattern[str]], re.Pattern[str] | None], ...]] = (
    (
        # End-anchored (GENERIC_TITLE convention): the WHOLE title must be the login
        # phrase, so a real article like "Sign in sheets for events: a guide" doesn't match.
        ("login-required-title", re.compile(r"^\s*(?:sign\s*in|log\s*in|login\s+required)\s*[-:|]?\s*$", re.IGNORECASE)),
        None,
    ),
    (
        ("create-account-body", re.compile(r".", re.DOTALL)),
        re.compile(r"sign\s*in\s+to\s+(?:read|continue|view|access)|please\s+(?:log|sign)\s*in\s+to", re.IGNORECASE),
    ),
)

# ---------- Paywall ---------- #
#
# Article served behind a "subscribe" wall. The visible text usually
# contains a subscribe CTA + truncation language. Conservative — many
# articles legitimately mention subscriptions in passing.

# Each entry: (name, title_re, body_re, severity). Prose CTAs are strong evidence of a
# real wall (`warning`); the raw-HTML class marker alone is weak (a free article may ship a
# hidden `paywall-banner` element), so it's downgraded to `info` — a hint to review, not a
# fidelity warning.
PAYWALL_SIGNATURES: Final[tuple[tuple[str, re.Pattern[str], re.Pattern[str], str], ...]] = (
    (
        "subscribe-to-continue",
        re.compile(r".", re.DOTALL),
        re.compile(
            r"subscribe\s+to\s+(?:read|continue|unlock|access|view)|"
            r"unlock\s+this\s+article|"
            r"to\s+continue\s+reading,?\s+(?:please\s+)?subscribe|"
            r"this\s+(?:story|article)\s+is\s+for\s+subscribers",
            re.IGNORECASE,
        ),
        "warning",
    ),
    (
        "paywall-marker",
        re.compile(r".", re.DOTALL),
        # Sites often expose data-paywall / class="paywall*" hooks — but these can ship on
        # free pages too, so the marker alone is informational, not a warning.
        re.compile(
            r'data-paywall|class="[^"]*\bpaywall\b|id="paywall',
            re.IGNORECASE,
        ),
        "info",
    ),
)

# ---------- Captcha ---------- #
#
# Page is a captcha / human-verification challenge. Cloudflare's "Just a
# moment" is bot-block territory (handled separately). hCaptcha/reCAPTCHA
# script presence is a strong tell.

CAPTCHA_SIGNATURES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "hcaptcha",
        re.compile(r"hcaptcha\.com/[0-9]?/api\.js|h-captcha\b", re.IGNORECASE),
    ),
    (
        "recaptcha",
        re.compile(
            r"google\.com/recaptcha/(?:api\.js|enterprise\.js)|g-recaptcha\b",
            re.IGNORECASE,
        ),
    ),
    (
        "verify-you-are-human",
        re.compile(
            r"verify\s+(?:you\s+are|that\s+you(?:'?re|\s+are))\s+(?:human|not\s+a\s+robot)|"
            r"please\s+(?:complete|solve)\s+the\s+(?:captcha|challenge)",
            re.IGNORECASE,
        ),
    ),
    (
        "image-challenge",
        re.compile(r"select\s+all\s+(?:images?|squares?)\s+(?:with|containing)", re.IGNORECASE),
    ),
)

# ---------- Generic title ---------- #
#
# Title is a placeholder, loading state, or empty — capture didn't reach a
# real page. Anchored: pattern must be the whole title (after strip), not a
# substring (otherwise "Loading capacity" or "Just a moment in time" would
# false-match).

GENERIC_TITLE_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("empty-title", re.compile(r"^\s*$")),
    ("just-a-moment", re.compile(r"^\s*just\s+a\s+moment\.{0,3}\s*$", re.IGNORECASE)),
    ("loading", re.compile(r"^\s*loading\.{0,3}\s*$", re.IGNORECASE)),
    ("please-wait", re.compile(r"^\s*please\s+wait\.{0,3}\s*$", re.IGNORECASE)),
    ("untitled", re.compile(r"^\s*untitled(?:\s+document)?\s*$", re.IGNORECASE)),
    ("plain-404", re.compile(r"^\s*404(?:\s+(?:not\s+found|error))?\s*$", re.IGNORECASE)),
    ("plain-error", re.compile(r"^\s*(?:error|server\s+error|access\s+denied)\s*$", re.IGNORECASE)),
)

# ---------- Mojibake (UTF-8 misdecode signatures) ---------- #
#
# Classic mojibake patterns from UTF-8 bytes interpreted as Latin-1 / cp1252.
# Each signature is a short byte-pair string that almost never appears in
# legitimate text but is common in misdecoded copy (e.g. é → Ã©, ' → â€™).

MOJIBAKE_SIGNATURES: Final[tuple[str, ...]] = (
    "Ã©",   # é
    "Ã¨",   # è
    "Ã¢",   # â
    "Ã®",   # î
    "Ã´",   # ô
    "Ã»",   # û
    "Ã§",   # ç
    "Ã¤",   # ä
    "Ã¶",   # ö
    "Ã¼",   # ü
    "Ã±",   # ñ
    "â€™",  # ’ (right single quote)
    "â€œ",  # “ (left double quote)
    "â€\x9d",  # ” (right double quote)
    "â€“",  # – (en dash)
    "â€”",  # — (em dash)
    "â€¦",  # … (ellipsis)
    "â‚¬",  # € (euro sign)
    "Â",    # leading byte common in misdecoded NBSP / superscripts
)

# ---------- Tiny-artifact thresholds (bytes) ---------- #
#
# Per-MIME minimum reasonable sizes. Below this, the artifact is almost
# certainly an error page, an empty stub, or a truncated capture. Keys
# can be exact MIME types or type families (e.g. "image/").

TINY_ARTIFACT_THRESHOLDS: Final[dict[str, int]] = {
    "text/html":              5 * 1024,    # 5 KB
    "application/xhtml+xml":  5 * 1024,
    "application/pdf":        10 * 1024,   # 10 KB — even a 1-page PDF is bigger
    "application/json":       64,          # 64 bytes — `{}` is fine, `null` is fine
    "application/x-ndjson":   64,
    "text/markdown":          64,
    "text/plain":             64,
    # Type-family fallbacks (lookup tries exact first, then prefix match).
    "image/":                 256,         # tiny pixel-tracker / favicon territory
    "audio/":                 4 * 1024,
    "video/":                 100 * 1024,  # 100 KB — anything smaller is a stub
    "application/":           512,
}


def threshold_for(media_type: str) -> int | None:
    """Look up the tiny-artifact threshold for a MIME type.

    Tries the exact MIME first; falls back to the `type/` family prefix;
    returns None when neither matches (in which case the detector should
    not fire — we don't have an opinion).
    """
    if media_type in TINY_ARTIFACT_THRESHOLDS:
        return TINY_ARTIFACT_THRESHOLDS[media_type]
    family = media_type.split("/", 1)[0] + "/"
    return TINY_ARTIFACT_THRESHOLDS.get(family)
