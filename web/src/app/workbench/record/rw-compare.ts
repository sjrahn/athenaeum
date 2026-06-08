// Compare mode · source pane — the real artifact beside the reader. The active segment
// (from the reader/outline) drives a synced page/bbox/time-range highlight; "⛶ regions"
// jumps to the crop editor. Reuses the Console's artifact renderer + highlight.
//
// HTML is special: its artifact is a cross-origin sandboxed iframe we can't scroll to a
// segment, so when a segment is selected we show the resolver-materialized render of that
// segment's address (the same mechanism that renders embed images) — "region" — with a
// toggle back to the full source. PDF/image/AV already follow selection via activeRegion.

import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  linkedSignal,
  output,
} from '@angular/core';
import { CorpusStore } from '../../core/store';
import { RecordDetail, Region, SegmentNode } from '../../core/models';
import { firstAddr, mimeInfo, parseAddr } from '../../core/util';
import { CxMimeChip, CxAddress } from '../../chips/chips';
import { CxArtifactView } from '../../viewer/artifact';

@Component({
  selector: 'rw-compare',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip, CxAddress, CxArtifactView],
  template: `
    <div class="cmp">
      <div class="hd">
        <span class="t-label">source artifact</span>
        <cx-mime-chip [m]="r().mime" />
        <span class="name">{{ r().transport.name }}</span>
        <span class="sp"></span>
        @if (activeSeg()) { <cx-address [address]="addr(activeSeg()!.address)" [active]="true" /> }
        @if (canRegion()) {
          <div class="vtog">
            <button [class.on]="srcView() === 'region'" (click)="srcView.set('region')">region</button>
            <button [class.on]="srcView() === 'full'" (click)="srcView.set('full')">full source</button>
          </div>
        }
        <button class="rg" (click)="crop.emit()">⛶ regions</button>
      </div>
      <div class="stage">
        @if (showRegion()) {
          <div class="rgn cx-scroll">
            @if (regionUrl()) { <img [src]="regionUrl()" alt="selected region" (error)="srcView.set('full')" /> }
            <div class="cap">▶ region · {{ addr(activeSeg()!.address) }}</div>
          </div>
        } @else {
          <cx-artifact-view [r]="r()" [activeRegion]="region()" />
        }
      </div>
    </div>
  `,
  styles: [`
    .cmp { display: flex; flex-direction: column; height: 100%; min-height: 0; background: var(--surface);
      font-family: var(--mono); }
    .hd { flex-shrink: 0; height: 32px; display: flex; align-items: center; gap: 8px; padding: 0 12px;
      border-bottom: 1px solid var(--border); background: var(--surface-2); }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted); }
    .name { font-size: 9.5px; color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .sp { flex: 1; }
    .vtog { display: inline-flex; border: 1px solid var(--border); flex-shrink: 0; }
    .vtog button { height: 20px; padding: 0 8px; border: none; border-right: 1px solid var(--border);
      background: transparent; color: var(--muted); font-family: var(--mono); font-size: 9.5px; cursor: pointer; }
    .vtog button:last-child { border-right: none; }
    .vtog button.on { background: var(--accent-soft); color: var(--accent); }
    .rg { height: 22px; padding: 0 8px; border: 1px solid var(--border); background: var(--surface);
      color: var(--text); font-family: var(--mono); font-size: 10px; cursor: pointer; flex-shrink: 0; }
    .stage { flex: 1; min-height: 0; display: flex; flex-direction: column; }
    .rgn { flex: 1; min-height: 0; overflow: auto; background: var(--surface-2); padding: 16px; text-align: center; }
    .rgn img { max-width: 100%; height: auto; background: #fff; border: 1px solid var(--border);
      box-shadow: 0 2px 10px rgba(0,0,0,0.18); }
    .rgn .cap { margin-top: 10px; font-size: 9px; color: var(--accent); }
  `],
})
export class RwCompare {
  private store = inject(CorpusStore);
  r = input.required<RecordDetail>();
  activeSeg = input<SegmentNode | null>(null);
  crop = output<void>();
  readonly addr = firstAddr;
  readonly isHtml = computed(() => mimeInfo(this.r().mime).short === 'html');
  readonly region = computed<Region | null>(() => {
    const s = this.activeSeg();
    return s ? parseAddr(s.address) : null;
  });
  // Resets to 'region' on every new selection so the source follows the reader; the user can
  // flip to 'full' to see the whole page, until they pick another segment.
  readonly srcView = linkedSignal<'region' | 'full'>(() => {
    this.activeSeg();
    return 'region';
  });
  // Only non-text HTML segments (image/av) materialize to a renderable region; text segments
  // (often `el=`-ranges the image transform rejects) fall back to the full source iframe.
  readonly canRegion = computed(() => {
    const s = this.activeSeg();
    return this.isHtml() && s != null && s.atom !== 'text';
  });
  readonly showRegion = computed(() => this.canRegion() && this.srcView() === 'region');
  readonly regionUrl = computed(() => {
    const s = this.activeSeg();
    return s ? this.store.resolveUrl(`corpus://${this.r().id}?${firstAddr(s.address)}`) : null;
  });
}
