// Crop mode · bbox region editor (net-new). Draw / move / resize boxes over the artifact
// page (PDF page via resolve?page=N, or the image). Each box maps to a segment address
// (bbox=x,y,w,h on page=N) with an atom + overlay. Seeded from the record's existing bbox
// segments. Save POSTs to /records/{id}/regions (the real write endpoint) via
// store.saveRegions, which reloads the record so the editor re-seeds from the canonical
// addresses the server wrote.

import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { CorpusStore } from '../../core/store';
import { RegionPayload } from '../../core/api';
import { RecordDetail } from '../../core/models';
import { atomColor, flatSegments, parseAddr, titleFor } from '../../core/util';
import { CxMimeChip } from '../../chips/chips';

interface Region {
  id: string;
  page: number;
  box: [number, number, number, number]; // x,y,w,h normalized
  atom: string;
  overlay: string;
  entry: string;
}
// The cropper draws bboxes over visual artifacts (PDF pages / images), so it offers the
// two atoms a drawn region can carry; audio/video are temporal (time=/frame=), not bbox.
const ATOMS = ['text', 'image'];
const OVERLAYS: Record<string, string[]> = {
  text: ['', 'data-table', 'transcript', 'ocr', 'captions'],
  image: [''],
};
const clamp = (n: number) => Math.max(0, Math.min(1, n));

@Component({
  selector: 'rw-cropper',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip],
  template: `
    <div class="crop">
      <div class="bar">
        <cx-mime-chip [m]="r().mime" />
        <span class="ttl">{{ title(r()) }}</span><span class="dim">· region editor</span>
        <span class="sp"></span>
        <div class="seg">
          @for (t of tools; track t[0]) {
            <button [class.on]="tool() === t[0]" (click)="tool.set($any(t[0]))">{{ t[1] }}</button>
          }
        </div>
        @if (dirty()) { <span class="unsaved">● unsaved</span> }
        <button class="btn" (click)="revert()" [disabled]="saving()">revert</button>
        <button class="btn primary" (click)="save()" [disabled]="saving()">{{ saving() ? 'saving…' : 'save regions' }}</button>
      </div>

      <div class="work">
        <div class="stagewrap">
          @if (paged()) {
            <div class="pagebar">
              <span class="dim">page</span>
              <button class="nav" (click)="setPage(page() - 1)">‹</button>
              <span class="pn">{{ page() }} / {{ pages() }}</span>
              <button class="nav" (click)="setPage(page() + 1)">›</button>
              <span class="sp"></span>
              <span class="dim">{{ pageRegions().length }} on page · {{ tool() === 'draw' ? 'drag to draw' : 'click a box to edit' }}</span>
            </div>
          }
          <div class="scroll cx-scroll">
            <div #stage class="stage" (pointerdown)="onStageDown($event)"
              [style.cursor]="tool() === 'draw' ? 'crosshair' : 'default'">
              <img [src]="pageSrc()" alt="" draggable="false" />
              @for (rg of pageRegions(); track rg.id) {
                <div class="box" [class.sel]="sel() === rg.id"
                  [style.left.%]="rg.box[0] * 100" [style.top.%]="rg.box[1] * 100"
                  [style.width.%]="rg.box[2] * 100" [style.height.%]="rg.box[3] * 100"
                  [style.borderColor]="sel() === rg.id ? 'var(--accent)' : color(rg.atom)"
                  (pointerdown)="onBoxDown($event, rg)">
                  <span class="tag" [style.background]="sel() === rg.id ? 'var(--accent)' : color(rg.atom)">
                    {{ rg.atom }}{{ rg.overlay ? '/' + rg.overlay : '' }}</span>
                  @if (sel() === rg.id && tool() === 'select') {
                    @for (h of handles; track h) {
                      <span class="h" [attr.data-h]="h" [class]="'h-' + h" (pointerdown)="onResize($event, rg, h)"></span>
                    }
                  }
                </div>
              }
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="ph"><span class="t-label">regions · {{ regions().length }}</span>
            <span class="sp"></span><span class="dim">→ segment blocks</span></div>
          <div class="rlist cx-scroll">
            @for (rg of regions(); track rg.id) {
              <div class="rrow" [class.on]="sel() === rg.id" (click)="select(rg)">
                <div class="rtop"><span class="dot" [style.background]="color(rg.atom)"></span>
                  <span class="addr">{{ boxAddr(rg) }}</span><span class="sp"></span>
                  <span class="x" (click)="remove($event, rg)">×</span></div>
                <div class="rsel">
                  <select [value]="rg.atom" (click)="$event.stopPropagation()" (change)="setAtom(rg, $any($event.target).value)">
                    @for (a of atoms; track a) { <option [value]="a">atom · {{ a }}</option> }
                  </select>
                  <select [value]="rg.overlay" (click)="$event.stopPropagation()" (change)="patch(rg, { overlay: $any($event.target).value })">
                    @for (o of overlaysFor(rg.atom); track o) { <option [value]="o">{{ o ? 'overlay · ' + o : 'no overlay' }}</option> }
                  </select>
                </div>
                <input class="entry" [value]="rg.entry" (click)="$event.stopPropagation()"
                  (input)="patch(rg, { entry: $any($event.target).value })" placeholder="entry label (optional)…" />
              </div>
            }
            @if (regions().length === 0) { <div class="empty">no regions. switch to draw and drag a box on the page.</div> }
          </div>
        </div>
      </div>

      @if (toast()) { <div class="toast" [class.err]="toastErr()">{{ toastErr() ? '✕' : '✓' }} {{ toast() }}</div> }
    </div>
  `,
  styles: [`
    .crop { position: absolute; inset: 0; display: flex; flex-direction: column; background: var(--surface);
      font-family: var(--mono); }
    .bar { flex-shrink: 0; min-height: 40px; border-bottom: 1px solid var(--border); background: var(--surface-2);
      display: flex; align-items: center; gap: 10px; padding: 0 14px; font-size: 11px; }
    .ttl { font-family: var(--sans); font-weight: 600; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .dim { color: var(--dim); } .sp { flex: 1; }
    .seg { display: inline-flex; border: 1px solid var(--border); }
    .seg button { height: 22px; padding: 0 9px; border: none; border-radius: 0; background: transparent;
      color: var(--muted); font-size: 10px; cursor: pointer; font-family: var(--mono); }
    .seg button.on { background: var(--accent-soft); color: var(--accent); }
    .unsaved { color: var(--warn); font-size: 10px; }
    .btn { height: 24px; padding: 0 10px; border: 1px solid var(--border); background: var(--surface);
      color: var(--text); font-family: var(--mono); font-size: 11px; cursor: pointer; }
    .btn.primary { background: var(--accent); color: #fff; border-color: transparent; }
    .work { flex: 1; min-height: 0; display: flex; }
    .stagewrap { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column;
      background: var(--surface-2); border-right: 1px solid var(--border); }
    .pagebar { flex-shrink: 0; height: 30px; border-bottom: 1px solid var(--border); background: var(--surface);
      display: flex; align-items: center; gap: 8px; padding: 0 12px; font-size: 10px; }
    .nav { width: 22px; height: 20px; border: 1px solid var(--border); background: var(--surface); cursor: pointer; }
    .pn { min-width: 46px; text-align: center; }
    .scroll { flex: 1; overflow: auto; display: flex; justify-content: center; align-items: flex-start; padding: 22px; }
    .stage { position: relative; flex-shrink: 0; touch-action: none; max-width: 100%; }
    .stage img { display: block; max-width: 760px; width: 100%; height: auto; box-shadow: 0 8px 30px rgba(0,0,0,0.18); user-select: none; }
    .box { position: absolute; border: 1.5px solid; background: rgba(163,90,0,0.06); box-sizing: border-box; }
    .box.sel { background: rgba(163,90,0,0.12); }
    .tag { position: absolute; top: -16px; left: -1.5px; font-size: 8.5px; color: #fff; padding: 0 4px; white-space: nowrap; }
    .h { position: absolute; width: 11px; height: 11px; background: #fff; border: 1.5px solid var(--accent);
      transform: translate(-50%, -50%); }
    .h-nw { left: 0; top: 0; } .h-n { left: 50%; top: 0; } .h-ne { left: 100%; top: 0; }
    .h-e { left: 100%; top: 50%; } .h-se { left: 100%; top: 100%; } .h-s { left: 50%; top: 100%; }
    .h-sw { left: 0; top: 100%; } .h-w { left: 0; top: 50%; }
    .panel { width: 320px; flex-shrink: 0; display: flex; flex-direction: column; background: var(--surface); min-height: 0; }
    .ph { flex-shrink: 0; padding: 9px 12px; border-bottom: 1px solid var(--border); display: flex; align-items: center; }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted); }
    .rlist { flex: 1; overflow: auto; min-height: 0; }
    .rrow { padding: 8px 12px; border-bottom: 1px solid var(--border); cursor: pointer; border-left: 2px solid transparent; }
    .rrow.on { background: var(--accent-soft); border-left-color: var(--accent); }
    .rtop { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
    .dot { width: 9px; height: 9px; flex-shrink: 0; }
    .addr { font-size: 9px; color: var(--muted); } .x { cursor: pointer; color: var(--dim); font-size: 12px; }
    .rsel { display: flex; gap: 6px; margin-bottom: 6px; }
    .rsel select { flex: 1; height: 22px; font-family: var(--mono); font-size: 10px; background: var(--surface);
      color: var(--text); border: 1px solid var(--border); outline: none; }
    .entry { width: 100%; height: 22px; font-family: var(--mono); font-size: 10px; background: var(--bg);
      color: var(--text); border: 1px solid var(--border); outline: none; padding: 0 6px; }
    .empty { padding: 14px; font-size: 10px; color: var(--dim); }
    .toast { position: absolute; bottom: 32px; left: 50%; transform: translateX(-50%); background: var(--text);
      color: var(--bg); font-size: 11px; padding: 7px 14px; box-shadow: var(--sh-float); z-index: 50; }
    .toast.err { background: var(--err); color: #fff; }
    .btn:disabled { opacity: 0.55; cursor: default; }
  `],
})
export class RwCropper {
  private store = inject(CorpusStore);
  r = input.required<RecordDetail>();
  startPage = input(1);
  private stage = viewChild<ElementRef<HTMLElement>>('stage');

  readonly title = titleFor;
  readonly color = atomColor;
  readonly atoms = ATOMS;
  readonly tools: [string, string][] = [['draw', '⊞ draw'], ['select', '⤢ select']];
  readonly handles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

  readonly tool = signal<'draw' | 'select'>('draw');
  readonly page = signal(1);
  readonly sel = signal<string | null>(null);
  readonly dirty = signal(false);
  readonly toast = signal<string | null>(null);
  readonly toastErr = signal(false);
  readonly saving = signal(false);
  readonly regions = signal<Region[]>([]);

  readonly paged = computed(() => !this.r().isImage && !!this.r().pages);
  readonly pages = computed(() => this.r().pages ?? 1);
  readonly pageRegions = computed(() => this.regions().filter((rg) => rg.page === this.page()));
  readonly pageSrc = computed(() => {
    const r = this.r();
    return this.paged()
      ? this.store.resolveUrl(`corpus://${r.id}?page=${this.page()}`)
      : this.store.artifactUrl(r.id);
  });

  private drag: { mode: 'draw' | 'move' | 'resize'; id: string; ox?: number; oy?: number; dx?: number; dy?: number; h?: string } | null = null;

  constructor() {
    effect(() => {
      // reseed when the record changes
      const r = this.r();
      const seed: Region[] = [];
      let i = 0;
      for (const f of flatSegments(r)) {
        const a = parseAddr(f.seg.address);
        if (a.bbox && (!this.paged() || a.page)) {
          seed.push({
            id: 'seg-' + i++,
            page: a.page ?? 1,
            box: a.bbox.slice(0, 4) as [number, number, number, number],
            atom: f.seg.atom,
            overlay: f.seg.overlay ?? '',
            entry: f.seg.entry ?? '',
          });
        }
      }
      if (seed.length === 0) {
        seed.push({ id: 'r0', page: 1, box: [0.12, 0.14, 0.62, 0.12], atom: 'text', overlay: '', entry: 'region 1' });
      }
      this.regions.set(seed);
      this.dirty.set(false);
      this.sel.set(seed[0]?.id ?? null);
      this.page.set(this.startPage() || 1);
    });
  }

  setPage(p: number): void {
    this.page.set(Math.max(1, Math.min(this.pages(), p)));
  }
  select(rg: Region): void {
    this.sel.set(rg.id);
    if (this.paged()) this.page.set(rg.page);
  }
  overlaysFor(atom: string): string[] {
    return OVERLAYS[atom] ?? [''];
  }
  boxAddr(rg: Region): string {
    const b = rg.box.map((n) => Math.round(n * 1000) / 1000).join(',');
    return (this.paged() ? `page=${rg.page}&` : '') + `bbox=${b}`;
  }
  patch(rg: Region, p: Partial<Region>): void {
    this.regions.update((rs) => rs.map((x) => (x.id === rg.id ? { ...x, ...p } : x)));
    this.dirty.set(true);
  }
  setAtom(rg: Region, atom: string): void {
    this.patch(rg, { atom, overlay: '' });
  }
  remove(e: Event, rg: Region): void {
    e.stopPropagation();
    this.regions.update((rs) => rs.filter((x) => x.id !== rg.id));
    if (this.sel() === rg.id) this.sel.set(null);
    this.dirty.set(true);
  }
  revert(): void {
    // re-trigger the seed effect by toggling dirty off; simplest is to re-read segments
    const r = this.r();
    const seed: Region[] = [];
    let i = 0;
    for (const f of flatSegments(r)) {
      const a = parseAddr(f.seg.address);
      if (a.bbox && (!this.paged() || a.page)) {
        seed.push({
          id: 'seg-' + i++, page: a.page ?? 1, box: a.bbox.slice(0, 4) as [number, number, number, number],
          atom: f.seg.atom, overlay: f.seg.overlay ?? '', entry: f.seg.entry ?? '',
        });
      }
    }
    this.regions.set(seed);
    this.dirty.set(false);
    this.sel.set(seed[0]?.id ?? null);
  }
  async save(): Promise<void> {
    if (this.saving()) return;
    this.saving.set(true);
    const payload: RegionPayload[] = this.regions().map((rg) => ({
      page: this.paged() ? rg.page : null,
      box: rg.box,
      atom: rg.atom,
      overlay: rg.overlay || '',
      entry: rg.entry || '',
    }));
    try {
      const res = await this.store.saveRegions(this.r().id, payload);
      this.dirty.set(false);
      this.toastErr.set(false);
      this.toast.set(`saved ${res.bbox_segment_count} regions → ${this.r().id.slice(0, 8)}….md`);
    } catch (e) {
      this.toastErr.set(true);
      this.toast.set(`save failed: ${(e as Error).message}`);
    } finally {
      this.saving.set(false);
      setTimeout(() => this.toast.set(null), 3200);
    }
  }

  private norm(cx: number, cy: number): [number, number] {
    const el = this.stage()?.nativeElement;
    if (!el) return [0, 0];
    const rc = el.getBoundingClientRect();
    return [clamp((cx - rc.left) / rc.width), clamp((cy - rc.top) / rc.height)];
  }
  onStageDown(e: PointerEvent): void {
    if (this.tool() !== 'draw') return;
    if ((e.target as HTMLElement).dataset['h']) return;
    const [x, y] = this.norm(e.clientX, e.clientY);
    const id = 'r' + this.regions().length + '_' + Math.round(x * 1000);
    this.regions.update((rs) => [...rs, { id, page: this.page(), box: [x, y, 0.001, 0.001], atom: 'text', overlay: '', entry: '' }]);
    this.sel.set(id);
    this.dirty.set(true);
    this.drag = { mode: 'draw', id, ox: x, oy: y };
    this.attach();
  }
  onBoxDown(e: PointerEvent, rg: Region): void {
    if (this.tool() === 'select') {
      e.stopPropagation();
      const [x, y] = this.norm(e.clientX, e.clientY);
      this.sel.set(rg.id);
      this.drag = { mode: 'move', id: rg.id, dx: x - rg.box[0], dy: y - rg.box[1] };
      this.attach();
    } else {
      e.stopPropagation();
      this.sel.set(rg.id);
    }
  }
  onResize(e: PointerEvent, rg: Region, h: string): void {
    e.stopPropagation();
    this.sel.set(rg.id);
    this.drag = { mode: 'resize', id: rg.id, h };
    this.attach();
  }
  private attach(): void {
    const move = (e: PointerEvent) => this.onMove(e);
    const up = () => {
      this.drag = null;
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }
  private onMove(e: PointerEvent): void {
    const d = this.drag;
    if (!d) return;
    const [x, y] = this.norm(e.clientX, e.clientY);
    this.regions.update((rs) =>
      rs.map((rg) => {
        if (rg.id !== d.id) return rg;
        let [bx, by, bw, bh] = rg.box;
        if (d.mode === 'draw') {
          bx = Math.min(d.ox!, x); by = Math.min(d.oy!, y); bw = Math.abs(x - d.ox!); bh = Math.abs(y - d.oy!);
        } else if (d.mode === 'move') {
          bx = clamp(x - d.dx!); by = clamp(y - d.dy!); bx = Math.min(bx, 1 - bw); by = Math.min(by, 1 - bh);
        } else {
          const r2 = bx + bw;
          const b2 = by + bh;
          if (d.h!.includes('e')) bw = Math.max(0.01, x - bx);
          if (d.h!.includes('s')) bh = Math.max(0.01, y - by);
          if (d.h!.includes('w')) { bx = Math.min(x, r2 - 0.01); bw = r2 - bx; }
          if (d.h!.includes('n')) { by = Math.min(y, b2 - 0.01); bh = b2 - by; }
        }
        return { ...rg, box: [bx, by, bw, bh] };
      }),
    );
    this.dirty.set(true);
  }
}
