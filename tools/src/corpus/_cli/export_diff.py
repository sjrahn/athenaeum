"""Export-diff — `corpus export-diff <A> <B>` (spec §12.3.14, the onboarding gate).

Turnkey measurement for the temporal-stratification onboarding gate: "no declaration
without measurement" — a producer joins the month-grain standard's closed-period
byte-stability claim only on a banked two-export diff over the SAME closed period, which
decides (1) whether the serializer is deterministic across export jobs, (2) the exact
chrome (churn) set to declare (`strip_headers` / `strip_fields`), and (3) full-strata vs
member-dedup-only onboarding. The precedent: two Gmail Takeouts diffed member-wise showed
identity modulo the `X-Gmail-Labels` header = 99.1% stable — the header was the COMPLETE
churn set (the export-sources runbook, "Temporal stratification onboarding" — runbooks
ride the corpus repo, e.g. corpus/runbooks/export-sources.md).

Read-only; no corpus root involved — this analyzes two export deliveries directly, before
either is ever ingested.

Two comparison modes, chosen by inspecting A and B (both must agree):

- **mbox pair** (member grain). Members are matched first by un-stuffed blake3 (spec
  §12.11 — the promotable identity mboxfile.scan already computes); non-identical members
  are then paired across sides by Message-ID (falling back to the (Date, From, Subject)
  triple when absent) and their HEADER ZONES diffed line-by-line, name by name. A paired
  member whose body differs is content-divergent — never chrome, regardless of what its
  headers do. A paired member whose body matches but header(s) differ is chrome-eligible;
  the churned header NAMES feed the histogram.
- **directory/zip pair** (file grain). Trees are walked and keyed by relative path (a zip
  is read as a read-only directory of members via `zipfile`, never unpacked). Same-path
  files are compared by blake3; differing files that both parse as JSON (size-capped) get
  a structural diff — dotted paths (array indices generalized to `[]`) whose values differ
  or exist on only one side feed the histogram as `strip_fields` candidates. Non-JSON (or
  oversize, or unparseable) differing files are byte-divergent findings, never chrome —
  media/photos are expected identical, so a divergence there is real signal.

Either mode ends in the same reconciliation math: for a candidate churn-name set S, a
chrome-eligible pair/file "reconciles" when its own churned-name set is a SUBSET of S (the
non-churned names already agree by construction, so ignoring a superset of what actually
differs makes the two sides byte-identical). The histogram's descending prefixes are the
natural candidate sets; the report picks the smallest one clearing 95% stability as the
recommended `strip_headers`/`strip_fields` declaration, or reports MEMBER-DEDUP-ONLY when
none does — the two outcomes the onboarding gate distinguishes.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable
from contextlib import ExitStack
from pathlib import Path

import blake3

from corpus import mboxfile

# Above this, a differing file is reported byte-divergent without attempting a JSON parse
# (matches the assemble/ingest family's caution around materializing large payloads).
_JSON_SIZE_CAP = 50 * 1024 * 1024

# Cap on how many descending-histogram prefixes the report evaluates as candidate
# strip sets — churn beyond this is already well past "chrome", so the tail is noise.
_CANDIDATE_CAP = 8

# The reconciliation bar a candidate churn set must clear to be recommended as a full
# strata (closed-period byte-stability) declaration rather than member-dedup-only. Below
# the Gmail precedent's 99.1% but conservative enough that a producer needs a genuinely
# small, near-complete churn set to pass — the operator still judges and banks the number.
_STABILITY_BAR_PCT = 95.0


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "a", metavar="A", help="first export — an mbox file, a directory tree, or a zip."
    )
    parser.add_argument(
        "b",
        metavar="B",
        help="second export of the SAME closed period as A — same shape as A.",
    )
    parser.add_argument(
        "--json",
        dest="json_out",
        default=None,
        metavar="PATH",
        help="also write the full machine-readable report to PATH as JSON.",
    )


def run(args: argparse.Namespace) -> int:
    report = build_report(Path(args.a), Path(args.b))
    if getattr(args, "json_out", None):
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")
    print(render_report(report))
    return 0


# ---------- mode detection ---------- #


def _sniff_mboxrd(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(5) == b"From "
    except OSError:
        return False


def _classify(path: Path) -> str:
    """`"mbox"` or `"tree"` — a zip is always `"tree"` (read as a directory of members),
    never an mbox-in-a-zip. A plain file earns `"mbox"` by extension or, absent that, by
    sniffing the mboxrd separator; everything else (directories, zips, unrecognized
    files) is `"tree"`."""
    if path.is_dir():
        return "tree"
    if path.is_file():
        if path.suffix.lower() == ".mbox":
            return "mbox"
        if zipfile.is_zipfile(path):
            return "tree"
        return "mbox" if _sniff_mboxrd(path) else "tree"
    sys.exit(f"export-diff: not found: {path}")


def build_report(a: Path, b: Path) -> dict:
    if not a.exists():
        sys.exit(f"export-diff: not found: {a}")
    if not b.exists():
        sys.exit(f"export-diff: not found: {b}")
    mode_a, mode_b = _classify(a), _classify(b)
    if mode_a != mode_b:
        sys.exit(
            f"export-diff: mismatched export shapes — {a} looks like {mode_a}, "
            f"{b} looks like {mode_b}; compare like with like."
        )
    return _mbox_report(a, b) if mode_a == "mbox" else _tree_report(a, b)


# ---------- mbox pair (member grain) ---------- #


def _fold_headers(lines: list[bytes]) -> list[tuple[str, bytes]]:
    """Group raw header LINES into logical (name, blob) entries — a folded continuation
    line (leading space/tab) is appended onto the preceding entry's blob, never treated as
    its own header. `name` is lowercased for case-insensitive matching; `blob` keeps every
    physical line's raw bytes, so an exact-bytes compare is a true header-zone diff."""
    logical: list[tuple[str, bytes]] = []
    for line in lines:
        if line[:1] in (b" ", b"\t") and logical:
            name, blob = logical[-1]
            logical[-1] = (name, blob + line)
        else:
            head, sep, _ = line.partition(b":")
            name = head.decode("ascii", "replace").strip().lower() if sep else "<malformed>"
            logical.append((name, line))
    return logical


def _header_map(logical: list[tuple[str, bytes]]) -> dict[str, list[bytes]]:
    out: dict[str, list[bytes]] = {}
    for name, blob in logical:
        out.setdefault(name, []).append(blob)
    return out


def _header_value(blob: bytes) -> str:
    """The header's value, unfolded to one line (whitespace-collapsed) — used only to
    build the Message-ID match key, never for the byte-exact churn compare."""
    _, _, rest = blob.partition(b":")
    return " ".join(rest.decode("utf-8", "replace").split())


def _read_member(path: Path, ordinal: int) -> tuple[dict[str, list[bytes]], bytes]:
    """One `mboxfile.open_member` pass: the folded header map plus the raw body bytes —
    a single streaming read serves both the match-key lookup and the header/body diff."""
    with mboxfile.open_member(path, ordinal) as fh:
        lines: list[bytes] = []
        while True:
            line = fh.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            lines.append(line)
        body = fh.read()
    return _header_map(_fold_headers(lines)), body


def _match_key(
    ordinal: int,
    detail: dict[int, tuple[dict[str, list[bytes]], bytes]],
    facts: dict[int, mboxfile.MessageFacts],
) -> tuple:
    hmap, _body = detail[ordinal]
    message_id = hmap.get("message-id")
    if message_id:
        return ("mid", _header_value(message_id[0]))
    f = facts[ordinal]
    return ("triple", (f.date, f.sender, f.subject))


def _mbox_report(a: Path, b: Path) -> dict:
    scan_a = mboxfile.scan(a, None)
    scan_b = mboxfile.scan(b, None)
    hashes_a = {f.blake3 for f in scan_a.facts.values()}
    hashes_b = {f.blake3 for f in scan_b.facts.values()}
    identical = len(hashes_a & hashes_b)

    only_a_ord = [n for n, f in scan_a.facts.items() if f.blake3 not in hashes_b]
    only_b_ord = [n for n, f in scan_b.facts.items() if f.blake3 not in hashes_a]

    detail_a = {n: _read_member(a, n) for n in only_a_ord}
    detail_b = {n: _read_member(b, n) for n in only_b_ord}

    keys_a: dict[tuple, list[int]] = {}
    for n in only_a_ord:
        keys_a.setdefault(_match_key(n, detail_a, scan_a.facts), []).append(n)
    keys_b: dict[tuple, list[int]] = {}
    for n in only_b_ord:
        keys_b.setdefault(_match_key(n, detail_b, scan_b.facts), []).append(n)

    unmatched_a = set(only_a_ord)
    unmatched_b = set(only_b_ord)
    chrome_pairs: list[frozenset[str]] = []
    content_divergent = 0
    for key, ords_a in keys_a.items():
        ords_b = keys_b.get(key)
        if not ords_b:
            continue
        for na, nb in zip(ords_a, ords_b, strict=False):
            unmatched_a.discard(na)
            unmatched_b.discard(nb)
            hmap_a, body_a = detail_a[na]
            hmap_b, body_b = detail_b[nb]
            if body_a != body_b:
                content_divergent += 1
                continue
            churned = frozenset(
                name
                for name in set(hmap_a) | set(hmap_b)
                if hmap_a.get(name) != hmap_b.get(name)
            )
            chrome_pairs.append(churned)

    matched_pairs = len(chrome_pairs) + content_divergent
    matched_total = identical + matched_pairs
    histogram, candidates, verdict = _build_verdict(
        identical=identical,
        chrome_pairs=chrome_pairs,
        content_divergent=content_divergent,
        matched_total=matched_total,
    )
    return {
        "mode": "mbox",
        "a": {"path": str(a), "total": scan_a.count},
        "b": {"path": str(b), "total": scan_b.count},
        "identical": identical,
        "only_a": len(only_a_ord),
        "only_b": len(only_b_ord),
        "matched_pairs": matched_pairs,
        "content_divergent": content_divergent,
        "chrome_eligible": len(chrome_pairs),
        "unmatched_only_a": len(unmatched_a),
        "unmatched_only_b": len(unmatched_b),
        "histogram": histogram,
        "candidates": candidates,
        "verdict": verdict,
    }


# ---------- directory/zip pair (file grain) ---------- #


class _Entry:
    """A lazily-hashed, lazily-read file — from a real directory entry or a zip member —
    behind one interface so tree-walking code never cares which."""

    __slots__ = ("_blake3_fn", "_hash", "_read_fn", "size")

    def __init__(
        self, size: int, blake3_fn: Callable[[], str], read_fn: Callable[[], bytes]
    ) -> None:
        self.size = size
        self._blake3_fn = blake3_fn
        self._read_fn = read_fn
        self._hash: str | None = None

    def blake3(self) -> str:
        if self._hash is None:
            self._hash = self._blake3_fn()
        return self._hash

    def read(self) -> bytes:
        return self._read_fn()


def _blake3_file(p: Path) -> str:
    h = blake3.blake3()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _blake3_zip(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    h = blake3.blake3()
    with zf.open(info) as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _dir_entries(root: Path) -> dict[str, _Entry]:
    entries: dict[str, _Entry] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            entries[rel] = _Entry(
                p.stat().st_size, lambda p=p: _blake3_file(p), lambda p=p: p.read_bytes()
            )
    return entries


def _zip_entries(zf: zipfile.ZipFile) -> dict[str, _Entry]:
    entries: dict[str, _Entry] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        entries[info.filename] = _Entry(
            info.file_size,
            lambda info=info: _blake3_zip(zf, info),
            lambda info=info: zf.read(info),
        )
    return entries


def _load_entries(stack: ExitStack, path: Path) -> dict[str, _Entry]:
    if path.is_dir():
        return _dir_entries(path)
    if zipfile.is_zipfile(path):
        zf = stack.enter_context(zipfile.ZipFile(path))
        return _zip_entries(zf)
    # A lone non-mbox file compared file-grain: a one-entry tree keyed by its own name.
    return {path.name: _Entry(path.stat().st_size, lambda: _blake3_file(path), path.read_bytes)}


def _json_leaf_map(value: object) -> dict[str, list[str]]:
    """Dotted-path → the leaf value(s) at that path (as sorted-safe JSON reprs), with
    array indices generalized to `[]` so same-shaped list items don't fragment the path
    space (spec's `strip_fields` candidate shape)."""
    out: dict[str, list[str]] = {}

    def walk(v: object, path: str) -> None:
        if isinstance(v, dict):
            for k, cv in v.items():
                walk(cv, f"{path}.{k}" if path else str(k))
        elif isinstance(v, list):
            for cv in v:
                walk(cv, f"{path}[]")
        else:
            out.setdefault(path, []).append(json.dumps(v, sort_keys=True, default=str))

    walk(value, "")
    return out


def _json_diff_paths(a: object, b: object) -> set[str]:
    ma, mb = _json_leaf_map(a), _json_leaf_map(b)
    names = set(ma) | set(mb)
    return {p for p in names if sorted(ma.get(p, [])) != sorted(mb.get(p, []))}


def _tree_report(a: Path, b: Path) -> dict:
    with ExitStack() as stack:
        entries_a = _load_entries(stack, a)
        entries_b = _load_entries(stack, b)

        common = sorted(set(entries_a) & set(entries_b))
        only_a = sorted(set(entries_a) - set(entries_b))
        only_b = sorted(set(entries_b) - set(entries_a))

        identical = 0
        differing: list[str] = []
        for rel in common:
            if entries_a[rel].blake3() == entries_b[rel].blake3():
                identical += 1
            else:
                differing.append(rel)

        chrome_pairs: list[frozenset[str]] = []
        content_divergent = 0
        for rel in differing:
            ea, eb = entries_a[rel], entries_b[rel]
            if ea.size > _JSON_SIZE_CAP or eb.size > _JSON_SIZE_CAP:
                content_divergent += 1
                continue
            try:
                json_a = json.loads(ea.read())
                json_b = json.loads(eb.read())
            except (json.JSONDecodeError, UnicodeDecodeError):
                content_divergent += 1
                continue
            chrome_pairs.append(frozenset(_json_diff_paths(json_a, json_b)))

        matched_pairs = len(chrome_pairs) + content_divergent
        matched_total = identical + matched_pairs
        histogram, candidates, verdict = _build_verdict(
            identical=identical,
            chrome_pairs=chrome_pairs,
            content_divergent=content_divergent,
            matched_total=matched_total,
        )
        return {
            "mode": "tree",
            "a": {"path": str(a), "total": len(entries_a)},
            "b": {"path": str(b), "total": len(entries_b)},
            "identical": identical,
            "only_a": len(only_a),
            "only_b": len(only_b),
            "matched_pairs": matched_pairs,
            "content_divergent": content_divergent,
            "chrome_eligible": len(chrome_pairs),
            "histogram": histogram,
            "candidates": candidates,
            "verdict": verdict,
        }


# ---------- shared histogram / reconciliation / verdict ---------- #


def _fmt_names(names: Iterable[str]) -> str:
    names = list(names)
    return "<" + ", ".join(names) + ">" if names else "<none>"


def _build_verdict(
    *,
    identical: int,
    chrome_pairs: list[frozenset[str]],
    content_divergent: int,
    matched_total: int,
) -> tuple[list[tuple[str, int]], list[dict], dict]:
    """The histogram (descending churn-name frequency across chrome-eligible pairs/files),
    the reconciliation table (one entry per histogram prefix — how many pairs/files become
    stable if exactly those names are ignored), and the verdict picking the smallest
    prefix clearing `_STABILITY_BAR_PCT`, else the best achieved. A pair/file's churned-
    name set is a SUBSET test against a candidate: names outside the churned set already
    agree by construction, so a candidate covering (a superset of) the churn reconciles it
    exactly — no need to re-derive the stripped bytes to confirm."""
    counter: Counter[str] = Counter()
    for names in chrome_pairs:
        counter.update(names)
    histogram = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))

    def reconciled(candidate: frozenset[str]) -> int:
        return sum(1 for names in chrome_pairs if names <= candidate)

    candidates: list[dict] = []
    prefix: list[str] = []
    for k in range(0, min(len(histogram), _CANDIDATE_CAP) + 1):
        if k > 0:
            prefix.append(histogram[k - 1][0])
        candidate_set = frozenset(prefix)
        recon = reconciled(candidate_set)
        stable = identical + recon
        pct = (stable / matched_total * 100) if matched_total else 100.0
        candidates.append(
            {"names": list(prefix), "reconciled": recon, "stable": stable,
             "total": matched_total, "pct": pct}
        )

    if matched_total == 0:
        verdict = {
            "kind": "no_data",
            "modulo": [],
            "stable": identical,
            "total": 0,
            "pct": 100.0,
            "text": "no comparable members/files between A and B — nothing measured.",
        }
    elif not histogram and content_divergent == 0:
        verdict = {
            "kind": "clean",
            "modulo": [],
            "stable": identical,
            "total": matched_total,
            "pct": 100.0,
            "text": "CLEAN — serializer already deterministic; no chrome strip needed.",
        }
    else:
        chosen = next(
            (c for c in candidates if c["pct"] >= _STABILITY_BAR_PCT),
            max(candidates, key=lambda c: c["pct"]),
        )
        if chosen["pct"] >= _STABILITY_BAR_PCT:
            kind = "full_strata_candidate"
            text = (
                f"FULL STRATA CANDIDATE — modulo {_fmt_names(chosen['names'])}: "
                f"{chosen['stable']}/{chosen['total']} ({chosen['pct']:.1f}%) stable. "
                "Bank this in the overlay's comment block before declaring partition:."
            )
        else:
            kind = "member_dedup_only"
            text = (
                "MEMBER-DEDUP-ONLY — churn doesn't reconcile closed-period byte-stability "
                f"(best modulo {_fmt_names(chosen['names'])}: {chosen['stable']}/"
                f"{chosen['total']} ({chosen['pct']:.1f}%)); onboard via the "
                "window-reduction pattern (§12.3.13) until a stronger measurement lands."
            )
        verdict = {
            "kind": kind,
            "modulo": chosen["names"],
            "stable": chosen["stable"],
            "total": chosen["total"],
            "pct": chosen["pct"],
            "text": text,
        }
    return histogram, candidates, verdict


# ---------- rendering ---------- #


def render_report(report: dict) -> str:
    mode = report["mode"]
    unit = "member(s)" if mode == "mbox" else "file(s)"
    field = "header" if mode == "mbox" else "field path"
    lines = [
        f"export-diff [{mode}]  A={report['a']['path']}  B={report['b']['path']}",
        f"  A: {report['a']['total']} {unit}   B: {report['b']['total']} {unit}",
        f"  identical: {report['identical']}",
        f"  only-A: {report['only_a']}   only-B: {report['only_b']}",
        f"  paired non-identical: {report['matched_pairs']} "
        f"(content-divergent: {report['content_divergent']}, "
        f"chrome-eligible: {report['chrome_eligible']})",
    ]
    if "unmatched_only_a" in report:
        lines.append(
            f"  unmatched after Message-ID/fallback pairing — "
            f"only-A: {report['unmatched_only_a']}   only-B: {report['unmatched_only_b']}"
        )
    lines.append("")
    if report["histogram"]:
        lines.append(f"churn histogram ({field}s, descending):")
        for name, count in report["histogram"]:
            lines.append(f"  {name}: {count}")
    else:
        lines.append(f"churn histogram: (empty — no {field} churn observed)")
    lines.append("")
    lines.append("reconciliation (identical + reconciled-if-ignored / matched):")
    for c in report["candidates"]:
        lines.append(f"  modulo {_fmt_names(c['names'])}: {c['stable']}/{c['total']} "
                      f"({c['pct']:.1f}%)")
    lines.append("")
    v = report["verdict"]
    lines.append(
        f"VERDICT: deterministic modulo {_fmt_names(v['modulo'])}: "
        f"{v['stable']}/{v['total']} ({v['pct']:.1f}%)"
    )
    lines.append(f"  {v['text']}")
    return "\n".join(lines)
