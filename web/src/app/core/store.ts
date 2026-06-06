import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { httpResource } from '@angular/common/http';
import { CorpusApiService, RecordsRequest } from './api';
import { Corpus, Endpoint, Facet, QueryResult, RecordDetail, SchemaRegistry } from './models';

export type ViewMode = 'columns' | 'table' | 'gallery' | 'cards';
export type SortMode = 'recent' | 'title';
export type AppMode = 'browse' | 'record' | 'crop';

/** Default API base follows the host the app was loaded from, so the same build
 *  works locally (localhost:8099) and over the Tailnet (example-host…ts.net:8099) without
 *  a rebuild. Override via the endpoint switcher. */
function defaultBase(): string {
  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8099/v1`;
  }
  return 'http://127.0.0.1:8099/v1';
}

const DEFAULT_ENDPOINTS: Endpoint[] = [
  { id: 'api', base: defaultBase(), label: 'api', online: true, corpora: [] },
];

/**
 * The single source of UI + query state, mirroring the prototype's `CorpusApp`
 * orchestration but server-fed. State is signals; data is `httpResource` (auto
 * re-fetches when the derived URL changes). Faceting/refinement run server-side;
 * the rail's universal-filter / pin / refinement UX stays client-side.
 */
@Injectable({ providedIn: 'root' })
export class CorpusStore {
  private api = inject(CorpusApiService);

  // ---- endpoints / corpus ----
  readonly endpoints = signal<Endpoint[]>(DEFAULT_ENDPOINTS);
  readonly endpointId = signal(DEFAULT_ENDPOINTS[0].id);
  readonly endpoint = computed(
    () => this.endpoints().find((e) => e.id === this.endpointId()) ?? this.endpoints()[0],
  );
  readonly base = computed(() => this.endpoint().base);
  readonly corpusId = signal('');

  // ---- filters / view state ----
  readonly query = signal('');
  readonly selection = signal<Record<string, Set<string>>>({});
  readonly fieldSel = signal<Record<string, Set<string>>>({});
  readonly savedView = signal('all');
  readonly view = signal<ViewMode>('columns');
  readonly sort = signal<SortMode>('recent');

  // ---- ui state ----
  readonly mode = signal<AppMode>('browse');
  readonly recordId = signal<string | null>(null);
  readonly theme = signal<'theme-light' | 'theme-dark'>('theme-light');
  readonly density = signal<'dens-dense' | 'dens-comfy' | 'dens-spacious'>('dens-comfy');
  readonly submitOpen = signal(false); // next-phase surface (stub dialog)
  readonly drawerOpen = signal(false); // mobile facets drawer

  // ---- resources ----
  readonly corporaRes = httpResource<Corpus[]>(() => this.api.corporaUrl(this.base()));
  readonly corpora = computed(() => this.corporaRes.value() ?? []);
  readonly corpus = computed(
    () => this.corpora().find((c) => c.id === this.corpusId()) ?? this.corpora()[0],
  );

  readonly facetsRes = httpResource<Facet[]>(() =>
    this.corpusId()
      ? this.api.facetsUrl(this.base(), this.corpusId(), this.query(), this.savedView())
      : undefined,
  );
  readonly facets = computed(() => this.facetsRes.value() ?? []);

  readonly schemaRes = httpResource<SchemaRegistry>(() =>
    this.corpusId() ? this.api.schemaUrl(this.base(), this.corpusId()) : undefined,
  );
  readonly schema = computed(() => this.schemaRes.value() ?? {});

  readonly recordsReq = computed<RecordsRequest | null>(() => {
    if (!this.corpusId()) return null;
    const facets: string[] = [];
    for (const [k, set] of Object.entries(this.selection())) {
      for (const v of set) facets.push(`${k}=${v}`);
    }
    const fields: string[] = [];
    for (const [k, set] of Object.entries(this.fieldSel())) {
      for (const v of set) fields.push(`${k}=${v}`);
    }
    return {
      base: this.base(),
      corpus: this.corpusId(),
      q: this.query(),
      view: this.savedView(),
      sort: this.sort(),
      offset: 0,
      limit: 2000,
      facets,
      fields,
    };
  });
  readonly recordsRes = httpResource<QueryResult>(() => {
    const req = this.recordsReq();
    return req ? this.api.recordsUrl(req) : undefined;
  });
  readonly records = computed(() => this.recordsRes.value()?.records ?? []);
  readonly total = computed(() => this.recordsRes.value()?.total ?? 0);
  readonly loading = computed(() => this.recordsRes.isLoading());

  readonly recordRes = httpResource<RecordDetail>(() => {
    const id = this.recordId();
    return this.mode() === 'record' && id && this.corpusId()
      ? this.api.recordUrl(this.base(), this.corpusId(), id)
      : undefined;
  });
  readonly record = computed(() => this.recordRes.value() ?? null);

  readonly selectionCount = computed(() => sumSets(this.selection()) + sumSets(this.fieldSel()));

  constructor() {
    // default-select the first corpus when corpora load or the endpoint switches
    effect(() => {
      const list = this.corpora();
      if (list.length && !list.some((c) => c.id === this.corpusId())) {
        this.corpusId.set(list[0].id);
      }
    });
  }

  // ---- url helpers for the artifact pane ----
  artifactUrl(id: string): string {
    return this.api.artifactUrl(this.base(), this.corpusId(), id);
  }
  resolveUrl(uri: string): string {
    return this.api.resolveUrl(this.base(), this.corpusId(), uri);
  }

  // ---- actions ----
  setEndpoint(id: string): void {
    this.endpointId.set(id);
    this.resetFilters();
    this.mode.set('browse');
  }
  addEndpoint(base: string): void {
    const id = 'ep' + (this.endpoints().length + 1);
    this.endpoints.update((list) => [
      ...list,
      { id, base, label: base, online: true, corpora: [] },
    ]);
    this.setEndpoint(id);
  }
  setCorpus(id: string): void {
    this.corpusId.set(id);
    this.resetFilters();
    this.mode.set('browse');
    this.drawerOpen.set(false);
  }
  setSavedView(v: string): void {
    this.savedView.set(v);
    this.mode.set('browse');
  }
  setQuery(q: string): void {
    this.query.set(q);
  }
  setView(v: ViewMode): void {
    this.view.set(v);
  }
  setSort(s: SortMode): void {
    this.sort.set(s);
  }

  toggleFacet(facetKey: string, value: string): void {
    this.selection.update((sel) => toggleIn(sel, facetKey, value));
  }
  toggleField(overlayKey: string, field: string, value: string): void {
    this.fieldSel.update((sel) => toggleIn(sel, `${overlayKey}::${field}`, value));
  }
  clearAll(): void {
    this.selection.set({});
    this.fieldSel.set({});
  }
  private resetFilters(): void {
    this.selection.set({});
    this.fieldSel.set({});
    this.savedView.set('all');
    this.query.set('');
  }

  openRecord(id: string): void {
    this.recordId.set(id);
    this.mode.set('record');
    this.drawerOpen.set(false);
  }
  back(): void {
    this.mode.set('browse');
  }
  openCrop(): void {
    this.mode.set('crop'); // next-phase surface
  }
  openSubmit(): void {
    this.submitOpen.set(true);
  }
  closeSubmit(): void {
    this.submitOpen.set(false);
  }
  openDrawer(): void {
    this.drawerOpen.set(true);
  }
  closeDrawer(): void {
    this.drawerOpen.set(false);
  }

  toggleTheme(): void {
    this.theme.update((t) => (t === 'theme-dark' ? 'theme-light' : 'theme-dark'));
  }
  cycleDensity(): void {
    this.density.update((d) =>
      d === 'dens-dense' ? 'dens-comfy' : d === 'dens-comfy' ? 'dens-spacious' : 'dens-dense',
    );
  }
}

function sumSets(rec: Record<string, Set<string>>): number {
  return Object.values(rec).reduce((n, s) => n + s.size, 0);
}
function toggleIn(
  rec: Record<string, Set<string>>,
  key: string,
  value: string,
): Record<string, Set<string>> {
  const next = { ...rec };
  const set = new Set(next[key] ?? []);
  if (set.has(value)) set.delete(value);
  else set.add(value);
  if (set.size) next[key] = set;
  else delete next[key];
  return next;
}
