import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { httpResource } from '@angular/common/http';
import { CorpusApiService, RecordsRequest, WorkbenchRequest } from './api';
import {
  Cond,
  Corpus,
  Endpoint,
  Facet,
  FieldStat,
  QueryResult,
  RecordDetail,
  SchemaRegistry,
  WorkbenchResponse,
} from './models';

export type ViewMode = 'columns' | 'table' | 'gallery' | 'cards';
export type LedgerView = 'ledger' | 'gallery' | 'cards';
export type SortMode = 'recent' | 'title';
// 'browse' is the legacy Corpus Console surface; 'workbench' supersedes it (Part F swap).
export type AppMode = 'workbench' | 'browse' | 'record' | 'crop';
export type TlMode = 'strip' | 'brush' | 'lanes';
export type WorkMode = 'inspect' | 'compare' | 'crop' | 'graph';

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

  // ---- workbench filter state (the design's shared CorpusWorkbench state) ----
  readonly conds = signal<Record<string, Cond>>({}); // fid -> typed condition
  readonly tlRange = signal<[number, number] | null>(null); // captured-date brush (ms)
  readonly tlDay = signal<number | null>(null); // day cursor (highlight only, no filter)
  readonly tlMode = signal<TlMode>('brush');
  readonly ledgerView = signal<LedgerView>('ledger');
  readonly selectedId = signal<string | null>(null); // ledger selection -> detail pane
  readonly paletteOpen = signal(false); // ⌘K command palette
  readonly workMode = signal<WorkMode>('inspect'); // record workbench work mode

  // ---- ui state ----
  readonly mode = signal<AppMode>('workbench');
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

  // ---- workbench resources ----
  // The whole-corpus typed field registry (global stats) — the field controls + palette
  // read this; the per-query availableFields is just a gated id list joined against it.
  readonly fieldsRes = httpResource<FieldStat[]>(() =>
    this.corpusId() ? this.api.fieldsUrl(this.base(), this.corpusId()) : undefined,
  );
  readonly fields = computed(() => this.fieldsRes.value() ?? []);
  readonly fieldById = computed(() => new Map(this.fields().map((f) => [f.id, f])));

  readonly workbenchReq = computed<WorkbenchRequest | null>(() => {
    if (!this.corpusId()) return null;
    const facets: string[] = [];
    for (const [k, set] of Object.entries(this.selection())) {
      for (const v of set) facets.push(`${k}=${v}`);
    }
    const conds: string[] = [];
    for (const c of Object.values(this.conds())) {
      if (this.condActive(c)) conds.push(encodeCond(c));
    }
    const rng = this.tlRange();
    return {
      base: this.base(),
      corpus: this.corpusId(),
      q: this.query(),
      view: this.savedView(),
      sort: this.sort(),
      offset: 0,
      limit: 2000,
      facets,
      conds,
      range: rng ? `${rng[0]},${rng[1]}` : '',
    };
  });
  readonly workbenchRes = httpResource<WorkbenchResponse>(() => {
    const req = this.workbenchReq();
    return req ? this.api.workbenchUrl(req) : undefined;
  });
  readonly wb = computed(() => this.workbenchRes.value() ?? null);
  readonly wbRows = computed(() => this.wb()?.records ?? []);
  readonly wbTotal = computed(() => this.wb()?.total ?? 0);
  readonly wbFacetStack = computed(() => this.wb()?.facetStack ?? []);
  readonly wbTimeline = computed(() => this.wb()?.timeline ?? null);
  readonly wbOverview = computed(() => this.wb()?.overview ?? null);
  readonly wbLoading = computed(() => this.workbenchRes.isLoading());
  /** Available field ids joined to their registry defs (gated to the narrowed set). */
  readonly availableFields = computed<FieldStat[]>(() => {
    const ids = this.wb()?.availableFields ?? [];
    const by = this.fieldById();
    const added = this.conds();
    return ids.map((id) => by.get(id)).filter((f): f is FieldStat => !!f && !added[f.id]);
  });
  /** The conditions added to the filter (rendered with their controls). */
  readonly addedConds = computed<{ field: FieldStat; cond: Cond }[]>(() => {
    const by = this.fieldById();
    return Object.values(this.conds())
      .map((c) => ({ field: by.get(c.fid)!, cond: c }))
      .filter((x) => !!x.field);
  });

  // The detail pane (right) shows the ledger-selected record's full detail.
  readonly selectedRes = httpResource<RecordDetail>(() => {
    const id = this.selectedId();
    return this.mode() === 'workbench' && id && this.corpusId()
      ? this.api.recordUrl(this.base(), this.corpusId(), id)
      : undefined;
  });
  readonly selected = computed(() => this.selectedRes.value() ?? null);

  readonly filterCount = computed(
    () =>
      sumSets(this.selection()) +
      Object.values(this.conds()).filter((c) => this.condActive(c)).length +
      (this.query().trim() ? 1 : 0) +
      (this.tlRange() ? 1 : 0),
  );

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
    this.mode.set('workbench');
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
    this.mode.set('workbench');
    this.drawerOpen.set(false);
  }
  setSavedView(v: string): void {
    this.savedView.set(v);
    this.mode.set('workbench');
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
    this.conds.set({});
    this.tlRange.set(null);
    this.query.set('');
  }
  private resetFilters(): void {
    this.selection.set({});
    this.fieldSel.set({});
    this.conds.set({});
    this.tlRange.set(null);
    this.tlDay.set(null);
    this.savedView.set('all');
    this.query.set('');
    this.selectedId.set(null);
  }

  // ---- workbench actions ----
  /** A condition is active (sent to the server) only when it actually narrows: a non-full
   *  range, a non-empty contains/checklist, or any bool. Inactive conds stay added (their
   *  control renders) but don't filter — mirrors the design's `labCondIsEmpty`. */
  condActive(c: Cond): boolean {
    if (c.op === 'contains') return !!String(c.value ?? '').trim();
    if (c.op === 'in') return Array.isArray(c.value) && c.value.length > 0;
    if (c.op === 'between') {
      const f = this.fieldById().get(c.fid);
      const v = c.value as [number, number];
      if (!f || !Array.isArray(v)) return true;
      const { min, max } = f.stats;
      return !(v[0] <= (min ?? -Infinity) && v[1] >= (max ?? Infinity));
    }
    return true; // is
  }
  setCond(fid: string, cond: Cond): void {
    this.conds.update((cs) => ({ ...cs, [fid]: cond }));
  }
  removeCond(fid: string): void {
    this.conds.update((cs) => {
      const next = { ...cs };
      delete next[fid];
      return next;
    });
  }
  setTlRange(r: [number, number] | null): void {
    this.tlRange.set(r);
  }
  setTlDay(d: number | null): void {
    this.tlDay.set(d);
  }
  setTlMode(m: TlMode): void {
    this.tlMode.set(m);
  }
  setLedgerView(v: LedgerView): void {
    this.ledgerView.set(v);
  }
  selectRecord(id: string | null): void {
    this.selectedId.set(id);
  }
  openPalette(): void {
    this.paletteOpen.set(true);
  }
  closePalette(): void {
    this.paletteOpen.set(false);
  }
  togglePalette(): void {
    this.paletteOpen.update((o) => !o);
  }
  setWorkMode(m: WorkMode): void {
    this.workMode.set(m);
  }

  openRecord(id: string): void {
    this.recordId.set(id);
    this.selectedId.set(id);
    this.workMode.set('inspect');
    this.mode.set('record');
    this.paletteOpen.set(false);
    this.drawerOpen.set(false);
  }
  back(): void {
    this.mode.set('workbench');
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

/** Encode a condition for the `cond=` query param: `<fid>~<type>~<op>~<value>`. */
function encodeCond(c: Cond): string {
  let v: string;
  if (c.op === 'between') {
    const [lo, hi] = c.value as [number, number];
    v = `${lo},${hi}`;
  } else if (c.op === 'in') {
    v = (c.value as string[]).join(',');
  } else if (c.op === 'is') {
    v = c.value ? 'true' : 'false';
  } else {
    v = String(c.value ?? '');
  }
  return `${c.fid}~${c.type}~${c.op}~${v}`;
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
