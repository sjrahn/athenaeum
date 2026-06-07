// Slot pattern (coreteq) — composable named content projection for the dock + work
// surfaces. A consumer declares `<ng-template slot="left">…</ng-template>`; a host
// queries `contentChildren(SLOT)`, flattens with the `asRecord` pipe, and projects with
// `*ngTemplateOutlet`, optionally passing context. Optional slots simply aren't rendered.

import {
  Directive,
  InjectionToken,
  Pipe,
  PipeTransform,
  TemplateRef,
  inject,
  input,
} from '@angular/core';

export const SLOT = new InjectionToken<Slot>('SLOT');

/** Marks a `<ng-template slot="name">` as a named slot. */
@Directive({
  selector: 'ng-template[slot]',
  standalone: true,
  providers: [{ provide: SLOT, useExisting: Slot }],
})
export class Slot {
  readonly template = inject(TemplateRef);
  readonly name = input.required<string>({ alias: 'slot' });
}

/** `slots() | asRecord` -> `{ name: TemplateRef }` for `@let t = …; t.left` lookups. */
@Pipe({ name: 'asRecord', standalone: true })
export class SlotsAsRecordPipe implements PipeTransform {
  transform(slots: readonly Slot[]): Record<string, TemplateRef<unknown> | undefined> {
    return Object.fromEntries(slots.map((s) => [s.name(), s.template]));
  }
}
