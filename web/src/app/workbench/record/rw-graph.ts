// Graph mode · the record's connections across the corpus, served by `GET …/records/{id}/graph`.
// Resolved edges reach its origins, embeds, classification-sharing records, and captured
// cross-references (navigable). Uncaptured edges are outbound links found in the body that
// aren't in the corpus yet — capture routes them to the submit phase (capture → ingest →
// draft → normalize), which is where ingest actually happens.

import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { CorpusStore } from '../../core/store';
import { GraphNode, RecordDetail } from '../../core/models';
import { titleFor } from '../../core/util';

const KIND_COLOR: Record<string, string> = {
  origin: '#a35a00',
  embed: '#3a6a7a',
  record: 'var(--accent)',
  link: 'var(--dim)',
};

@Component({
  selector: 'rw-graph',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="graph">
      <div class="canvas">
        <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
          @for (n of placed(); track n.id) {
            <line x1="50" y1="50" [attr.x2]="n.x" [attr.y2]="n.y"
              [attr.stroke]="n.resolved ? 'var(--border-strong)' : 'var(--border)'"
              [attr.stroke-width]="n.resolved ? 0.4 : 0.3"
              [attr.stroke-dasharray]="n.resolved ? 'none' : '1.2 1'" />
          }
        </svg>
        <div class="center">
          <div class="logo"></div>
          <span class="ct">{{ title(r()) }}</span>
          <span class="cs">this record</span>
        </div>
        @for (n of placed(); track n.id) {
          <div class="node" [style.left.%]="n.x" [style.top.%]="n.y"
            [class.on]="selId() === n.id" (click)="selId.set(n.id)">
            <span class="dot" [class.sq]="n.kind === 'record'"
              [style.background]="n.resolved ? color(n.kind) : 'var(--surface)'"
              [style.borderColor]="n.resolved ? color(n.kind) : 'var(--border-strong)'"></span>
            <span class="nl" [style.color]="n.resolved ? 'var(--text)' : 'var(--dim)'">{{ n.label }}</span>
            @if (!n.resolved) { <span class="unc">uncaptured</span> }
          </div>
        }
        @if (!loading() && !placed().length) {
          <div class="canvas-empty">no connections — no origins, embeds, peers, or outbound links.</div>
        }
        <div class="legend">
          @for (k of kinds; track k[0]) {
            <span class="lk"><span class="ld" [class.sq]="k[0] === 'record'" [style.background]="k[1]" [style.borderColor]="k[1]"></span>{{ k[0] }}</span>
          }
        </div>
      </div>

      <div class="side">
        <div class="sh"><span class="t-label">connections</span><span class="sp"></span>
          <span class="acc">{{ resolved().length }}</span><span class="dim">resolved</span>
          <span class="warn">{{ unresolved().length }}</span><span class="dim">open</span></div>
        <div class="list cx-scroll">
          <div class="grp">resolved · {{ resolved().length }}</div>
          @for (n of resolved(); track n.id) {
            <div class="row" [class.on]="selId() === n.id" (click)="selId.set(n.id)">
              <span class="d" [class.sq]="n.kind === 'record'" [style.background]="color(n.kind)"></span>
              <div class="ri"><div class="rl">{{ n.label }}</div><div class="rs">{{ n.sub }}</div></div>
              @if (n.recId) { <span class="open" (click)="open($event, n.recId!)">open ›</span> }
            </div>
          }
          @if (!loading() && !resolved().length) { <div class="none">— none</div> }
          <div class="grp bd">uncaptured links · {{ unresolved().length }}</div>
          @if (!loading() && unresolved().length === 0) { <div class="none">— all references resolved</div> }
          @for (n of unresolved(); track n.id) {
            <div class="row" [class.on]="selId() === n.id" (click)="selId.set(n.id)">
              <span class="d open-dot"></span>
              <div class="ri"><div class="rl muted">{{ n.label }}</div><div class="rs">{{ n.sub }}</div></div>
              <button class="cap" (click)="capture($event)">⇱ capture</button>
            </div>
          }
          @if (loading()) { <div class="none">loading connections…</div> }
        </div>
        <div class="note">capture routes an outbound link to the submit phase — capture → ingest →
          draft → normalize lands there; once normalized it resolves to a record you can open here.</div>
      </div>
    </div>
  `,
  styles: [`
    .graph { position: absolute; inset: 0; display: flex; background: var(--surface); font-family: var(--mono); }
    .canvas { flex: 1; min-width: 0; position: relative; overflow: hidden;
      background: radial-gradient(circle at 50% 46%, var(--surface) 0%, var(--surface-2) 100%); }
    svg { position: absolute; inset: 0; width: 100%; height: 100%; }
    .center { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); z-index: 2;
      display: flex; flex-direction: column; align-items: center; gap: 4px; max-width: 150px; text-align: center; }
    .logo { width: 16px; height: 16px; background: var(--accent); position: relative; }
    .logo::before { content: ''; position: absolute; inset: 3px; background: var(--surface); }
    .logo::after { content: ''; position: absolute; inset: 6px; background: var(--accent); }
    .ct { font-family: var(--sans); font-weight: 700; font-size: 11px; line-height: 1.2; }
    .cs { font-size: 8px; color: var(--dim); }
    .node { position: absolute; transform: translate(-50%, -50%); z-index: 1; cursor: pointer;
      display: flex; flex-direction: column; align-items: center; gap: 3px; }
    .dot { width: 11px; height: 11px; border-radius: 50%; border: 1.5px solid; }
    .dot.sq { border-radius: 0; }
    .node.on .dot { box-shadow: 0 0 0 3px var(--accent-soft); }
    .nl { font-size: 8.5px; text-align: center; max-width: 116px; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; background: var(--surface); padding: 0 3px; }
    .unc { font-size: 7.5px; color: var(--warn); text-transform: uppercase; letter-spacing: 0.06em; }
    .canvas-empty { position: absolute; left: 50%; bottom: 28px; transform: translateX(-50%); max-width: 240px;
      text-align: center; font-size: 9.5px; color: var(--dim); }
    .legend { position: absolute; left: 12px; bottom: 10px; display: flex; gap: 12px; font-size: 8.5px; color: var(--dim); }
    .lk { display: inline-flex; align-items: center; gap: 4px; }
    .ld { width: 8px; height: 8px; border-radius: 50%; border: 1px solid; } .ld.sq { border-radius: 0; }
    .side { width: 300px; flex-shrink: 0; border-left: 1px solid var(--border); display: flex; flex-direction: column;
      min-height: 0; background: var(--surface); }
    .sh { flex-shrink: 0; padding: 9px 12px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted); }
    .sp { flex: 1; } .acc { font-size: 9px; color: var(--accent); } .warn { font-size: 9px; color: var(--warn); }
    .dim { font-size: 9px; color: var(--dim); }
    .list { flex: 1; overflow: auto; min-height: 0; }
    .grp { padding: 8px 12px 4px; font-size: 8px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.10em; }
    .grp.bd { border-top: 1px solid var(--border); }
    .row { display: flex; align-items: center; gap: 8px; padding: 6px 12px; cursor: pointer; border-left: 2px solid transparent; }
    .row.on { background: var(--accent-soft); border-left-color: var(--accent); }
    .d { width: 8px; height: 8px; flex-shrink: 0; border-radius: 50%; } .d.sq { border-radius: 0; }
    .open-dot { background: var(--surface); border: 1.5px solid var(--border-strong); }
    .ri { min-width: 0; flex: 1; } .rl { font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .rl.muted { color: var(--muted); } .rs { font-size: 8.5px; color: var(--dim); }
    .open { font-size: 9px; color: var(--accent); cursor: pointer; flex-shrink: 0; }
    .cap { height: 20px; font-size: 9px; padding: 0 6px; border: 1px solid var(--border); background: var(--surface);
      color: var(--text); cursor: pointer; font-family: var(--mono); flex-shrink: 0; }
    .none { padding: 2px 12px 10px; font-size: 9.5px; color: var(--dim); }
    .note { flex-shrink: 0; border-top: 1px solid var(--border); padding: 10px; background: var(--surface-2);
      font-family: var(--sans); font-size: 10.5px; color: var(--muted); line-height: 1.5; }
  `],
})
export class RwGraph {
  private store = inject(CorpusStore);
  r = input.required<RecordDetail>();
  readonly title = titleFor;
  readonly kinds = Object.entries(KIND_COLOR);
  readonly selId = signal<string | null>(null);

  readonly loading = this.store.recordGraphLoading;
  readonly resolved = computed<GraphNode[]>(() => this.store.recordGraph()?.resolved ?? []);
  readonly unresolved = computed<GraphNode[]>(() => this.store.recordGraph()?.uncaptured ?? []);
  readonly nodes = computed(() => [
    ...this.resolved().map((n) => ({ ...n, resolved: true })),
    ...this.unresolved().map((n) => ({ ...n, resolved: false })),
  ]);
  readonly placed = computed(() => {
    const ns = this.nodes();
    const radius = 33;
    return ns.map((n, i) => {
      const a = -Math.PI / 2 + (i / Math.max(1, ns.length)) * 2 * Math.PI;
      return { ...n, x: 50 + radius * Math.cos(a), y: 50 + radius * Math.sin(a) };
    });
  });

  color(kind: string): string {
    return KIND_COLOR[kind] ?? 'var(--muted)';
  }
  open(e: Event, id: string): void {
    e.stopPropagation();
    this.store.openRecord(id);
  }
  capture(e: Event): void {
    e.stopPropagation();
    this.store.openSubmit(); // capture/ingest is the submit phase — route there honestly
  }
}
