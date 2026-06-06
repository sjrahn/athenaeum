import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { CorpusStore } from '../core/store';
import { Viewport } from '../core/viewport';
import { fmtClock } from '../core/util';

/** Persistent terminal-style status bar; condenses to the essentials on mobile. */
@Component({
  selector: 'cx-status-bar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (mobile()) {
      <div class="bar">
        <span><span class="dot" [style.color]="online()">●</span> {{ store.records().length }}/{{ total() }}</span>
        <span>·</span>
        <span>{{ store.selectionCount() }} filters</span>
        <span class="spacer"></span>
        <span class="host">{{ host() }}</span>
      </div>
    } @else {
      <div class="bar">
        <span><span class="dot" [style.color]="online()">●</span> api · {{ apiPath() }}</span>
        <span>·</span>
        <span>{{ store.records().length }} / {{ total() }} records</span>
        <span>·</span>
        <span>{{ store.selectionCount() }} filters active</span>
        <span class="spacer"></span>
        <span>{{ store.loading() ? 'loading…' : 'idle' }}</span>
        <span>·</span>
        <span>last sync {{ clock() }}</span>
      </div>
    }
  `,
  styles: [`
    .bar { height: 22px; flex-shrink: 0; border-top: 1px solid var(--border); background: var(--surface-2);
      display: flex; align-items: center; padding: 0 12px; font-size: 10px; color: var(--muted);
      font-family: var(--mono); gap: 12px; }
    .spacer { flex: 1; }
    .host { color: var(--dim); }
  `],
})
export class CxStatusBar {
  readonly store = inject(CorpusStore);
  readonly mobile = inject(Viewport).mobile;
  readonly clock = signal(fmtClock(new Date()));
  readonly total = computed(() => this.store.corpus()?.record_count ?? 0);
  readonly online = computed(() => (this.store.endpoint().online ? 'var(--ok)' : 'var(--err)'));
  readonly host = computed(() => this.store.base().replace(/^https?:\/\//, ''));
  readonly apiPath = computed(() => `${this.host()}/${this.store.corpusId()}/records`);

  constructor() {
    const id = setInterval(() => this.clock.set(fmtClock(new Date())), 1000);
    inject(DestroyRef).onDestroy(() => clearInterval(id));
  }
}
