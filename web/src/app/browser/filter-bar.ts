import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CorpusStore, ViewMode } from '../core/store';
import { Viewport } from '../core/viewport';

/** Browser toolbar: result count, sort, and the view switcher. On mobile it gains a
 *  "filters" button (opens the facets drawer) and drops to a touch-sized switcher. */
@Component({
  selector: 'cx-filter-bar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (mobile()) {
      <div class="mbar">
        <button class="btn fbtn" [class.on]="store.selectionCount() > 0" (click)="store.openDrawer()">
          <span class="g">⛭</span> filters{{ store.selectionCount() ? ' · ' + store.selectionCount() : '' }}
        </button>
        <span class="count">{{ store.records().length }} results</span>
        <span class="spacer"></span>
        <select [value]="store.sort()" (change)="store.setSort($any($event.target).value)" aria-label="sort">
          <option value="recent">captured ↓</option>
          <option value="title">title a→z</option>
        </select>
        <div class="views" role="tablist" aria-label="view">
          @for (v of mobileViews; track v.id) {
            <button class="vbtn" role="tab" [attr.aria-selected]="isOn(v.id)" [class.on]="isOn(v.id)"
              [title]="v.id" (click)="store.setView(v.id)">{{ v.glyph }}</button>
          }
        </div>
      </div>
    } @else {
      <div class="bar">
        <span class="count">{{ store.records().length }} results</span>
        <div class="hairv" style="height:16px"></div>
        <span class="hint">active filters live in the rail — pick facets at left →</span>
        <div class="sort">
          <span class="lbl">sort</span>
          <select [value]="store.sort()" (change)="store.setSort($any($event.target).value)" aria-label="sort">
            <option value="recent">captured ↓</option>
            <option value="title">title a→z</option>
          </select>
        </div>
        <div class="views" role="tablist" aria-label="view">
          @for (v of viewDefs; track v.id) {
            <button class="vbtn" role="tab" [attr.aria-selected]="store.view() === v.id"
              [class.on]="store.view() === v.id" [title]="v.id" (click)="store.setView(v.id)">{{ v.glyph }}</button>
          }
        </div>
      </div>
    }
  `,
  styles: [`
    .bar { flex-shrink: 0; border-bottom: 1px solid var(--border); background: var(--surface);
      font-family: var(--mono); min-height: 32px; display: flex; align-items: center; gap: 8px; padding: 5px 12px; }
    .count { font-size: 10px; color: var(--dim); flex-shrink: 0; }
    .hint { flex: 1; min-width: 0; font-size: 10px; color: var(--dim); overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap; }
    .sort { display: flex; align-items: center; gap: 5px; flex-shrink: 0; }
    .sort .lbl { font-size: 10px; color: var(--dim); }
    select { height: 22px; font-family: var(--mono); font-size: 10px; background: var(--surface);
      color: var(--text); border: 1px solid var(--border); outline: none; }
    .views { display: flex; border: 1px solid var(--border); flex-shrink: 0; }
    .vbtn { height: 22px; width: 26px; padding: 0; font-size: 12px; border-radius: 0; border: none;
      background: transparent; color: var(--muted); cursor: pointer; }
    .vbtn.on { background: var(--accent-soft); color: var(--accent); }
    /* mobile */
    .mbar { flex-shrink: 0; border-bottom: 1px solid var(--border); background: var(--surface);
      font-family: var(--mono); min-height: 46px; display: flex; align-items: center; gap: 8px; padding: 7px 10px; }
    .fbtn { height: 34px; gap: 7px; padding: 0 11px; font-size: 12px; }
    .fbtn.on { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
    .fbtn .g { font-size: 13px; }
    .mbar .count { font-size: 11px; }
    .mbar select { height: 34px; font-size: 12px; padding: 0 6px; }
    .mbar .views .vbtn { height: 34px; width: 38px; font-size: 15px; }
    .spacer { flex: 1; }
  `],
})
export class CxFilterBar {
  readonly store = inject(CorpusStore);
  readonly mobile = inject(Viewport).mobile;
  readonly viewDefs: { id: ViewMode; glyph: string }[] = [
    { id: 'columns', glyph: '◫' },
    { id: 'table', glyph: '≣' },
    { id: 'gallery', glyph: '⊞' },
    { id: 'cards', glyph: '☰' },
  ];
  readonly mobileViews: { id: ViewMode; glyph: string }[] = [
    { id: 'columns', glyph: '☰' },
    { id: 'gallery', glyph: '⊞' },
    { id: 'cards', glyph: '▭' },
  ];
  isOn(v: ViewMode): boolean {
    const cur = this.store.view();
    return cur === v || (v === 'columns' && cur === 'table');
  }
}
