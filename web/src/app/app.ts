import { ChangeDetectionStrategy, Component, HostListener, computed, inject } from '@angular/core';
import { CorpusStore } from './core/store';
import { Viewport } from './core/viewport';
import { CxTopBar } from './shell/top-bar';
import { CxSidebar } from './shell/sidebar';
import { CxStatusBar } from './shell/status-bar';
import { CxSubmitStub } from './shell/submit-stub';
import { CxFilterBar } from './browser/filter-bar';
import {
  CxCardsView,
  CxColumnsView,
  CxGalleryView,
  CxListView,
  CxTableView,
} from './browser/views';
import { CxViewer } from './viewer/viewer';

/** Orchestrator: theme/density wrapper + fixed chrome (top bar / sidebar / status bar)
 *  around the single scrolling content region (browser ⇄ viewer ⇄ crop). Below 760px the
 *  three regions collapse to a single stack-navigated column with a facets drawer. */
@Component({
  selector: 'app-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CxTopBar,
    CxSidebar,
    CxStatusBar,
    CxSubmitStub,
    CxFilterBar,
    CxColumnsView,
    CxListView,
    CxTableView,
    CxGalleryView,
    CxCardsView,
    CxViewer,
  ],
  template: `
    <div class="app cx-app-root" [class]="store.theme() + ' ' + store.density()">
      <cx-top-bar />
      <div class="main">
        @if (!mobile()) { <cx-sidebar /> }
        @if (mobile() && store.drawerOpen()) {
          <div class="drawer-wrap">
            <div class="scrim" (click)="store.closeDrawer()"></div>
            <div class="drawer"><cx-sidebar /></div>
          </div>
        }
        <div class="content">
          @switch (store.mode()) {
            @case ('browse') {
              <cx-filter-bar />
              @switch (effView()) {
                @case ('columns') { <cx-columns-view [records]="store.records()" (open)="store.openRecord($event)" /> }
                @case ('list') { <cx-list-view [records]="store.records()" (open)="store.openRecord($event)" /> }
                @case ('table') { <cx-table-view [records]="store.records()" (open)="store.openRecord($event)" /> }
                @case ('gallery') { <cx-gallery-view [records]="store.records()" (open)="store.openRecord($event)" /> }
                @case ('cards') { <cx-cards-view [records]="store.records()" (open)="store.openRecord($event)" /> }
              }
            }
            @case ('record') { <cx-viewer /> }
            @case ('crop') {
              <div class="soon">⛶ crop / region editor — coming next (bbox editor lands in the crop phase)</div>
            }
          }
        </div>
      </div>
      <cx-status-bar />
      @if (store.submitOpen()) { <cx-submit-stub /> }
    </div>
  `,
  styles: [`
    .app { position: fixed; inset: 0; display: flex; flex-direction: column;
      background: var(--bg); color: var(--text); overflow: hidden; }
    .main { flex: 1; display: flex; min-height: 0; position: relative; }
    .content { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; }
    .soon { padding: 24px; font-family: var(--mono); font-size: 12px; color: var(--muted); }
    .drawer-wrap { position: absolute; inset: 0; z-index: 60; display: flex; }
    .scrim { position: absolute; inset: 0; background: rgba(0,0,0,0.42); animation: cxfadein 0.16s ease; }
    .drawer { position: relative; height: 100%; box-shadow: var(--sh-float);
      animation: cxdrawerin 0.2s cubic-bezier(0.32,0.72,0,1); }
  `],
})
export class App {
  readonly store = inject(CorpusStore);
  readonly mobile = inject(Viewport).mobile;
  // the column view's preview pane can't fit on phones — fall back to the list
  readonly effView = computed(() =>
    this.mobile() && this.store.view() === 'columns' ? 'list' : this.store.view(),
  );

  @HostListener('window:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      if (this.store.submitOpen()) this.store.closeSubmit();
      else if (this.store.drawerOpen()) this.store.closeDrawer();
      else if (this.store.mode() === 'crop') this.store.mode.set('record');
      else if (this.store.mode() === 'record') this.store.back();
    }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      document.getElementById('cx-search')?.focus();
    }
  }
}
