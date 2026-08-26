#!/usr/bin/env python3
"""Seed testdata/instance from testdata/exemplars.yaml (see testdata/README.md).

For each manifest entry, locates the artifact bytes in a source instance,
copies them into testdata/instance/corpus/capture/, and ingests them via the
`corpus` CLI. Idempotent: an entry whose record already exists in the test
instance is skipped.

A `source: promoted` entry (see the manifest header comment) names a
`container` blake3 + member `address` instead: the container is ingested
first (also idempotent, and not itself a manifest entry), then `corpus
promote corpus://<container>?<address>` re-mints the same content-addressed
leaf record inside the test instance.

A `source: synthetic` entry names a `file:` (relative to testdata/) whose
bytes are committed straight into this repo under testdata/synthetic/ — no
source instance involved. It's staged and ingested exactly like a `direct`
entry, just with the bytes coming from testdata/ instead of `--from`.

After the manifest is seeded, `seed_v39_ontology_exemplars` (below) also
seeds the v39 ontology layer's exemplars (spec/ledger.md §15) straight into
the test instance's ledger — this library is otherwise strictly
mime-record-shaped (exemplars.yaml has no ledger-fact axis at all), so
there is no manifest entry for it. Entirely synthetic (a fictional TV
franchise, hand-authored evidence record) — no dependency on --from, no
real bytes, safe to commit its provenance here even though the exemplars
themselves land only in the gitignored `instance/`.

Plain stdlib only — no PyYAML, no `corpus`-package imports. Talks to the
`corpus`/`ath` CLIs as a subprocess, exactly as a human operator would.

Usage:
    uv run --no-sync python testdata/seed.py [--from SOURCE_INSTANCE_ROOT]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTANCE_ROOT = HERE / "instance"
MANIFEST_PATH = HERE / "exemplars.yaml"


# --- a tiny, format-specific manifest parser (stdlib only; not general YAML) ---
#
# exemplars.yaml is hand-authored to a fixed shape: a top-level list of
# mappings ("- key: value" at 2-space indent, continuation keys at 2-space
# indent, one optional nested "via:" mapping with children at 4-space
# indent). That fixed shape is all this parses — it is not a YAML parser.
def parse_manifest(path: Path) -> list[dict]:
    entries: list[dict] = []
    current: dict | None = None
    nested_key: str | None = None

    for raw_line in path.read_text().splitlines():
        line = raw_line.split(" #", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        m = re.match(r"^- (\w+): (.+)$", line)
        if m:
            if current is not None:
                entries.append(current)
            current = {m.group(1): m.group(2).strip()}
            nested_key = None
            continue

        if current is None:
            continue

        m = re.match(r"^  (\w+): ?(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if value:
                current[key] = value
                nested_key = None
            else:
                current[key] = {}
                nested_key = key
            continue

        m = re.match(r"^    (\w+): (.+)$", line)
        if m and nested_key:
            current[nested_key][m.group(1)] = m.group(2).strip()
            continue

    if current is not None:
        entries.append(current)
    return entries


def find_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        sys.exit(
            f"'{name}' not found on PATH — run `uv tool install --editable tools/` "
            f"from the distribution root first."
        )
    return path


def locate_source_bytes(source_root: Path, blake3: str, corpus_bin: str) -> Path | None:
    """The artifact bytes for `blake3` in the source instance, or None.

    Tries the co-located store directly first (fast, no subprocess — covers
    every exemplar this manifest names); falls back to `corpus locate --json`
    (spec §12.1.1) to also cover a store-location or attached-location
    residency, in case a future entry needs it.
    """
    shard = blake3[:2]
    matches = glob.glob(str(source_root / "corpus" / "artifacts" / shard / f"{blake3}.*"))
    if matches:
        return Path(matches[0])

    try:
        out = subprocess.run(
            [corpus_bin, "locate", blake3, "--json", "--corpus-root", str(source_root / "corpus")],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError:
        return None
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    artifact = data.get("artifact")
    if artifact and artifact.get("path"):
        return source_root / artifact["path"]
    for att in data.get("attached") or []:
        if att.get("path"):
            return Path(att["path"])
    return None


def record_exists(instance_corpus: Path, blake3: str) -> bool:
    return (instance_corpus / "records" / blake3[:2] / f"{blake3}.md").is_file()


def stage_and_ingest(src_bytes: Path, instance_corpus: Path, corpus_bin: str) -> str:
    capture_dir = instance_corpus / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)
    staged = capture_dir / src_bytes.name
    shutil.copy2(src_bytes, staged)
    result = subprocess.run(
        [corpus_bin, "ingest", str(staged), "--corpus-root", str(instance_corpus)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"ingest failed for {src_bytes.name}:\n{result.stdout}\n{result.stderr}")
    print("  " + result.stdout.strip().replace("\n", "\n  "))
    return result.stdout


def promote(instance_corpus: Path, container: str, address: str, corpus_bin: str) -> str:
    uri = f"corpus://{container}?{address}"
    result = subprocess.run(
        [corpus_bin, "promote", uri, "--json", "--corpus-root", str(instance_corpus)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"promote failed for {uri}:\n{result.stdout}\n{result.stderr}")
    data = json.loads(result.stdout)
    return data["id"] if "id" in data else data.get("record_id", "")


# --------------------------------------------------------- v39 ontology exemplars
#
# spec/ledger.md §15: a domain concept (ontology block, conditional
# commitment), a domain-minted member fact carrying both an ordinary claim
# and a presence claim (§5.5), and a rehearsal export (§15.7). A fictional
# TV franchise (Battlestar Galactica) so the whole thing is safe, synthetic
# content — no source instance, no real bytes.
#
# The one evidence record these facts cite is hand-authored directly as a
# corpus record (skipping `corpus ingest` entirely) — mirroring the ledger
# test suite's own fixture idiom (`tests/test_ledger_tools.py`'s bare
# `<!--origin-->`/`<!--segment-->` records): a `corpus ingest` pass would
# need this content routed through a declared mime drafter before its text
# becomes citable at all, which is real machinery this seeder has no
# business exercising just to mint one evidence source. The id below is
# deliberately patterned, not a real blake3 — exactly the H1/H2/… convention
# ledger tests already use for a hand-authored record's identity.

V39_NOTE_HASH = "39" * 32

_V39_NOTE_RECORD = f"""---
id: {V39_NOTE_HASH}
title: ''
status: normalized
touch:
- corpus.ingest@0.1.0
---

<!--artifact text/plain
-->

<!--origin
snapshot: '2026-08-26T00:00:00Z'
-->

<!--segment text
address: el=1
-->
Battlestar Galactica (2003 reimagined continuity) is a fictional
franchise; nothing asserted in this note is a real-world fact.
<!--/segment-->

<!--segment text
address: el=2
-->
The battlestar Galactica is classed as a battlestar.
<!--/segment-->

<!--segment text
address: el=3
-->
This note names no production designer for the Galactica program.
<!--/segment-->
"""

# facts/continuity/bsg-reimagined.json — the exemplar domain concept: an
# ordinary concept first (§15.1: "a domain is a real concept"), carrying an
# `ontology:` block that mints one domain-scoped type (`vessel`) with its
# own `extends:` chain into the spine, and declares `commitment:
# "conditional"` (§15.4, ISO/IEC 21838-2 §4.9.3(b) — no existence
# commitment for the franchise's in-universe content).
_V39_DOMAIN_FACT = {
    "id": "bsg-reimagined",
    "type": "continuity",
    "name": "Battlestar Galactica (2003 reimagined continuity)",
    "ontology": {
        "commitment": "conditional",
        "imports": [],
        "types": {
            "vessel": {
                "extends": "cco:Artifact",
                "description": "An in-universe craft (v39 exemplar domain-minted "
                               "type, spec/ledger.md §15.4).",
            },
        },
    },
    "sources": {"s1": {"record": V39_NOTE_HASH}},
    "claims": [{
        "id": "bsg-reimagined:kind", "predicate": "kind", "value": "television franchise",
        "status": "provisional", "asof": "2026-08-26",
        "evidence": [{"source": "s1", "anchor": "el=1", "kind": "incidental",
                     "quote": "Battlestar Galactica (2003 reimagined continuity) is "
                              "a fictional franchise"}],
    }],
}

# facts/vessel/galactica.json — the exemplar member fact: `domain:` names
# the concept above, its type (`vessel`) resolves as that domain's own
# minted sense (§15.4). Carries one ordinary claim and one presence claim
# (§5.5) — a fact verifiably has no value under `designer`, evidence-bearing
# rather than mere silence.
_V39_MEMBER_FACT = {
    "id": "galactica", "type": "vessel", "domain": "bsg-reimagined", "name": "Galactica",
    "sources": {"s1": {"record": V39_NOTE_HASH}},
    "claims": [
        {
            "id": "galactica:class", "predicate": "class", "value": "battlestar",
            "status": "provisional", "asof": "2026-08-26",
            "evidence": [{"source": "s1", "anchor": "el=2", "kind": "incidental",
                         "quote": "The battlestar Galactica is classed as a battlestar."}],
        },
        {
            "id": "galactica:designer", "predicate": "designer", "presence": "none",
            "status": "provisional", "asof": "2026-08-26",
            "evidence": [{"source": "s1", "anchor": "el=3", "kind": "incidental",
                         "quote": "This note names no production designer for the "
                                  "Galactica program."}],
        },
    ],
}


def _run_ath(ath_bin: str, *args: str, instance_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ath_bin, "ledger", *args, "--root", str(instance_root)],
        capture_output=True, text=True,
    )


def seed_v39_ontology_exemplars(instance_root: Path, ath_bin: str) -> bool:
    """Seed the v39 ontology exemplars into the test instance's ledger, then
    rehearse `check`/`verify`/`regen`/`export` over them as the regression
    check itself — a fixture that doesn't gate clean teaches nothing.
    Idempotent: skipped once the domain concept file exists. Returns False
    (never exits the process) on a gate failure, so the caller can fold it
    into the overall exit code exactly like a manifest-entry error.
    """
    ledger_root = instance_root / "ledger"
    domain_path = ledger_root / "facts" / "continuity" / "bsg-reimagined.json"
    if domain_path.is_file():
        print("skip (already seeded): v39 ontology exemplars")
        return True

    print("seeding: v39 ontology exemplars (domain concept + member fact + presence claim)")

    note_path = (instance_root / "corpus" / "records" / V39_NOTE_HASH[:2]
                / f"{V39_NOTE_HASH}.md")
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(_V39_NOTE_RECORD, encoding="utf-8")

    domain_path.parent.mkdir(parents=True, exist_ok=True)
    domain_path.write_text(json.dumps(_V39_DOMAIN_FACT, indent=2) + "\n", encoding="utf-8")
    member_path = ledger_root / "facts" / "vessel" / "galactica.json"
    member_path.parent.mkdir(parents=True, exist_ok=True)
    member_path.write_text(json.dumps(_V39_MEMBER_FACT, indent=2) + "\n", encoding="utf-8")

    check = _run_ath(ath_bin, "check", instance_root=instance_root)
    print("  " + check.stdout.strip().replace("\n", "\n  "))
    if check.returncode != 0:
        print(f"  ERROR: v39 exemplars failed `ath ledger check`:\n{check.stdout}{check.stderr}")
        return False

    verify = _run_ath(ath_bin, "verify", instance_root=instance_root)
    print("  " + verify.stdout.strip().replace("\n", "\n  "))
    if verify.returncode != 0:
        print(f"  ERROR: v39 exemplars failed `ath ledger verify`:\n"
              f"{verify.stdout}{verify.stderr}")
        return False

    regen = _run_ath(ath_bin, "regen", instance_root=instance_root)
    if regen.returncode != 0:
        print(f"  ERROR: v39 exemplars failed `ath ledger regen`:\n{regen.stdout}{regen.stderr}")
        return False

    export = _run_ath(ath_bin, "export", "--gate", instance_root=instance_root)
    if export.returncode != 0:
        print(f"  ERROR: v39 exemplars failed `ath ledger export`:\n"
              f"{export.stdout}{export.stderr}")
        return False
    export_path = ledger_root / ".cache" / "v39-export-sample.ttl"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(export.stdout, encoding="utf-8")
    print(f"  wrote {export_path.relative_to(instance_root)} (rehearsal export fixture, §15.7)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from", dest="source", default=os.environ.get("ATHENAEUM_ROOT"),
        help="source instance root (default: $ATHENAEUM_ROOT)",
    )
    args = parser.parse_args()

    entries = parse_manifest(MANIFEST_PATH)

    needs_source = any(e.get("source") != "synthetic" for e in entries)
    source_root: Path | None = None
    if needs_source:
        if not args.source:
            sys.exit("no source instance given: pass --from or set ATHENAEUM_ROOT")
        source_root = Path(args.source).resolve()
        if not (source_root / "corpus" / "records").is_dir():
            sys.exit(f"not a corpus instance root: {source_root}")
    elif args.source:
        source_root = Path(args.source).resolve()

    if not (INSTANCE_ROOT / "athenaeum.yaml").is_file():
        sys.exit(
            f"no scaffolded instance at {INSTANCE_ROOT} — run "
            f"`ath init testdata/instance --name athenaeum-testdata` first."
        )
    instance_corpus = INSTANCE_ROOT / "corpus"

    corpus_bin = find_tool("corpus")

    print(f"{len(entries)} manifest entries, source={source_root}\n")

    ingested = skipped = errors = 0

    for entry in entries:
        blake3 = entry["blake3"]
        shape = entry.get("shape", "?")
        mime = entry.get("mime", "?")
        label = f"{shape} ({mime}) {blake3[:12]}…"

        if record_exists(instance_corpus, blake3):
            print(f"skip (already seeded): {label}")
            skipped += 1
            continue

        print(f"seeding: {label}")

        if entry.get("source") == "synthetic":
            src = HERE / entry["file"]
            if not src.is_file():
                print(f"  ERROR: {src} not found — did you run testdata/synthetic/gen.py?")
                errors += 1
                continue
            stage_and_ingest(src, instance_corpus, corpus_bin)
            if not record_exists(instance_corpus, blake3):
                print(f"  ERROR: ingest did not produce {blake3} — mismatched bytes?")
                errors += 1
                continue
            ingested += 1
            continue

        if entry.get("source") == "promoted":
            via = entry["via"]
            container, address = via["container"], via["address"]
            if not record_exists(instance_corpus, container):
                src = locate_source_bytes(source_root, container, corpus_bin)
                if src is None:
                    print(f"  ERROR: container {container[:12]}… not locatable in source — skipped")
                    errors += 1
                    continue
                stage_and_ingest(src, instance_corpus, corpus_bin)
            minted_id = promote(instance_corpus, container, address, corpus_bin)
            if minted_id != blake3:
                print(f"  ERROR: promoted id {minted_id} != manifest blake3 {blake3}")
                errors += 1
                continue
            print(f"  promoted: records/{minted_id[:2]}/{minted_id}.md")
            ingested += 1
            continue

        src = locate_source_bytes(source_root, blake3, corpus_bin)
        if src is None:
            print(f"  ERROR: {blake3[:12]}… not locatable in source — skipped")
            errors += 1
            continue
        stage_and_ingest(src, instance_corpus, corpus_bin)
        if not record_exists(instance_corpus, blake3):
            print(f"  ERROR: ingest did not produce {blake3} — mismatched bytes?")
            errors += 1
            continue
        ingested += 1

    print(f"\ningested {ingested}, skipped {skipped}, errors {errors}, of {len(entries)} entries")

    print()
    ath_bin = find_tool("ath")
    if not seed_v39_ontology_exemplars(INSTANCE_ROOT, ath_bin):
        errors += 1

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
