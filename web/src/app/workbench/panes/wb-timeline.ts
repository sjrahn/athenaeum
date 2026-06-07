// Top · Timeline — brush a captured-date RANGE across the corpus, drop a DAY cursor,
// zoom presets (fit/3M/1M/2W/1W). Collapses to a strip; expands to stacked status lanes
// with a summary stat row. Charts the server-computed bins over the in-scope set (minus
// its own range, so the histogram shows the full distribution you brush within).

import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  viewChild,
} from '@angular/core';
import { CorpusStore } from '../../core/store';
import { fmtDateMs } from '../../core/util';

const DAYMS = 86_400_000;
const dayFloor = (ms: number) => Math.floor(ms / DAYMS) * DAYMS;

export const TL_HEIGHT: Record<string, number> = { strip: 30, brush: 128, lanes: 256 };

interface Tick {
  t: number;
  label: string;
}

@Component({
  selector: 'wb-timeline',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="tl">
      <div class="head" [class.bordered]="mode() !== 'strip'">
        <button class="ic" [title]="mode() === 'lanes' ? 'collapse' : 'expand'" (click)="cycle()">
          {{ mode() === 'strip' ? '▸' : '▾' }}
        </button>
        <span class="lbl">timeline</span>
        @if (mode() === 'strip') {
          <span class="dim">· {{ range() ? fmt(lo()) + ' – ' + fmt(hi()) + ' · ' + spanDays() + 'd' : 'full span' }}{{ day() ? ' · day ' + fmt(day()!) : '' }}</span>
        }
        <span class="sp"></span>
        @if (range()) {
          <span class="chip acc">range <b>{{ fmt(lo()) }} – {{ fmt(hi()) }}</b>
            <span class="x" (click)="store.setTlRange(null)">×</span></span>
        }
        @if (day()) {
          <span class="chip warn">day <b>{{ fmt(day()!) }}</b>
            <span class="x" (click)="store.setTlDay(null)">×</span></span>
        }
        <div class="seg">
          @for (p of presets; track p[0]) {
            <button [class.on]="presetActive(p[1])" (click)="applyPreset(p[1])">{{ p[0] }}</button>
          }
        </div>
      </div>

      @if (mode() !== 'strip') {
        <div class="track-wrap">
          @if (mode() === 'lanes') {
            <div class="lanes-key">
              @for (k of laneKey; track k[0]) {
                <span class="kk"><span class="sw" [style.background]="k[1]"></span>{{ k[0] }}</span>
              }
            </div>
          }
          <div class="ticks">
            @for (t of ticks(); track t.t) {
              <span class="tick" [style.left.%]="pct(t.t)">{{ t.label }}</span>
            }
          </div>
          <div #track class="track" [style.height.px]="mode() === 'lanes' ? 84 : 56"
            (mousedown)="onTrackDown($event)">
            <div class="bars">
              @for (b of bins(); track $index) {
                @if (mode() === 'lanes') {
                  <div class="lane" [style.opacity]="inSel($index) ? 1 : 0.4">
                    <span [style.height.px]="seg(b.stub)" style="background: var(--dim)"></span>
                    <span [style.height.px]="seg(b.draft)" style="background: var(--warn)"></span>
                    <span [style.height.px]="seg(b.normalized)"
                      [style.background]="inSel($index) ? 'var(--accent)' : 'var(--border-strong)'"></span>
                  </div>
                } @else {
                  <div class="bar" [style.height.px]="barH(b.n)"
                    [style.background]="inSel($index) ? 'var(--accent)' : 'var(--border-strong)'"
                    [style.opacity]="inSel($index) ? 0.85 : 0.4"></div>
                }
              }
            </div>
            <div class="band" [style.left.%]="pct(lo())" [style.width.%]="pct(hi()) - pct(lo())"
              (mousedown)="dragBand($event)"></div>
            <div class="handle" [style.left.%]="pct(lo())" (mousedown)="dragHandle('lo', $event)">
              <span class="bar2"></span><span class="knob"></span>
            </div>
            <div class="handle" [style.left.%]="pct(hi())" (mousedown)="dragHandle('hi', $event)">
              <span class="bar2"></span><span class="knob"></span>
            </div>
            @if (day() != null && day()! >= min() && day()! <= max()) {
              <div class="day" [style.left.%]="pct(day()!)" (mousedown)="dragHandle('day', $event)">
                <span class="bar3"></span><span class="tri"></span>
              </div>
            }
          </div>
          @if (!day()) {
            <button class="addday" (click)="store.setTlDay(dayFloor((lo() + hi()) / 2))">+ day cursor</button>
          }
          @if (mode() === 'lanes') {
            <div class="stats">
              @for (s of stats(); track s[0]) {
                <div class="stat"><div class="sl">{{ s[0] }}</div><div class="sv" [style.color]="s[2]">{{ s[1] }}</div></div>
              }
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .tl { height: 100%; display: flex; flex-direction: column; background: var(--surface);
      font-family: var(--mono); }
    .head { flex-shrink: 0; height: 30px; display: flex; align-items: center; gap: 8px; padding: 0 10px;
      background: var(--surface-2); }
    .head.bordered { border-bottom: 1px solid var(--border); }
    .ic { width: 20px; height: 20px; border: none; background: transparent; color: var(--muted);
      cursor: pointer; font-size: 12px; }
    .lbl { font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted);
      font-weight: 600; }
    .dim { font-size: 10px; color: var(--dim); }
    .sp { flex: 1; }
    .chip { display: inline-flex; align-items: center; gap: 6px; height: 20px; padding: 0 4px 0 7px;
      background: var(--surface); border: 1px solid var(--border-strong); font-size: 10px; }
    .chip.acc { border-color: var(--accent); } .chip.warn { border-color: var(--warn); }
    .chip b { font-weight: 500; } .chip .x { cursor: pointer; color: var(--dim); font-size: 13px; }
    .seg { display: inline-flex; border: 1px solid var(--border); }
    .seg button { height: 20px; padding: 0 8px; border: none; border-radius: 0; background: transparent;
      color: var(--muted); font-size: 10px; cursor: pointer; font-family: var(--mono); }
    .seg button.on { background: var(--accent-soft); color: var(--accent); }
    .track-wrap { flex: 1; min-height: 0; overflow: auto; padding: 8px 14px 4px; position: relative; }
    .lanes-key { display: flex; gap: 14px; padding-bottom: 4px; }
    .kk { display: inline-flex; align-items: center; gap: 5px; font-size: 9px; color: var(--muted); }
    .sw { width: 8px; height: 8px; }
    .ticks { position: relative; height: 12px; margin-bottom: 3px; }
    .tick { position: absolute; font-size: 8px; color: var(--dim); }
    .track { position: relative; user-select: none; touch-action: none; border-bottom: 1px solid var(--border); }
    .bars { position: absolute; inset: 0; display: flex; align-items: flex-end; gap: 1px; }
    .bar { flex: 1; min-height: 2px; }
    .lane { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; }
    .lane span { display: block; }
    .band { position: absolute; top: 0; bottom: 0; background: var(--accent-soft); opacity: 0.34;
      border-left: 2px solid var(--accent); border-right: 2px solid var(--accent); cursor: grab; }
    .handle { position: absolute; top: -3px; bottom: -3px; width: 12px; margin-left: -6px; cursor: ew-resize;
      display: flex; justify-content: center; z-index: 3; }
    .handle .bar2 { width: 2px; background: var(--accent); }
    .handle .knob { position: absolute; top: -2px; width: 9px; height: 9px; background: var(--accent);
      border: 1px solid var(--surface); }
    .day { position: absolute; top: -4px; bottom: -4px; width: 10px; margin-left: -5px; cursor: ew-resize;
      display: flex; justify-content: center; z-index: 4; }
    .day .bar3 { width: 2px; background: var(--warn); }
    .day .tri { position: absolute; top: -3px; width: 0; height: 0; border-left: 4px solid transparent;
      border-right: 4px solid transparent; border-top: 5px solid var(--warn); }
    .addday { margin-top: 5px; height: 18px; font-size: 9.5px; padding: 0 6px; border: 1px solid transparent;
      background: transparent; color: var(--muted); cursor: pointer; font-family: var(--mono); }
    .stats { display: flex; border-top: 1px solid var(--border); margin-top: 2px; }
    .stat { flex: 1; padding: 8px 14px; border-right: 1px solid var(--border); }
    .sl { font-size: 8.5px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--dim); }
    .sv { font-size: 18px; font-weight: 600; margin-top: 2px; }
  `],
})
export class WbTimeline {
  readonly store = inject(CorpusStore);
  private track = viewChild<ElementRef<HTMLElement>>('track');
  readonly dayFloor = dayFloor;
  readonly presets: [string, number | null][] = [['fit', null], ['3M', 90], ['1M', 30], ['2W', 14], ['1W', 7]];
  readonly laneKey: [string, string][] = [
    ['records', 'var(--accent)'], ['normalized', 'var(--ok)'], ['draft', 'var(--warn)'], ['stub', 'var(--dim)'],
  ];

  readonly mode = this.store.tlMode;
  readonly range = this.store.tlRange;
  readonly day = this.store.tlDay;
  readonly tl = computed(() => this.store.wbTimeline());
  readonly span2 = computed<[number, number]>(() => this.tl()?.span ?? [0, DAYMS]);
  readonly min = computed(() => this.span2()[0]);
  readonly max = computed(() => this.span2()[1]);
  readonly lo = computed(() => this.range()?.[0] ?? this.min());
  readonly hi = computed(() => this.range()?.[1] ?? this.max());
  readonly bins = computed(() => this.tl()?.bins ?? []);
  readonly binMax = computed(() => Math.max(1, ...this.bins().map((b) => b.n)));
  readonly spanDays = computed(() => Math.round((this.hi() - this.lo()) / DAYMS));
  readonly ticks = computed<Tick[]>(() => this.monthTicks(this.min(), this.max()));
  readonly stats = computed<[string, string | number, string][]>(() => {
    const r = this.tl()?.inRange;
    if (!r) return [];
    return [
      ['in range', r.count, 'var(--accent)'],
      ['normalized', r.normalized, 'var(--ok)'],
      ['drafts', r.drafts, 'var(--warn)'],
      ['stubs', r.stubs, 'var(--dim)'],
      ['origins', r.origins, 'var(--text)'],
      ['span', r.spanDays + 'd', 'var(--text)'],
    ];
  });

  fmt(ms: number): string {
    return fmtDateMs(ms).slice(5).replace('-', '/');
  }
  pct(v: number): number {
    const s = this.max() - this.min() || 1;
    return ((v - this.min()) / s) * 100;
  }
  barH(n: number): number {
    return Math.max(2, (n / this.binMax()) * 52);
  }
  seg(v: number): number {
    return Math.round((v / this.binMax()) * 80);
  }
  inSel(i: number): boolean {
    const n = this.bins().length || 1;
    const bc = (i / n) * 100;
    const bce = ((i + 1) / n) * 100;
    return bce > this.pct(this.lo()) && bc < this.pct(this.hi());
  }
  cycle(): void {
    const next = this.mode() === 'strip' ? 'brush' : this.mode() === 'brush' ? 'lanes' : 'strip';
    this.store.setTlMode(next);
  }
  presetActive(days: number | null): boolean {
    if (days == null) return !this.range();
    if (!this.range()) return false;
    return Math.round((this.hi() - this.lo()) / DAYMS) === days;
  }
  applyPreset(days: number | null): void {
    if (days == null) {
      this.store.setTlRange(null);
      return;
    }
    const end = this.day() ?? this.max();
    const start = Math.max(this.min(), end - days * DAYMS);
    this.store.setTlRange([start, end]);
  }

  private valAt(clientX: number): number {
    const el = this.track()?.nativeElement;
    if (!el) return this.min();
    const rc = el.getBoundingClientRect();
    const t = Math.max(0, Math.min(1, (clientX - rc.left) / rc.width));
    return this.min() + t * (this.max() - this.min());
  }
  onTrackDown(e: MouseEvent): void {
    if ((e.target as HTMLElement).closest('.handle, .band, .day')) return;
    const v = dayFloor(this.valAt(e.clientX));
    const which = Math.abs(v - this.lo()) <= Math.abs(v - this.hi()) ? 'lo' : 'hi';
    this.dragHandle(which, e);
  }
  dragHandle(which: 'lo' | 'hi' | 'day', e: MouseEvent): void {
    e.preventDefault();
    e.stopPropagation();
    const apply = (ev: MouseEvent) => {
      const v = dayFloor(this.valAt(ev.clientX));
      if (which === 'lo') this.store.setTlRange([Math.min(v, this.hi() - DAYMS), this.hi()]);
      else if (which === 'hi') this.store.setTlRange([this.lo(), Math.max(v, this.lo() + DAYMS)]);
      else this.store.setTlDay(v);
    };
    this.attach(apply);
  }
  dragBand(e: MouseEvent): void {
    e.preventDefault();
    e.stopPropagation();
    const w = this.hi() - this.lo();
    const apply = (ev: MouseEvent) => {
      const c = dayFloor(this.valAt(ev.clientX));
      let nl = c - w / 2;
      let nh = c + w / 2;
      if (nl < this.min()) { nl = this.min(); nh = this.min() + w; }
      if (nh > this.max()) { nh = this.max(); nl = this.max() - w; }
      this.store.setTlRange([nl, nh]);
    };
    this.attach(apply);
  }
  private attach(apply: (e: MouseEvent) => void): void {
    const up = () => {
      window.removeEventListener('mousemove', apply);
      window.removeEventListener('mouseup', up);
    };
    window.addEventListener('mousemove', apply);
    window.addEventListener('mouseup', up);
  }
  private monthTicks(min: number, max: number): Tick[] {
    const out: Tick[] = [];
    const d = new Date(min);
    let y = d.getUTCFullYear();
    let m = d.getUTCMonth();
    for (let i = 0; i < 24; i++) {
      const t = Date.UTC(y, m, 1);
      if (t > max) break;
      if (t >= min - 31 * DAYMS) {
        const label = new Date(Math.max(t, min))
          .toLocaleString('en', { month: 'short', timeZone: 'UTC' })
          .toUpperCase();
        out.push({ t: Math.max(t, min), label });
      }
      m++;
      if (m > 11) { m = 0; y++; }
    }
    return out;
  }
}
