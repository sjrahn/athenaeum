// Corpus (Search) Workbench — the orchestrator. A top bar (brand · ⌘K launcher · corpus
// selector) over the slot-based dock: timeline (top) · filter (left) · ledger (center) ·
// detail (right) · overview (bottom). The ⌘K palette overlays on top. All panes read the
// shared store, so the timeline, filter, ledger, detail, and overview move in lockstep.

import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { CorpusStore } from '../core/store';
import { Viewport } from '../core/viewport';
import { PaneConfig, WbDock } from './dock/wb-dock';
import { WbDockState } from './dock/wb-dock-state';
import { Slot } from '../core/slot';
import { CxAperture } from '../chips/chips';
import { WbTimeline, TL_HEIGHT } from './panes/wb-timeline';
import { WbFilter } from './panes/wb-filter';
import { WbLedger } from './panes/wb-ledger';
import { WbDetail } from './panes/wb-detail';
import { WbOverview } from './panes/wb-overview';
import { WbPalette } from './panes/wb-palette';

@Component({
  selector: 'cx-corpus-workbench',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [WbDockState],
  imports: [
    WbDock,
    Slot,
    CxAperture,
    WbTimeline,
    WbFilter,
    WbLedger,
    WbDetail,
    WbOverview,
    WbPalette,
  ],
  template: `
    <div class="wb">
      <!-- top bar -->
      <div class="bar">
        <div class="brand">
          <cx-aperture [size]="16" />
          <span class="name">athenaeum</span><span class="slash">/ corpus</span>
        </div>
        <span class="div"></span>
        <div class="ttl">
          <div class="t1">Search workbench</div>
          <div class="t2">{{ store.wbTotal() }} of {{ corpusTotal() }} records ·
            {{ store.filterCount() }} filters{{ store.tlRange() ? ' · timeline scoped' : '' }}</div>
        </div>
        <span class="sp"></span>
        <button class="launch" (click)="store.openPalette()">
          <span class="acc">⌕</span> search everything <span class="kbd">⌘K</span>
        </button>
        <div class="corpora">
          @for (c of store.corpora(); track c.id) {
            <button [class.on]="store.corpusId() === c.id" (click)="store.setCorpus(c.id)">{{ c.name }}</button>
          }
        </div>
        @if (store.filterCount() > 0) { <button class="reset" (click)="store.clearAll()">reset</button> }
      </div>

      <!-- dock -->
      <div class="dock-wrap">
        <wb-dock [topHeight]="topHeight()" [left]="leftPane()" [right]="rightPane" [bottom]="bottomPane">
          <ng-template slot="top"><wb-timeline /></ng-template>
          <ng-template slot="left"><wb-filter /></ng-template>
          <ng-template slot="center"><wb-ledger /></ng-template>
          <ng-template slot="right"><wb-detail /></ng-template>
          <ng-template slot="bottom"><wb-overview /></ng-template>
          <ng-template slot="bottom-rail">
            <span class="rail-metrics">
              <span class="m"><b class="acc">{{ store.wbTotal() }}</b> of {{ corpusTotal() }} <i>records</i></span>
              @for (s of statusLeg(); track s.s) {
                <span class="m"><span class="rdot" [style.background]="s.c"></span><b>{{ s.n }}</b> <i>{{ s.s }}</i></span>
              }
              <span class="m"><b>{{ sizeMb() }} MB</b> <i>Σ size</i></span>
              <span class="m"><b>{{ store.filterCount() }}</b> <i>filters</i></span>
            </span>
          </ng-template>
        </wb-dock>
      </div>

      @if (store.paletteOpen()) { <wb-palette /> }
    </div>
  `,
  styles: [`
    .wb { position: absolute; inset: 0; display: flex; flex-direction: column; background: var(--bg);
      color: var(--text); overflow: hidden; font-family: var(--mono); }
    .bar { flex-shrink: 0; height: 46px; background: var(--surface); border-bottom: 1px solid var(--border);
      display: flex; align-items: center; gap: 12px; padding: 0 12px; }
    .brand { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
    .name { font-weight: 700; font-size: 13px; } .slash { color: var(--dim); font-size: 12px; }
    .div { width: 1px; height: 18px; background: var(--border); }
    .ttl { min-width: 0; }
    .t1 { font-family: var(--sans); font-weight: 600; font-size: 14px; line-height: 1; }
    .t2 { font-size: 9.5px; color: var(--dim); margin-top: 2px; }
    .sp { flex: 1; }
    .launch { height: 28px; display: inline-flex; align-items: center; gap: 8px; padding: 0 10px;
      border: 1px solid var(--border); background: var(--surface); color: var(--text);
      font-family: var(--mono); font-size: 11px; cursor: pointer; }
    .launch .acc { color: var(--accent); }
    .kbd { font-size: 10px; padding: 1px 4px; border: 1px solid var(--border); border-bottom-width: 2px;
      color: var(--muted); }
    .corpora { display: flex; border: 1px solid var(--border); }
    .corpora button { height: 28px; padding: 0 10px; border: none; border-radius: 0; background: transparent;
      color: var(--muted); font-size: 11px; cursor: pointer; font-family: var(--mono); }
    .corpora button.on { background: var(--accent-soft); color: var(--accent); }
    .reset { height: 28px; padding: 0 8px; border: none; background: transparent; color: var(--muted);
      font-size: 11px; cursor: pointer; font-family: var(--mono); }
    .dock-wrap { flex: 1; min-height: 0; position: relative; }
    .rail-metrics { display: inline-flex; align-items: center; gap: 18px; font-family: var(--mono); }
    .rail-metrics .m { display: inline-flex; align-items: baseline; gap: 6px; }
    .rail-metrics b { font-size: 12px; font-weight: 600; } .rail-metrics b.acc { color: var(--accent); }
    .rail-metrics b.ok { color: var(--ok); }
    .rail-metrics .rdot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
    .rail-metrics i { font-size: 8.5px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--dim);
      font-style: normal; }
  `],
})
export class CxCorpusWorkbench {
  readonly store = inject(CorpusStore);
  private mobile = inject(Viewport).mobile;
  // the filter starts collapsed on phones so the ledger gets the full width (desktop-first
  // surface — narrow viewports degrade to the ledger with the rails tucked away)
  readonly leftPane = computed<PaneConfig>(() => ({
    label: 'filter',
    defaultW: 250,
    defaultCollapsed: this.mobile(),
  }));
  readonly rightPane: PaneConfig = { label: 'detail', defaultW: 300, defaultCollapsed: true };
  readonly bottomPane: PaneConfig = { label: 'overview', defaultOn: true, defaultCollapsed: true, defaultH: 168 };

  readonly topHeight = computed(() => TL_HEIGHT[this.store.tlMode()]);
  readonly corpusTotal = computed(() => this.store.corpus()?.record_count ?? this.store.wbTotal());
  readonly sizeMb = computed(() => (this.store.wbOverview()?.headline.sizeMB ?? 0).toLocaleString());
  readonly statusLeg = computed(() => {
    const col: Record<string, string> = {
      normalized: 'var(--ok)',
      draft: 'var(--warn)',
      stub: 'var(--dim)',
    };
    return (this.store.wbOverview()?.dists['byStatus'] ?? []).map(([s, n]) => ({
      s,
      n,
      c: col[s] ?? 'var(--dim)',
    }));
  });
}
