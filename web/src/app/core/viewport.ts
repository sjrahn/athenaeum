import { Injectable, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { BreakpointObserver } from '@angular/cdk/layout';
import { map } from 'rxjs';

/** Single viewport hook (the prototype's `useCxMobile`). Below 760px the console
 *  collapses from its three fixed regions to a single stack-navigated column.
 *  Backed by `@angular/cdk/layout` so it shares the platform's media-query plumbing. */
const MOBILE = '(max-width: 760px)';

@Injectable({ providedIn: 'root' })
export class Viewport {
  private bp = inject(BreakpointObserver);
  readonly mobile = toSignal(this.bp.observe(MOBILE).pipe(map((s) => s.matches)), {
    initialValue: this.bp.isMatched(MOBILE),
  });
}
