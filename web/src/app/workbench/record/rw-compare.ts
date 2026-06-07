// Compare mode · source pane — the real artifact beside the reader. The active segment
// (from the reader/outline) drives a synced page/bbox/time-range highlight; "⛶ regions"
// jumps to the crop editor. Reuses the Console's artifact renderer + highlight.

import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { RecordDetail, Region, SegmentNode } from '../../core/models';
import { firstAddr, parseAddr } from '../../core/util';
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
        <button class="rg" (click)="crop.emit()">⛶ regions</button>
      </div>
      <div class="stage">
        <cx-artifact-view [r]="r()" [activeRegion]="region()" />
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
    .rg { height: 22px; padding: 0 8px; border: 1px solid var(--border); background: var(--surface);
      color: var(--text); font-family: var(--mono); font-size: 10px; cursor: pointer; }
    .stage { flex: 1; min-height: 0; display: flex; flex-direction: column; }
  `],
})
export class RwCompare {
  r = input.required<RecordDetail>();
  activeSeg = input<SegmentNode | null>(null);
  crop = output<void>();
  readonly addr = firstAddr;
  readonly region = computed<Region | null>(() => {
    const s = this.activeSeg();
    return s ? parseAddr(s.address) : null;
  });
}
