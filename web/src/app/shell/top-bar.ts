import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { CorpusStore } from '../core/store';
import { Viewport } from '../core/viewport';
import { titleFor } from '../core/util';
import { CxAperture } from '../chips/chips';

/** Fixed app chrome. Desktop: brand + endpoint switcher + search + theme/density + submit,
 *  then corpus tabs / breadcrumb. Mobile: condensed two rows with an expandable search. */
@Component({
  selector: 'cx-top-bar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxAperture],
  template: `
    @if (mobile()) {
      <div class="bar">
        @if (searchOpen()) {
          <div class="mrow msearch">
            <button class="btn btn-ghost mback" (click)="searchOpen.set(false)">‹</button>
            <div class="mfield">
              <span class="ico">⌕</span>
              <input autofocus [value]="store.query()" (input)="store.setQuery($any($event.target).value)"
                placeholder="search title, tags, content, id…" aria-label="search records" />
              @if (store.query()) { <span class="x" (click)="store.setQuery('')">×</span> }
            </div>
          </div>
        } @else {
          <div class="mrow mactions">
            <div class="brand">
              <cx-aperture [size]="17" />
              <span class="wordmark" style="font-size:13px">athenaeum</span>
              <span class="slash" style="font-size:12px">/ corpus</span>
            </div>
            <span class="spacer"></span>
            <button class="btn btn-ghost mbtn search" title="search" (click)="searchOpen.set(true)">
              ⌕@if (store.query()) { <span class="dot"></span> }
            </button>
            <button class="btn btn-ghost mbtn" title="toggle theme" (click)="store.toggleTheme()">
              {{ store.theme() === 'theme-dark' ? '☾' : '☀' }}
            </button>
            <button class="btn btn-primary msubmit" (click)="store.openSubmit()">+ submit</button>
          </div>
        }
        @if (store.mode() === 'browse') {
          <div class="cx-scroll mrow mtabs">
            <span class="led" [style.background]="store.endpoint().online ? 'var(--ok)' : 'var(--err)'"></span>
            <div class="tabs">
              @for (c of store.corpora(); track c.id) {
                <button class="ctab mctab" [class.on]="c.id === store.corpusId()" (click)="store.setCorpus(c.id)">
                  <span class="cdot" [style.background]="c.color"></span>{{ c.name }}
                </button>
              }
            </div>
          </div>
        } @else {
          <div class="mrow mcrumb">
            <button class="btn btn-ghost mback2" (click)="store.back()">‹ records</button>
            <span class="crumbtitle">{{ recordTitle() }}</span>
          </div>
        }
      </div>
    } @else {
      <div class="bar">
        <div class="row1">
          <div class="brand">
            <cx-aperture [size]="16" />
            <span class="wordmark">athenaeum</span>
            <span class="slash">/ corpus</span>
          </div>
          <div class="hairv" style="height:18px"></div>
          <div class="ep">
            <button class="btn btn-ghost epbtn" (click)="epOpen.set(!epOpen())"
              aria-haspopup="menu" [attr.aria-expanded]="epOpen()">
              <span class="led" [style.background]="store.endpoint().online ? 'var(--ok)' : 'var(--err)'"></span>
              <span class="epbase">{{ store.base() }}</span>
              <span class="caret">▾</span>
            </button>
            @if (epOpen()) {
              <div class="scrim" (click)="epOpen.set(false)"></div>
              <div class="menu" role="menu">
                <div class="t-label menutitle">api endpoint</div>
                @for (ep of store.endpoints(); track ep.id) {
                  <div role="menuitemradio" [attr.aria-checked]="ep.id === store.endpointId()"
                    class="menurow" [class.on]="ep.id === store.endpointId()" (click)="pick(ep.id)">
                    <span class="led" [style.background]="ep.online ? 'var(--ok)' : 'var(--err)'"></span>
                    <div class="meta">
                      <div class="mbase">{{ ep.base }}</div>
                      <div class="mlabel">{{ ep.label }} · {{ ep.corpora.length || store.corpora().length }} corpora</div>
                    </div>
                    @if (ep.id === store.endpointId()) { <span class="check">✓</span> }
                  </div>
                }
                <div class="addrow">
                  <span class="plus">+</span>
                  <input #addInput placeholder="https://…/v1" class="addinput"
                    (keydown.enter)="add(addInput.value); addInput.value=''" />
                  <button class="btn additbtn" (click)="add(addInput.value); addInput.value=''">add</button>
                </div>
              </div>
            }
          </div>
          <span class="spacer"></span>
          <div class="search">
            <span class="ico">⌕</span>
            <input id="cx-search" [value]="store.query()" (input)="store.setQuery($any($event.target).value)"
              placeholder="search title, tags, content, id…" aria-label="search records" />
            <span class="kbd">⌘K</span>
          </div>
          <button class="btn btn-ghost iconbtn" title="toggle density" (click)="store.cycleDensity()">≣</button>
          <button class="btn btn-ghost iconbtn" title="toggle theme" (click)="store.toggleTheme()">
            {{ store.theme() === 'theme-dark' ? '☾' : '☀' }}
          </button>
          <button class="btn btn-primary submit" (click)="store.openSubmit()">+ submit</button>
        </div>
        <div class="row2">
          @if (store.mode() === 'browse') {
            <span class="corpuslbl">corpus</span>
            <div class="tabs" role="tablist" aria-label="corpus">
              @for (c of store.corpora(); track c.id) {
                <button class="ctab" role="tab" [attr.aria-selected]="c.id === store.corpusId()"
                  [class.on]="c.id === store.corpusId()" (click)="store.setCorpus(c.id)">
                  <span class="cdot" [style.background]="c.color"></span>{{ c.name }}
                </button>
              }
            </div>
            <span class="getline">GET {{ store.base() }}/{{ store.corpusId() }}/records</span>
          } @else {
            <button class="btn btn-ghost back" (click)="store.back()">‹ records</button>
            <span class="slash">/</span>
            <span class="crumb">{{ recordTitle() }}</span>
          }
        </div>
      </div>
    }
  `,
  styles: [`
    .bar { flex-shrink: 0; background: var(--surface); border-bottom: 1px solid var(--border);
      font-family: var(--mono); position: relative; z-index: 40; }
    .row1 { height: 38px; display: flex; align-items: center; gap: 10px; padding: 0 12px;
      border-bottom: 1px solid var(--border); }
    .brand { display: flex; align-items: center; gap: 7px; min-width: 0; }
    .wordmark { font-weight: 700; font-size: 12px; }
    .slash { color: var(--dim); font-size: 11px; }
    .ep { position: relative; }
    .epbtn { height: 24px; gap: 7px; padding-left: 7px; }
    .led { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
    .epbase { color: var(--text); }
    .caret { color: var(--dim); }
    .spacer { flex: 1; }
    .search { display: flex; align-items: center; gap: 6px; height: 24px; padding: 0 8px;
      border: 1px solid var(--border); background: var(--bg); width: 320px; }
    .search .ico { color: var(--dim); }
    .search input { flex: 1; min-width: 0; background: transparent; border: none; outline: none;
      color: var(--text); font-family: var(--mono); font-size: 11px; }
    .iconbtn { height: 24px; width: 26px; padding: 0; justify-content: center; }
    .submit { height: 24px; }
    .row2 { height: 30px; display: flex; align-items: center; gap: 8px; padding: 0 12px; }
    .corpuslbl { color: var(--muted); font-size: 11px; }
    .tabs { display: flex; border: 1px solid var(--border); }
    .ctab { height: 22px; padding: 0 9px; font-size: 10px; border-radius: 0; gap: 6px; border: none;
      background: transparent; color: var(--muted); cursor: pointer; display: inline-flex; align-items: center;
      font-family: var(--mono); white-space: nowrap; }
    .ctab.on { background: var(--accent-soft); color: var(--accent); }
    .cdot { width: 6px; height: 6px; }
    .getline { color: var(--dim); font-size: 10px; }
    .back { height: 22px; gap: 6px; }
    .crumb { color: var(--muted); font-size: 11px; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; max-width: 520px; }
    /* endpoint menu */
    .scrim { position: fixed; inset: 0; z-index: 1; }
    .menu { position: absolute; top: 30px; left: 0; z-index: 2; width: 320px; background: var(--surface);
      border: 1px solid var(--border-strong); box-shadow: var(--sh-popover); }
    .menutitle { padding: 7px 10px 4px; }
    .menurow { padding: 7px 10px; display: flex; align-items: center; gap: 8px; cursor: pointer;
      border-top: 1px solid var(--border); }
    .menurow.on { background: var(--accent-soft); }
    .menurow .meta { flex: 1; min-width: 0; }
    .mbase { font-size: 11px; color: var(--text); overflow: hidden; text-overflow: ellipsis; }
    .menurow.on .mbase { color: var(--accent); }
    .mlabel { font-size: 9px; color: var(--dim); }
    .check { color: var(--accent); }
    .addrow { border-top: 1px solid var(--border); padding: 6px 10px; display: flex; align-items: center; gap: 6px; }
    .plus { color: var(--dim); }
    .addinput { flex: 1; background: var(--bg); border: 1px solid var(--border); outline: none;
      color: var(--text); font-family: var(--mono); font-size: 10px; height: 20px; padding: 0 6px; }
    .additbtn { height: 20px; }
    /* mobile */
    .mrow { display: flex; align-items: center; gap: 8px; }
    .mactions { height: 48px; padding: 0 12px; border-bottom: 1px solid var(--border); }
    .msearch { height: 48px; padding: 0 10px; border-bottom: 1px solid var(--border); }
    .mback { height: 36px; width: 36px; padding: 0; font-size: 18px; justify-content: center; }
    .mfield { flex: 1; display: flex; align-items: center; gap: 7px; height: 36px; padding: 0 10px;
      border: 1px solid var(--border); background: var(--bg); }
    .mfield .ico { color: var(--dim); }
    .mfield input { flex: 1; min-width: 0; background: transparent; border: none; outline: none; color: var(--text); font-family: var(--mono); }
    .mfield .x { cursor: pointer; color: var(--dim); font-size: 16px; }
    .mbtn { height: 36px; width: 38px; padding: 0; font-size: 16px; position: relative; justify-content: center; }
    .mbtn .dot { position: absolute; top: 5px; right: 6px; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
    .msubmit { height: 36px; padding: 0 12px; font-size: 12px; }
    .mtabs { height: 40px; padding: 0 12px; overflow-x: auto; }
    .mctab { height: 28px; padding: 0 12px; font-size: 11px; }
    .mcrumb { height: 40px; padding: 0 10px; }
    .mback2 { height: 30px; gap: 6px; font-size: 12px; padding-left: 6px; }
    .crumbtitle { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; flex: 1; font-family: var(--sans); font-weight: 600; }
  `],
})
export class CxTopBar {
  readonly store = inject(CorpusStore);
  readonly mobile = inject(Viewport).mobile;
  readonly epOpen = signal(false);
  readonly searchOpen = signal(false);
  readonly recordTitle = computed(() => {
    const r = this.store.record();
    return r ? titleFor(r) : '';
  });

  pick(id: string): void {
    this.epOpen.set(false);
    this.store.setEndpoint(id);
  }
  add(base: string): void {
    base = (base || '').trim();
    if (!base) return;
    this.epOpen.set(false);
    this.store.addEndpoint(base);
  }
}
