// Bottom · Overview — aggregate distributions of the current result set (by mime / status
// / atom / origin / genre) + headline stats, with the terminal status strip integrated
// along the bottom edge (it used to be the app footer). When collapsed, the dock's rail
// surfaces the headline metrics (see the corpus-workbench bottom-rail slot).

import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { CorpusStore } from '../../core/store';

const CARDS: { title: string; key: string; color: string }[] = [
  { title: 'by mime', key: 'byMime', color: '#b00020' },
  { title: 'by status', key: 'byStatus', color: 'var(--accent)' },
  { title: 'by atom', key: 'byAtom', color: '#3a6a7a' },
  { title: 'by origin', key: 'byOrigin', color: '#a35a00' },
  { title: 'by genre', key: 'byGenre', color: '#7a4a8a' },
];

@Component({
  selector: 'wb-overview',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="ov">
      <div class="body">
        <div class="headline">
          @for (h of headline(); track h[0]) {
            <div class="hl"><div class="hl-l">{{ h[0] }}</div><div class="hl-v" [style.color]="h[2]">{{ h[1] }}</div></div>
          }
        </div>
        @for (c of cards; track c.key) {
          <div class="card">
            <div class="t-label">{{ c.title }} · {{ dist(c.key).length }}</div>
            <div class="rows cx-scroll">
              @for (d of dist(c.key).slice(0, 8); track d[0]) {
                <div class="row">
                  <span class="k">{{ d[0] }}</span>
                  <span class="bar"><span [style.width.%]="(d[1] / max(c.key)) * 100" [style.background]="c.color"></span></span>
                  <span class="n">{{ d[1] }}</span>
                </div>
              }
              @if (dist(c.key).length === 0) { <span class="dim">—</span> }
            </div>
          </div>
        }
      </div>
      <div class="strip">
        <span><span class="led">●</span> api · /v1/{{ store.corpusId() || 'records' }}/records</span>
        <span>·</span><span><b>{{ store.wbTotal() }}</b> of {{ corpusTotal() }} records</span>
        <span>·</span><span>{{ store.filterCount() }} filters</span>
        @if (store.selectedId()) { <span>·</span><span>selected {{ store.selectedId()!.slice(0, 10) }}…</span> }
        <span class="sp"></span>
        <span class="hint">panes: drag dividers · ‹ collapse · ⤢ separate</span>
      </div>
    </div>
  `,
  styles: [`
    .ov { height: 100%; display: flex; flex-direction: column; min-height: 0; font-family: var(--mono);
      background: var(--surface); }
    .body { flex: 1; min-height: 0; display: flex; }
    .headline { flex-shrink: 0; width: 150px; border-right: 1px solid var(--border); padding: 8px 12px;
      display: flex; flex-direction: column; justify-content: center; gap: 10px; }
    .hl-l { font-size: 8.5px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--dim); }
    .hl-v { font-size: 19px; font-weight: 600; }
    .card { flex: 1; min-width: 150px; border-right: 1px solid var(--border); padding: 8px 12px;
      min-height: 0; display: flex; flex-direction: column; }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted);
      margin-bottom: 7px; }
    .rows { overflow: auto; min-height: 0; }
    .row { display: flex; align-items: center; gap: 7px; margin-bottom: 4px; }
    .row .k { font-size: 10px; color: var(--text); width: 92px; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; }
    .row .bar { flex: 1; height: 8px; background: var(--bg); border: 1px solid var(--border); position: relative; }
    .row .bar span { position: absolute; left: 0; top: 0; bottom: 0; opacity: 0.8; }
    .row .n { font-size: 9.5px; color: var(--muted); width: 22px; text-align: right; }
    .dim { font-size: 9.5px; color: var(--dim); }
    .strip { flex-shrink: 0; height: 24px; border-top: 1px solid var(--border); background: var(--surface-2);
      display: flex; align-items: center; gap: 12px; padding: 0 12px; font-size: 9.5px; color: var(--muted); }
    .strip b { color: var(--accent); }
    .led { color: var(--ok); }
    .sp { flex: 1; }
    .hint { color: var(--dim); }
  `],
})
export class WbOverview {
  readonly store = inject(CorpusStore);
  readonly cards = CARDS;
  readonly corpusTotal = computed(() => this.store.corpus()?.record_count ?? this.store.wbTotal());
  readonly headline = computed<[string, string | number, string][]>(() => {
    const h = this.store.wbOverview()?.headline;
    if (!h) return [];
    return [
      ['records', h.records, 'var(--accent)'],
      ['normalized', h.records ? h.pctNormalized + '%' : '—', 'var(--ok)'],
      ['Σ size', h.sizeMB.toLocaleString() + ' MB', 'var(--text)'],
      ['span', h.spanDays + 'd', 'var(--text)'],
    ];
  });
  dist(key: string): [string, number][] {
    return this.store.wbOverview()?.dists[key] ?? [];
  }
  max(key: string): number {
    return Math.max(1, ...this.dist(key).map((d) => d[1]));
  }
}
