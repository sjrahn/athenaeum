// Top · Timeline — three coupled concerns kept distinct (the design's chat-5 model):
//   • WINDOW (tlRange, the FILTER): drag on an empty track to brush a fresh window; drag the
//     band/handles to move/resize it. Narrows the ledger.
//   • ZOOM (tlView, the VISIBLE axis only — NOT a filter): the fit/3M/1M/2W/1W presets rescale
//     what's shown; a preset narrower than the active window is disabled; ‹ › pan when zoomed.
//   • DAY (tlDay, highlight only): a plain click drops a day cursor (inside the window if one is
//     active); it highlights matching ledger rows and never filters.
// Charts the server-computed bins (the in-scope set minus its own range) clipped to the view.

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
interface VBin {
  b: { n: number; normalized: number; draft: number; stub: number };
  center: number;
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
          <span class="chip acc">window <b>{{ fmt(lo()) }} – {{ fmt(hi()) }}</b>
            <span class="x" (click)="store.setTlRange(null)">×</span></span>
        }
        @if (day()) {
          <span class="chip warn">day <b>{{ fmt(day()!) }}</b>
            <span class="x" (click)="store.setTlDay(null)">×</span></span>
        }
        @if (view()) {
          <div class="seg pan">
            <button (click)="pan(-1)" title="pan earlier">‹</button>
            <button (click)="pan(1)" title="pan later">›</button>
          </div>
        }
        <div class="seg">
          @for (p of presets; track p[0]) {
            <button [class.on]="presetActive(p[1])" [disabled]="presetDisabled(p[1])"
              (click)="applyPreset(p[1])">{{ p[0] }}</button>
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
              @for (v of visibleBins(); track $index) {
                @if (mode() === 'lanes') {
                  <div class="lane" [style.opacity]="inSel(v.center) ? 1 : 0.4">
                    <span [style.height.px]="seg(v.b.stub)" style="background: var(--dim)"></span>
                    <span [style.height.px]="seg(v.b.draft)" style="background: var(--warn)"></span>
                    <span [style.height.px]="seg(v.b.normalized)"
                      [style.background]="inSel(v.center) ? 'var(--accent)' : 'var(--border-strong)'"></span>
                  </div>
                } @else {
                  <div class="bar" [style.height.px]="barH(v.b.n)"
                    [style.background]="inSel(v.center) ? 'var(--accent)' : 'var(--border-strong)'"
                    [style.opacity]="inSel(v.center) ? 0.85 : 0.4"></div>
                }
              }
            </div>
            @if (range() && bandW() > 0) {
              <div class="band" [style.left.%]="bandLeft()" [style.width.%]="bandW()"
                (mousedown)="dragBand($event)"></div>
            }
            @if (inView(lo())) {
              <div class="handle" [style.left.%]="pct(lo())" (mousedown)="dragHandle('lo', $event)">
                <span class="bar2"></span><span class="knob"></span>
              </div>
            }
            @if (inView(hi())) {
              <div class="handle" [style.left.%]="pct(hi())" (mousedown)="dragHandle('hi', $event)">
                <span class="bar2"></span><span class="knob"></span>
              </div>
            }
            @if (day() != null && inView(day()!)) {
              <div class="day" [style.left.%]="pct(day()!)" (mousedown)="dragHandle('day', $event)">
                <span class="bar3"></span><span class="tri"></span>
              </div>
            }
          </div>
          @if (!day()) {
            <button class="addday" (click)="store.setTlDay(dayFloor(dayAnchor()))">+ day cursor</button>
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
    .seg button:disabled { color: var(--border-strong); cursor: not-allowed; }
    .seg.pan button { padding: 0 6px; }
    .track-wrap { flex: 1; min-height: 0; overflow: auto; padding: 8px 14px 4px; position: relative; }
    .lanes-key { display: flex; gap: 14px; padding-bottom: 4px; }
    .kk { display: inline-flex; align-items: center; gap: 5px; font-size: 9px; color: var(--muted); }
    .sw { width: 8px; height: 8px; }
    .ticks { position: relative; height: 12px; margin-bottom: 3px; }
    .tick { position: absolute; font-size: 8px; color: var(--dim); transform: translateX(-50%); white-space: nowrap; }
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
  readonly range = this.store.tlRange; // the FILTER window
  readonly view = this.store.tlView; // the visible ZOOM domain (null = full span)
  readonly day = this.store.tlDay;
  readonly tl = computed(() => this.store.wbTimeline());
  readonly span2 = computed<[number, number]>(() => this.tl()?.span ?? [0, DAYMS]);
  readonly min = computed(() => this.span2()[0]);
  readonly max = computed(() => this.span2()[1]);
  // window bounds (default to the full span when no window is brushed)
  readonly lo = computed(() => this.range()?.[0] ?? this.min());
  readonly hi = computed(() => this.range()?.[1] ?? this.max());
  // visible bounds (default to the full span when not zoomed)
  readonly vlo = computed(() => this.view()?.[0] ?? this.min());
  readonly vhi = computed(() => this.view()?.[1] ?? this.max());

  readonly bins = computed(() => this.tl()?.bins ?? []);
  readonly binCount = computed(() => this.tl()?.binCount || this.bins().length || 1);
  readonly step = computed(() => (this.max() - this.min()) / Math.max(1, this.binCount()));
  /** Bins whose time-center falls inside the visible domain, each tagged with its center. */
  readonly visibleBins = computed<VBin[]>(() => {
    const bins = this.bins();
    const step = this.step();
    const min = this.min();
    const vlo = this.vlo();
    const vhi = this.vhi();
    const out: VBin[] = [];
    for (let i = 0; i < bins.length; i++) {
      const center = min + (i + 0.5) * step;
      if (center >= vlo - step / 2 && center <= vhi + step / 2) out.push({ b: bins[i], center });
    }
    return out;
  });
  readonly binMaxVis = computed(() => Math.max(1, ...this.visibleBins().map((v) => v.b.n)));
  readonly spanDays = computed(() => Math.round((this.hi() - this.lo()) / DAYMS));
  readonly viewSpanDays = computed(() => Math.round((this.vhi() - this.vlo()) / DAYMS));
  readonly ticks = computed<Tick[]>(() => this.adaptiveTicks(this.vlo(), this.vhi()));
  readonly bandLeft = computed(() => Math.max(0, this.pct(this.lo())));
  readonly bandW = computed(() => Math.min(100, this.pct(this.hi())) - this.bandLeft());
  readonly dayAnchor = computed(() => (this.range() ? (this.lo() + this.hi()) / 2 : (this.vlo() + this.vhi()) / 2));
  readonly stats = computed<[string, string | number, string][]>(() => {
    const r = this.tl()?.inRange;
    if (!r) return [];
    return [
      ['in window', r.count, 'var(--accent)'],
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
  /** Position a timestamp as a percent of the VISIBLE domain. */
  pct(v: number): number {
    const s = this.vhi() - this.vlo() || 1;
    return ((v - this.vlo()) / s) * 100;
  }
  inView(v: number): boolean {
    return v >= this.vlo() && v <= this.vhi();
  }
  barH(n: number): number {
    return Math.max(2, (n / this.binMaxVis()) * 52);
  }
  seg(v: number): number {
    return Math.round((v / this.binMaxVis()) * 80);
  }
  inSel(center: number): boolean {
    return center >= this.lo() && center <= this.hi();
  }
  cycle(): void {
    const next = this.mode() === 'strip' ? 'brush' : this.mode() === 'brush' ? 'lanes' : 'strip';
    this.store.setTlMode(next);
  }

  // ---- zoom presets + pan (visible axis only) ----
  presetActive(days: number | null): boolean {
    if (days == null) return !this.view();
    return !!this.view() && this.viewSpanDays() === days;
  }
  presetDisabled(days: number | null): boolean {
    // can't zoom narrower than the active window
    return days != null && !!this.range() && days < this.spanDays();
  }
  applyPreset(days: number | null): void {
    if (this.presetDisabled(days)) return;
    if (days == null) {
      this.store.setTlView(null);
      return;
    }
    const min = this.min();
    const max = this.max();
    let width = days * DAYMS;
    const windowW = this.range() ? this.hi() - this.lo() : 0;
    if (width < windowW) width = windowW;
    width = Math.min(width, max - min);
    let center: number;
    if (this.range()) center = (this.lo() + this.hi()) / 2;
    else if (this.day() != null) center = this.day()!;
    else center = max - width / 2;
    let lo = center - width / 2;
    let hi = center + width / 2;
    if (lo < min) { lo = min; hi = min + width; }
    if (hi > max) { hi = max; lo = max - width; }
    this.store.setTlView([lo, hi]);
  }
  pan(dir: -1 | 1): void {
    const v = this.view();
    if (!v) return;
    const min = this.min();
    const max = this.max();
    const w = v[1] - v[0];
    let lo = v[0] + w * 0.5 * dir;
    let hi = v[1] + w * 0.5 * dir;
    if (lo < min) { lo = min; hi = min + w; }
    if (hi > max) { hi = max; lo = max - w; }
    this.store.setTlView([lo, hi]);
  }

  // ---- pointer: drag → window, click → day ----
  private valAt(clientX: number): number {
    const el = this.track()?.nativeElement;
    if (!el) return this.vlo();
    const rc = el.getBoundingClientRect();
    const t = Math.max(0, Math.min(1, (clientX - rc.left) / rc.width));
    return this.vlo() + t * (this.vhi() - this.vlo());
  }
  onTrackDown(e: MouseEvent): void {
    if ((e.target as HTMLElement).closest('.handle, .band, .day')) return;
    e.preventDefault();
    const anchor = dayFloor(this.valAt(e.clientX));
    let moved = false;
    const move = (ev: MouseEvent) => {
      if (Math.abs(ev.clientX - e.clientX) > 3) moved = true;
      if (!moved) return;
      const cur = dayFloor(this.valAt(ev.clientX));
      const a = Math.min(anchor, cur);
      const b = Math.max(anchor, cur);
      this.store.setTlRange([a, Math.max(b, a + DAYMS)]);
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      if (moved) return;
      // a plain click drops the day cursor — only inside the window when one is active
      const rng = this.range();
      if (!rng || (anchor >= rng[0] && anchor <= rng[1])) this.store.setTlDay(anchor);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
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

  // ---- adaptive ticks (month / week / day by visible span; no d3) ----
  private adaptiveTicks(lo: number, hi: number): Tick[] {
    const span = hi - lo || DAYMS;
    const out: Tick[] = [];
    if (span > 120 * DAYMS) {
      const d = new Date(lo);
      let y = d.getUTCFullYear();
      let m = d.getUTCMonth();
      let t = Date.UTC(y, m, 1);
      if (t < lo) { m++; if (m > 11) { m = 0; y++; } t = Date.UTC(y, m, 1); }
      while (t <= hi && out.length < 24) {
        out.push({ t, label: this.monthLabel(t) });
        m++; if (m > 11) { m = 0; y++; } t = Date.UTC(y, m, 1);
      }
    } else if (span > 45 * DAYMS) {
      let t = this.mondayOnOrAfter(lo);
      while (t <= hi && out.length < 20) { out.push({ t, label: this.dayLabel(t) }); t += 7 * DAYMS; }
    } else {
      const days = Math.max(1, Math.round(span / DAYMS));
      const stepD = Math.max(1, Math.ceil(days / 14));
      let t = Math.ceil(lo / DAYMS) * DAYMS;
      while (t <= hi && out.length < 16) { out.push({ t, label: this.dayLabel(t) }); t += stepD * DAYMS; }
    }
    return out;
  }
  private monthLabel(t: number): string {
    return new Date(t).toLocaleString('en', { month: 'short', timeZone: 'UTC' }).toUpperCase();
  }
  private dayLabel(t: number): string {
    return new Date(t)
      .toLocaleString('en', { month: 'short', day: 'numeric', timeZone: 'UTC' })
      .toUpperCase();
  }
  private mondayOnOrAfter(ms: number): number {
    const f = dayFloor(ms);
    const dow = new Date(f).getUTCDay(); // 0=Sun
    const add = (8 - (dow || 7)) % 7;
    return f + add * DAYMS;
  }
}
