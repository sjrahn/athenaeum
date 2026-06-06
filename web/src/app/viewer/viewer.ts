import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { CorpusStore } from '../core/store';
import { Viewport } from '../core/viewport';
import { Region } from '../core/models';
import { firstAddr, mimeInfo, parseAddr, titleFor } from '../core/util';
import { CxMimeChip, CxStatusChip, CxVisChip } from '../chips/chips';
import { CxArtifactView } from './artifact';
import { CxRawBody, CxRenderedBody, PickEvent } from './body';
import {
  CxAnnotationsTab,
  CxEmbedView,
  CxEmbedsTab,
  CxMetadataTab,
  CxProvenanceTab,
} from './tabs';

type TabId = 'split' | 'embeds' | 'metadata' | 'provenance' | 'annotations';
type BodyMode = 'rendered' | 'source';

/** Dual-pane record viewer: real artifact (left) ∥ record body (right, rendered
 *  markdown ⇄ raw source). Clicking a segment synced-highlights the artifact region. */
@Component({
  selector: 'cx-viewer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    NgTemplateOutlet,
    CxMimeChip,
    CxStatusChip,
    CxVisChip,
    CxArtifactView,
    CxEmbedView,
    CxRenderedBody,
    CxRawBody,
    CxEmbedsTab,
    CxMetadataTab,
    CxProvenanceTab,
    CxAnnotationsTab,
  ],
  template: `
    @if (store.record(); as r) {
      <div class="viewer">
        <!-- header -->
        <div class="header">
          <div class="hrow">
            <cx-mime-chip [m]="r.mime" [big]="true" />
            <span class="title">{{ title(r) }}</span>
            <span class="spacer"></span>
            @if (canCrop()) { <button class="btn" (click)="store.openCrop()">⛶ crop / regions</button> }
            <button class="btn btn-ghost" (click)="copyUri(r.id)">copy uri</button>
          </div>
          <div class="chips">
            <cx-status-chip [status]="r.status" /><cx-vis-chip [visibility]="r.visibility" />
            <span class="id">{{ r.id.slice(0, 18) }}…</span>
          </div>
          <div class="mono meta cx-meta">
            <span>{{ r.origins[0]?.uri?.[0] || '—' }}</span><span>·</span>
            <span>transport {{ r.transport.size ?? '—' }}</span>
            @if (r.embeds.length) { <span>·</span><span>{{ r.embeds.length }} embeds</span> }
            <span>·</span><span>captured {{ r.captured || '—' }}</span>
          </div>
        </div>

        <!-- tab strip -->
        <div class="cx-tabs tabs">
          @for (t of tabs(); track t[0]) {
            <div class="tab" role="tab" [attr.aria-selected]="tab() === t[0]"
              [class.on]="tab() === t[0]" (click)="tab.set(t[0])">{{ t[1] }}</div>
          }
          <span class="spacer"></span>
          @if (tab() === 'split' && hasArtifact()) {
            <div class="toggle">
              @for (m of bodyModes; track m[0]) {
                <button class="tbtn" [class.on]="bodyMode() === m[0]" (click)="bodyMode.set(m[0])">{{ m[1] }}</button>
              }
            </div>
          }
        </div>

        <!-- tab body -->
        <div class="tabbody">
          @switch (tab()) {
            @case ('split') {
              @if (hasArtifact()) {
                @if (mobile()) {
                  <div class="msplit">
                    <div class="mseg">
                      @for (p of paneDefs; track p[0]) {
                        <button class="msegbtn" [class.on]="pane() === p[0]" (click)="pane.set(p[0])">{{ p[1] }}</button>
                      }
                    </div>
                    @if (pane() === 'artifact') {
                      <div class="mart">
                        <ng-container [ngTemplateOutlet]="selbar" [ngTemplateOutletContext]="{ r: r }" />
                        <ng-container [ngTemplateOutlet]="artifactPane" [ngTemplateOutletContext]="{ r: r }" />
                      </div>
                    } @else {
                      <div class="cx-scroll mbody">
                        <ng-container [ngTemplateOutlet]="bodyPane" [ngTemplateOutletContext]="{ r: r }" />
                      </div>
                    }
                  </div>
                } @else {
                  <div class="left">
                    <ng-container [ngTemplateOutlet]="selbar" [ngTemplateOutletContext]="{ r: r }" />
                    <ng-container [ngTemplateOutlet]="artifactPane" [ngTemplateOutletContext]="{ r: r }" />
                  </div>
                  <div class="right cx-scroll">
                    <ng-container [ngTemplateOutlet]="bodyPane" [ngTemplateOutletContext]="{ r: r }" />
                  </div>
                }
              } @else {
                <div class="right full cx-scroll">
                  <cx-rendered-body [r]="r" [activeKey]="activeKey()" (pick)="onPick($event)" />
                </div>
              }
            }
            @case ('embeds') { <cx-embeds-tab [r]="r" (region)="setRegion($event)" /> }
            @case ('metadata') { <cx-metadata-tab [r]="r" /> }
            @case ('provenance') { <cx-provenance-tab [r]="r" /> }
            @case ('annotations') { <cx-annotations-tab [r]="r" (region)="setRegion($event)" /> }
          }
        </div>
      </div>

      <!-- shared panes (desktop side-by-side ⇄ mobile artifact/body toggle) -->
      <ng-template #selbar let-r="r">
        <div class="cx-scroll selbar">
          <div class="sel" [class.on]="viewEmbed() === null" (click)="viewEmbed.set(null)">
            <cx-mime-chip [m]="r.transport.mime" />
            <span class="sname">{{ r.transport.name }}</span>
            <span class="tlabel">TRANSPORT</span>
            <span class="dim">{{ r.transport.size ?? '' }}</span>
          </div>
          @if (r.embeds.length) { <div class="embsep">embeds</div> }
          @for (e of r.embeds; track $index; let i = $index) {
            <div class="sel" [class.on]="viewEmbed() === i" (click)="viewEmbed.set(i)">
              <cx-mime-chip [m]="e.mime" />
              <span class="sname">{{ firstAddr(e.address) }}</span>
            </div>
          }
        </div>
      </ng-template>
      <ng-template #artifactPane let-r="r">
        @if (viewEmbed() === null) {
          <cx-artifact-view [r]="r" [activeRegion]="activeRegion()" />
        } @else {
          <cx-embed-view [embed]="r.embeds[viewEmbed()!]" [recordId]="r.id" />
        }
      </ng-template>
      <ng-template #bodyPane let-r="r">
        @if (bodyMode() === 'rendered') {
          <cx-rendered-body [r]="r" [activeKey]="activeKey()" (pick)="onPick($event)" />
        } @else {
          <cx-raw-body [r]="r" />
        }
      </ng-template>
    } @else {
      <div class="loading">loading record…</div>
    }
  `,
  styles: [`
    .viewer { flex: 1; display: flex; flex-direction: column; min-height: 0; background: var(--surface); }
    .header { flex-shrink: 0; padding: 11px 16px 9px; border-bottom: 1px solid var(--border); }
    .hrow { display: flex; align-items: center; gap: 7px; margin-bottom: 7px; }
    .title { font-family: var(--sans); font-size: 16px; font-weight: 700; min-width: 0; overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap; }
    .spacer { flex: 1; }
    .chips { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin-bottom: 5px; }
    .id { font-family: var(--mono); font-size: 9px; color: var(--dim); margin-left: 4px; }
    .meta { font-size: 10px; color: var(--dim); display: flex; gap: 9px; flex-wrap: wrap; }
    .tabs { flex-shrink: 0; display: flex; align-items: center; border-bottom: 1px solid var(--border);
      background: var(--surface-2); padding: 0 12px; }
    .tab { font-family: var(--mono); font-size: 11px; padding: 7px 11px; border-bottom: 2px solid transparent;
      color: var(--muted); cursor: pointer; margin-bottom: -1px; }
    .tab.on { border-bottom-color: var(--accent); color: var(--accent); }
    .toggle { display: flex; border: 1px solid var(--border); margin: 4px 0; }
    .tbtn { height: 20px; padding: 0 8px; font-size: 10px; border-radius: 0; border: none; background: transparent;
      color: var(--muted); cursor: pointer; }
    .tbtn.on { background: var(--accent-soft); color: var(--accent); }
    .tabbody { flex: 1; min-height: 0; overflow: hidden; display: flex; }
    .left { flex: 1.1; min-width: 0; display: flex; flex-direction: column; border-right: 1px solid var(--border); }
    .right { flex: 1; min-width: 0; overflow: auto; background: var(--surface); }
    .right.full { flex: 1; }
    .selbar { flex-shrink: 0; display: flex; align-items: stretch; border-bottom: 1px solid var(--border);
      background: var(--surface); font-family: var(--mono); font-size: 10px; overflow-x: auto; }
    .sel { display: flex; align-items: center; gap: 6px; padding: 5px 10px; cursor: pointer;
      border-right: 1px solid var(--border); white-space: nowrap; flex-shrink: 0; }
    .sel.on { background: var(--accent-soft); }
    .sname { color: var(--text); }
    .sel.on .sname { color: var(--accent); }
    .tlabel { font-size: 8px; color: var(--accent); letter-spacing: 0.1em; }
    .dim { color: var(--dim); }
    .embsep { padding: 0 10px; display: flex; align-items: center; color: var(--dim);
      border-right: 1px solid var(--border); flex-shrink: 0; text-transform: uppercase; letter-spacing: 0.1em; }
    .loading { padding: 24px; font-family: var(--mono); color: var(--dim); }
    /* mobile artifact ⇄ body */
    .msplit { flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0; }
    .mseg { flex-shrink: 0; display: flex; border-bottom: 1px solid var(--border); background: var(--surface-2);
      padding: 6px; gap: 6px; }
    .msegbtn { flex: 1; height: 36px; font-size: 12px; border-radius: 2px; background: transparent;
      color: var(--muted); border: 1px solid var(--border); cursor: pointer; font-family: var(--mono); }
    .msegbtn.on { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
    .mart { flex: 1; min-height: 0; display: flex; flex-direction: column; }
    .mbody { flex: 1; min-width: 0; overflow: auto; background: var(--surface); }
  `],
})
export class CxViewer {
  readonly store = inject(CorpusStore);
  readonly mobile = inject(Viewport).mobile;
  readonly tab = signal<TabId>('split');
  readonly bodyMode = signal<BodyMode>('rendered');
  readonly activeKey = signal<string | null>(null);
  readonly activeRegion = signal<Region | null>(null);
  readonly viewEmbed = signal<number | null>(null);
  readonly pane = signal<'artifact' | 'body'>('body'); // mobile artifact ⇄ body toggle
  readonly bodyModes: [BodyMode, string][] = [
    ['rendered', 'rendered md'],
    ['source', 'raw source'],
  ];
  readonly paneDefs: ['artifact' | 'body', string][] = [
    ['artifact', 'artifact'],
    ['body', 'normalized body'],
  ];

  title = titleFor;
  firstAddr = firstAddr;
  hasArtifact = computed(() => !!this.store.record()?.transport);
  canCrop = computed(() => {
    const r = this.store.record();
    if (!r) return false;
    const s = mimeInfo(r.mime).short;
    return r.isImage || s === 'pdf' || s === 'docx';
  });
  tabs = computed<[TabId, string][]>(() => {
    const r = this.store.record();
    const t: [TabId, string][] = [['split', 'source ∥ body']];
    if (r?.embeds.length) t.push(['embeds', 'embeds · ' + r.embeds.length]);
    t.push(['metadata', 'metadata'], ['provenance', 'provenance']);
    t.push(['annotations', 'annotations' + (r?.annotations.length ? ' · ' + r.annotations.length : '')]);
    return t;
  });

  constructor() {
    // reset transient view state whenever a different record loads
    effect(() => {
      this.store.recordId();
      this.activeKey.set(null);
      this.activeRegion.set(null);
      this.viewEmbed.set(null);
      this.tab.set('split');
      this.pane.set('body');
    });
  }

  onPick(ev: PickEvent): void {
    this.activeKey.set(ev.key);
    this.activeRegion.set(ev.seg ? parseAddr(ev.seg.address) : null);
    if (ev.seg) {
      this.viewEmbed.set(null);
      if (this.mobile()) this.pane.set('artifact'); // reveal the synced highlight
    }
  }
  setRegion(region: Region): void {
    this.activeRegion.set(region);
    this.activeKey.set(null);
    this.viewEmbed.set(null);
    this.tab.set('split');
    if (this.mobile()) this.pane.set('artifact');
  }
  copyUri(id: string): void {
    navigator.clipboard?.writeText('corpus://' + id);
  }
}
