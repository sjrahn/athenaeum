"""The read surface — spec/athenaeum.md §5.1: two planes, public projection
fail-closed, owner plane token-gated, read-only, OpenAPI stamped with the
spec version. Self-skips without the `serve` extra installed."""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from ath.serve import SPEC_VERSION, create_app
from corpus import paths as corpus_paths
from corpus import records as corpus_records

H_PUB = "a" * 64       # public origin overlay
H_PUB2 = "d" * 64      # a second public record, cited but not evidenced
H_PRIV = "b" * 64      # no origin declares — falls to the instance's private floor

FACT_PUBLIC = "public-thing"
FACT_PRIVATE = "private-thing"
FACT_MIXED = "mixed-thing"
RETIRED_ID = "retired-thing"
INTERP_ID = "guess-1"

OPENQ_SKELETON = "# Open questions\n\n<!--worklist:begin-->\n<!--worklist:end-->\n"


def _mk_record(corpus_root: Path, h: str, *, public: bool) -> None:
    post = frontmatter.Post(
        content="body text",
        **corpus_records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0"),
    )
    corpus_records.set_artifact_block(post, mime="text/plain", fields={})
    if public:
        corpus_records.append_origin_block(
            post, uri="https://openhost.example/x", snapshot="2026-01-01T00:00:00Z",
            schema_id="openhost",
        )
    corpus_records.dump(post, corpus_paths.record_path(corpus_root, h))


def _write_fact(ledger_root: Path, fid: str, obj: dict) -> None:
    p = ledger_root / "facts" / "thing" / f"{fid}.json"
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


@pytest.fixture()
def instance(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "athenaeum.yaml").write_text(
        "name: testeum\nvisibility: private\n", encoding="utf-8"
    )

    corpus_root = root / "corpus"
    (corpus_root / "schema" / "origin").mkdir(parents=True)
    (corpus_root / "schema" / "origin" / "openhost.yaml").write_text(
        "tenancy: public\n", encoding="utf-8"
    )
    _mk_record(corpus_root, H_PUB, public=True)
    _mk_record(corpus_root, H_PUB2, public=True)
    _mk_record(corpus_root, H_PRIV, public=False)

    ledger_root = root / "ledger"
    (ledger_root / "facts" / "thing").mkdir(parents=True)
    (ledger_root / "interpretations").mkdir()
    (ledger_root / "open-questions.md").write_text(OPENQ_SKELETON, encoding="utf-8")
    (ledger_root / "schemas").mkdir()
    (ledger_root / "schemas" / "thing.yaml").write_text(
        "type: thing\ndescription: a test concept\nfields:\n"
        "  colour: { description: colour }\n  secret: { description: shh }\n",
        encoding="utf-8",
    )

    _write_fact(ledger_root, FACT_PUBLIC, {
        "id": FACT_PUBLIC, "type": "thing", "name": "Public Thing",
        "sources": {"s1": {"record": H_PUB}},
        "artifacts": [{"uri": f"corpus://{H_PUB}", "role": "documents"}],
        "claims": [{
            "id": f"{FACT_PUBLIC}:colour", "predicate": "colour", "value": "red",
            "status": "confirmed", "asof": "2026-01",
            "evidence": [{"source": "s1", "kind": "authoritative"}],
        }],
    })

    _write_fact(ledger_root, FACT_PRIVATE, {
        "id": FACT_PRIVATE, "type": "thing", "name": "Private Thing",
        "sources": {"s1": {"record": H_PRIV}},
        "claims": [{
            "id": f"{FACT_PRIVATE}:colour", "predicate": "colour", "value": "blue",
            "status": "confirmed", "asof": "2026-01",
            "evidence": [{"source": "s1", "kind": "authoritative"}],
        }],
    })

    _write_fact(ledger_root, FACT_MIXED, {
        "id": FACT_MIXED, "type": "thing", "name": "Mixed Thing",
        "sources": {
            "s1": {"record": H_PUB},
            "s2": {"record": H_PRIV},
            "s3": {"record": H_PUB2},   # public, but no claim evidences it — must be stripped
        },
        "artifacts": [
            {"uri": f"corpus://{H_PUB}", "role": "documents"},
            {"uri": f"corpus://{H_PRIV}", "role": "documents"},
        ],
        "claims": [
            {
                "id": f"{FACT_MIXED}:colour", "predicate": "colour", "value": "green",
                "status": "confirmed", "asof": "2026-01",
                "evidence": [{"source": "s1", "kind": "authoritative"}],
            },
            {
                "id": f"{FACT_MIXED}:secret", "predicate": "secret", "value": "shh",
                "status": "confirmed", "asof": "2026-01",
                "evidence": [{"source": "s2", "kind": "authoritative"}],
            },
        ],
    })

    (ledger_root / "facts" / "LINEAGE.json").write_text(
        json.dumps({RETIRED_ID: FACT_PUBLIC}), encoding="utf-8"
    )

    (ledger_root / "interpretations" / f"{INTERP_ID}.json").write_text(json.dumps({
        "id": INTERP_ID, "kind": "hypothesis", "status": "open",
        "statement": "a guess", "confidence": "plausible",
        "based_on": [f"{FACT_PUBLIC}:colour"],
    }), encoding="utf-8")

    return root


OWNER_TOKEN = "s3cr3t-owner-token"


def _client(instance: Path, *, owner_token: str | None = OWNER_TOKEN) -> TestClient:
    app = create_app(instance, owner_token)
    return TestClient(app)


def _owner_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {OWNER_TOKEN}"}


def _wrong_headers() -> dict[str, str]:
    return {"Authorization": "Bearer not-the-token"}


# ------------------------------------------------------------------- /instance


def test_instance_shape(instance: Path) -> None:
    client = _client(instance)
    r = client.get("/instance")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "testeum"
    assert body["spec_version"] == 30
    assert body["plane"] == "public"
    assert "instance_commit" in body


def test_instance_owner_plane(instance: Path) -> None:
    client = _client(instance)
    r = client.get("/instance", headers=_owner_headers())
    assert r.json()["plane"] == "owner"


def test_no_owner_token_configured_is_always_public(instance: Path) -> None:
    client = _client(instance, owner_token=None)
    r = client.get("/instance", headers=_owner_headers())
    assert r.json()["plane"] == "public"
    r = client.get("/interpretations", headers=_owner_headers())
    assert r.status_code == 404


# --------------------------------------------------------------- leak: facts


def test_fully_private_fact_404_on_public(instance: Path) -> None:
    client = _client(instance)
    assert client.get(f"/facts/{FACT_PRIVATE}").status_code == 404


def test_fully_private_fact_absent_from_listing(instance: Path) -> None:
    client = _client(instance)
    r = client.get("/facts")
    ids = {row["id"] for row in r.json()["facts"]}
    assert FACT_PRIVATE not in ids
    assert FACT_PUBLIC in ids
    assert FACT_MIXED in ids


def test_fully_private_fact_absent_from_scope(instance: Path) -> None:
    client = _client(instance)
    spec = json.dumps({"seed": {"type": "thing"}})
    r = client.get("/scope", params={"spec": spec})
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()["members"]}
    assert FACT_PRIVATE not in ids
    assert FACT_PUBLIC in ids


def test_fully_private_fact_present_on_owner_plane(instance: Path) -> None:
    client = _client(instance)
    r = client.get(f"/facts/{FACT_PRIVATE}", headers=_owner_headers())
    assert r.status_code == 200
    assert r.json()["id"] == FACT_PRIVATE

    r = client.get("/facts", headers=_owner_headers())
    ids = {row["id"] for row in r.json()["facts"]}
    assert FACT_PRIVATE in ids

    spec = json.dumps({"seed": {"type": "thing"}})
    r = client.get("/scope", params={"spec": spec}, headers=_owner_headers())
    ids = {m["id"] for m in r.json()["members"]}
    assert FACT_PRIVATE in ids


# --------------------------------------------------------------- leak: mixed


def test_mixed_fact_public_projection(instance: Path) -> None:
    client = _client(instance)
    r = client.get(f"/facts/{FACT_MIXED}")
    assert r.status_code == 200
    body = r.json()

    claim_ids = {c["id"] for c in body["claims"]}
    assert claim_ids == {f"{FACT_MIXED}:colour"}  # the private-backed :secret is stripped

    # the surviving claim's status/evidence ride along unchanged (§12: the
    # epistemic ladder survives into transport)
    colour = body["claims"][0]
    assert colour["status"] == "confirmed"
    assert colour["evidence"]

    # s2 (private) and s3 (public but unreferenced by any served claim) both
    # strip; only s1 (public, referenced) survives
    assert set(body["sources"]) == {"s1"}

    # roster: only the public-tenancy record survives
    roster_uris = {e["uri"] for e in body["artifacts"]}
    assert roster_uris == {f"corpus://{H_PUB}"}


def test_mixed_fact_full_on_owner_plane(instance: Path) -> None:
    client = _client(instance)
    r = client.get(f"/facts/{FACT_MIXED}", headers=_owner_headers())
    body = r.json()
    assert {c["id"] for c in body["claims"]} == {
        f"{FACT_MIXED}:colour", f"{FACT_MIXED}:secret",
    }
    assert set(body["sources"]) == {"s1", "s2", "s3"}
    assert len(body["artifacts"]) == 2


def test_mixed_fact_claim_endpoint_leak(instance: Path) -> None:
    client = _client(instance)
    r = client.get(f"/facts/{FACT_MIXED}/claims/colour")
    assert r.status_code == 200
    r = client.get(f"/facts/{FACT_MIXED}/claims/secret")
    assert r.status_code == 404
    r = client.get(f"/facts/{FACT_MIXED}/claims/secret", headers=_owner_headers())
    assert r.status_code == 200


# -------------------------------------------------------------- leak: records


def test_records_leak(instance: Path) -> None:
    client = _client(instance)
    assert client.get(f"/records/{H_PRIV}").status_code == 404
    assert client.get(f"/records/{H_PRIV}", headers=_owner_headers()).status_code == 200
    r = client.get(f"/records/{H_PUB}")
    assert r.status_code == 200
    assert r.json()["hash"] == H_PUB
    r = client.get(f"/records/{H_PUB}", headers=_owner_headers())
    assert r.status_code == 200


# ------------------------------------------------------- owner-only surfaces


@pytest.mark.parametrize("path", [
    "/interpretations",
    f"/interpretations/{INTERP_ID}",
    f"/facts/{FACT_PUBLIC}/demands",
    "/coverage",
    "/open-questions",
])
def test_owner_only_404_without_token(instance: Path, path: str) -> None:
    client = _client(instance)
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", [
    "/interpretations",
    f"/interpretations/{INTERP_ID}",
    f"/facts/{FACT_PUBLIC}/demands",
    "/coverage",
    "/open-questions",
])
def test_owner_only_404_with_wrong_token(instance: Path, path: str) -> None:
    client = _client(instance)
    assert client.get(path, headers=_wrong_headers()).status_code == 404


@pytest.mark.parametrize("path", [
    "/interpretations",
    f"/interpretations/{INTERP_ID}",
    f"/facts/{FACT_PUBLIC}/demands",
    "/coverage",
    "/open-questions",
])
def test_owner_only_200_with_owner_token(instance: Path, path: str) -> None:
    client = _client(instance)
    r = client.get(path, headers=_owner_headers())
    assert r.status_code == 200


def test_worklist_owner_only(instance: Path) -> None:
    client = _client(instance)
    assert client.get("/worklist", params={"ref": FACT_PUBLIC}).status_code == 404
    assert client.get(
        "/worklist", params={"ref": FACT_PUBLIC}, headers=_wrong_headers()
    ).status_code == 404
    r = client.get("/worklist", params={"ref": FACT_PUBLIC}, headers=_owner_headers())
    assert r.status_code == 200
    assert "dependents" in r.json()


def test_interpretations_never_leak_content(instance: Path) -> None:
    client = _client(instance)
    r = client.get("/interpretations", headers=_owner_headers())
    ids = {o["id"] for o in r.json()}
    assert INTERP_ID in ids


def test_coverage_and_open_questions_generated_shape(instance: Path) -> None:
    client = _client(instance)
    for path in ("/coverage", "/open-questions"):
        r = client.get(path, headers=_owner_headers())
        body = r.json()
        assert body["generated"] is True
        assert isinstance(body["markdown"], str)


# ------------------------------------------------------------ wrong-token public


def test_wrong_token_on_public_route_still_public_filtered(instance: Path) -> None:
    client = _client(instance)
    r = client.get(f"/facts/{FACT_MIXED}", headers=_wrong_headers())
    assert r.status_code == 200
    assert {c["id"] for c in r.json()["claims"]} == {f"{FACT_MIXED}:colour"}


# ----------------------------------------------------------- lineage / ETag


def test_lineage_redirect(instance: Path) -> None:
    client = _client(instance)
    r = client.get(f"/facts/{RETIRED_ID}", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == f"/facts/{FACT_PUBLIC}"


def test_etag_and_304(instance: Path) -> None:
    client = _client(instance)
    r = client.get(f"/facts/{FACT_PUBLIC}")
    assert r.status_code == 200
    etag = r.headers.get("etag")
    assert etag
    r2 = client.get(f"/facts/{FACT_PUBLIC}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_unknown_fact_404(instance: Path) -> None:
    client = _client(instance)
    assert client.get("/facts/no-such-fact").status_code == 404


# --------------------------------------------------------------- pagination


def test_facts_pagination(instance: Path) -> None:
    client = _client(instance)
    all_ids: list[str] = []
    after = None
    for _ in range(10):  # generous bound against an infinite loop on a bug
        params = {"limit": 1}
        if after is not None:
            params["after"] = after
        r = client.get("/facts", params=params, headers=_owner_headers())
        page = r.json()
        ids = [row["id"] for row in page["facts"]]
        assert len(ids) <= 1
        all_ids.extend(ids)
        after = page["next"]
        if after is None:
            break
    assert all_ids == sorted({FACT_PUBLIC, FACT_PRIVATE, FACT_MIXED})
    assert len(all_ids) == len(set(all_ids))  # no duplicates across pages


def test_facts_type_and_predicate_filters(instance: Path) -> None:
    client = _client(instance)
    r = client.get("/facts", params={"type": "thing"})
    assert {row["id"] for row in r.json()["facts"]} == {FACT_PUBLIC, FACT_MIXED}

    r = client.get("/facts", params={"predicate": "secret"})
    # the only claim under `secret` is private-backed — never surfaces the
    # fact via the predicate filter on the public plane
    assert r.json()["facts"] == []

    r = client.get("/facts", params={"predicate": "secret"}, headers=_owner_headers())
    assert {row["id"] for row in r.json()["facts"]} == {FACT_MIXED}


# ------------------------------------------------------------------ /scope


def test_scope_malformed_spec_422(instance: Path) -> None:
    client = _client(instance)
    r = client.get("/scope", params={"spec": "not json"})
    assert r.status_code == 422
    r = client.get("/scope", params={"spec": json.dumps({"seed": {}})})
    assert r.status_code == 422


def test_scope_evidence_filters_private_claims_within_public_fact(instance: Path) -> None:
    """A whole-fact filter is not enough: FACT_MIXED is a PUBLIC fact (it
    survives fact_is_public) that still carries a private-backed claim
    (:secret, evidenced by H_PRIV). The public-plane evidence expansion must
    drop that claim's URI while keeping the public claim's — never emit the
    private hash anywhere in the response, on this fact's list or anywhere
    else in the body (§12: "evidence that resolves only privately")."""
    client = _client(instance)
    spec = json.dumps({"seed": {"type": "thing"}, "evidence": "references"})

    r = client.get("/scope", params={"spec": spec})
    assert r.status_code == 200
    uris = r.json()["evidence"][FACT_MIXED]
    assert any(H_PUB in u for u in uris)
    assert not any(H_PRIV in u for u in uris)
    assert H_PRIV not in r.text  # belt and suspenders: nowhere in the body

    r_owner = client.get("/scope", params={"spec": spec}, headers=_owner_headers())
    owner_uris = r_owner.json()["evidence"][FACT_MIXED]
    assert any(H_PUB in u for u in owner_uris)
    assert any(H_PRIV in u for u in owner_uris)


def test_scope_roster_filters_private_entries_within_public_fact(instance: Path) -> None:
    """Same leak, roster side: FACT_MIXED rosters both H_PUB and H_PRIV."""
    client = _client(instance)
    spec = json.dumps({"seed": {"type": "thing"}, "follow": ["roster"]})

    r = client.get("/scope", params={"spec": spec})
    assert r.status_code == 200
    roster = r.json()["roster"][FACT_MIXED]
    assert f"corpus://{H_PUB}" in roster
    assert f"corpus://{H_PRIV}" not in roster
    assert H_PRIV not in r.text

    r_owner = client.get("/scope", params={"spec": spec}, headers=_owner_headers())
    owner_roster = r_owner.json()["roster"][FACT_MIXED]
    assert f"corpus://{H_PUB}" in owner_roster
    assert f"corpus://{H_PRIV}" in owner_roster


# ----------------------------------------------------------------- /schemas


def test_schemas_and_values(instance: Path) -> None:
    client = _client(instance)
    r = client.get("/schemas")
    assert "thing" in r.json()
    r = client.get("/schemas/thing")
    assert r.status_code == 200
    assert r.json()["type"] == "thing"
    r = client.get("/schemas/no-such-type")
    assert r.status_code == 404
    r = client.get("/schemas/values")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_vocab_generated_shape(instance: Path) -> None:
    client = _client(instance)
    r = client.get("/vocab")
    body = r.json()
    assert body["generated"] is True
    assert "thing" in body["markdown"]


# ---------------------------------------------------------------- OpenAPI


def test_openapi_stamped_with_spec_version(instance: Path) -> None:
    client = _client(instance)
    r = client.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    assert data["info"]["title"] == "Athenaeum read surface"
    assert data["info"]["version"] == str(SPEC_VERSION) == "30"


def test_openapi_is_read_only(instance: Path) -> None:
    """No non-GET method appears on any path — read-only is a checked
    property of the emitted contract, not just an intention (§5.1)."""
    client = _client(instance)
    data = client.get("/openapi.json").json()
    http_methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    for path, item in data["paths"].items():
        methods = set(item) & http_methods
        assert methods == {"get"}, f"{path} declares non-GET method(s): {methods - {'get'}}"


def test_binary_instance_no_audiences_unaffected(instance: Path) -> None:
    """A binary instance (no `tenancy:` block), `create_app` called exactly
    as pre-v30 — positional owner_token only, no audience_tokens — reads
    identically: public plane by default, owner plane on the owner token,
    unknown bearer stays public (§5.1: "the planes are the grant sets" —
    the binary instance's only grant sets are public and everything)."""
    app = create_app(instance, OWNER_TOKEN)
    client = TestClient(app)
    assert client.get("/instance").json()["plane"] == "public"
    assert client.get("/instance", headers=_owner_headers()).json()["plane"] == "owner"
    assert client.get("/instance", headers=_wrong_headers()).json()["plane"] == "public"


def test_create_app_undeclared_audience_raises(instance: Path) -> None:
    with pytest.raises(ValueError, match="undeclared"):
        create_app(instance, OWNER_TOKEN, audience_tokens={"family": "tok"})


# =============================================================== audience planes
#
# "The planes are the grant sets" (spec/athenaeum.md §5.1): a second instance
# fixture declaring one audience (`family`) beside the reserved public/private
# tiers, with a family-tier record + claim beside public and private ones —
# the tenancy tests the binary `instance` fixture above cannot exercise.

FAM_H_PUB = "e" * 64    # public origin overlay
FAM_H_PRIV = "f" * 64   # no origin declares — falls to the instance's private floor
FAM_H_FAM = "c" * 64    # family-tier origin overlay

FAM_FACT_PUBLIC = "fam-public-thing"
FAM_FACT_PRIVATE = "fam-private-thing"
FAM_FACT_FAMILY = "fam-family-thing"   # fully family-tier: sole claim backed by FAM_H_FAM
FAM_FACT_MIXED = "fam-mixed-thing"     # a public claim beside a family-tier claim

FAMILY_TOKEN = "s3cr3t-family-token"


def _mk_tiered_record(corpus_root: Path, h: str, *, tier: str | None) -> None:
    """A record whose origin overlay declares `tenancy: {tier}` (registered
    at `schema/origin/{tier}host.yaml`, mirroring `_mk_record`'s "openhost").
    `tier=None` means no origin declares — falls to the instance's
    `visibility:` floor, same as `_mk_record(..., public=False)`."""
    post = frontmatter.Post(
        content="body text",
        **corpus_records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0"),
    )
    corpus_records.set_artifact_block(post, mime="text/plain", fields={})
    if tier is not None:
        corpus_records.append_origin_block(
            post, uri=f"https://{tier}host.example/x", snapshot="2026-01-01T00:00:00Z",
            schema_id=f"{tier}host",
        )
    corpus_records.dump(post, corpus_paths.record_path(corpus_root, h))


@pytest.fixture()
def tenant_instance(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "athenaeum.yaml").write_text(
        "name: tenanteum\nvisibility: private\n"
        "tenancy:\n  tiers: [family]\n  audiences:\n    family: [family]\n",
        encoding="utf-8",
    )

    corpus_root = root / "corpus"
    (corpus_root / "schema" / "origin").mkdir(parents=True)
    (corpus_root / "schema" / "origin" / "openhost.yaml").write_text(
        "tenancy: public\n", encoding="utf-8"
    )
    (corpus_root / "schema" / "origin" / "familyhost.yaml").write_text(
        "tenancy: family\n", encoding="utf-8"
    )
    _mk_record(corpus_root, FAM_H_PUB, public=True)
    _mk_record(corpus_root, FAM_H_PRIV, public=False)
    _mk_tiered_record(corpus_root, FAM_H_FAM, tier="family")

    ledger_root = root / "ledger"
    (ledger_root / "facts" / "thing").mkdir(parents=True)
    (ledger_root / "interpretations").mkdir()
    (ledger_root / "open-questions.md").write_text(OPENQ_SKELETON, encoding="utf-8")
    (ledger_root / "schemas").mkdir()
    (ledger_root / "schemas" / "thing.yaml").write_text(
        "type: thing\ndescription: a test concept\nfields:\n"
        "  colour: { description: colour }\n  kin: { description: family-only }\n",
        encoding="utf-8",
    )

    _write_fact(ledger_root, FAM_FACT_PUBLIC, {
        "id": FAM_FACT_PUBLIC, "type": "thing", "name": "Family Public Thing",
        "sources": {"s1": {"record": FAM_H_PUB}},
        "claims": [{
            "id": f"{FAM_FACT_PUBLIC}:colour", "predicate": "colour", "value": "red",
            "status": "confirmed", "asof": "2026-01",
            "evidence": [{"source": "s1", "kind": "authoritative"}],
        }],
    })

    _write_fact(ledger_root, FAM_FACT_PRIVATE, {
        "id": FAM_FACT_PRIVATE, "type": "thing", "name": "Family Private Thing",
        "sources": {"s1": {"record": FAM_H_PRIV}},
        "claims": [{
            "id": f"{FAM_FACT_PRIVATE}:colour", "predicate": "colour", "value": "blue",
            "status": "confirmed", "asof": "2026-01",
            "evidence": [{"source": "s1", "kind": "authoritative"}],
        }],
    })

    _write_fact(ledger_root, FAM_FACT_FAMILY, {
        "id": FAM_FACT_FAMILY, "type": "thing", "name": "Family Only Thing",
        "sources": {"s1": {"record": FAM_H_FAM}},
        "artifacts": [{"uri": f"corpus://{FAM_H_FAM}", "role": "documents"}],
        "claims": [{
            "id": f"{FAM_FACT_FAMILY}:kin", "predicate": "kin", "value": "aunt",
            "status": "confirmed", "asof": "2026-01",
            "evidence": [{"source": "s1", "kind": "authoritative"}],
        }],
    })

    _write_fact(ledger_root, FAM_FACT_MIXED, {
        "id": FAM_FACT_MIXED, "type": "thing", "name": "Family Mixed Thing",
        "sources": {"s1": {"record": FAM_H_PUB}, "s2": {"record": FAM_H_FAM}},
        "artifacts": [
            {"uri": f"corpus://{FAM_H_PUB}", "role": "documents"},
            {"uri": f"corpus://{FAM_H_FAM}", "role": "documents"},
        ],
        "claims": [
            {
                "id": f"{FAM_FACT_MIXED}:colour", "predicate": "colour", "value": "green",
                "status": "confirmed", "asof": "2026-01",
                "evidence": [{"source": "s1", "kind": "authoritative"}],
            },
            {
                "id": f"{FAM_FACT_MIXED}:kin", "predicate": "kin", "value": "cousin",
                "status": "confirmed", "asof": "2026-01",
                "evidence": [{"source": "s2", "kind": "authoritative"}],
            },
        ],
    })

    return root


def _tenant_client(
    root: Path, *, owner_token: str | None = OWNER_TOKEN,
    audience_tokens: dict[str, str] | None = None,
) -> TestClient:
    tokens = audience_tokens if audience_tokens is not None else {"family": FAMILY_TOKEN}
    app = create_app(root, owner_token, audience_tokens=tokens)
    return TestClient(app)


def _family_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {FAMILY_TOKEN}"}


def test_create_app_undeclared_audience_lists_declared(tenant_instance: Path) -> None:
    with pytest.raises(ValueError) as exc:
        create_app(tenant_instance, OWNER_TOKEN, audience_tokens={"accountant": "tok"})
    assert "accountant" in str(exc.value)
    assert "family" in str(exc.value)


def test_instance_plane_names_audience(tenant_instance: Path) -> None:
    client = _tenant_client(tenant_instance)
    assert client.get("/instance", headers=_family_headers()).json()["plane"] == "family"


def test_unknown_token_is_public_plane(tenant_instance: Path) -> None:
    client = _tenant_client(tenant_instance)
    r = client.get("/instance", headers={"Authorization": "Bearer totally-unknown"})
    assert r.json()["plane"] == "public"


def test_family_claim_visible_on_family_plane_not_public(tenant_instance: Path) -> None:
    client = _tenant_client(tenant_instance)

    r = client.get(f"/facts/{FAM_FACT_MIXED}")
    assert r.status_code == 200
    assert {c["id"] for c in r.json()["claims"]} == {f"{FAM_FACT_MIXED}:colour"}

    r = client.get(f"/facts/{FAM_FACT_MIXED}", headers=_family_headers())
    assert r.status_code == 200
    assert {c["id"] for c in r.json()["claims"]} == {
        f"{FAM_FACT_MIXED}:colour", f"{FAM_FACT_MIXED}:kin",
    }

    r = client.get(f"/facts/{FAM_FACT_MIXED}", headers=_owner_headers())
    assert {c["id"] for c in r.json()["claims"]} == {
        f"{FAM_FACT_MIXED}:colour", f"{FAM_FACT_MIXED}:kin",
    }


def test_family_only_fact_absent_from_public_list_present_on_family(
    tenant_instance: Path,
) -> None:
    client = _tenant_client(tenant_instance)

    r = client.get("/facts")
    assert FAM_FACT_FAMILY not in {row["id"] for row in r.json()["facts"]}
    assert client.get(f"/facts/{FAM_FACT_FAMILY}").status_code == 404

    r = client.get("/facts", headers=_family_headers())
    assert FAM_FACT_FAMILY in {row["id"] for row in r.json()["facts"]}
    r = client.get(f"/facts/{FAM_FACT_FAMILY}", headers=_family_headers())
    assert r.status_code == 200
    assert r.json()["id"] == FAM_FACT_FAMILY


def test_private_fact_absent_on_every_audience_plane(tenant_instance: Path) -> None:
    client = _tenant_client(tenant_instance)
    assert client.get(f"/facts/{FAM_FACT_PRIVATE}").status_code == 404
    assert client.get(f"/facts/{FAM_FACT_PRIVATE}", headers=_family_headers()).status_code == 404
    r = client.get(f"/facts/{FAM_FACT_PRIVATE}", headers=_owner_headers())
    assert r.status_code == 200
    assert r.json()["id"] == FAM_FACT_PRIVATE


def test_records_family_tier_visible_on_family_plane_only(tenant_instance: Path) -> None:
    client = _tenant_client(tenant_instance)
    assert client.get(f"/records/{FAM_H_FAM}").status_code == 404
    r = client.get(f"/records/{FAM_H_FAM}", headers=_family_headers())
    assert r.status_code == 200
    assert r.json()["hash"] == FAM_H_FAM
    r = client.get(f"/records/{FAM_H_FAM}", headers=_owner_headers())
    assert r.status_code == 200


@pytest.mark.parametrize("path", [
    "/interpretations",
    f"/facts/{FAM_FACT_PUBLIC}/demands",
    "/coverage",
    "/open-questions",
])
def test_owner_only_404_with_audience_token(tenant_instance: Path, path: str) -> None:
    client = _tenant_client(tenant_instance)
    assert client.get(path, headers=_family_headers()).status_code == 404


def test_worklist_404_with_audience_token(tenant_instance: Path) -> None:
    client = _tenant_client(tenant_instance)
    r = client.get("/worklist", params={"ref": FAM_FACT_PUBLIC}, headers=_family_headers())
    assert r.status_code == 404


def test_scope_family_evidence_filters_across_planes(tenant_instance: Path) -> None:
    """Same leak shape as `test_scope_evidence_filters_private_claims_within_public_fact`,
    generalized to a grant set: FAM_FACT_MIXED is visible on both the public
    and family planes, but the family-tier claim's evidence must surface only
    on the family plane."""
    client = _tenant_client(tenant_instance)
    spec = json.dumps({"seed": {"type": "thing"}, "evidence": "references"})

    r = client.get("/scope", params={"spec": spec})
    assert r.status_code == 200
    uris = r.json()["evidence"][FAM_FACT_MIXED]
    assert any(FAM_H_PUB in u for u in uris)
    assert not any(FAM_H_FAM in u for u in uris)
    assert FAM_H_FAM not in r.text

    r_fam = client.get("/scope", params={"spec": spec}, headers=_family_headers())
    fam_uris = r_fam.json()["evidence"][FAM_FACT_MIXED]
    assert any(FAM_H_PUB in u for u in fam_uris)
    assert any(FAM_H_FAM in u for u in fam_uris)


def test_scope_family_roster_filters_across_planes(tenant_instance: Path) -> None:
    client = _tenant_client(tenant_instance)
    spec = json.dumps({"seed": {"type": "thing"}, "follow": ["roster"]})

    r = client.get("/scope", params={"spec": spec})
    assert r.status_code == 200
    roster = r.json()["roster"][FAM_FACT_MIXED]
    assert f"corpus://{FAM_H_PUB}" in roster
    assert f"corpus://{FAM_H_FAM}" not in roster
    assert FAM_H_FAM not in r.text

    r_fam = client.get("/scope", params={"spec": spec}, headers=_family_headers())
    fam_roster = r_fam.json()["roster"][FAM_FACT_MIXED]
    assert f"corpus://{FAM_H_PUB}" in fam_roster
    assert f"corpus://{FAM_H_FAM}" in fam_roster


def test_etag_differs_across_planes(tenant_instance: Path) -> None:
    client = _tenant_client(tenant_instance)
    r_pub = client.get(f"/facts/{FAM_FACT_MIXED}")
    r_fam = client.get(f"/facts/{FAM_FACT_MIXED}", headers=_family_headers())
    r_own = client.get(f"/facts/{FAM_FACT_MIXED}", headers=_owner_headers())
    etags = {r_pub.headers["etag"], r_fam.headers["etag"], r_own.headers["etag"]}
    assert len(etags) == 3
