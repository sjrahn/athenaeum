import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { atomColor, mimeInfo, TYPE_COLOR } from '../core/util';

/** Aperture logomark — nested amber squares (CSS). */
@Component({
  selector: 'cx-aperture',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="ap" [style.width.px]="size()" [style.height.px]="size()">
      <span class="i1" [style.inset.px]="size() * 0.14"></span>
      <span class="i2" [style.inset.px]="size() * 0.28"></span>
    </span>
  `,
  styles: [`
    .ap { background: var(--accent); position: relative; display: inline-block; flex-shrink: 0; }
    .i1 { position: absolute; background: var(--bg); }
    .i2 { position: absolute; background: var(--accent); }
  `],
})
export class CxAperture {
  size = input(16);
}

@Component({
  selector: 'cx-mime-chip',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="mime-chip"
      [style.minWidth.px]="big() ? 42 : 34"
      [style.height.px]="big() ? 16 : 14"
      [style.fontSize.px]="big() ? 10 : 9"
      [style.background]="info().color">{{ info().label }}</span>
  `,
})
export class CxMimeChip {
  m = input.required<string>();
  big = input(false);
  info = computed(() => mimeInfo(this.m()));
}

@Component({
  selector: 'cx-status-chip',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="chip" [style.color]="color()" [style.borderColor]="color()">
      <span class="dot" [style.background]="color()"></span>{{ label() }}
    </span>
  `,
  styles: [`
    .chip { display: inline-flex; align-items: center; gap: 4px; height: 14px; padding: 0 5px;
      font-family: var(--mono); font-size: 9px; font-weight: 600; letter-spacing: 0.08em;
      text-transform: uppercase; border: 1px solid; flex-shrink: 0; }
    .dot { width: 5px; height: 5px; border-radius: 50%; }
  `],
})
export class CxStatusChip {
  status = input.required<string>();
  private map: Record<string, string> = {
    normalized: 'var(--ok)',
    draft: 'var(--warn)',
    stub: 'var(--dim)',
  };
  color = computed(() => this.map[this.status()] ?? 'var(--muted)');
  label = computed(() => this.status());
}

@Component({
  selector: 'cx-vis-chip',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (show()) {
      <span class="chip" [style.color]="color()" [style.borderColor]="color()">{{ visibility() }}</span>
    }
  `,
  styles: [`
    .chip { display: inline-flex; align-items: center; height: 14px; padding: 0 5px;
      font-family: var(--mono); font-size: 9px; font-weight: 600; letter-spacing: 0.08em;
      text-transform: uppercase; border: 1px solid; flex-shrink: 0; }
  `],
})
export class CxVisChip {
  visibility = input<string | null>(null);
  show = computed(() => {
    const v = this.visibility();
    return !!v && v !== 'visible';
  });
  private map: Record<string, string> = {
    deranked: '#8a6a3a',
    hidden: 'var(--err)',
    quarantined: 'var(--err)',
  };
  color = computed(() => this.map[this.visibility() ?? ''] ?? 'var(--muted)');
}

/** Segment-atom chip (text / image / audio / video [/overlay]). */
@Component({
  selector: 'cx-atom-chip',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="chip" [style.color]="color()" [style.borderColor]="color()">{{ text() }}</span>
  `,
  styles: [`
    .chip { display: inline-flex; align-items: center; height: 14px; padding: 0 5px;
      font-family: var(--mono); font-size: 9px; font-weight: 600; letter-spacing: 0.06em;
      border: 1px solid; background: transparent; flex-shrink: 0; white-space: nowrap; }
  `],
})
export class CxAtomChip {
  atom = input.required<string>();
  overlay = input<string | null>(null);
  color = computed(() => atomColor(this.atom()));
  text = computed(() => this.atom() + (this.overlay() ? '/' + this.overlay() : ''));
}

/** Mono address pill — page=, bbox=, time_range=, el=. */
@Component({
  selector: 'cx-address',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="addr"
      [style.background]="active() ? 'var(--accent)' : 'var(--surface-2)'"
      [style.color]="active() ? '#fff' : 'var(--muted)'"
      [style.borderColor]="active() ? 'var(--accent)' : 'var(--border)'">{{ address() }}</span>
  `,
  styles: [`
    .addr { display: inline-flex; align-items: center; height: 15px; padding: 0 5px;
      font-family: var(--mono); font-size: 9px; letter-spacing: 0.02em;
      border: 1px solid; white-space: nowrap; }
  `],
})
export class CxAddress {
  address = input.required<string>();
  active = input(false);
}

/** Typed extended-field badge (STRING / NUMBER / URI / DATE / …). */
@Component({
  selector: 'cx-type-badge',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="b" [style.color]="color()" [style.borderColor]="color()">{{ type() }}</span>`,
  styles: [`
    .b { font-family: var(--mono); font-size: 8px; font-weight: 600; letter-spacing: 0.06em;
      text-transform: uppercase; padding: 0 3px; height: 12px; display: inline-flex;
      align-items: center; border: 1px solid; flex-shrink: 0; }
  `],
})
export class CxTypeBadge {
  type = input.required<string>();
  color = computed(() => TYPE_COLOR[this.type()] ?? 'var(--muted)');
}
