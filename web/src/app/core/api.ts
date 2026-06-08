import { Injectable } from '@angular/core';

export interface RecordsRequest {
  base: string;
  corpus: string;
  q: string;
  view: string;
  sort: string;
  offset: number;
  limit: number;
  facets: string[]; // "facetKey=value"
  fields: string[]; // "overlayKey::field=value"
}

export interface WorkbenchRequest {
  base: string;
  corpus: string;
  q: string;
  view: string;
  sort: string;
  offset: number;
  limit: number;
  facets: string[]; // "facetKey=value"
  conds: string[]; // "fid~type~op~value"
  range: string; // "loMs,hiMs" | ""
}

/**
 * Pure URL builders for the `corpus.api` server. The store feeds these into
 * `httpResource(() => url)` so fetches re-run reactively when the URL changes.
 *
 * Encoding matters: facet/field/query values go through URLSearchParams (so `+`,
 * `/`, `=` inside a value are escaped); a functional-URI value is fully
 * percent-encoded because the server parses one `uri=` param and `&` inside it
 * would otherwise split into separate params (proven in the API smoke tests).
 */
@Injectable({ providedIn: 'root' })
export class CorpusApiService {
  corporaUrl(base: string): string {
    return `${base}/corpora`;
  }

  facetsUrl(base: string, corpus: string, q: string, view: string): string {
    const p = new URLSearchParams({ q, view });
    return `${base}/${corpus}/facets?${p}`;
  }

  schemaUrl(base: string, corpus: string): string {
    return `${base}/${corpus}/schema`;
  }

  recordsUrl(req: RecordsRequest): string {
    const p = new URLSearchParams();
    if (req.q) p.set('q', req.q);
    p.set('view', req.view);
    p.set('sort', req.sort);
    p.set('offset', String(req.offset));
    p.set('limit', String(req.limit));
    for (const f of req.facets) p.append('facet', f);
    for (const f of req.fields) p.append('field', f);
    return `${req.base}/${req.corpus}/records?${p}`;
  }

  /** Combined workbench query — records + drill-down facet stack + timeline + available
   *  fields + overview, all over the narrowed set. */
  workbenchUrl(req: WorkbenchRequest): string {
    const p = new URLSearchParams();
    if (req.q) p.set('q', req.q);
    p.set('view', req.view);
    p.set('sort', req.sort);
    p.set('offset', String(req.offset));
    p.set('limit', String(req.limit));
    for (const f of req.facets) p.append('facet', f);
    for (const c of req.conds) p.append('cond', c);
    if (req.range) p.set('range', req.range);
    return `${req.base}/${req.corpus}/workbench?${p}`;
  }

  /** Whole-corpus typed field registry (global stats) for the field controls + palette. */
  fieldsUrl(base: string, corpus: string): string {
    return `${base}/${corpus}/fields`;
  }

  recordUrl(base: string, corpus: string, id: string): string {
    return `${base}/${corpus}/records/${id}`;
  }

  /** The record's connection graph (resolved + uncaptured outbound links) for graph mode. */
  graphUrl(base: string, corpus: string, id: string): string {
    return `${base}/${corpus}/records/${id}/graph`;
  }

  artifactUrl(base: string, corpus: string, id: string): string {
    return `${base}/${corpus}/artifacts/${id}`;
  }

  resolveUrl(base: string, corpus: string, uri: string): string {
    return `${base}/${corpus}/resolve?uri=${encodeURIComponent(uri)}`;
  }

  regionsUrl(base: string, corpus: string, id: string): string {
    return `${base}/${corpus}/records/${id}/regions`;
  }

  /** POST drawn crop regions to the write endpoint. A non-2xx surfaces the API's
   *  `detail` message as an Error (422 detail is a list — stringify it). */
  async saveRegions(
    base: string,
    corpus: string,
    id: string,
    regions: RegionPayload[],
  ): Promise<SaveRegionsResult> {
    const res = await fetch(this.regionsUrl(base, corpus, id), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ regions }),
    });
    if (!res.ok) {
      let msg = `region save failed (${res.status})`;
      try {
        const j = await res.json();
        if (j?.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
      } catch {
        /* non-JSON error body */
      }
      throw new Error(msg);
    }
    return res.json() as Promise<SaveRegionsResult>;
  }
}

/** One region in the crop-save payload — mirrors the API's `RegionIn`. */
export interface RegionPayload {
  page?: number | null;
  box: [number, number, number, number];
  atom: string;
  overlay?: string;
  entry?: string;
}

export interface SaveRegionsResult {
  record_id: string;
  segment_count: number;
  bbox_segment_count: number;
  addresses: string[];
  status: string | null;
  touch: string[];
}
