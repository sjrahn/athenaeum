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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from corpus import records, schemas
from corpus.api import serialize
from corpus.api.config import CorpusEntry

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


@dataclass
class CorpusIndex:
    entry: CorpusEntry
    items: list[IndexedRecord] = field(default_factory=list)
    # overlayKey -> field -> ordered distinct stringified values (for the registry)
    overlay_values: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    # overlayKey -> field -> first raw value (for type inference)
    overlay_sample: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ---- build ----

    @classmethod
    def build(cls, entry: CorpusEntry) -> CorpusIndex:
        idx = cls(entry=entry)
        for _path, post in records.load_all(entry.root):
            idx._ingest(post)
        return idx

    def _ingest(self, post: Any) -> None:
        mime = records.media_type_for(post)
        summary = serialize.record_summary(post, self.entry.id)
        contexts = post.metadata.get("_contexts") or []
        embeds = post.metadata.get("_embeds") or []

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
