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
import { DomSanitizer } from '@angular/platform-browser';
import { CorpusStore } from '../core/store';
import { RecordDetail, Region } from '../core/models';
import { fmtTime, mimeInfo } from '../core/util';
import { CxAddress } from '../chips/chips';

/** Normalized-bbox highlight overlay drawn over a page/image. */
@Component({
  selector: 'cx-highlight',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (box(); as b) {
      <div class="hl" [style.left.%]="b[0] * 100" [style.top.%]="b[1] * 100"
        [style.width.%]="b[2] * 100" [style.height.%]="b[3] * 100">
        @if (label()) { <span class="lbl">{{ label() }}</span> }
      </div>
    }
  `,
  styles: [`
    .hl { position: absolute; border: 2px solid var(--accent); background: rgba(163,90,0,0.10);
      box-shadow: 0 0 0 9999px rgba(0,0,0,0.04); pointer-events: none; transition: all 0.15s ease; }
    .lbl { position: absolute; top: -16px; left: -2px; font-family: var(--mono); font-size: 9px;
      background: var(--accent); color: #fff; padding: 0 4px; white-space: nowrap; }
  `],
})
export class CxHighlight {
  box = input<number[] | null>(null);
  label = input<string | null>(null);
}

/** Paged document — real page images via the server's `resolve?page=N`. */
@Component({
  selector: 'cx-paged-artifact',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxAddress, CxHighlight],
  template: `
    <div class="paged">
      <div class="toolbar">
        <span class="dim">page</span>
        <button class="btn btn-ghost nav" (click)="prev()">‹</button>
        <span class="pageno">{{ page() }} / {{ total() }}</span>
        <button class="btn btn-ghost nav" (click)="next()">›</button>
        <span class="spacer"></span>
        <cx-address [address]="'page=' + page()" />
        <button class="btn rgn" (click)="store.openCrop()">⛶ regions</button>
      </div>
      <div class="stage">
        <div class="page">
          <img [src]="pageUrl()" alt="page {{ page() }}" />
          <cx-highlight [box]="hl()" [label]="hl() ? 'page=' + page() : null" />
        </div>
      </div>
    </div>
  `,
  styles: [`
    :host { display: flex; flex: 1; min-height: 0; }
    .paged { flex: 1; display: flex; flex-direction: column; min-height: 0; background: var(--surface-2); }
    .toolbar { flex-shrink: 0; height: 30px; border-bottom: 1px solid var(--border); background: var(--surface);
      display: flex; align-items: center; gap: 8px; padding: 0 12px; font-family: var(--mono); font-size: 10px; }
    .dim { color: var(--dim); }
    .nav { height: 20px; width: 22px; padding: 0; justify-content: center; }
    .pageno { min-width: 46px; text-align: center; }
    .spacer { flex: 1; }
    .rgn { height: 20px; gap: 5px; }
    .stage { flex: 1; overflow: auto; display: flex; justify-content: center; align-items: flex-start; padding: 20px; }
    .page { position: relative; flex-shrink: 0; box-shadow: 0 2px 10px rgba(0,0,0,0.18); background: #fff; }
    .page img { display: block; max-width: 560px; height: auto; }
  `],
})
export class CxPagedArtifact {
  readonly store = inject(CorpusStore);
  r = input.required<RecordDetail>();
  activeRegion = input<Region | null>(null);
  page = signal(1);
  total = computed(() => this.r().pages ?? 1);
  pageUrl = computed(() => this.store.resolveUrl(`corpus://${this.r().id}?page=${this.page()}`));
  hl = computed(() => {
    const reg = this.activeRegion();
    return reg && reg.page === this.page() && reg.bbox ? reg.bbox : null;
  });

  constructor() {
    effect(() => {
      const reg = this.activeRegion();
      if (reg?.page) this.page.set(reg.page);
    });
  }
  prev(): void {
    this.page.update((p) => Math.max(1, p - 1));
  }
  next(): void {
    this.page.update((p) => Math.min(this.total(), p + 1));
  }
}

/** Image / scan — real bytes via `artifacts/{id}`, with a bbox highlight overlay. */
@Component({
  selector: 'cx-image-artifact',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxHighlight],
  template: `
    <div class="img">
      <div class="toolbar">
        <span class="dim">{{ r().imgW }}×{{ r().imgH }}px · {{ label() }}</span>
        <span class="spacer"></span>
        <button class="btn rgn" (click)="store.openCrop()">⛶ regions</button>
      </div>
      <div class="stage">
        <div class="frame">
          <img [src]="url()" alt="artifact image" />
          <cx-highlight [box]="hl()" [label]="hl() ? 'bbox' : null" />
        </div>
      </div>
    </div>
  `,
  styles: [`
    :host { display: flex; flex: 1; min-height: 0; }
    .img { flex: 1; display: flex; flex-direction: column; min-height: 0; background: #151310; }
    .toolbar { flex-shrink: 0; height: 30px; border-bottom: 1px solid var(--border); background: var(--surface);
      display: flex; align-items: center; gap: 8px; padding: 0 12px; font-family: var(--mono); font-size: 10px; }
    .dim { color: var(--dim); }
    .spacer { flex: 1; }
    .rgn { height: 20px; gap: 5px; }
    .stage { flex: 1; overflow: auto; display: flex; justify-content: center; align-items: center; padding: 24px; }
    .frame { position: relative; box-shadow: 0 8px 30px rgba(0,0,0,0.5); }
    .frame img { display: block; max-width: 560px; max-height: 70vh; height: auto; }
  `],
})
export class CxImageArtifact {
  readonly store = inject(CorpusStore);
  r = input.required<RecordDetail>();
  activeRegion = input<Region | null>(null);
  url = computed(() => this.store.artifactUrl(this.r().id));
  label = computed(() => mimeInfo(this.r().mime).label);
  hl = computed(() => {
    const reg = this.activeRegion();
    return reg && reg.bbox && reg.t0 == null ? reg.bbox : null;
  });
}

/** Video — native player on the real bytes; seeks to a segment's time_range. */
@Component({
  selector: 'cx-video-artifact',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxAddress],
  template: `
    <div class="vid">
      <div class="stage">
        <video #v [src]="url()" controls preload="metadata"></video>
      </div>
      <div class="bar">
        <cx-address [address]="rangeLabel()" [active]="inRange()" />
        @if (inRange()) { <span class="seg">▶ segment {{ fmt(activeRegion()!.t0!) }}–{{ fmt(activeRegion()!.t1!) }}</span> }
      </div>
    </div>
  `,
  styles: [`
    :host { display: flex; flex: 1; min-height: 0; }
    .vid { flex: 1; display: flex; flex-direction: column; min-height: 0; background: #0a0a0a; }
    .stage { flex: 1; display: flex; align-items: center; justify-content: center; min-height: 0; padding: 12px; }
    video { max-width: 100%; max-height: 100%; background: #000; }
    .bar { flex-shrink: 0; background: var(--surface-2); border-top: 1px solid var(--border);
      padding: 8px 14px; display: flex; align-items: center; gap: 10px; font-family: var(--mono); font-size: 9px; }
    .seg { color: var(--accent); }
  `],
})
export class CxVideoArtifact {
  r = input.required<RecordDetail>();
  activeRegion = input<Region | null>(null);
  private store = inject(CorpusStore);
  private video = viewChild<ElementRef<HTMLVideoElement>>('v');
  url = computed(() => this.store.artifactUrl(this.r().id));
  inRange = computed(() => this.activeRegion()?.t0 != null);
  rangeLabel = computed(() => {
    const reg = this.activeRegion();
    return reg?.t0 != null ? `time_range=${Math.floor(reg.t0)}-${Math.floor(reg.t1 ?? reg.t0)}` : 'time_range=0-0';
  });
  fmt = fmtTime;

  constructor() {
    effect(() => {
      const reg = this.activeRegion();
      const el = this.video()?.nativeElement;
      if (el && reg?.t0 != null) {
        el.currentTime = reg.t0;
      }
    });
  }
}

/** Audio — native player on the real bytes; seeks to a segment's time_range. */
@Component({
  selector: 'cx-audio-artifact',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxAddress],
  template: `
    <div class="aud">
      <div class="toolbar"><span class="dim">{{ label() }}</span><span class="spacer"></span>
        <cx-address [address]="rangeLabel()" [active]="inRange()" /></div>
      <div class="stage">
        <audio #a [src]="url()" controls preload="metadata"></audio>
        @if (inRange()) { <div class="seg">▶ segment {{ fmt(activeRegion()!.t0!) }}–{{ fmt(activeRegion()!.t1!) }}</div> }
      </div>
    </div>
  `,
  styles: [`
    :host { display: flex; flex: 1; min-height: 0; }
    .aud { flex: 1; display: flex; flex-direction: column; min-height: 0; background: var(--surface-2); }
    .toolbar { flex-shrink: 0; height: 30px; border-bottom: 1px solid var(--border); background: var(--surface);
      display: flex; align-items: center; gap: 8px; padding: 0 12px; font-family: var(--mono); font-size: 10px; }
    .dim { color: var(--dim); } .spacer { flex: 1; }
    .stage { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 24px; }
    audio { width: 90%; max-width: 560px; }
    .seg { font-family: var(--mono); font-size: 10px; color: var(--accent); }
  `],
})
export class CxAudioArtifact {
  r = input.required<RecordDetail>();
  activeRegion = input<Region | null>(null);
  private store = inject(CorpusStore);
  private audio = viewChild<ElementRef<HTMLAudioElement>>('a');
  url = computed(() => this.store.artifactUrl(this.r().id));
  label = computed(() => mimeInfo(this.r().mime).label);
  inRange = computed(() => this.activeRegion()?.t0 != null);
  rangeLabel = computed(() => {
    const reg = this.activeRegion();
    return reg?.t0 != null ? `time_range=${Math.floor(reg.t0)}-${Math.floor(reg.t1 ?? reg.t0)}` : 'time_range=0-0';
  });
  fmt = fmtTime;
  constructor() {
    effect(() => {
      const reg = this.activeRegion();
      const el = this.audio()?.nativeElement;
      if (el && reg?.t0 != null) el.currentTime = reg.t0;
    });
  }
}

/** HTML snapshot — the real SingleFile artifact in a sandboxed iframe. */
@Component({
  selector: 'cx-html-artifact',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="html">
      <div class="toolbar"><span class="dim">html snapshot · {{ r().origins[0]?.uri?.[0] || '' }}</span></div>
      <iframe [src]="safeUrl()" sandbox="allow-same-origin" referrerpolicy="no-referrer"></iframe>
    </div>
  `,
  styles: [`
    :host { display: flex; flex: 1; min-height: 0; }
    .html { flex: 1; display: flex; flex-direction: column; min-height: 0; background: var(--surface-2); }
    .toolbar { flex-shrink: 0; height: 24px; border-bottom: 1px solid var(--border); background: var(--surface);
      display: flex; align-items: center; padding: 0 12px; font-family: var(--mono); font-size: 9px; }
    .dim { color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    iframe { flex: 1; border: none; background: #fff; width: 100%; }
  `],
})
export class CxHtmlArtifact {
  r = input.required<RecordDetail>();
  private store = inject(CorpusStore);
  private sanitizer = inject(DomSanitizer);
  safeUrl = computed(() =>
    this.sanitizer.bypassSecurityTrustResourceUrl(this.store.artifactUrl(this.r().id)),
  );
}

/** Plain-text transports (md / json / eml / txt) — fetched and shown verbatim. */
@Component({
  selector: 'cx-text-artifact',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="txt">
      <div class="card">
        <div class="t-label hd">{{ r().transport.name }} · {{ label() }}</div>
        <pre>{{ body() }}</pre>
      </div>
    </div>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; flex: 1; min-height: 0; }
    .txt { flex: 1; overflow: auto; background: var(--surface-2); min-height: 0; padding: 20px; }
    .card { max-width: 640px; margin: 0 auto; background: var(--surface); border: 1px solid var(--border); padding: 14px 18px; }
    .hd { margin-bottom: 10px; }
    pre { font-family: var(--mono); font-size: 11px; line-height: 1.7; color: var(--text); white-space: pre-wrap; margin: 0; }
  `],
})
export class CxTextArtifact {
  r = input.required<RecordDetail>();
  private store = inject(CorpusStore);
  label = computed(() => mimeInfo(this.r().mime).label);
  body = signal('loading…');
  constructor() {
    effect(() => {
      const url = this.store.artifactUrl(this.r().id);
      fetch(url)
        .then((res) => (res.ok ? res.text() : Promise.reject(res.status)))
        .then((t) => this.body.set(t.slice(0, 100_000)))
        .catch(() => this.body.set('(could not load artifact bytes)'));
    });
  }
}

/** Dispatcher by mime — picks the right real-bytes renderer. */
@Component({
  selector: 'cx-artifact-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CxPagedArtifact,
    CxImageArtifact,
    CxVideoArtifact,
    CxAudioArtifact,
    CxHtmlArtifact,
    CxTextArtifact,
  ],
  template: `
    @switch (kind()) {
      @case ('image') { <cx-image-artifact [r]="r()" [activeRegion]="activeRegion()" /> }
      @case ('video') { <cx-video-artifact [r]="r()" [activeRegion]="activeRegion()" /> }
      @case ('audio') { <cx-audio-artifact [r]="r()" [activeRegion]="activeRegion()" /> }
      @case ('html') { <cx-html-artifact [r]="r()" /> }
      @case ('text') { <cx-text-artifact [r]="r()" /> }
      @default { <cx-paged-artifact [r]="r()" [activeRegion]="activeRegion()" /> }
    }
  `,
  styles: [`:host { display: flex; flex-direction: column; flex: 1; min-height: 0; }`],
})
export class CxArtifactView {
  r = input.required<RecordDetail>();
  activeRegion = input<Region | null>(null);
  kind = computed(() => {
    const r = this.r();
    const s = mimeInfo(r.mime).short;
    if (r.isImage || ['png', 'jpg', 'tiff', 'webp'].includes(s)) return 'image';
    if (s === 'mp4') return 'video';
    if (s === 'mp3' || s === 'm4a') return 'audio';
    if (s === 'html') return 'html';
    if (['md', 'json', 'eml', 'txt'].includes(s)) return 'text';
    return 'paged'; // pdf / docx / epub / xlsx
  });
}
