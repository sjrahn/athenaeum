import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CorpusStore } from '../core/store';
import { Viewport } from '../core/viewport';
import { CxAperture } from '../chips/chips';

/** Placeholder submit dialog (centered on desktop, bottom sheet on mobile). The
 *  capture→ingest→draft→normalize pipeline + `corpus check` land in the submit phase. */
@Component({
  selector: 'cx-submit-stub',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxAperture],
  template: `
    <div class="scrim" [class.mobile]="mobile()" (click)="store.closeSubmit()">
      <div class="dialog" [class.sheet]="mobile()" (click)="$event.stopPropagation()">
        @if (mobile()) { <div class="grab"></div> }
        <div class="head">
          <cx-aperture [size]="14" />
          <span class="ttl">submit to corpus</span>
          @if (!mobile()) { <span class="ep">POST {{ store.base() }}/{{ store.corpusId() }}/submit</span> }
          <span class="spacer"></span>
          <span class="x" (click)="store.closeSubmit()">✕</span>
        </div>
        <div class="body">
          <div class="soon">
            <div class="g">⇱</div>
            <div class="t">submit flow — coming next</div>
            <div class="d">
              link / file capture, the <code>corpus check</code> dedup probe, and the live
              capture → ingest → draft → normalize queue land in the submit phase.
              The API routes are wired and return <code>501</code> until then.
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .scrim { position: fixed; inset: 0; z-index: 100; display: flex; align-items: flex-start;
      justify-content: center; background: rgba(0,0,0,0.42); padding-top: 6vh; }
    .scrim.mobile { align-items: flex-end; padding: 0; }
    .dialog { width: 620px; max-width: 92vw; background: var(--bg); border: 1px solid var(--border-strong);
      box-shadow: var(--sh-float); display: flex; flex-direction: column; font-family: var(--mono); }
    .dialog.sheet { width: 100%; max-width: 100%; border-radius: 18px 18px 0 0; border-bottom: none;
      box-shadow: var(--sh-sheet); animation: cxsheetin 0.24s cubic-bezier(0.32,0.72,0,1); padding-bottom: env(safe-area-inset-bottom); }
    .grab { width: 36px; height: 4px; border-radius: 2px; background: var(--border-strong);
      margin: 8px auto 2px; }
    .head { flex-shrink: 0; padding: 11px 14px; border-bottom: 1px solid var(--border);
      background: var(--surface-2); display: flex; align-items: center; gap: 8px; }
    .dialog.sheet .head { background: transparent; }
    .ttl { font-size: 12px; font-weight: 600; }
    .ep { font-size: 10px; color: var(--dim); }
    .spacer { flex: 1; }
    .x { cursor: pointer; color: var(--muted); font-size: 14px; padding: 4px; }
    .body { padding: 16px; }
    .soon { border: 1.5px dashed var(--border-strong); background: var(--surface); padding: 28px 16px;
      text-align: center; }
    .g { font-size: 26px; color: var(--dim); }
    .t { font-size: 13px; color: var(--text); margin-top: 8px; }
    .d { font-size: 11px; color: var(--muted); margin-top: 8px; line-height: 1.6; max-width: 440px;
      margin-left: auto; margin-right: auto; }
    code { font-family: var(--mono); color: var(--text); }
  `],
})
export class CxSubmitStub {
  readonly store = inject(CorpusStore);
  readonly mobile = inject(Viewport).mobile;
}
