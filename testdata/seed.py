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

Plain stdlib only — no PyYAML, no `corpus`-package imports. Talks to the
`corpus` CLI as a subprocess, exactly as a human operator would.

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from", dest="source", default=os.environ.get("ATHENAEUM_ROOT"),
        help="source instance root (default: $ATHENAEUM_ROOT)",
    )
    args = parser.parse_args()

    if not args.source:
        sys.exit("no source instance given: pass --from or set ATHENAEUM_ROOT")
    source_root = Path(args.source).resolve()
    if not (source_root / "corpus" / "records").is_dir():
        sys.exit(f"not a corpus instance root: {source_root}")

    if not (INSTANCE_ROOT / "athenaeum.yaml").is_file():
        sys.exit(
            f"no scaffolded instance at {INSTANCE_ROOT} — run "
            f"`ath init testdata/instance --name athenaeum-testdata` first."
        )
    instance_corpus = INSTANCE_ROOT / "corpus"

    corpus_bin = find_tool("corpus")

    entries = parse_manifest(MANIFEST_PATH)
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
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
