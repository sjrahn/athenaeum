// Right · Detail — the selected record with its typed extended-field values surfaced
// (the through-line), plus origin/transport, classifications, and a normalized preview.
// "open record" enters the record workbench; a classification chip filters like-this.

import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { CorpusStore } from '../../core/store';
import { fmtBytes, fmtVal, hostOf, titleFor } from '../../core/util';
import { CxMimeChip, CxTypeBadge } from '../../chips/chips';

interface ExtField {
  label: string;
  type: string;
  groupLabel: string;
  value: string;
}

@Component({
  selector: 'wb-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip, CxTypeBadge],
  template: `
    @if (!r()) {
      <div class="empty">
        <span class="ic">⛁</span>
        <span class="t">select a record</span>
        <span class="s">its metadata, typed extended fields, and normalized preview show here —
          your tools beside the workbench.</span>
      </div>
    } @else {
      <div class="detail cx-scroll">
        <div class="hdr">
          <div class="chips">
            <cx-mime-chip [m]="r()!.mime" />
            <span class="sp"></span>
            <span class="id">{{ r()!.id.slice(0, 12) }}…</span>
          </div>
          <div class="title">{{ title(r()!) }}</div>
          <div class="meta">
            <span class="st"><span class="dot" [style.background]="statusColor(r()!.status)"></span>{{ r()!.status }}</span>
            @if (segCount() > 0) { <span class="dim">{{ segCount() }} segments</span> }
            @if (r()!.transport.size) { <span class="dim">{{ fmtBytes(r()!.transport.size) }}</span> }
          </div>
          @if (r()!.description) { <div class="desc">{{ r()!.description }}</div> }
        </div>

        @if (extFields().length > 0) {
          <div class="sec">
            <div class="t-label">extended fields · {{ extFields().length }}</div>
            @for (grp of groupedExt(); track grp.label) {
              <div class="ext-grp">{{ grp.label }}</div>
              @for (f of grp.fields; track f.label) {
                <div class="ext-row">
                  <cx-type-badge [type]="f.type" />
                  <span class="ef-lbl">{{ f.label }}</span>
                  <span class="sp"></span>
                  <span class="ef-val">{{ f.value }}</span>
                </div>
              }
            }
          </div>
        }

        <div class="sec">
          <div class="t-label">origin &amp; transport</div>
          @for (o of r()!.origins; track $index) {
            <div class="kv"><span class="k">origin</span><span class="v mono">{{ host(o.uri[0]) }}</span></div>
            @if (o.uri[0]) { <div class="kv"><span class="k">uri</span><span class="v acc brk">{{ o.uri[0] }}</span></div> }
          }
          <div class="kv"><span class="k">transport</span><span class="v mono">{{ r()!.transport.name }} · {{ fmtBytes(r()!.transport.size) }}</span></div>
          <div class="kv"><span class="k">captured</span><span class="v mono">{{ r()!.captured || '—' }}</span></div>
        </div>

        @if (composites().length > 0) {
          <div class="sec">
            <div class="t-label">classifications</div>
            <div class="cls">
              @for (c of composites(); track c) {
                <span class="pill" (click)="filterLike(c)" title="filter like this">{{ c }}</span>
              }
            </div>
          </div>
        }

        @if (preview()) {
          <div class="sec">
            <div class="t-label">normalized · preview</div>
            <div class="prev">{{ preview() }}…</div>
          </div>
        }

        <div class="sp"></div>
        <div class="actions">
          <button class="btn primary" (click)="store.openRecord(r()!.id)">open record ⤢</button>
          <button class="btn">cite</button>
        </div>
      </div>
    }
  `,
  styles: [`
    :host { display: block; height: 100%; }
    .empty { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 8px; color: var(--dim); font-family: var(--mono); padding: 24px; text-align: center;
      background: var(--surface); }
    .empty .ic { font-size: 22px; opacity: 0.5; }
    .empty .t { font-size: 11px; }
    .empty .s { font-size: 9.5px; max-width: 200px; line-height: 1.5; }
    .detail { height: 100%; overflow: auto; font-family: var(--mono); background: var(--surface);
      display: flex; flex-direction: column; }
    .hdr { padding: 11px 12px 10px; }
    .chips { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
    .id { font-size: 8px; color: var(--dim); }
    .sp { flex: 1; }
    .title { font-family: var(--sans); font-size: 16px; font-weight: 700; line-height: 1.25; margin-bottom: 8px; }
    .meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 10px; }
    .st { display: inline-flex; align-items: center; gap: 5px; }
    .dot { width: 7px; height: 7px; border-radius: 50%; }
    .dim { color: var(--dim); font-size: 9.5px; }
    .desc { font-family: var(--sans); font-size: 11.5px; color: var(--muted); line-height: 1.55; margin-top: 9px; }
    .sec { border-top: 1px solid var(--border); padding: 10px 12px; }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted);
      margin-bottom: 8px; }
    .ext-grp { font-size: 8.5px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.10em;
      margin: 4px 0; }
    .ext-row { display: flex; align-items: center; gap: 8px; padding: 3px 0; border-bottom: 1px solid var(--border); }
    .ef-lbl { font-size: 10px; color: var(--muted); }
    .ef-val { font-size: 10.5px; color: var(--text); font-weight: 500; text-align: right; overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap; max-width: 170px; }
    .kv { display: flex; gap: 10px; font-size: 10.5px; margin-bottom: 4px; }
    .kv .k { width: 74px; flex-shrink: 0; color: var(--dim); font-size: 9.5px; }
    .kv .v { flex: 1; color: var(--text); word-break: break-word; }
    .v.mono { font-family: var(--mono); } .v.acc { color: var(--accent); font-size: 9.5px; } .v.brk { word-break: break-all; }
    .cls { display: flex; flex-wrap: wrap; gap: 5px; }
    .pill { display: inline-flex; align-items: center; height: 17px; padding: 0 6px; cursor: pointer;
      font-size: 9px; background: var(--surface-2); border: 1px solid var(--border); color: var(--muted); }
    .prev { font-family: var(--sans); font-size: 11px; color: var(--muted); line-height: 1.6;
      max-height: 92px; overflow: hidden; }
    .actions { position: sticky; bottom: 0; display: flex; gap: 7px; padding: 10px;
      border-top: 1px solid var(--border); background: var(--surface-2); }
    .btn { height: 26px; padding: 0 10px; border: 1px solid var(--border); background: var(--surface);
      color: var(--text); font-family: var(--mono); font-size: 11px; cursor: pointer; }
    .btn.primary { flex: 1; justify-content: center; background: var(--accent); color: #fff; border-color: transparent; }
  `],
})
export class WbDetail {
  readonly store = inject(CorpusStore);
  readonly r = this.store.selected;
  readonly fmtBytes = fmtBytes;
  readonly title = titleFor;
  readonly host = hostOf;

  readonly segCount = computed(() => this.flatSegs().length);
  readonly composites = computed(() =>
    (this.r()?.classifications ?? []).filter((c) => c.includes('/')),
  );
  readonly preview = computed(() => {
    const seg = this.flatSegs().find((s) => s.atom === 'text' && s.body);
    if (!seg) return '';
    return seg.body.replace(/^#+\s*/gm, '').replace(/\*\*/g, '').slice(0, 280);
  });
  readonly extFields = computed<ExtField[]>(() => {
    const r = this.r();
    if (!r) return [];
    const by = this.store.fieldById();
    const out: ExtField[] = [];
    const push = (overlayKey: string, groupLabel: string, fields: Record<string, unknown>) => {
      for (const [k, v] of Object.entries(fields)) {
        if (v == null || v === '') continue;
        const def = by.get(`${overlayKey}::${k}`);
        const type = def?.type ?? 'string';
        const val = Array.isArray(v) ? v.join(', ') : String(v);
        out.push({ label: def?.label ?? k, type, groupLabel, value: fmtVal(val, type) });
      }
    };
    push(`mime/${r.mime}`, this.mimeShort(r.mime), r.artifactFields);
    for (const o of r.origins) {
      const h = hostOf(o.uri[0] ?? '');
      if (h) push(`origin/${h}`, h, o.fields);
    }
    for (const c of r.classifyBlocks) {
      push(`composite/${c.ns}/${c.id}`, `${c.ns}/${c.id}`, c.fields);
    }
    return out;
  });
  readonly groupedExt = computed(() => {
    const by = new Map<string, ExtField[]>();
    for (const f of this.extFields()) {
      const arr = by.get(f.groupLabel) ?? [];
      arr.push(f);
      by.set(f.groupLabel, arr);
    }
    return [...by.entries()].map(([label, fields]) => ({ label, fields }));
  });

  private flatSegs() {
    const out: { atom: string; body: string }[] = [];
    for (const node of this.r()?.content ?? []) {
      if (node.type === 'section') {
        for (const s of node.children) out.push({ atom: s.atom, body: s.body });
      } else {
        out.push({ atom: node.atom, body: node.body });
      }
    }
    return out;
  }
  private mimeShort(m: string): string {
    return m.split('/').pop()?.split('+')[0] ?? m;
  }
  statusColor(s: string): string {
    return s === 'normalized' ? 'var(--ok)' : s === 'draft' ? 'var(--warn)' : 'var(--dim)';
  }
  filterLike(c: string): void {
    const [ns, id] = c.split('/');
    if (ns && id) this.store.toggleFacet(`composite:${ns}`, id);
  }
}
