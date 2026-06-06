import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  linkedSignal,
  output,
} from '@angular/core';
import { RecordSummary } from '../core/models';
import { titleFor } from '../core/util';
import { CxMimeChip, CxStatusChip, CxVisChip } from '../chips/chips';
import { CxThumb } from './thumb';

// ---- compact row (columns list) ----
@Component({
  selector: 'cx-row',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip],
  template: `
    <div class="cx-row row" [class.sel]="sel()" (click)="pick.emit()">
      <cx-mime-chip [m]="r().mime" />
      <span class="title">{{ title() }}</span>
      @if (r().status !== 'normalized') { <span class="st" [class.draft]="r().status === 'draft'">{{ r().status }}</span> }
      <span class="chev">›</span>
    </div>
  `,
  styles: [`
    .row { min-height: var(--rowH); display: flex; align-items: center; gap: 7px; padding: 2px 12px;
      font-size: var(--fs); cursor: pointer; color: var(--text); border-bottom: 1px solid var(--border); }
    .row.sel { background: var(--accent-soft); color: var(--accent); }
    .title { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      font-family: var(--sans); font-weight: 500; }
    .st { font-size: 8px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.08em; }
    .st.draft { color: var(--warn); }
    .chev { color: var(--dim); font-size: 10px; flex-shrink: 0; }
  `],
})
export class CxRow {
  r = input.required<RecordSummary>();
  sel = input(false);
  pick = output<void>();
  title = computed(() => titleFor(this.r()));
}

// ---- plain list view (mobile default; rows open the record directly) ----
@Component({
  selector: 'cx-list-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxRow],
  template: `
    <div class="cx-scroll list">
      <div class="t-label lhead">{{ records().length }} records</div>
      @for (r of records(); track r.id) { <cx-row [r]="r" (pick)="open.emit(r.id)" /> }
      @if (records().length === 0) { <div class="empty">no records match the active filters.</div> }
    </div>
  `,
  styles: [`
    .list { flex: 1; overflow: auto; background: var(--surface); min-height: 0; }
    .lhead { padding: 7px 12px 6px; border-bottom: 1px solid var(--border); background: var(--surface-2);
      position: sticky; top: 0; z-index: 1; }
    .empty { padding: 16px; color: var(--dim); font-size: 12px; font-family: var(--mono); }
  `],
})
export class CxListView {
  records = input.required<RecordSummary[]>();
  open = output<string>();
}

// ---- columns view: list | summary peek ----
@Component({
  selector: 'cx-columns-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxRow, CxMimeChip, CxStatusChip, CxVisChip],
  template: `
    <div class="cols">
      <div class="list">
        <div class="t-label lhead">{{ records().length }} records</div>
        @for (r of records(); track r.id) {
          <cx-row [r]="r" [sel]="r.id === peek()" (pick)="peek.set(r.id)" />
        }
        @if (records().length === 0) { <div class="empty">no records match the active filters.</div> }
      </div>
      <div class="peek">
        @if (doc(); as d) {
          <div class="phead">
            <div class="prow">
              <cx-mime-chip [m]="d.mime" [big]="true" />
              <span class="spacer"></span>
              <button class="btn btn-primary" (click)="open.emit(d.id)">open ⤢</button>
            </div>
            <div class="ptitle">{{ title(d) }}</div>
            <div class="pchips">
              <cx-status-chip [status]="d.status" /><cx-vis-chip [visibility]="d.visibility" />
            </div>
            <div class="pdesc">{{ d.description || '— not yet normalized; no description authored.' }}</div>
          </div>
          <div class="pbody">
            <div class="kv"><span class="k">id</span><span class="v mono">{{ d.id }}</span></div>
            <div class="kv"><span class="k">origin</span><span class="v">{{ d.origin_host || '—' }}</span></div>
            <div>
              <div class="t-label" style="margin-bottom:6px">classifications — derived</div>
              <div class="cls">
                @for (c of d.classifications; track c) { <span class="clschip">{{ c }}</span> }
              </div>
            </div>
            @if (d.embed_count > 0) {
              <div class="t-label">{{ d.embed_count }} embeds — embedded transports, directly addressed</div>
            }
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    .cols { flex: 1; display: flex; overflow: hidden; background: var(--surface); min-height: 0; }
    .list { width: 360px; border-right: 1px solid var(--border); overflow: auto; flex-shrink: 0; }
    .lhead { padding: 6px 12px 5px; border-bottom: 1px solid var(--border); background: var(--surface-2);
      position: sticky; top: 0; z-index: 1; }
    .empty { padding: 16px; color: var(--dim); font-size: 11px; font-family: var(--mono); }
    .peek { flex: 1; min-width: 0; overflow: auto; display: flex; flex-direction: column; font-family: var(--mono); }
    .phead { padding: 12px 16px; border-bottom: 1px solid var(--border); }
    .prow { display: flex; align-items: center; gap: 7px; margin-bottom: 7px; }
    .spacer { flex: 1; }
    .ptitle { font-family: var(--sans); font-size: 18px; font-weight: 700; line-height: 1.2; margin-bottom: 8px; }
    .pchips { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; }
    .pdesc { font-family: var(--sans); font-size: 13px; color: var(--muted); line-height: 1.6; }
    .pbody { padding: 12px 16px; display: flex; flex-direction: column; gap: 14px; font-size: 11px; }
    .kv { display: flex; gap: 10px; }
    .kv .k { width: 86px; flex-shrink: 0; color: var(--dim); font-family: var(--mono); font-size: 10px; }
    .kv .v { flex: 1; color: var(--text); word-break: break-word; font-family: var(--sans); }
    .kv .v.mono { font-family: var(--mono); }
    .cls { display: flex; flex-wrap: wrap; gap: 4px; }
    .clschip { display: inline-flex; align-items: center; height: 17px; padding: 0 6px; font-size: 9px;
      border: 1px solid var(--border); background: var(--surface-2); color: var(--muted); }
  `],
})
export class CxColumnsView {
  records = input.required<RecordSummary[]>();
  open = output<string>();
  peek = linkedSignal<RecordSummary[], string | null>({
    source: this.records,
    computation: (recs, prev) =>
      recs.find((r) => r.id === prev?.value)?.id ?? recs[0]?.id ?? null,
  });
  doc = computed(
    () => this.records().find((r) => r.id === this.peek()) ?? this.records()[0] ?? null,
  );
  title = titleFor;
}

// ---- table view ----
@Component({
  selector: 'cx-table-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip, CxStatusChip],
  template: `
    <div class="wrap">
      <table>
        <thead>
          <tr>
            @for (c of cols; track c) { <th>{{ c }}</th> }
          </tr>
        </thead>
        <tbody>
          @for (r of records(); track r.id) {
            <tr (click)="open.emit(r.id)">
              <td><cx-mime-chip [m]="r.mime" /></td>
              <td class="title">{{ title(r) }}</td>
              <td class="muted">{{ r.origin_host || '—' }}</td>
              <td><cx-status-chip [status]="r.status" /></td>
              <td class="muted">{{ r.captured || '—' }}</td>
            </tr>
          }
        </tbody>
      </table>
      @if (records().length === 0) { <div class="empty">no records match the active filters.</div> }
    </div>
  `,
  styles: [`
    .wrap { flex: 1; overflow: auto; background: var(--surface); }
    table { width: 100%; border-collapse: collapse; font-size: var(--fs); font-family: var(--mono); }
    thead tr { position: sticky; top: 0; z-index: 1; background: var(--surface-2); border-bottom: 1px solid var(--border); }
    th { text-align: left; font-weight: 500; font-size: 9px; color: var(--dim); padding: 5px 9px;
      text-transform: uppercase; letter-spacing: 0.1em; border-right: 1px solid var(--border); }
    tbody tr { border-bottom: 1px solid var(--border); cursor: pointer; height: var(--rowH); }
    tbody tr:hover { background: var(--surface-2); }
    td { padding: 3px 9px; border-right: 1px solid var(--border); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    td.title { font-family: var(--sans); font-weight: 500; }
    td.muted { color: var(--muted); }
    .empty { padding: 16px; color: var(--dim); font-size: 11px; font-family: var(--mono); }
  `],
})
export class CxTableView {
  records = input.required<RecordSummary[]>();
  open = output<string>();
  readonly cols = ['mime', 'title', 'origin', 'status', 'captured'];
  title = titleFor;
}

// ---- gallery view ----
@Component({
  selector: 'cx-gallery-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip, CxThumb],
  template: `
    <div class="cx-gallery cx-scroll grid">
      @for (r of records(); track r.id) {
        <div class="tile" (click)="open.emit(r.id)">
          <div class="well">
            <cx-thumb [mime]="r.mime" />
            <div class="chip"><cx-mime-chip [m]="r.mime" /></div>
            @if (r.embed_count > 0) { <div class="emb">+{{ r.embed_count }} embeds</div> }
          </div>
          <div class="meta">
            <div class="title">{{ title(r) }}</div>
            <div class="host">{{ r.origin_host || '—' }}</div>
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    .grid { flex: 1; overflow: auto; padding: 14px; display: grid;
      grid-template-columns: repeat(auto-fill, minmax(184px, 1fr)); gap: 14px; align-content: start; background: var(--surface); }
    .tile { border: 1px solid var(--border); background: var(--surface); cursor: pointer; display: flex; flex-direction: column; }
    .tile:hover { border-color: var(--accent); }
    .well { height: 116px; background: var(--surface-2); border-bottom: 1px solid var(--border);
      display: flex; align-items: center; justify-content: center; position: relative; }
    .chip { position: absolute; top: 6px; left: 6px; }
    .emb { position: absolute; bottom: 6px; right: 6px; font-size: 8px; color: var(--muted);
      font-family: var(--mono); background: var(--surface); padding: 1px 4px; }
    .meta { padding: 7px 9px; }
    .title { font-size: 11.5px; line-height: 1.3; font-family: var(--sans); font-weight: 500;
      overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; min-height: 30px; }
    .host { font-size: 9px; color: var(--dim); margin-top: 4px; font-family: var(--mono);
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  `],
})
export class CxGalleryView {
  records = input.required<RecordSummary[]>();
  open = output<string>();
  title = titleFor;
}

// ---- cards feed ----
@Component({
  selector: 'cx-cards-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip, CxStatusChip, CxThumb],
  template: `
    <div class="cx-cards cx-scroll feed">
      @for (r of records(); track r.id) {
        <div class="card" (click)="open.emit(r.id)">
          <div class="thumb"><cx-thumb [mime]="r.mime" /></div>
          <div class="body">
            <div class="top">
              <cx-mime-chip [m]="r.mime" />
              <span class="title">{{ title(r) }}</span>
              <span class="date">{{ r.captured || '' }}</span>
            </div>
            <div class="desc">{{ r.description || '— not normalized' }}</div>
            <div class="meta">
              <cx-status-chip [status]="r.status" />
              @for (c of composites(r); track c) { <span class="pill">{{ c }}</span> }
            </div>
          </div>
        </div>
      }
      @if (records().length === 0) { <div class="empty">no records match the active filters.</div> }
    </div>
  `,
  styles: [`
    .feed { flex: 1; overflow: auto; padding: 14px; background: var(--bg); }
    .card { background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--border);
      padding: 12px; margin-bottom: 9px; display: flex; gap: 12px; cursor: pointer; }
    .card:hover { border-left-color: var(--accent); }
    .thumb { width: 66px; height: 66px; background: var(--surface-2); border: 1px solid var(--border);
      display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
    .body { flex: 1; min-width: 0; }
    .top { display: flex; align-items: center; gap: 7px; margin-bottom: 4px; }
    .top .title { font-size: 14px; font-weight: 600; font-family: var(--sans); overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
    .top .date { font-family: var(--mono); font-size: 10px; color: var(--dim); flex-shrink: 0; }
    .desc { font-size: 12px; color: var(--muted); margin-bottom: 6px; line-height: 1.5; font-family: var(--sans);
      overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
    .meta { display: flex; gap: 6px; align-items: center; font-family: var(--mono); font-size: 10px;
      color: var(--dim); flex-wrap: wrap; }
    .empty { padding: 16px; color: var(--dim); font-size: 11px; font-family: var(--mono); }
  `],
})
export class CxCardsView {
  records = input.required<RecordSummary[]>();
  open = output<string>();
  title = titleFor;
  composites(r: RecordSummary): string[] {
    return r.classifications.filter((c) => !c.startsWith('mime/') && !c.startsWith('origin/')).slice(0, 3);
  }
}
