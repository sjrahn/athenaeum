// Center · Ledger — the subject. A dense records table (resizable, persisted columns)
// plus gallery + cards views. Single-click selects (drives the detail pane), double-click
// opens the record workbench. Reuses the Console's mime chip + thumb.

import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { CorpusStore } from '../../core/store';
import { WorkbenchRow } from '../../core/models';
import { fmtBytes, mimeInfo, titleFor } from '../../core/util';
import { CxMimeChip } from '../../chips/chips';
import { CxThumb } from '../../browser/thumb';

interface Col {
  key: string;
  label: string;
  w: number;
}
const COLGROUPS: { label: string; cols: Col[] }[] = [
  { label: 'record', cols: [{ key: 'title', label: 'title', w: 230 }] },
  {
    label: 'metadata',
    cols: [
      { key: 'status', label: 'status', w: 104 },
      { key: 'segs', label: 'segments', w: 92 },
    ],
  },
  {
    label: 'provenance',
    cols: [
      { key: 'origin', label: 'origin', w: 168 },
      { key: 'captured', label: 'captured', w: 104 },
      { key: 'size', label: 'size', w: 78 },
    ],
  },
  { label: 'classification', cols: [{ key: 'class', label: 'composite', w: 190 }] },
];
const COLS: Col[] = COLGROUPS.flatMap((g) => g.cols);

@Component({
  selector: 'wb-ledger',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip, CxThumb],
  template: `
    <div class="ledger">
      <div class="head">
        <span class="t-label">ledger</span>
        <span class="dim">· {{ rows().length }} records</span>
        <span class="sp"></span>
        <div class="seg">
          @for (v of views; track v[0]) {
            <button [class.on]="store.ledgerView() === v[0]" [title]="v[0]"
              (click)="store.setLedgerView($any(v[0]))">{{ v[1] }}</button>
          }
        </div>
      </div>

      <div class="body cx-scroll">
        @switch (store.ledgerView()) {
          @case ('ledger') {
            <table [style.width.px]="totalW()">
              <colgroup>@for (c of cols; track c.key) { <col [style.width.px]="widths()[c.key]" /> }</colgroup>
              <thead>
                <tr class="grp">
                  @for (g of colgroups; track g.label) {
                    <th [attr.colspan]="g.cols.length">{{ g.label }}</th>
                  }
                </tr>
                <tr class="cols">
                  @for (c of cols; track c.key; let last = $last) {
                    <th>{{ c.label }}
                      @if (!last) { <span class="rz wb-col-resize" (mousedown)="resize(c.key, $event)"></span> }
                    </th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (r of rows(); track r.id) {
                  <tr [class.on]="store.selectedId() === r.id" [class.day]="isDay(r)"
                    (click)="store.selectRecord(r.id)" (dblclick)="store.openRecord(r.id)">
                    <td class="title-cell">
                      <span class="dot" [style.background]="statusColor(r.status)"></span>
                      <cx-mime-chip [m]="r.mime" />
                      @if (r.title) { <span class="title">{{ r.title }}</span> }
                      @else { <span class="ph">{{ placeholder(r) }} · {{ r.status }}</span> }
                    </td>
                    <td class="muted">{{ r.status }}</td>
                    <td class="muted">@if (r.segments) { <b>{{ r.segments }}</b> seg } @else { — }</td>
                    <td class="muted">{{ r.origin_host || '—' }}</td>
                    <td class="muted">{{ (r.captured || '—').slice(0, 10) }}</td>
                    <td class="muted">{{ fmtBytes(r.size) }}</td>
                    <td>
                      @for (c of composites(r); track c) { <span class="pill">{{ c }}</span> }
                      @if (composites(r).length === 0) { <span class="dim">—</span> }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
            @if (rows().length === 0) { <div class="empty">no records match the current filter & timeline.</div> }
          }
          @case ('gallery') {
            <div class="gallery">
              @for (r of rows(); track r.id) {
                <div class="tile" [class.on]="store.selectedId() === r.id"
                  (click)="store.selectRecord(r.id)" (dblclick)="store.openRecord(r.id)">
                  <div class="thumb">
                    <span class="badge"><span class="dot" [style.background]="statusColor(r.status)"></span><cx-mime-chip [m]="r.mime" /></span>
                    <cx-thumb [mime]="r.mime" />
                  </div>
                  <div class="cap">{{ title(r) }}</div>
                </div>
              }
            </div>
          }
          @case ('cards') {
            <div class="cards">
              @for (r of rows(); track r.id) {
                <div class="card" [class.on]="store.selectedId() === r.id"
                  (click)="store.selectRecord(r.id)" (dblclick)="store.openRecord(r.id)">
                  <div class="card-h">
                    <span class="dot" [style.background]="statusColor(r.status)"></span>
                    <cx-mime-chip [m]="r.mime" /><span class="title">{{ title(r) }}</span>
                  </div>
                  <div class="desc">{{ r.description || '— not normalized' }}</div>
                </div>
              }
            </div>
          }
        }
      </div>

      <div class="foot">
        <span><b>{{ rows().length }}</b> of {{ store.wbTotal() }} records</span>
        <span class="sp"></span>
        @for (s of statusLegend; track s[0]) {
          <span class="leg"><span class="dot" [style.background]="s[1]"></span>{{ s[0] }} {{ countStatus(s[0]) }}</span>
        }
        <span>· Σ {{ totalMb() }} MB</span>
      </div>
    </div>
  `,
  styles: [`
    .ledger { display: flex; flex-direction: column; height: 100%; min-height: 0;
      font-family: var(--mono); background: var(--surface); }
    .head { flex-shrink: 0; height: 30px; display: flex; align-items: center; gap: 8px;
      padding: 0 10px; border-bottom: 1px solid var(--border); background: var(--surface-2); }
    .t-label { font-family: var(--mono); font-size: 10px; text-transform: uppercase;
      letter-spacing: 0.10em; color: var(--muted); }
    .dim { font-size: 10px; color: var(--dim); }
    .sp { flex: 1; }
    .seg { display: inline-flex; border: 1px solid var(--border); }
    .seg button { height: 20px; width: 26px; padding: 0; border: none; border-radius: 0;
      background: transparent; color: var(--muted); cursor: pointer; font-size: 12px; font-family: var(--mono); }
    .seg button.on { background: var(--accent-soft); color: var(--accent); }
    .body { flex: 1; overflow: auto; min-height: 0; }
    table { border-collapse: collapse; min-width: 100%; table-layout: fixed; }
    thead { position: sticky; top: 0; z-index: 2; }
    .grp th { text-align: left; font-size: 8.5px; color: var(--dim); text-transform: uppercase;
      letter-spacing: 0.10em; padding: 5px 10px 3px; border-right: 1px solid var(--border);
      border-bottom: 1px solid var(--border); background: var(--surface-2); font-weight: 600; }
    .cols th { position: relative; text-align: left; font-size: 8.5px; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.08em; padding: 3px 10px 5px; font-weight: 500;
      border-right: 1px solid var(--border); border-bottom: 1px solid var(--border-strong);
      background: var(--surface-2); }
    .rz { position: absolute; top: 0; right: -3px; width: 7px; height: 100%; cursor: col-resize; z-index: 3; }
    tbody tr { cursor: pointer; height: 30px; border-bottom: 1px solid var(--border); }
    tbody tr:hover { background: var(--surface-2); }
    tbody tr.day { background: rgba(184,134,11,0.08); }
    tbody tr.on { background: var(--accent-soft); }
    td { padding: 0 10px; border-right: 1px solid var(--border); white-space: nowrap;
      overflow: hidden; text-overflow: ellipsis; font-size: 11px; }
    td.muted { color: var(--muted); }
    tr.on td { color: var(--accent); }
    .title-cell { display: flex; align-items: center; gap: 7px; border-left: 2px solid transparent; }
    tr.on .title-cell { border-left-color: var(--accent); }
    .title { font-family: var(--sans); font-weight: 500; overflow: hidden; text-overflow: ellipsis; }
    .ph { font-style: italic; color: var(--dim); font-size: 10px; }
    .pill { display: inline-flex; align-items: center; height: 15px; padding: 0 5px; margin-right: 3px;
      font-size: 8.5px; background: var(--surface-2); border: 1px solid var(--border); color: var(--muted); }
    .dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
    .empty { padding: 18px; font-size: 11.5px; color: var(--dim); }
    .foot { flex-shrink: 0; height: 26px; display: flex; align-items: center; gap: 12px; padding: 0 12px;
      border-top: 1px solid var(--border); background: var(--surface-2); font-size: 9.5px; color: var(--muted); }
    .foot b { color: var(--accent); }
    .leg { display: inline-flex; align-items: center; gap: 4px; }
    .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; padding: 12px; }
    .tile { border: 1px solid var(--border); background: var(--surface); cursor: pointer; }
    .tile.on { border-color: var(--accent); }
    .tile .thumb { height: 74px; border-bottom: 1px solid var(--border); position: relative; }
    .tile .badge { position: absolute; top: 5px; left: 5px; display: flex; gap: 3px; z-index: 1; }
    .tile .cap { padding: 6px 8px; font-family: var(--sans); font-size: 11px; font-weight: 500;
      line-height: 1.3; height: 46px; overflow: hidden; }
    .cards { padding: 12px; }
    .card { border: 1px solid var(--border); border-left: 3px solid var(--border); background: var(--surface);
      padding: 10px; margin-bottom: 8px; cursor: pointer; }
    .card.on { border-left-color: var(--accent); background: var(--accent-soft); }
    .card-h { display: flex; align-items: center; gap: 7px; margin-bottom: 4px; }
    .card-h .title { font-family: var(--sans); font-weight: 600; font-size: 13px; overflow: hidden;
      text-overflow: ellipsis; }
    .desc { font-family: var(--sans); font-size: 11.5px; color: var(--muted); line-height: 1.5;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  `],
})
export class WbLedger {
  readonly store = inject(CorpusStore);
  readonly cols = COLS;
  readonly colgroups = COLGROUPS;
  readonly views: [string, string][] = [['ledger', '≣'], ['gallery', '⊞'], ['cards', '☰']];
  readonly statusLegend: [string, string][] = [
    ['normalized', 'var(--ok)'],
    ['draft', 'var(--warn)'],
    ['stub', 'var(--dim)'],
  ];
  readonly fmtBytes = fmtBytes;
  readonly title = titleFor;

  readonly rows = this.store.wbRows;
  readonly widths = signal<Record<string, number>>(this.loadWidths());
  readonly totalW = computed(() => COLS.reduce((s, c) => s + this.widths()[c.key], 0));

  constructor() {
    effect(() => {
      try {
        localStorage.setItem('wb-ledger-widths', JSON.stringify(this.widths()));
      } catch {
        /* ignore */
      }
    });
  }

  private loadWidths(): Record<string, number> {
    let saved: Record<string, number> = {};
    try {
      saved = JSON.parse(localStorage.getItem('wb-ledger-widths') || '{}');
    } catch {
      /* ignore */
    }
    return Object.fromEntries(COLS.map((c) => [c.key, saved[c.key] || c.w]));
  }

  resize(key: string, e: MouseEvent): void {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startW = this.widths()[key];
    const move = (ev: MouseEvent) =>
      this.widths.update((w) => ({ ...w, [key]: Math.max(56, startW + (ev.clientX - startX)) }));
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      document.body.style.cursor = '';
    };
    document.body.style.cursor = 'col-resize';
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  }

  placeholder(r: WorkbenchRow): string {
    return `${r.id.slice(0, 12)}.${mimeInfo(r.mime).short}`;
  }
  composites(r: WorkbenchRow): string[] {
    return r.classifications.map((c) => (c.includes('/') ? c.split('/').pop()! : c)).slice(0, 2);
  }
  isDay(r: WorkbenchRow): boolean {
    const day = this.store.tlDay();
    if (day == null || !r.captured) return false;
    const d = new Date(r.captured.slice(0, 10) + 'T00:00:00Z').getTime();
    return Math.abs(d - day) < 86_400_000 / 2;
  }
  statusColor(s: string): string {
    return s === 'normalized'
      ? 'var(--ok)'
      : s === 'draft'
        ? 'var(--warn)'
        : s === 'stub'
          ? 'var(--dim)'
          : 'var(--border-strong)';
  }
  countStatus(s: string): number {
    return this.rows().filter((r) => r.status === s).length;
  }
  totalMb(): string {
    const mb = this.rows().reduce((s, r) => s + (r.size ?? 0) / 1_000_000, 0);
    return mb >= 1000 ? Math.round(mb).toLocaleString() : mb.toFixed(1);
  }
}
