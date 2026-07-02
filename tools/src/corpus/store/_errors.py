"""Shared classification of remote object-store errors.

Kept dependency-free (no boto3 / azure imports) so the logic is unit-testable with the
base install — the cloud adapters are opt-in extras that may not be present in CI.

Backends surface errors differently (botocore's `e.response["Error"]["Code"]` vs azure's
exception type name + message), so callers pass whatever code/identifier string they have;
the classifier matches known tokens as substrings to absorb both shapes (e.g. botocore
`"NoSuchKey"` and azure `"ResourceNotFoundError"` both classify as `missing`).
"""

from __future__ import annotations

# Object genuinely absent.
_MISSING_TOKENS = ("404", "NoSuchKey", "NotFound")
# Access denied — under a restrictive IAM/ACL (e.g. no s3:ListBucket) S3 returns 403 for a
# *missing* key rather than 404, so a denial is ambiguous between "absent" and "no perms".
_DENIED_TOKENS = ("403", "AccessDenied", "Forbidden")


def classify_remote_error(code: str) -> str:
    """Map a backend error code/identifier to `missing` | `denied` | `operational`.

    - `missing` — object absent; surface as `ArtifactMissing`.
    - `denied` — access denied; ambiguous (often a missing object under restrictive IAM),
      so surface as `ArtifactMissing` with an operator-actionable hint rather than a raw
      SDK error.
    - `operational` — transient/network/throttle/auth; swallow to "remote unknown" for a
      presence check, re-raise for a hard fetch.
    """
    c = code or ""
    if any(tok in c for tok in _MISSING_TOKENS):
        return "missing"
    if any(tok in c for tok in _DENIED_TOKENS):
        return "denied"
    return "operational"
