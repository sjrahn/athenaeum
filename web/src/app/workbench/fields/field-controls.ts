// Typed-field controls — the design's Lab* UI atoms, fed global `FieldStat.stats` from
// the API and emitting a `Cond`. Each control takes (field, cond) and emits `changed`;
// the parent commits to the store, whose httpResource aborts in-flight queries so a brush
// drag / live typing re-queries cleanly. `wb-field-control` dispatches by field type.

import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { Cond, FieldStat } from '../../core/models';

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, n));
}
function fmtMs(ms: number): string {
  const d = new Date(ms);
  const p = (x: number) => String(x).padStart(2, '0');
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`;
}
function fmtNum(n: number): string {
  if (!Number.isFinite(n)) return '—';
  return Number.isInteger(n) ? String(n) : (Math.round(n * 100) / 100).toLocaleString();
}

/** Dual-thumb range brush over a histogram — numbers (with inputs) and dates (with date
 *  labels). value = [lo, hi] (epoch ms for dates). */
@Component({
  selector: 'wb-range-brush',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="brush">
      <div #track class="track" (mousedown)="onTrackDown($event)">
        @for (b of bins(); track $index) {
          <span
            class="bin"
            [style.height.%]="barPct(b)"
            [class.sel]="inSel($index)"
          ></span>
        }
        <span class="band" [style.left.%]="pLo()" [style.width.%]="pHi() - pLo()"></span>
        <span class="handle" [style.left.%]="pLo()" (mousedown)="startDrag('lo', $event)">
          <span class="knob"></span>
        </span>
        <span class="handle" [style.left.%]="pHi()" (mousedown)="startDrag('hi', $event)">
          <span class="knob"></span>
        </span>
      </div>
      @if (isDate()) {
        <div class="foot">
          <span class="pill">{{ fmtLo() }}</span><span class="arr">→</span>
          <span class="pill">{{ fmtHi() }}</span>
          <span class="sp"></span>
          <span class="dim">{{ stat().distinct }} distinct</span>
        </div>
      } @else {
        <div class="foot">
          <input class="num" type="number" [value]="lo()" (input)="setLo($event)" />
          <span class="arr">→</span>
          <input class="num" type="number" [value]="hi()" (input)="setHi($event)" />
          <span class="sp"></span>
          <span class="dim">{{ fmtMin() }}–{{ fmtMax() }} · {{ stat().distinct }}</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .brush { font-family: var(--mono); }
    .track { position: relative; height: 46px; display: flex; align-items: flex-end; gap: 1px;
      background: var(--bg); border: 1px solid var(--border); padding: 0 1px; user-select: none;
      touch-action: none; cursor: crosshair; }
    .bin { flex: 1; background: var(--border-strong); opacity: 0.4; min-height: 2px; }
    .bin.sel { background: var(--accent); opacity: 0.85; }
    .band { position: absolute; top: 0; bottom: 0; background: var(--accent-soft); opacity: 0.32;
      pointer-events: none; }
    .handle { position: absolute; top: -3px; bottom: -3px; width: 11px; margin-left: -6px;
      display: flex; justify-content: center; cursor: ew-resize; z-index: 2; }
    .handle::before { content: ''; width: 2px; background: var(--accent); }
    .knob { position: absolute; top: -2px; width: 9px; height: 9px; background: var(--accent);
      border: 1px solid var(--surface); }
    .foot { display: flex; align-items: center; gap: 6px; margin-top: 6px; }
    .num { width: 78px; height: 22px; background: var(--bg); border: 1px solid var(--border);
      outline: none; color: var(--text); font-family: var(--mono); font-size: 10.5px; padding: 0 6px; }
    .pill { padding: 2px 6px; border: 1px solid var(--border); background: var(--bg); font-size: 10px; }
    .arr { font-size: 9px; color: var(--dim); }
    .sp { flex: 1; }
    .dim { font-size: 8.5px; color: var(--dim); }
  `],
  imports: [],
})
export class WbRangeBrush {
  field = input.required<FieldStat>();
  cond = input.required<Cond>();
  changed = output<Cond>();
  private track = viewChild<ElementRef<HTMLElement>>('track');

  readonly stat = computed(() => this.field().stats);
  readonly isDate = computed(() => this.field().type === 'date');
  readonly bins = computed(() => this.stat().bins ?? []);
  readonly min = computed(() => this.stat().min ?? 0);
  readonly max = computed(() => this.stat().max ?? 1);
  readonly lo = computed(() => (this.cond().value as [number, number])[0]);
  readonly hi = computed(() => (this.cond().value as [number, number])[1]);
  readonly span = computed(() => this.max() - this.min() || 1);
  readonly pLo = computed(() => ((this.lo() - this.min()) / this.span()) * 100);
  readonly pHi = computed(() => ((this.hi() - this.min()) / this.span()) * 100);
  readonly fmtLo = computed(() => fmtMs(this.lo()));
  readonly fmtHi = computed(() => fmtMs(this.hi()));
  readonly fmtMin = computed(() => fmtNum(this.min()));
  readonly fmtMax = computed(() => fmtNum(this.max()));

  barPct(b: number): number {
    return Math.max(4, (b / (this.stat().binMax || 1)) * 100);
  }
  inSel(i: number): boolean {
    const n = this.bins().length || 1;
    const bc = (i / n) * 100;
    const bce = ((i + 1) / n) * 100;
    return bce > this.pLo() && bc < this.pHi();
  }

  private valAt(clientX: number): number {
    const el = this.track()?.nativeElement;
    if (!el) return this.min();
    const rc = el.getBoundingClientRect();
    const t = clamp01((clientX - rc.left) / rc.width);
    let v = this.min() + t * this.span();
    if (!this.isDate() && Number.isInteger(this.min()) && Number.isInteger(this.max())) {
      v = Math.round(v);
    }
    return v;
  }
  onTrackDown(e: MouseEvent): void {
    // click on the track moves the nearest handle
    const v = this.valAt(e.clientX);
    const which = Math.abs(v - this.lo()) <= Math.abs(v - this.hi()) ? 'lo' : 'hi';
    this.startDrag(which, e);
  }
  startDrag(which: 'lo' | 'hi', e: MouseEvent): void {
    e.preventDefault();
    e.stopPropagation();
    const move = (ev: MouseEvent) => {
      const v = this.valAt(ev.clientX);
      const next: [number, number] =
        which === 'lo' ? [Math.min(v, this.hi()), this.hi()] : [this.lo(), Math.max(v, this.lo())];
      this.emit(next);
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  }
  setLo(e: Event): void {
    this.emit([Math.min(Number((e.target as HTMLInputElement).value), this.hi()), this.hi()]);
  }
  setHi(e: Event): void {
    this.emit([this.lo(), Math.max(Number((e.target as HTMLInputElement).value), this.lo())]);
  }
  private emit(value: [number, number]): void {
    this.changed.emit({ ...this.cond(), value });
  }
}

/** Value checklist (string / list / uri / hash) with a search box past 7 values. */
@Component({
  selector: 'wb-checklist',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (searchable()) {
      <div class="search">
        <span class="ic">⌕</span>
        <input [value]="q()" (input)="q.set($any($event.target).value)"
          [placeholder]="'filter ' + values().length + ' values…'" />
      </div>
    }
    <div class="list cx-scroll">
      @for (it of shown(); track it.v) {
        <div class="row" [class.on]="sel().has(it.v)" (click)="toggle(it.v)">
          <span class="box" [class.on]="sel().has(it.v)">@if (sel().has(it.v)) { ✓ }</span>
          <span class="v">{{ it.v }}</span>
          <span class="bar"><span [style.width.%]="(it.n / topN()) * 100"></span></span>
          <span class="n">{{ it.n }}</span>
        </div>
      }
      @if (shown().length === 0) { <div class="empty">no values match.</div> }
    </div>
  `,
  styles: [`
    :host { font-family: var(--mono); display: block; }
    .search { display: flex; align-items: center; gap: 6px; height: 24px; padding: 0 7px;
      border: 1px solid var(--border); background: var(--bg); margin-bottom: 5px; }
    .search .ic { color: var(--dim); font-size: 10px; }
    .search input { flex: 1; min-width: 0; background: transparent; border: none; outline: none;
      color: var(--text); font-family: var(--mono); font-size: 10.5px; }
    .list { max-height: 168px; overflow: auto; border: 1px solid var(--border); background: var(--bg); }
    .row { display: flex; align-items: center; gap: 7px; height: 22px; padding: 0 8px;
      cursor: pointer; border-bottom: 1px solid var(--border); font-size: 10.5px; color: var(--text); }
    .row.on { background: var(--accent-soft); color: var(--accent); }
    .box { width: 9px; height: 9px; border: 1px solid var(--border-strong); display: flex;
      align-items: center; justify-content: center; font-size: 7px; color: #fff; flex-shrink: 0; }
    .box.on { background: var(--accent); border-color: var(--accent); }
    .v { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar { width: 26px; height: 4px; background: var(--border); position: relative; flex-shrink: 0; }
    .bar span { position: absolute; inset: 0; background: var(--border-strong); }
    .row.on .bar span { background: var(--accent); }
    .n { font-size: 9px; color: var(--dim); width: 22px; text-align: right; }
    .empty { padding: 8px; font-size: 9.5px; color: var(--dim); }
  `],
  imports: [],
})
export class WbChecklist {
  field = input.required<FieldStat>();
  cond = input.required<Cond>();
  changed = output<Cond>();
  readonly q = signal('');

  readonly values = computed(() => this.field().stats.values ?? []);
  readonly topN = computed(() => this.values()[0]?.n || 1);
  readonly searchable = computed(() => this.values().length > 7);
  readonly sel = computed(() => new Set((this.cond().value as string[]) ?? []));
  readonly shown = computed(() => {
    const ql = this.q().trim().toLowerCase();
    const vs = ql ? this.values().filter((x) => x.v.toLowerCase().includes(ql)) : this.values();
    return vs.slice(0, 200);
  });

  toggle(v: string): void {
    const set = new Set(this.sel());
    if (set.has(v)) set.delete(v);
    else set.add(v);
    this.changed.emit({ ...this.cond(), value: [...set] });
  }
}

/** Free-text "contains" box (string / uri / hash). */
@Component({
  selector: 'wb-contains',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="box">
      <span class="ic">⊃</span>
      <input [value]="(cond().value ?? '') + ''" (input)="emit($any($event.target).value)"
        [placeholder]="'contains in ' + field().label + '…'" />
    </div>
  `,
  styles: [`
    .box { display: flex; align-items: center; gap: 6px; height: 26px; padding: 0 8px;
      border: 1px solid var(--border); background: var(--bg); font-family: var(--mono); }
    .ic { color: var(--dim); font-size: 10px; }
    input { flex: 1; min-width: 0; background: transparent; border: none; outline: none;
      color: var(--text); font-family: var(--mono); font-size: 11px; }
  `],
  imports: [],
})
export class WbContains {
  field = input.required<FieldStat>();
  cond = input.required<Cond>();
  changed = output<Cond>();
  emit(v: string): void {
    this.changed.emit({ ...this.cond(), value: v });
  }
}

/** Boolean is-true/is-false toggle. */
@Component({
  selector: 'wb-bool',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="seg">
      <button [class.on]="cond().value === true" (click)="emit(true)">true</button>
      <button [class.on]="cond().value === false" (click)="emit(false)">false</button>
    </div>
  `,
  styles: [`
    .seg { display: inline-flex; border: 1px solid var(--border); font-family: var(--mono); }
    button { height: 24px; padding: 0 14px; border: none; border-radius: 0; background: transparent;
      color: var(--muted); font-family: var(--mono); font-size: 11px; cursor: pointer; }
    button.on { background: var(--accent-soft); color: var(--accent); }
  `],
  imports: [],
})
export class WbBool {
  field = input.required<FieldStat>();
  cond = input.required<Cond>();
  changed = output<Cond>();
  emit(v: boolean): void {
    this.changed.emit({ ...this.cond(), value: v });
  }
}

/** The universal type-dispatching control (the design's `LabFieldControl`). */
@Component({
  selector: 'wb-field-control',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @switch (field().type) {
      @case ('number') { <wb-range-brush [field]="field()" [cond]="cond()" (changed)="changed.emit($event)" /> }
      @case ('date') { <wb-range-brush [field]="field()" [cond]="cond()" (changed)="changed.emit($event)" /> }
      @case ('list') { <wb-checklist [field]="field()" [cond]="cond()" (changed)="changed.emit($event)" /> }
      @case ('bool') { <wb-bool [field]="field()" [cond]="cond()" (changed)="changed.emit($event)" /> }
      @default { <wb-contains [field]="field()" [cond]="cond()" (changed)="changed.emit($event)" /> }
    }
  `,
  imports: [WbRangeBrush, WbChecklist, WbBool, WbContains],
})
export class WbFieldControl {
  field = input.required<FieldStat>();
  cond = input.required<Cond>();
  changed = output<Cond>();
}

/** Build the default condition for a field (the design's `labDefaultCond`). */
export function defaultCond(f: FieldStat): Cond {
  const s = f.stats;
  if (f.type === 'number') return { fid: f.id, type: 'number', op: 'between', value: [s.min ?? 0, s.max ?? 0] };
  if (f.type === 'date') return { fid: f.id, type: 'date', op: 'between', value: [s.min ?? 0, s.max ?? 0] };
  if (f.type === 'bool') return { fid: f.id, type: 'bool', op: 'is', value: true };
  if (f.type === 'list') return { fid: f.id, type: 'list', op: 'in', value: [] };
  return { fid: f.id, type: f.type, op: 'contains', value: '' };
}
