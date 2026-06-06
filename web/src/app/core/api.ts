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

  recordUrl(base: string, corpus: string, id: string): string {
    return `${base}/${corpus}/records/${id}`;
  }

  artifactUrl(base: string, corpus: string, id: string): string {
    return `${base}/${corpus}/artifacts/${id}`;
  }

  resolveUrl(base: string, corpus: string, uri: string): string {
    return `${base}/${corpus}/resolve?uri=${encodeURIComponent(uri)}`;
  }
}
