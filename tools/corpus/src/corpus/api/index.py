"""Per-corpus record index — facets, typed-field registry, filter/sort/paginate.

Loads every record once via the library (`records.load_all`), keeps a lightweight
per-record entry (summary + a small filter index, NOT the heavy content body), and
answers the browser's queries in memory. This is the server-side equivalent of the
prototype's `cxBuildFacets` / `cxMatches` / `cxMatchesFields` / `cxOverlayValues`,
moved off the client so corpora of thousands of records stay responsive.

Pure: stdlib + the `corpus` library. The index is process-cached per (id, root);
pass ``fresh=True`` to rebuild (a `/reload`-style hook lands next phase).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from corpus import records, schemas, segments
from corpus.api import serialize
from corpus.api.config import CorpusEntry
from corpus.store import ArtifactStore, get_store

_DAYMS = 86_400_000
_DATE8 = re.compile(r"^\d{8}$")
_DATE_DASH = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
# field-name prefixes the design strips for a human label (`ytdlp_view_count` -> `view count`)
_LABEL_PREFIX = re.compile(r"^(ytdlp_|sc_|gh_|og_|exif_)")

# explicit short labels for the common MIME types (matches the design's chip set);
# everything else falls back to the subtype token.
_MIME_SHORT = {
    "application/pdf": "pdf",
    "text/html": "html",
    "video/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/tiff": "tiff",
    "image/webp": "webp",
    "application/epub+zip": "epub",
    "message/rfc822": "eml",
    "text/markdown": "md",
    "text/plain": "txt",
    "application/json": "json",
    "text/vtt": "vtt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}


def mime_short(mime: str) -> str:
    if mime in _MIME_SHORT:
        return _MIME_SHORT[mime]
    sub = (mime or "").split("/")[-1]
    sub = sub.split("+")[0]
    return sub[:6] or "?"


def _stringify(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _date_to_ms(value: Any) -> int | None:
    """`YYYYMMDD` / `YYYY-MM-DD[...]` -> UTC-midnight epoch ms (mirrors `labToDate`)."""
    s = str(value)
    if _DATE8.match(s):
        y, mo, d = int(s[:4]), int(s[4:6]), int(s[6:8])
    else:
        m = _DATE_DASH.match(s)
        if not m:
            return None
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return int(datetime(y, mo, d, tzinfo=UTC).timestamp() * 1000)
    except ValueError:
        return None


def _humanize(field_name: str) -> str:
    return _LABEL_PREFIX.sub("", field_name).replace("_", " ")


def _overlay_group(overlay_key: str) -> tuple[str, str]:
    """`(group, groupLabel)` for an overlay key (the design's `labGroupOf`)."""
    if overlay_key.startswith("mime/"):
        return "mime", mime_short(overlay_key[len("mime/") :])
    if overlay_key.startswith("origin/"):
        return "origin", overlay_key[len("origin/") :]
    if overlay_key.startswith("composite/"):
        return "composite", overlay_key[len("composite/") :]
    return "core", "record"


def _present(value: Any) -> bool:
    if value is None or value == "":
        return False
    return not (isinstance(value, list) and not value)


def _compute_stats(ftype: str, raw_values: list[Any]) -> dict[str, Any] | None:
    """Per-type value statistics over the whole corpus (the design's `labComputeStats`):
    number/date -> a fixed-bin histogram + min/max/distinct; everything else -> a
    count-ordered value distribution. Returns None when no usable values exist."""
    st: dict[str, Any] = {"type": ftype}
    if ftype == "number":
        nums = sorted(float(v) for v in raw_values if _is_number(v))
        if not nums:
            return None
        lo, hi = nums[0], nums[-1]
        st["min"], st["max"], st["distinct"] = lo, hi, len(set(nums))
        st["bins"], st["binMax"] = _histogram(nums, lo, hi, 28)
    elif ftype == "date":
        ds = sorted(d for d in (_date_to_ms(v) for v in raw_values) if d is not None)
        if not ds:
            return None
        lo, hi = ds[0], ds[-1]
        st["min"], st["max"], st["distinct"] = lo, hi, len(set(ds))
        st["bins"], st["binMax"] = _histogram(ds, lo, hi, 24)
    else:  # string / list / uri / hash -> value distribution
        counter = Counter(str(v) for v in raw_values)
        st["values"] = [
            {"v": v, "n": n} for v, n in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        st["distinct"] = len(st["values"])
    return st


def _histogram(values: list[float], lo: float, hi: float, nbins: int) -> tuple[list[int], int]:
    span = (hi - lo) or 1
    bins = [0] * nbins
    for x in values:
        i = int((x - lo) / span * nbins)
        bins[min(max(i, 0), nbins - 1)] += 1
    return bins, max(bins) or 1


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def parse_cond(spec: str) -> dict[str, Any] | None:
    """Decode a `cond=` query value: `<fid>~<type>~<op>~<value>`. The value is typed by
    `<type>` (number/date `between` -> `[lo, hi]`; `in` -> csv list; `is` -> bool; else the
    raw string for `contains`). Returns None on a malformed spec (skipped by the caller)."""
    parts = spec.split("~", 3)
    if len(parts) != 4:
        return None
    fid, ctype, op, raw = parts
    value: Any
    if op == "between":
        lo, _sep, hi = raw.partition(",")
        try:
            value = [int(float(lo)), int(float(hi))] if ctype == "date" else [float(lo), float(hi)]
        except ValueError:
            return None
    elif op == "in":
        value = [v for v in raw.split(",") if v != ""]
    elif op == "is":
        value = raw.strip().lower() == "true"
    else:  # contains (string / uri / hash)
        value = raw
    return {"fid": fid, "type": ctype, "op": op, "value": value}


def parse_range(raw: str) -> tuple[int, int] | None:
    """Decode `range=loMs,hiMs` (epoch ms) into an inclusive bound, or None for full span."""
    if not raw:
        return None
    lo, _sep, hi = raw.partition(",")
    try:
        return (int(float(lo)), int(float(hi)))
    except ValueError:
        return None


@dataclass
class IndexedRecord:
    summary: dict[str, Any]
    mime: str
    hosts: list[str]
    status: str
    visibility: str | None
    composites: list[tuple[str, str]]  # (namespace, id)
    block_fields: dict[str, dict[str, Any]]  # overlayKey -> {field: raw value}
    haystack: str
    title_key: str
    captured: str
    has_embeds: bool
    has_issues: bool
    # workbench extras
    size: int | None  # artifact bytes (None when not local)
    segment_count: int
    embed_mimes: list[str]  # distinct short labels (jpg, png, …)
    atom_counts: dict[str, int]  # atom -> segment count
    captured_ms: int | None  # captured snapshot as epoch ms


@dataclass
class CorpusIndex:
    entry: CorpusEntry
    items: list[IndexedRecord] = field(default_factory=list)
    # overlayKey -> field -> ordered distinct stringified values (for the registry)
    overlay_values: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    # overlayKey -> field -> first raw value (for type inference)
    overlay_sample: dict[str, dict[str, Any]] = field(default_factory=dict)
    # full captured-date span [minMs, maxMs] (padded ±1 day), stable for the timeline axis
    full_span: tuple[int, int] = (0, _DAYMS)
    _fields_cache: list[dict[str, Any]] | None = None
    _by_id_cache: dict[str, IndexedRecord] | None = None
    _uri_index_cache: dict[str, str] | None = None

    # ---- build ----

    @classmethod
    def build(cls, entry: CorpusEntry) -> CorpusIndex:
        idx = cls(entry=entry)
        store = get_store(entry.root)
        for _path, post in records.load_all(entry.root):
            idx._ingest(post, store)
        days = sorted(it.captured_ms for it in idx.items if it.captured_ms is not None)
        if days:
            idx.full_span = (days[0] - _DAYMS, days[-1] + _DAYMS)
        return idx

    def _ingest(self, post: Any, store: ArtifactStore | None = None) -> None:
        mime = records.media_type_for(post)
        summary = serialize.record_summary(post, self.entry.id)
        contexts = post.metadata.get("_contexts") or []
        embeds = list(records.iter_embed_blocks(post))

        hosts: list[str] = []
        block_fields: dict[str, dict[str, Any]] = {}

        if mime:
            block_fields[f"mime/{mime}"] = dict((records.artifact_block(post) or {}).get("fields") or {})

        for origin in records.iter_origin_blocks(post):
            ofields = dict(origin.get("fields") or {})
            uris = ofields.pop("uri", None)
            ofields.pop("snapshot", None)
            uri_list = uris if isinstance(uris, list) else ([uris] if uris else [])
            host = serialize.host_of(str(uri_list[0])) if uri_list else ""
            if host and host not in hosts:
                hosts.append(host)
            if host:
                block_fields.setdefault(f"origin/{host}", {}).update(ofields)

        composites: list[tuple[str, str]] = []
        for block in records.iter_classify_blocks(post):
            ns = block.get("namespace") or ""
            cid = block.get("id") or ""
            if not ns or not cid:
                continue
            composites.append((ns, cid))
            cfields = dict(block.get("fields") or {})
            cfields.pop("provenance", None)
            block_fields.setdefault(f"composite/{ns}/{cid}", {}).update(cfields)

        haystack = " ".join(
            [
                summary["title"] or "",
                summary["description"] or "",
                summary["id"] or "",
                " ".join(records.iter_origin_uris(post)),
            ]
        ).lower()

        # flatten the content zone once: segment count + atom mix (overview `by atom`)
        atom_counts: dict[str, int] = {}
        segment_count = 0
        for block in segments.iter_blocks(post.content or ""):
            segs = block.segments if isinstance(block, segments.Section) else [block]
            for seg in segs:
                segment_count += 1
                atom = seg.atom or "text"
                atom_counts[atom] = atom_counts.get(atom, 0) + 1

        embed_mimes: list[str] = []
        for block in embeds:
            short = mime_short(block.get("media_type") or "")
            if short and short not in embed_mimes:
                embed_mimes.append(short)

        size = serialize.artifact_size(self.entry.root, summary["id"] or "", mime, store)
        captured_ms = _date_to_ms(summary["captured"]) if summary["captured"] else None

        self.items.append(
            IndexedRecord(
                summary=summary,
                mime=mime,
                hosts=hosts,
                status=summary["status"] or "",
                visibility=summary["visibility"],
                composites=composites,
                block_fields=block_fields,
                haystack=haystack,
                title_key=(summary["title"] or "").lower(),
                captured=summary["captured"] or "",
                has_embeds=bool(embeds),
                has_issues=bool(contexts),
                size=size,
                segment_count=segment_count,
                embed_mimes=embed_mimes,
                atom_counts=atom_counts,
                captured_ms=captured_ms,
            )
        )

        for key, fields_ in block_fields.items():
            vbucket = self.overlay_values.setdefault(key, {})
            sbucket = self.overlay_sample.setdefault(key, {})
            for fname, raw in fields_.items():
                if raw is None:
                    continue
                sbucket.setdefault(fname, raw)
                sval = _stringify(raw)
                vals = vbucket.setdefault(fname, [])
                if sval not in vals:
                    vals.append(sval)

    # ---- scope + matching ----

    def _scope(self, q: str, saved_view: str) -> list[IndexedRecord]:
        ql = (q or "").strip().lower()
        out = []
        for it in self.items:
            if saved_view == "queue" and it.status == "normalized":
                continue
            if saved_view == "issues" and not it.has_issues:
                continue
            if saved_view == "embeds" and not it.has_embeds:
                continue
            if ql and ql not in it.haystack:
                continue
            out.append(it)
        return out

    @staticmethod
    def _facet_values(it: IndexedRecord, key: str) -> list[str]:
        if key == "mime":
            return [it.mime] if it.mime else []
        if key == "origin":
            return it.hosts
        if key == "status":
            return [it.status] if it.status else []
        if key == "visibility":
            return [it.visibility] if it.visibility else []
        if key == "embedmime":
            return it.embed_mimes
        if key.startswith("composite:"):
            ns = key[len("composite:") :]
            return [cid for (cns, cid) in it.composites if cns == ns]
        return []

    def _matches_facets(self, it: IndexedRecord, facets: dict[str, set[str]]) -> bool:
        for key, wanted in facets.items():
            if not wanted:
                continue
            have = set(self._facet_values(it, key))
            if not (have & wanted):
                return False
        return True

    def _matches_fields(self, it: IndexedRecord, fields_sel: dict[str, set[str]]) -> bool:
        for compound, wanted in fields_sel.items():
            if not wanted:
                continue
            overlay_key, _, fname = compound.partition("::")
            block = it.block_fields.get(overlay_key)
            if not block or fname not in block:
                return False
            if _stringify(block[fname]) not in wanted:
                return False
        return True

    # ---- public queries ----

    def facets(self, q: str = "", saved_view: str = "all") -> list[dict[str, Any]]:
        """Facet tree over the (query + saved-view) scope, NOT reduced by facet selection
        (matches the design: live counts independent of the current selection)."""
        scope = self._scope(q, saved_view)
        counters: dict[str, dict[str, int]] = {}
        labels: dict[str, str] = {}

        def bump(key: str, label: str, value: str) -> None:
            labels[key] = label
            c = counters.setdefault(key, {})
            c[value] = c.get(value, 0) + 1

        composite_ns: set[str] = set()
        for it in scope:
            if it.mime:
                bump("mime", "mime", it.mime)
            for h in it.hosts:
                bump("origin", "origin", h)
            if it.status:
                bump("status", "status", it.status)
            if it.visibility and it.visibility != "visible":
                bump("visibility", "visibility", it.visibility)
            for ns, cid in it.composites:
                key = f"composite:{ns}"
                bump(key, ns, cid)
                composite_ns.add(ns)

        order = ["mime", "origin", "status"]
        order += [f"composite:{ns}" for ns in sorted(composite_ns)]
        order += ["visibility"]

        out: list[dict[str, Any]] = []
        for key in order:
            c = counters.get(key)
            if not c:
                continue
            values = [
                {"v": v, "n": n, "label": mime_short(v) if key == "mime" else v}
                for v, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
            ]
            out.append({"key": key, "label": labels[key], "values": values})
        return out

    def schema_registry(self) -> dict[str, list[dict[str, Any]]]:
        """For every overlay key present in the corpus, the typed extended fields and
        their distinct values (server-side `cxOverlayValues`)."""
        out: dict[str, list[dict[str, Any]]] = {}
        for key in sorted(self.overlay_values):
            declared = _declared_fields(self.entry.root, key)
            present = self.overlay_values.get(key, {})
            samples = self.overlay_sample.get(key, {})
            ordered: list[str] = []
            for fname, _t in declared:
                if fname in present and fname not in ordered:
                    ordered.append(fname)
            for fname in present:
                if fname not in ordered:
                    ordered.append(fname)
            declared_map = dict(declared)
            fields_out = []
            for fname in ordered:
                vals = present.get(fname) or []
                if not vals:
                    continue
                ftype = serialize.normalize_type(
                    declared_map.get(fname), fname, samples.get(fname)
                )
                fields_out.append({"field": fname, "type": ftype, "values": vals})
            if fields_out:
                out[key] = fields_out
        return out

    def query(
        self,
        *,
        q: str = "",
        saved_view: str = "all",
        facets: dict[str, set[str]] | None = None,
        fields_sel: dict[str, set[str]] | None = None,
        sort: str = "recent",
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        facets = facets or {}
        fields_sel = fields_sel or {}
        scope = self._scope(q, saved_view)
        matched = [
            it
            for it in scope
            if self._matches_facets(it, facets) and self._matches_fields(it, fields_sel)
        ]
        if sort == "title":
            matched.sort(key=lambda it: it.title_key)
        else:  # "recent" (default): newest captured first
            matched.sort(key=lambda it: it.captured, reverse=True)
        total = len(matched)
        page = matched[offset : offset + limit] if limit else matched[offset:]
        return {"total": total, "records": [it.summary for it in page]}

    # ---- typed conditions (the "narrow on a field" layer) ----

    def _field_raw(self, it: IndexedRecord, fid: str) -> Any:
        """Raw value of a field id on a record. `core::<name>` reads the summary/size;
        `<overlayKey>::<field>` reads the block-field index."""
        if fid.startswith("core::"):
            name = fid[len("core::") :]
            if name == "title":
                return it.summary["title"] or None
            if name == "description":
                return it.summary["description"] or None
            if name == "size_mb":
                return (it.size / 1_000_000) if it.size else None
            if name == "captured":
                return it.captured or None
            return None
        overlay_key, sep, fname = fid.partition("::")
        if not sep:
            return None
        return it.block_fields.get(overlay_key, {}).get(fname)

    def _match_cond(self, it: IndexedRecord, cond: dict[str, Any]) -> bool:
        raw = self._field_raw(it, cond["fid"])
        if raw is None or (isinstance(raw, list) and not raw):
            return False
        op, ctype, val = cond["op"], cond["type"], cond["value"]
        if op == "between":
            if ctype == "date":
                d = _date_to_ms(raw) if not isinstance(raw, list) else None
                return d is not None and val[0] <= d <= val[1]
            try:
                n = float(raw)
            except (TypeError, ValueError):
                return False
            return val[0] <= n <= val[1]
        if op == "contains":
            return str(val).lower() in str(raw).lower()
        if op == "in":
            have = {str(x) for x in raw} if isinstance(raw, list) else {str(raw)}
            return bool(have & {str(x) for x in val})
        if op == "is":
            return (str(raw).strip().lower() == "true") == bool(val)
        return True

    def _matches_conds(self, it: IndexedRecord, conds: list[dict[str, Any]]) -> bool:
        return all(self._match_cond(it, c) for c in conds)

    @staticmethod
    def _in_range(it: IndexedRecord, rng: tuple[int, int] | None) -> bool:
        if rng is None:
            return True
        return it.captured_ms is not None and rng[0] <= it.captured_ms <= rng[1]

    # ---- typed field registry (global stats, the design's `labFields`) ----

    @staticmethod
    def _core_field_defs() -> list[tuple[str, str, str, str, Any]]:
        """`(id, field, label, type, accessor)` for the record-level baseline fields."""
        return [
            ("core::title", "title", "title", "string", lambda it: it.summary["title"] or None),
            (
                "core::description",
                "description",
                "description",
                "string",
                lambda it: it.summary["description"] or None,
            ),
            (
                "core::size_mb",
                "size_mb",
                "size · MB",
                "number",
                lambda it: (it.size / 1_000_000) if it.size else None,
            ),
        ]

    def fields(self) -> list[dict[str, Any]]:
        """The whole-corpus typed field registry: core baseline + every overlay's extended
        fields, each with global per-type stats. Cached (the controls show global
        distributions; availability is scoped separately)."""
        if self._fields_cache is not None:
            return self._fields_cache
        out: list[dict[str, Any]] = []

        for fid, fname, label, ftype, acc in self._core_field_defs():
            raw, coverage = self._collect(self.items, acc)
            if not raw:
                continue
            stats = _compute_stats(ftype, raw)
            if stats is None:
                continue
            out.append(
                {
                    "id": fid,
                    "key": None,
                    "group": "core",
                    "groupLabel": "record",
                    "field": fname,
                    "label": label,
                    "type": ftype,
                    "coverage": coverage,
                    "stats": stats,
                }
            )

        for okey in sorted(self.overlay_values):
            declared = dict(_declared_fields(self.entry.root, okey))
            samples = self.overlay_sample.get(okey, {})
            group, glabel = _overlay_group(okey)
            for fname in self.overlay_values[okey]:
                ftype = serialize.normalize_type(declared.get(fname), fname, samples.get(fname))
                raw, coverage = self._collect(
                    self.items, lambda it, k=okey, f=fname: it.block_fields.get(k, {}).get(f)
                )
                if not raw:
                    continue
                stats = _compute_stats(ftype, raw)
                if stats is None:
                    continue
                out.append(
                    {
                        "id": f"{okey}::{fname}",
                        "key": okey,
                        "group": group,
                        "groupLabel": glabel,
                        "field": fname,
                        "label": _humanize(fname),
                        "type": ftype,
                        "coverage": coverage,
                        "stats": stats,
                    }
                )
        self._fields_cache = out
        return out

    @staticmethod
    def _collect(items: list[IndexedRecord], accessor: Any) -> tuple[list[Any], int]:
        raw: list[Any] = []
        coverage = 0
        for it in items:
            v = accessor(it)
            if not _present(v):
                continue
            coverage += 1
            if isinstance(v, list):
                raw.extend(v)
            else:
                raw.append(v)
        return raw, coverage

    # ---- the combined workbench query ----

    def workbench(
        self,
        *,
        q: str = "",
        saved_view: str = "all",
        facets: dict[str, set[str]] | None = None,
        conds: list[dict[str, Any]] | None = None,
        rng: tuple[int, int] | None = None,
        sort: str = "recent",
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Everything every pane needs in one pass. `tl_scope` is the in-scope set MINUS
        the timeline's own range, so the histogram shows the full distribution you brush
        within; `narrowed` adds the range and drives records/facets/fields/overview."""
        facets = facets or {}
        conds = conds or []
        base = self._scope(q, saved_view)
        constrained = [
            it
            for it in base
            if self._matches_facets(it, facets) and self._matches_conds(it, conds)
        ]
        narrowed = [it for it in constrained if self._in_range(it, rng)]

        if sort == "title":
            ordered = sorted(narrowed, key=lambda it: it.title_key)
        else:
            ordered = sorted(narrowed, key=lambda it: it.captured, reverse=True)
        total = len(ordered)
        page = ordered[offset : offset + limit] if limit else ordered[offset:]

        return {
            "total": total,
            "records": [self._row(it) for it in page],
            "facetStack": self._facet_stack(narrowed, facets),
            "timeline": self._timeline(constrained, rng),
            "availableFields": self._available_field_ids(narrowed, facets),
            "overview": self._overview(narrowed),
        }

    @staticmethod
    def _row(it: IndexedRecord) -> dict[str, Any]:
        name = serialize.transport_name(it.summary.get("id") or "", it.summary.get("mime") or "")
        return {
            **it.summary,
            "size": it.size,
            "segments": it.segment_count,
            "transport_name": name,
        }

    # ---- graph (record connections) ----

    def _by_id(self) -> dict[str, IndexedRecord]:
        if self._by_id_cache is None:
            self._by_id_cache = {
                str(it.summary.get("id")): it for it in self.items if it.summary.get("id")
            }
        return self._by_id_cache

    def _uri_index(self) -> dict[str, str]:
        """The corpus-wide URI → record-id index (origin URIs), built once and cached on
        the index instance — so the graph route stays cheap. Refreshed implicitly: a write
        rebuilds the whole CorpusIndex (a fresh instance), dropping this cache with it."""
        if self._uri_index_cache is None:
            self._uri_index_cache = records.build_uri_index(self.entry.root)
        return self._uri_index_cache

    def graph(self, post: Any) -> dict[str, Any]:
        """The record's connection graph: resolved (origins · embeds · classification-shared
        records · captured cross-refs) + uncaptured outbound links. `post` is the loaded
        record (the route loads it for the existence check, same as record_detail)."""
        from corpus import graph as graph_mod

        rid = str(post.metadata.get("id") or "")
        resolved: list[dict[str, Any]] = []

        for i, origin in enumerate(records.iter_origin_blocks(post)):
            fields = origin.get("fields") or {}
            uri = fields.get("uri")
            first = (uri[0] if isinstance(uri, list) and uri else uri) or ""
            host = serialize.host_of(str(first)) if first else (origin.get("id") or "origin")
            resolved.append(
                {
                    "id": f"origin:{i}",
                    "kind": "origin",
                    "label": host,
                    "sub": f"origin · {origin.get('id') or ''}".rstrip(" ·"),
                    "recId": None,
                    "url": str(first) or None,
                }
            )

        for i, embed in enumerate(records.iter_embed_blocks(post)):
            mt = embed.get("media_type") or ""
            efields = embed.get("fields") or {}
            sub = str(efields.get("alt") or embed.get("address") or "")[:40]
            resolved.append(
                {
                    "id": f"embed:{i}",
                    "kind": "embed",
                    "label": f"{mime_short(mt)} embed",
                    "sub": sub or "embed",
                    "recId": None,
                    "url": None,
                }
            )

        me = self._by_id().get(rid)
        if me and me.composites:
            mine = set(me.composites)
            shared = [
                it
                for it in self.items
                if str(it.summary.get("id")) != rid and mine.intersection(it.composites)
            ]
            shared.sort(key=lambda it: it.captured, reverse=True)
            for it in shared[:8]:
                sid = str(it.summary.get("id"))
                resolved.append(
                    {
                        "id": f"rec:{sid}",
                        "kind": "record",
                        "label": it.summary.get("title") or self._row(it)["transport_name"],
                        "sub": "shares classification",
                        "recId": sid,
                        "url": None,
                    }
                )

        uncaptured: list[dict[str, Any]] = []
        for n, link in enumerate(graph_mod.build_links(self.entry.root, post, uri_index=self._uri_index())):
            node = {
                "id": f"link:{n}",
                "kind": "link",
                "label": link["url"],
                "host": link["host"],
                "url": link["url"],
                "recId": link["recId"],
            }
            if link["recId"]:
                node["sub"] = f"captured · {link['host']}"
                resolved.append(node)
            else:
                node["sub"] = f"uncaptured · {link['host']}"
                uncaptured.append(node)

        return {"resolved": resolved, "uncaptured": uncaptured}

    def _facet_stack(
        self, scope: list[IndexedRecord], sel: dict[str, set[str]]
    ) -> list[dict[str, Any]]:
        """Drill-down facets over the in-scope set (include-self pure-AND): a selected
        facet collapses to what's reachable while the others narrow alongside. Order:
        status · mime · embed-mime · origin · composite:* · visibility."""
        counters: dict[str, dict[str, int]] = {}
        labels: dict[str, str] = {}
        composite_ns: set[str] = set()

        def bump(key: str, label: str, value: str) -> None:
            labels[key] = label
            c = counters.setdefault(key, {})
            c[value] = c.get(value, 0) + 1

        for it in scope:
            if it.status:
                bump("status", "status", it.status)
            if it.mime:
                bump("mime", "mime", it.mime)
            for em in it.embed_mimes:
                bump("embedmime", "embed mime", em)
            for h in it.hosts:
                bump("origin", "origin", h)
            for ns, cid in it.composites:
                bump(f"composite:{ns}", ns, cid)
                composite_ns.add(ns)
            if it.visibility and it.visibility != "visible":
                bump("visibility", "visibility", it.visibility)

        for key in sel:
            if key.startswith("composite:"):
                composite_ns.add(key[len("composite:") :])

        order = ["status", "mime", "embedmime", "origin"]
        order += [f"composite:{ns}" for ns in sorted(composite_ns)]
        order += ["visibility"]

        out: list[dict[str, Any]] = []
        for key in order:
            counts = dict(counters.get(key) or {})
            for v in sel.get(key, set()):  # keep a selected value visible even at n=0
                counts.setdefault(v, 0)
            if not counts:
                continue
            values = [
                {"v": v, "n": n, "label": mime_short(v) if key == "mime" else v}
                for v, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ]
            label = labels.get(key) or key.split(":")[-1]
            out.append({"key": key, "label": label, "values": values})
        return out

    def _timeline(
        self, tl_scope: list[IndexedRecord], rng: tuple[int, int] | None
    ) -> dict[str, Any]:
        min_ms, max_ms = self.full_span
        span = (max_ms - min_ms) or 1
        nbins = 48
        bins = [{"n": 0, "normalized": 0, "draft": 0, "stub": 0} for _ in range(nbins)]
        for it in tl_scope:
            if it.captured_ms is None:
                continue
            i = int((it.captured_ms - min_ms) / span * nbins)
            b = bins[min(max(i, 0), nbins - 1)]
            b["n"] += 1
            lane = it.status if it.status in ("normalized", "draft") else "stub"
            b[lane] += 1

        in_range = [it for it in tl_scope if self._in_range(it, rng)]
        rdates = sorted(it.captured_ms for it in in_range if it.captured_ms is not None)
        origins: set[str] = set()
        for it in in_range:
            origins.update(it.hosts)
        return {
            "span": [min_ms, max_ms],
            "binCount": nbins,
            "bins": bins,
            "inRange": {
                "count": len(in_range),
                "normalized": sum(1 for it in in_range if it.status == "normalized"),
                "drafts": sum(1 for it in in_range if it.status == "draft"),
                "stubs": sum(1 for it in in_range if it.status not in ("normalized", "draft")),
                "origins": len(origins),
                "spanDays": round((rdates[-1] - rdates[0]) / _DAYMS) if len(rdates) >= 2 else 0,
            },
        }

    def _available_field_ids(
        self, narrowed: list[IndexedRecord], sel: dict[str, set[str]]
    ) -> list[str]:
        """The field ids you can narrow on next: core baseline always, plus a selected
        overlay's extended fields — only those actually present in the narrowed set."""
        ids: list[str] = []
        for fid, _f, _lbl, _t, acc in self._core_field_defs():
            if any(_present(acc(it)) for it in narrowed):
                ids.append(fid)

        selected_overlays: set[str] = set()
        for m in sel.get("mime", set()):
            selected_overlays.add(f"mime/{m}")
        for h in sel.get("origin", set()):
            selected_overlays.add(f"origin/{h}")
        for key, vals in sel.items():
            if key.startswith("composite:"):
                ns = key[len("composite:") :]
                for cid in vals:
                    selected_overlays.add(f"composite/{ns}/{cid}")

        for okey in sorted(selected_overlays):
            for fname in self.overlay_values.get(okey, {}):
                if any(_present(it.block_fields.get(okey, {}).get(fname)) for it in narrowed):
                    ids.append(f"{okey}::{fname}")
        return ids

    def _overview(self, narrowed: list[IndexedRecord]) -> dict[str, Any]:
        n = len(narrowed)
        norm = sum(1 for it in narrowed if it.status == "normalized")
        size_mb = sum((it.size or 0) for it in narrowed) / 1_000_000
        dates = sorted(it.captured_ms for it in narrowed if it.captured_ms is not None)
        span_days = round((dates[-1] - dates[0]) / _DAYMS) if len(dates) >= 2 else 0

        def dist(key_fn: Any) -> list[list[Any]]:
            counter: Counter[str] = Counter()
            for it in narrowed:
                for k in key_fn(it):
                    counter[k] += 1
            return [[k, v] for k, v in counter.most_common()]

        atom_total: Counter[str] = Counter()
        for it in narrowed:
            atom_total.update(it.atom_counts)

        return {
            "headline": {
                "records": n,
                "pctNormalized": round(norm / n * 100) if n else 0,
                "sizeMB": round(size_mb, 1),
                "spanDays": span_days,
            },
            "dists": {
                "byMime": dist(lambda it: [mime_short(it.mime)] if it.mime else []),
                "byStatus": dist(lambda it: [it.status] if it.status else []),
                "byAtom": [[k, v] for k, v in atom_total.most_common()],
                "byOrigin": dist(lambda it: it.hosts),
                "byGenre": dist(
                    lambda it: [cid for (ns, cid) in it.composites if ns == "genre"]
                ),
            },
        }


def _declared_fields(corpus_root: Path, overlay_key: str) -> list[tuple[str, str | None]]:
    """`(field, declared_type)` pairs for an overlay key, in schema order. Empty when
    the schema is absent (bare origins, undeclared composites) -> types are inferred."""
    schema: dict[str, Any] | None = None
    if overlay_key.startswith("mime/"):
        schema = schemas.load_mime_schema(corpus_root, overlay_key[len("mime/") :])
    elif overlay_key.startswith("origin/"):
        schema = schemas.load_origin_overlay_by_id(corpus_root, overlay_key[len("origin/") :])
    elif overlay_key.startswith("composite/"):
        schema = schemas.load_classification_schema(corpus_root, overlay_key[len("composite/") :])
    if not schema:
        return []
    ext = schema.get("extended_fields") or {}
    out: list[tuple[str, str | None]] = []
    for fname, spec in ext.items():
        declared = (spec or {}).get("type") if isinstance(spec, dict) else None
        out.append((fname, declared))
    return out


# ---- process cache ----

_CACHE: dict[str, CorpusIndex] = {}


def get_index(entry: CorpusEntry, *, fresh: bool = False) -> CorpusIndex:
    cache_key = f"{entry.id}:{entry.root}"
    if fresh or cache_key not in _CACHE:
        _CACHE[cache_key] = CorpusIndex.build(entry)
    return _CACHE[cache_key]
