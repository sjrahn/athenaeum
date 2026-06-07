// ⌘K command palette — a Spotlight for the corpus. One input returns a mixed ranked list:
// matching FIELDS (filter by a typed field), matching VALUES (jump straight to a facet),
// and matching RECORDS. Picking a field expands it inline into its typed control. Writes
// into the same store filter state, so the rail + ledger update live.

import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { CorpusStore } from '../../core/store';
import { Cond, FieldStat } from '../../core/models';
import { titleFor } from '../../core/util';
import { CxMimeChip, CxTypeBadge } from '../../chips/chips';
import { WbFieldControl, defaultCond } from '../fields/field-controls';

interface FieldItem { kind: 'field'; f: FieldStat; }
interface ValueItem { kind: 'value'; key: string; label: string; v: string; n: number; }
interface RecordItem { kind: 'record'; id: string; title: string; mime: string; sub: string; }
type Item = FieldItem | ValueItem | RecordItem;

@Component({
  selector: 'wb-palette',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip, CxTypeBadge, WbFieldControl],
  template: `
    <div class="scrim" (mousedown)="close($event)">
      <div class="card" (mousedown)="$event.stopPropagation()">
        <div class="input">
          <span class="ic">{{ detail() ? '‹' : '⌕' }}</span>
          @if (detail()) {
            <span class="dlabel" (click)="detail.set(null)">filter by
              <span class="acc">{{ detailField()?.label }}</span>
              <span class="dim">· {{ detailField()?.groupLabel }}</span></span>
          } @else {
            <input #box [value]="q()" (input)="q.set($any($event.target).value)"
              (keydown)="onKey($event)" placeholder="search records, fields, values…" />
            <span class="kbd">esc</span>
          }
        </div>

        <div class="body cx-scroll">
          @if (detail() && detailField()) {
            <div class="cfg">
              <div class="cfg-h">
                <cx-type-badge [type]="detailField()!.type" />
                <span class="dim">{{ detailField()!.coverage }} records carry this field</span>
              </div>
              <wb-field-control [field]="detailField()!" [cond]="detailCond()!"
                (changed)="store.setCond(detailField()!.id, $event)" />
              <div class="cfg-actions">
                <button class="btn primary" (click)="detail.set(null)">done · {{ store.wbTotal() }} results</button>
                <button class="btn" (click)="removeDetail()">remove</button>
              </div>
            </div>
          } @else {
            @if (fieldItems().length) { <div class="t-label">fields — filter by a typed field</div> }
            @for (it of fieldItems(); track it.f.id) {
              <div class="prow" [class.on]="flat()[hi()] === it" (mouseenter)="setHi(it)" (mousedown)="pick(it)">
                <span class="pic" [style.color]="groupColor(it.f.group)">⛁</span>
                <span class="pc"><span class="pt">{{ it.f.label }}</span><span class="ps">{{ it.f.groupLabel }}</span></span>
                <cx-type-badge [type]="it.f.type" /><span class="pr">{{ it.f.coverage }} →</span>
              </div>
            }
            @if (valueItems().length) { <div class="t-label bd">values — jump to a filter</div> }
            @for (it of valueItems(); track it.key + it.v) {
              <div class="prow" [class.on]="flat()[hi()] === it" (mouseenter)="setHi(it)" (mousedown)="pick(it)">
                <span class="pic acc">•</span>
                <span class="pc"><span class="pt">{{ it.v }}</span><span class="ps">{{ it.label }}</span></span>
                <span class="pr">{{ it.n }} recs</span>
              </div>
            }
            @if (recordItems().length) { <div class="t-label bd">records</div> }
            @for (it of recordItems(); track it.id) {
              <div class="prow" [class.on]="flat()[hi()] === it" (mouseenter)="setHi(it)" (mousedown)="pick(it)">
                <cx-mime-chip [m]="it.mime" />
                <span class="pc"><span class="pt sans">{{ it.title }}</span><span class="ps">{{ it.sub }}</span></span>
              </div>
            }
            @if (flat().length === 0) {
              <div class="none">{{ q() ? 'nothing matches “' + q() + '”.' : 'start typing — or pick a field above.' }}</div>
            }
          }
        </div>

        <div class="foot">
          <span><span class="kbd">↑↓</span> navigate</span><span><span class="kbd">⏎</span> select</span>
          <span class="sp"></span><span>{{ store.wbTotal() }} records</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .scrim { position: fixed; inset: 0; z-index: 300; display: flex; align-items: flex-start;
      justify-content: center; padding-top: 34px; background: rgba(20,18,14,0.42); }
    .card { width: 560px; max-width: 94vw; background: var(--surface); border: 1px solid var(--border-strong);
      box-shadow: var(--sh-float); font-family: var(--mono); display: flex; flex-direction: column;
      max-height: calc(100% - 60px); overflow: hidden; }
    .input { display: flex; align-items: center; gap: 9px; padding: 11px 14px; border-bottom: 1px solid var(--border); }
    .input .ic { color: var(--accent); font-size: 15px; }
    .input input { flex: 1; min-width: 0; background: transparent; border: none; outline: none;
      color: var(--text); font-family: var(--mono); font-size: 14px; }
    .dlabel { flex: 1; font-size: 13px; color: var(--text); cursor: pointer; }
    .acc { color: var(--accent); } .dim { color: var(--dim); font-size: 10px; }
    .kbd { font-family: var(--mono); font-size: 10px; padding: 1px 4px; border: 1px solid var(--border);
      border-bottom-width: 2px; color: var(--muted); background: var(--surface); }
    .body { flex: 1; overflow: auto; min-height: 0; }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted);
      padding: 7px 14px 4px; }
    .t-label.bd { border-top: 1px solid var(--border); }
    .prow { display: flex; align-items: center; gap: 10px; padding: 7px 14px; cursor: pointer;
      border-left: 2px solid transparent; }
    .prow.on { background: var(--accent-soft); border-left-color: var(--accent); }
    .pic { width: 16px; text-align: center; font-size: 12px; color: var(--dim); flex-shrink: 0; }
    .pic.acc { color: var(--accent); }
    .pc { min-width: 0; flex: 1; }
    .pt { display: block; font-size: 12.5px; color: var(--text); overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; }
    .pt.sans { font-family: var(--sans); }
    .ps { display: block; font-size: 9px; color: var(--dim); overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; }
    .pr { font-size: 9px; color: var(--dim); flex-shrink: 0; }
    .none { padding: 16px; font-size: 11px; color: var(--dim); }
    .cfg { padding: 14px; }
    .cfg-h { display: flex; align-items: center; gap: 7px; margin-bottom: 10px; }
    .cfg-actions { display: flex; gap: 8px; margin-top: 14px; }
    .btn { height: 26px; padding: 0 10px; border: 1px solid var(--border); background: var(--surface);
      color: var(--text); font-family: var(--mono); font-size: 11px; cursor: pointer; }
    .btn.primary { background: var(--accent); color: #fff; border-color: transparent; }
    .foot { display: flex; align-items: center; gap: 12px; padding: 6px 14px; border-top: 1px solid var(--border);
      background: var(--surface-2); font-size: 9px; color: var(--dim); }
    .sp { flex: 1; }
  `],
})
export class WbPalette {
  readonly store = inject(CorpusStore);
  private box = viewChild<ElementRef<HTMLInputElement>>('box');
  readonly q = signal('');
  readonly hi = signal(0);
  readonly detail = signal<string | null>(null);

  readonly detailField = computed(() => {
    const id = this.detail();
    return id ? (this.store.fieldById().get(id) ?? null) : null;
  });
  readonly detailCond = computed(() => {
    const id = this.detail();
    return id ? this.store.conds()[id] ?? null : null;
  });

  readonly fieldItems = computed<FieldItem[]>(() => {
    const ql = this.q().trim().toLowerCase();
    const fields = this.store.fields().filter(
      (f) =>
        !ql ||
        f.label.toLowerCase().includes(ql) ||
        f.groupLabel.toLowerCase().includes(ql) ||
        f.field.toLowerCase().includes(ql),
    );
    fields.sort((a, b) =>
      (a.group === 'core') === (b.group === 'core')
        ? b.coverage - a.coverage
        : a.group === 'core' ? -1 : 1,
    );
    return fields.slice(0, ql ? 5 : 4).map((f) => ({ kind: 'field', f }) as FieldItem);
  });
  readonly valueItems = computed<ValueItem[]>(() => {
    const ql = this.q().trim().toLowerCase();
    if (!ql) return [];
    const out: ValueItem[] = [];
    for (const f of this.store.wbFacetStack()) {
      for (const v of f.values) {
        if ((v.label || v.v).toLowerCase().includes(ql)) {
          out.push({ kind: 'value', key: f.key, label: f.label, v: v.v, n: v.n });
        }
      }
    }
    return out.slice(0, 6);
  });
  readonly recordItems = computed<RecordItem[]>(() => {
    const ql = this.q().trim().toLowerCase();
    return this.store
      .wbRows()
      .filter((r) => !ql || titleFor(r).toLowerCase().includes(ql) || r.description.toLowerCase().includes(ql))
      .slice(0, ql ? 6 : 4)
      .map(
        (r) =>
          ({
            kind: 'record',
            id: r.id,
            title: titleFor(r),
            mime: r.mime,
            sub: (r.origin_host || '—') + ' · ' + r.mime.split('/').pop(),
          }) as RecordItem,
      );
  });
  readonly flat = computed<Item[]>(() => [...this.fieldItems(), ...this.valueItems(), ...this.recordItems()]);

  constructor() {
    effect(() => {
      this.q();
      this.hi.set(0);
    });
    // focus the input on open
    effect(() => {
      if (!this.detail()) this.box()?.nativeElement.focus();
    });
  }

  setHi(it: Item): void {
    this.hi.set(this.flat().indexOf(it));
  }
  onKey(e: KeyboardEvent): void {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      this.hi.update((h) => Math.min(h + 1, this.flat().length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      this.hi.update((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const it = this.flat()[this.hi()];
      if (it) this.pick(it);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      this.store.closePalette();
    }
  }
  pick(it: Item): void {
    if (it.kind === 'field') {
      if (!this.store.conds()[it.f.id]) this.store.setCond(it.f.id, defaultCond(it.f) as Cond);
      this.detail.set(it.f.id);
    } else if (it.kind === 'value') {
      this.store.toggleFacet(it.key, it.v);
      this.q.set('');
    } else {
      this.store.selectRecord(it.id);
      this.store.closePalette();
    }
  }
  removeDetail(): void {
    const id = this.detail();
    if (id) this.store.removeCond(id);
    this.detail.set(null);
  }
  close(e: MouseEvent): void {
    if (e.target === e.currentTarget) this.store.closePalette();
  }
  groupColor(group: string): string {
    return (
      { core: '#1a1814', mime: '#b00020', origin: '#a35a00', composite: '#7a4a8a' }[group] ??
      'var(--muted)'
    );
  }
}
