// Left · Filter — a single coherent drill-down. One search box, a facet stack
// (status · mime · embed-mime · origin · composite:*) where every facet recomputes over
// the narrowed set (pure-AND, server-side), and a "narrow on a field" section offering the
// typed extended fields present in the narrowed set (overlay-gated) as typed conditions.

import { ChangeDetectionStrategy, Component, computed, inject, input, output, signal } from '@angular/core';
import { CorpusStore } from '../../core/store';
import { Cond, Facet, FieldStat } from '../../core/models';
import { CxTypeBadge } from '../../chips/chips';
import { WbFieldControl, defaultCond } from '../fields/field-controls';

/** One categorical facet group with live count bars + a "+N more" expander. */
@Component({
  selector: 'wb-facet-group',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="grp">
      <div class="hd" (click)="open.set(!open())">
        <span class="caret">{{ open() ? '▾' : '▸' }}</span>
        <span class="lbl" [class.comp]="isComposite()">{{ facet().label }}</span>
        @if (isComposite()) { <span class="tag">composite</span> }
        <span class="sp"></span>
        @if (sel().size > 0) { <span class="chk">{{ sel().size }} ✓</span> }
        <span class="cnt">{{ facet().values.length }}</span>
      </div>
      @if (open()) {
        <div class="vals">
          @for (v of shown(); track v.v) {
            <div class="row" [class.on]="sel().has(v.v)" (click)="toggle.emit(v.v)">
              <span class="box" [class.on]="sel().has(v.v)">@if (sel().has(v.v)) { ✓ }</span>
              <span class="v">{{ v.label || v.v }}</span>
              <span class="bar"><span [style.width.%]="(v.n / maxN()) * 100"></span></span>
              <span class="n">{{ v.n }}</span>
            </div>
          }
          @if (ordered().length > limit) {
            <div class="more" (click)="showAll.set(!showAll())">
              {{ showAll() ? '− less' : '+ ' + (ordered().length - limit) + ' more' }}
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .grp { border-bottom: 1px solid var(--border); }
    .hd { display: flex; align-items: center; gap: 6px; padding: 7px 12px; cursor: pointer; }
    .caret { color: var(--dim); font-size: 8px; width: 8px; }
    .lbl { font-size: 9.5px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.10em;
      font-weight: 600; }
    .lbl.comp { color: var(--accent); }
    .tag { font-size: 7.5px; color: var(--dim); border: 1px solid var(--border); padding: 0 3px; }
    .sp { flex: 1; }
    .chk { font-size: 8px; color: var(--accent); }
    .cnt { font-size: 8px; color: var(--dim); }
    .vals { padding-bottom: 5px; }
    .row { height: 22px; display: flex; align-items: center; gap: 7px; padding: 0 12px 0 26px;
      font-size: 10.5px; cursor: pointer; color: var(--text); }
    .row.on { background: var(--accent-soft); color: var(--accent); }
    .box { width: 9px; height: 9px; border: 1px solid var(--border-strong); flex-shrink: 0; display: flex;
      align-items: center; justify-content: center; font-size: 7px; color: #fff; }
    .box.on { background: var(--accent); border-color: var(--accent); }
    .v { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar { width: 24px; height: 4px; background: var(--border); position: relative; flex-shrink: 0; }
    .bar span { position: absolute; inset: 0; background: var(--border-strong); }
    .row.on .bar span { background: var(--accent); }
    .n { color: var(--dim); font-size: 9px; width: 20px; text-align: right; }
    .row.on .n { color: var(--accent); }
    .more { padding: 3px 12px 2px 26px; font-size: 9px; color: var(--dim); cursor: pointer; }
  `],
})
export class WbFacetGroup {
  facet = input.required<Facet>();
  sel = input.required<Set<string>>();
  defaultOpen = input(true);
  toggle = output<string>();
  readonly open = signal(true);
  readonly showAll = signal(false);
  readonly limit = 6;
  readonly isComposite = computed(() => this.facet().key.startsWith('composite:'));
  readonly maxN = computed(() => Math.max(1, ...this.facet().values.map((v) => v.n)));
  readonly ordered = computed(() => {
    const s = this.sel();
    return [...this.facet().values].sort((a, b) =>
      s.has(b.v) === s.has(a.v) ? b.n - a.n : s.has(b.v) ? 1 : -1,
    );
  });
  readonly shown = computed(() => (this.showAll() ? this.ordered() : this.ordered().slice(0, this.limit)));
  constructor() {
    this.open.set(true);
  }
}

@Component({
  selector: 'wb-filter',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [WbFacetGroup, WbFieldControl, CxTypeBadge],
  template: `
    <div class="filter">
      <!-- search + count -->
      <div class="top">
        <div class="search">
          <span class="ic">⌕</span>
          <input id="cx-search" [value]="store.query()" (input)="store.setQuery($any($event.target).value)"
            placeholder="search titles & content…" />
          @if (store.query()) { <span class="x" (click)="store.setQuery('')">×</span> }
        </div>
        <div class="count">
          <span class="acc">{{ store.wbTotal() }}</span><span class="dim">of {{ corpusTotal() }} narrowed</span>
          <span class="sp"></span>
          @if (store.filterCount() > 0) {
            <span class="reset" (click)="store.clearAll()">reset · {{ store.filterCount() }}</span>
          }
        </div>
      </div>

      <!-- added field filters (with their controls) -->
      @if (store.addedConds().length > 0) {
        <div class="added">
          <div class="t-label acc">field filters · {{ store.addedConds().length }}</div>
          @for (a of store.addedConds(); track a.field.id) {
            <div class="fld">
              <div class="fld-h">
                <span class="sw" [style.background]="groupColor(a.field.group)"></span>
                <span class="acc">{{ a.field.label }}</span>
                <span class="dim">· {{ a.field.groupLabel }}</span>
                <cx-type-badge [type]="a.field.type" />
                <span class="sp"></span>
                <span class="x" (click)="store.removeCond(a.field.id)">×</span>
              </div>
              <wb-field-control [field]="a.field" [cond]="a.cond"
                (changed)="store.setCond(a.field.id, $event)" />
            </div>
          }
        </div>
      }

      <!-- facet stack + narrow-on-a-field -->
      <div class="stack cx-scroll">
        @for (f of store.wbFacetStack(); track f.key) {
          <wb-facet-group [facet]="f" [sel]="selFor(f.key)" (toggle)="store.toggleFacet(f.key, $event)" />
        }
        @if (store.wbFacetStack().length === 0) {
          <div class="empty">nothing reachable — loosen a filter above.</div>
        }

        @if (store.availableFields().length > 0) {
          <div class="avail">
            <div class="av-h" (click)="availOpen.set(!availOpen())">
              <span class="caret">{{ availOpen() ? '▾' : '▸' }}</span>
              <span class="t-label">narrow on a field</span>
              <span class="sp"></span>
              <span class="acc">{{ store.availableFields().length }}</span>
            </div>
            @if (availOpen()) {
              <div class="av-body">
                @for (grp of grouped(); track grp.label) {
                  <div class="av-grp">{{ grp.label }}</div>
                  @for (f of grp.fields; track f.id) {
                    <div class="av-row" (click)="add(f)">
                      <span class="sw" [style.background]="groupColor(f.group)"></span>
                      <span class="v">{{ f.label }}</span>
                      <cx-type-badge [type]="f.type" />
                      <span class="plus">+</span>
                    </div>
                  }
                }
              </div>
            }
          </div>
        }
        <div style="height: 10px"></div>
      </div>
    </div>
  `,
  styles: [`
    .filter { display: flex; flex-direction: column; height: 100%; min-height: 0;
      font-family: var(--mono); background: var(--surface); }
    .top { padding: 8px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
    .search { display: flex; align-items: center; gap: 6px; height: 26px; padding: 0 8px;
      border: 1px solid var(--border); background: var(--bg); }
    .search .ic { color: var(--dim); font-size: 11px; }
    .search input { flex: 1; min-width: 0; background: transparent; border: none; outline: none;
      color: var(--text); font-family: var(--mono); font-size: 11.5px; }
    .search .x { cursor: pointer; color: var(--dim); font-size: 13px; }
    .count { display: flex; align-items: center; gap: 8px; margin-top: 7px; font-size: 9.5px; }
    .acc { color: var(--accent); }
    .dim { color: var(--dim); }
    .sp { flex: 1; }
    .reset { color: var(--accent); cursor: pointer; }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted); }
    .added { border-bottom: 1px solid var(--border); padding: 8px 10px; flex-shrink: 0; }
    .fld { margin-bottom: 8px; }
    .fld-h { display: flex; align-items: center; gap: 5px; margin-bottom: 3px; font-size: 9.5px; }
    .fld-h .x { cursor: pointer; color: var(--dim); font-size: 13px; line-height: 1; }
    .sw { width: 6px; height: 6px; flex-shrink: 0; }
    .stack { flex: 1; overflow: auto; min-height: 0; }
    .empty { padding: 16px; font-size: 10.5px; color: var(--dim); }
    .avail { border-bottom: 1px solid var(--border); background: var(--surface-2); }
    .av-h { display: flex; align-items: center; gap: 6px; padding: 8px 12px; cursor: pointer; }
    .caret { color: var(--dim); font-size: 8px; width: 8px; }
    .av-body { padding-bottom: 6px; background: var(--surface); }
    .av-grp { font-size: 8px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.10em;
      padding: 6px 12px 2px 26px; }
    .av-row { display: flex; align-items: center; gap: 7px; padding: 3px 12px 3px 26px; cursor: pointer;
      font-size: 10.5px; }
    .av-row:hover { background: var(--surface-2); }
    .av-row .v { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .av-row .plus { color: var(--dim); font-size: 13px; width: 10px; text-align: center; }
  `],
})
export class WbFilter {
  readonly store = inject(CorpusStore);
  readonly availOpen = signal(false);
  readonly corpusTotal = computed(() => this.store.corpus()?.record_count ?? this.store.wbTotal());

  readonly grouped = computed(() => {
    const by = new Map<string, FieldStat[]>();
    for (const f of this.store.availableFields()) {
      const arr = by.get(f.groupLabel) ?? [];
      arr.push(f);
      by.set(f.groupLabel, arr);
    }
    return [...by.entries()].map(([label, fields]) => ({ label, fields }));
  });

  selFor(key: string): Set<string> {
    return this.store.selection()[key] ?? new Set<string>();
  }
  groupColor(group: string): string {
    return (
      { core: '#1a1814', mime: '#b00020', origin: '#a35a00', composite: '#7a4a8a' }[group] ??
      'var(--muted)'
    );
  }
  add(f: FieldStat): void {
    this.store.setCond(f.id, defaultCond(f) as Cond);
  }
}
