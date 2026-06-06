import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { mimeInfo } from '../core/util';

/** Procedural filetype thumbnail — CSS-drawn marks (no imagery), per the design. */
@Component({
  selector: 'cx-thumb',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @switch (kind()) {
      @case ('doc') {
        <div class="doc">
          @for (l of docLines; track $index) {
            <div class="line" [style.background]="$index === 0 ? 'var(--accent)' : 'var(--border)'"
              [style.width.%]="92 - $index * 7"></div>
          }
        </div>
      }
      @case ('mp4') { <div class="vid"><span class="play"></span></div> }
      @case ('mp3') { <div class="wave">@for (h of waveBars; track $index) { <span [style.height.px]="h"></span> }</div> }
      @case ('html') {
        <div class="html"><div class="bar"></div>
          <div class="body">@for (w of htmlLines; track $index) { <div [style.width.%]="w"></div> }</div>
        </div>
      }
      @case ('img') { <div class="img"></div> }
      @case ('xlsx') { <div class="xls">@for (c of cells; track $index) { <div [class.head]="$index < 4"></div> }</div> }
      @default { <div class="txt"># title<br />## section<br />- item<br />- item</div> }
    }
  `,
  styles: [`
    :host { display: inline-flex; align-items: center; justify-content: center; }
    .doc { width: 46px; height: 60px; background: #fff; border: 1px solid var(--border); padding: 5px;
      display: flex; flex-direction: column; gap: 3px; }
    .doc .line { height: 2px; }
    .vid { width: 64px; height: 44px; background: #0a0a0a; display: flex; align-items: center; justify-content: center; }
    .play { width: 0; height: 0; border-left: 11px solid rgba(255,255,255,.85);
      border-top: 7px solid transparent; border-bottom: 7px solid transparent; margin-left: 3px; }
    .wave { display: flex; align-items: end; gap: 2px; height: 40px; }
    .wave span { width: 3px; background: var(--accent); }
    .html { width: 64px; height: 48px; background: #fff; border: 1px solid var(--border); }
    .html .bar { height: 9px; background: var(--surface-2); border-bottom: 1px solid var(--border); }
    .html .body { padding: 5px; display: flex; flex-direction: column; gap: 3px; }
    .html .body div { height: 2px; background: var(--border-strong); }
    .img { width: 60px; height: 44px; background: linear-gradient(135deg,#b08968,#ddbea9 55%,#cb997e); }
    .xls { width: 56px; height: 44px; background: #fff; border: 1px solid var(--border);
      display: grid; grid-template-columns: repeat(4,1fr); grid-template-rows: repeat(4,1fr); }
    .xls div { border-right: 1px solid var(--border); border-bottom: 1px solid var(--border); }
    .xls .head { background: rgba(32,114,69,.12); }
    .txt { font-family: var(--mono); font-size: 8px; color: var(--muted); text-align: left; line-height: 1.5; }
  `],
})
export class CxThumb {
  mime = input.required<string>();
  readonly docLines = Array.from({ length: 7 });
  readonly waveBars = [12, 22, 34, 18, 40, 28, 44, 20, 36, 24];
  readonly htmlLines = [80, 60, 70, 40];
  readonly cells = Array.from({ length: 16 });

  kind = computed(() => {
    const s = mimeInfo(this.mime()).short;
    if (s === 'pdf' || s === 'docx' || s === 'epub') return 'doc';
    if (s === 'mp4') return 'mp4';
    if (s === 'mp3' || s === 'm4a') return 'mp3';
    if (s === 'html') return 'html';
    if (s === 'png' || s === 'jpg' || s === 'tiff' || s === 'webp') return 'img';
    if (s === 'xlsx') return 'xlsx';
    return 'txt';
  });
}
