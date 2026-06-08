// Shared dock state — the design's `WBDockContext`. A WbDock writes its three pane modes
// here so sibling content (projected into the center slot) can react to them: the ledger
// shows its hover-card only when the detail (right) pane is collapsed. Provide ONE instance
// per workbench (CxCorpusWorkbench / CxRecordWorkbench `providers`), so projected content
// and the dock share it via the host injector.

import { Injectable, signal } from '@angular/core';
import type { PaneMode } from './wb-dock';

@Injectable()
export class WbDockState {
  readonly left = signal<PaneMode>('docked');
  readonly right = signal<PaneMode>('collapsed');
  readonly bottom = signal<PaneMode>('collapsed');
}
