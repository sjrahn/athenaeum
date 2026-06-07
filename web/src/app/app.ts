import { ChangeDetectionStrategy, Component, HostListener, inject } from '@angular/core';
import { CorpusStore } from './core/store';
import { CxCorpusWorkbench } from './workbench/corpus-workbench';
import { CxRecordWorkbench } from './workbench/record/record-workbench';
import { CxSubmitStub } from './shell/submit-stub';

/** Orchestrator: theme/density wrapper around the workbench surfaces. The Search Workbench
 *  is primary; opening a record swaps to the record workbench (its own work modes). */
@Component({
  selector: 'app-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxCorpusWorkbench, CxRecordWorkbench, CxSubmitStub],
  template: `
    <div class="app cx-app-root" [class]="store.theme() + ' ' + store.density()">
      @if (store.mode() === 'record') { <cx-record-workbench /> }
      @else { <cx-corpus-workbench /> }
      @if (store.submitOpen()) { <cx-submit-stub /> }
    </div>
  `,
  styles: [`
    .app { position: fixed; inset: 0; background: var(--bg); color: var(--text); overflow: hidden; }
  `],
})
export class App {
  readonly store = inject(CorpusStore);

  @HostListener('window:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    // ⌘K opens the palette in the corpus workbench (the record workbench owns its keyboard)
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k' && this.store.mode() !== 'record') {
      e.preventDefault();
      this.store.togglePalette();
      return;
    }
    if (e.key === 'Escape') {
      if (this.store.paletteOpen()) this.store.closePalette();
      else if (this.store.submitOpen()) this.store.closeSubmit();
      else if (this.store.mode() === 'record') this.store.back();
    }
  }
}
