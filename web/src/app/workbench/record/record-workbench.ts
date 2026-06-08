// Record Workbench — a focused single-record workspace reusing the same dock/panel system
// as the corpus workbench, with a work-mode switcher (inspect · compare · crop · graph;
// keys 1–4). inspect: contents · reader · inspector · related. compare: reader beside the
// real source artifact. crop: the bbox editor. graph: connections across the corpus.
// `[` / `]` step through the current result set; Esc returns to the corpus (app shell).

import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { CorpusStore } from '../../core/store';
import { flatSegments, mimeInfo, fmtBytes, segKey, titleFor } from '../../core/util';
import { PaneConfig, WbDock } from '../dock/wb-dock';
import { WbDockState } from '../dock/wb-dock-state';
import { Slot } from '../../core/slot';
import { PickEvent } from '../../viewer/body';
import { CxMimeChip } from '../../chips/chips';
import { RwContents, RwReader, RwInspector, RwRelated } from './rw-panes';
import { RwCompare } from './rw-compare';
import { RwCropper } from './rw-cropper';
import { RwGraph } from './rw-graph';

type ReaderView = 'reading' | 'segments' | 'source';
const MODES: [string, string, string][] = [
  ['inspect', 'inspect', 'metadata & normalized reader'],
  ['compare', 'compare', 'normalized vs. source artifact'],
  ['crop', 'crop', 'bbox & addressing editor'],
  ['graph', 'graph', 'connections across the corpus'],
];

@Component({
  selector: 'cx-record-workbench',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [WbDockState],
  imports: [
    WbDock, Slot, CxMimeChip,
    RwContents, RwReader, RwInspector, RwRelated, RwCompare, RwCropper, RwGraph,
  ],
  template: `
    @if (r(); as rec) {
      <div class="rw">
        <!-- top bar -->
        <div class="bar">
          <button class="back" (click)="store.back()">‹ corpus</button>
          <span class="div"></span>
          <cx-mime-chip [m]="rec.mime" />
          <span class="ttl">{{ title(rec) }}</span>
          <span class="id">· {{ rec.id.slice(0, 12) }}…</span>
          <span class="sp"></span>
          @if (sibIdx() >= 0) {
            <span class="pos">{{ sibIdx() + 1 }} / {{ siblings().length }}</span>
            <div class="nav">
              <button (click)="go(-1)" [disabled]="sibIdx() <= 0" title="previous [">‹</button>
              <button (click)="go(1)" [disabled]="sibIdx() >= siblings().length - 1" title="next ]">›</button>
            </div>
          }
          <button class="close" (click)="store.back()" title="close ⎋">✕</button>
        </div>

        <!-- work-mode switcher -->
        <div class="modebar">
          <div class="modes">
            @for (m of modes; track m[0]; let i = $index) {
              <button [class.on]="store.workMode() === m[0]" [title]="m[2] + ' · ' + (i + 1)"
                (click)="store.setWorkMode($any(m[0]))">{{ m[1] }}</button>
            }
          </div>
          <span class="mdesc">{{ modeDesc() }}</span>
          <span class="sp"></span>
          <span class="minfo">{{ flat().length }} segments · {{ short(rec.mime) }}{{ rec.transport.size ? ' · ' + fmtBytes(rec.transport.size) : '' }}</span>
        </div>

        <!-- work surface -->
        <div class="surface">
          @switch (store.workMode()) {
            @case ('crop') { <rw-cropper [r]="rec" [startPage]="cropPage()" /> }
            @case ('graph') { <rw-graph [r]="rec" /> }
            @case ('compare') {
              <wb-dock [topHeight]="0" [left]="contentsPane" [right]="comparePane" [bottom]="relatedOffPane">
                <ng-template slot="left"><rw-contents [r]="rec" [activeKey]="activeKey()" (pick)="onPick($event)" /></ng-template>
                <ng-template slot="center"><rw-reader [r]="rec" [view]="readerView()" [activeKey]="activeKey()"
                  (pick)="onPick($event)" (setView)="readerView.set($event)" /></ng-template>
                <ng-template slot="right"><rw-compare [r]="rec" [activeSeg]="activeSeg()" (crop)="store.setWorkMode('crop')" /></ng-template>
                <ng-template slot="bottom"><rw-related [r]="rec" /></ng-template>
              </wb-dock>
            }
            @default {
              <wb-dock [topHeight]="0" [left]="contentsPane" [right]="inspectorPane" [bottom]="relatedPane">
                <ng-template slot="left"><rw-contents [r]="rec" [activeKey]="activeKey()" (pick)="onPick($event)" /></ng-template>
                <ng-template slot="center"><rw-reader [r]="rec" [view]="readerView()" [activeKey]="activeKey()"
                  (pick)="onPick($event)" (setView)="readerView.set($event)" /></ng-template>
                <ng-template slot="right"><rw-inspector [r]="rec" (pick)="onPick($event)" /></ng-template>
                <ng-template slot="bottom"><rw-related [r]="rec" /></ng-template>
              </wb-dock>
            }
          }
        </div>
      </div>
    }
  `,
  styles: [`
    .rw { position: absolute; inset: 0; display: flex; flex-direction: column; background: var(--bg);
      color: var(--text); overflow: hidden; font-family: var(--mono); }
    .bar { flex-shrink: 0; height: 46px; background: var(--surface); border-bottom: 1px solid var(--border);
      display: flex; align-items: center; gap: 10px; padding: 0 12px; }
    .back { height: 28px; padding: 0 8px; border: none; background: transparent; color: var(--muted);
      font-family: var(--mono); font-size: 11px; cursor: pointer; }
    .div { width: 1px; height: 18px; background: var(--border); }
    .ttl { font-family: var(--sans); font-weight: 600; font-size: 14px; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; }
    .id { font-size: 9px; color: var(--dim); flex-shrink: 0; }
    .sp { flex: 1; }
    .pos { font-size: 10.5px; color: var(--dim); }
    .nav { display: inline-flex; border: 1px solid var(--border); }
    .nav button { height: 26px; width: 28px; border: none; background: transparent; color: var(--muted);
      cursor: pointer; font-family: var(--mono); } .nav button:disabled { opacity: 0.35; }
    .close { height: 28px; width: 30px; border: none; background: transparent; color: var(--muted);
      cursor: pointer; font-size: 14px; }
    .modebar { flex-shrink: 0; height: 38px; display: flex; align-items: center; gap: 12px; padding: 0 12px;
      border-bottom: 1px solid var(--border); background: var(--surface-2); }
    .modes { display: inline-flex; border: 1px solid var(--border); background: var(--surface); }
    .modes button { height: 26px; padding: 0 15px; border: none; border-right: 1px solid var(--border);
      border-radius: 0; background: transparent; color: var(--muted); font-size: 11px; cursor: pointer;
      font-family: var(--mono); }
    .modes button:last-child { border-right: none; }
    .modes button.on { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
    .mdesc { font-size: 10px; color: var(--dim); }
    .minfo { font-size: 9.5px; color: var(--dim); }
    .surface { flex: 1; min-height: 0; position: relative; }
  `],
})
export class CxRecordWorkbench {
  readonly store = inject(CorpusStore);
  readonly title = titleFor;
  readonly fmtBytes = fmtBytes;
  readonly modes = MODES;

  readonly contentsPane: PaneConfig = { label: 'contents', defaultW: 244 };
  readonly inspectorPane: PaneConfig = { label: 'inspector', defaultW: 348 };
  readonly comparePane: PaneConfig = { label: 'source', defaultW: 520 };
  readonly relatedPane: PaneConfig = { label: 'related', defaultOn: true, defaultH: 188 };
  readonly relatedOffPane: PaneConfig = { label: 'related', defaultOn: false, defaultH: 170 };

  readonly r = this.store.record;
  readonly flat = computed(() => flatSegments(this.r()));
  readonly activeKey = signal<string | null>(null);
  readonly readerView = signal<ReaderView>('reading');
  readonly activeSeg = computed(() => {
    const k = this.activeKey();
    return this.flat().find((f) => segKey(f.seg) === k)?.seg ?? null;
  });
  readonly siblings = computed(() => this.store.wbRows().map((x) => x.id));
  readonly sibIdx = computed(() => this.siblings().indexOf(this.store.recordId() ?? ''));
  readonly modeDesc = computed(() => MODES.find((m) => m[0] === this.store.workMode())?.[2] ?? '');
  readonly cropPage = computed(() => {
    const s = this.activeSeg();
    if (!s) return 1;
    const a = s.address;
    const first = Array.isArray(a) ? a[0] : a;
    const m = /page=(\d+)/.exec(first ?? '');
    return m ? +m[1] : 1;
  });

  constructor() {
    // reset transient state when the open record changes
    effect(() => {
      this.store.recordId();
      this.activeKey.set(null);
      this.readerView.set('reading');
    });
  }

  short(m: string): string {
    return mimeInfo(m).short;
  }
  onPick(ev: PickEvent): void {
    this.activeKey.set(ev.key);
  }
  go(d: number): void {
    const next = this.siblings()[this.sibIdx() + d];
    if (next) this.store.openRecord(next);
  }

  @HostListener('window:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    const t = e.target as HTMLElement;
    if (t && /input|textarea|select/i.test(t.tagName)) return;
    if (e.key === '[' || e.key === ']') {
      e.preventDefault();
      this.go(e.key === ']' ? 1 : -1);
    } else if (e.key >= '1' && e.key <= '4') {
      const m = MODES[+e.key - 1];
      if (m) this.store.setWorkMode(m[0] as 'inspect' | 'compare' | 'crop' | 'graph');
    }
  }
}
