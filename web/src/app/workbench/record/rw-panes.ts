// Record workbench — inspect-mode panes: contents (left) · reader (center) · inspector
// (right) · related (bottom). The reader reuses the Console's rendered/raw body; the
// inspector surfaces typed extended fields + hashes + touch lineage; related shows
// artifact-layer neighbors (shared classification/origin) within the current result set.

import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { CorpusStore } from '../../core/store';
import { RecordDetail, SegmentNode } from '../../core/models';
import {
  FlatSeg,
  atomColor,
  fmtBytes,
  fmtVal,
  firstAddr,
  flatSegments,
  hostOf,
  mimeInfo,
  segKey,
  titleFor,
} from '../../core/util';
import { CxMimeChip, CxTypeBadge } from '../../chips/chips';
import { CxRenderedBody, PickEvent } from '../../viewer/body';
import { CxRawBody } from '../../viewer/body';

interface OutlineGroup {
  entry: string | null;
  items: FlatSeg[];
}
function group(flat: FlatSeg[]): OutlineGroup[] {
  const out: OutlineGroup[] = [];
  for (const f of flat) {
    const entry = f.section?.entry ?? null;
    let g = out[out.length - 1];
    if (!g || g.entry !== entry) {
      g = { entry, items: [] };
      out.push(g);
    }
    g.items.push(f);
  }
  return out;
}

// ---- LEFT · contents (artifacts + outline) ----
@Component({
  selector: 'rw-contents',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="contents cx-scroll">
      <div class="sh"><span class="t-label">artifacts · {{ 1 + r().embeds.length }}</span></div>
      <div class="art">
        <span class="sq" [style.background]="mimeColor(r().mime)">{{ short(r().mime) }}</span>
        <div class="ai"><div class="an">{{ r().transport.name }}</div>
          <div class="ad">transport · {{ fmtBytes(r().transport.size) }}</div></div>
        <span class="prim">primary</span>
      </div>
      @for (e of r().embeds; track $index) {
        <div class="art">
          <span class="sq" [style.background]="mimeColor(e.mime)">{{ short(e.mime) }}</span>
          <div class="ai"><div class="an">{{ e.alt || short(e.mime) + ' embed' }}</div>
            <div class="ad">embed{{ e.width && e.height ? ' · ' + e.width + '×' + e.height : '' }}</div></div>
        </div>
      }

      <div class="sh bd"><span class="t-label">outline · {{ flat().length }}</span></div>
      @for (g of groups(); track $index) {
        @if (g.entry) { <div class="oentry">{{ g.entry }}</div> }
        @for (f of g.items; track f.idx) {
          <div class="orow" [class.on]="key(f.seg) === activeKey()" (click)="pick.emit({ key: key(f.seg), seg: f.seg })">
            <span class="dot" [style.background]="color(f.seg.atom)"></span>
            <span class="ol">{{ label(f.seg) }}</span>
          </div>
        }
      }
      @if (flat().length === 0) { <div class="empty">— no segments</div> }
    </div>
  `,
  styles: [`
    .contents { height: 100%; overflow: auto; background: var(--surface); font-family: var(--mono); }
    .sh { padding: 9px 12px 4px; } .sh.bd { border-top: 1px solid var(--border); margin-top: 4px; }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted); }
    .art { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-bottom: 1px solid var(--border); }
    .sq { width: 26px; height: 26px; flex-shrink: 0; color: #fff; display: flex; align-items: center;
      justify-content: center; font-size: 8.5px; font-weight: 700; }
    .ai { min-width: 0; flex: 1; } .an { font-size: 10.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .ad { font-size: 9px; color: var(--dim); }
    .prim { font-size: 7.5px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--accent); border: 1px solid var(--accent); padding: 0 4px; height: 13px; display: inline-flex; align-items: center; }
    .oentry { padding: 6px 12px 3px; font-size: 9.5px; color: var(--muted); font-weight: 600; }
    .orow { display: flex; align-items: center; gap: 8px; padding: 4px 12px 4px 18px; cursor: pointer;
      border-left: 2px solid transparent; }
    .orow:hover { background: var(--surface-2); }
    .orow.on { background: var(--accent-soft); border-left-color: var(--accent); }
    .dot { width: 6px; height: 6px; flex-shrink: 0; opacity: 0.85; }
    .ol { font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .orow.on .ol { color: var(--accent); }
    .empty { padding: 0 12px 10px; font-size: 9.5px; color: var(--dim); }
  `],
  imports: [],
})
export class RwContents {
  r = input.required<RecordDetail>();
  activeKey = input<string | null>(null);
  pick = output<PickEvent>();
  readonly fmtBytes = fmtBytes;
  readonly key = segKey;
  readonly color = atomColor;
  readonly flat = computed(() => flatSegments(this.r()));
  readonly groups = computed(() => group(this.flat()));
  short(m: string): string {
    return mimeInfo(m).short;
  }
  mimeColor(m: string): string {
    return mimeInfo(m).color;
  }
  label(seg: SegmentNode): string {
    return (
      seg.entry ||
      (seg.body ? seg.body.replace(/[#*]/g, '').slice(0, 40) : seg.description?.slice(0, 40)) ||
      seg.atom
    );
  }
}

// ---- CENTER · reader (reading / segments / source) ----
@Component({
  selector: 'rw-reader',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxRenderedBody, CxRawBody],
  template: `
    <div class="reader">
      <div class="rh">
        <span class="t-label">reader</span><span class="dim">· {{ flat().length }} segments</span>
        <span class="sp"></span>
        <div class="seg">
          @for (v of views; track v[0]) {
            <button [class.on]="view() === v[0]" (click)="setView.emit($any(v[0]))" [title]="v[0]">{{ v[1] }}</button>
          }
        </div>
      </div>
      <div class="rb cx-scroll">
        @switch (view()) {
          @case ('source') { <cx-raw-body [r]="r()" /> }
          @case ('segments') {
            @for (f of flat(); track f.idx) {
              <div class="sline" [class.on]="key(f.seg) === activeKey()" (click)="pick.emit({ key: key(f.seg), seg: f.seg })">
                <span class="dot" [style.background]="color(f.seg.atom)"></span>
                <div class="si">
                  <div class="st"><span class="sa" [style.color]="color(f.seg.atom)">{{ f.seg.atom }}{{ f.seg.overlay ? ' · ' + f.seg.overlay : '' }}</span>
                    <span class="sad">{{ addr(f.seg.address) }}</span></div>
                  <div class="sb">{{ (f.seg.body || f.seg.description || '—').replace(/[#*|]/g, '').slice(0, 180) }}</div>
                </div>
              </div>
            }
            @if (flat().length === 0) { <div class="empty">no normalized content.</div> }
          }
          @default {
            @if (flat().length) { <cx-rendered-body [r]="r()" [activeKey]="activeKey()" (pick)="pick.emit($event)" /> }
            @else {
              <div class="none"><span class="ic">⛁</span><span>no normalized content</span>
                <span class="s">this record is a {{ r().status }} — its body is authored when the normalize pass runs.</span></div>
            }
          }
        }
      </div>
    </div>
  `,
  styles: [`
    .reader { display: flex; flex-direction: column; height: 100%; min-height: 0; background: var(--surface);
      font-family: var(--mono); }
    .rh { flex-shrink: 0; height: 32px; display: flex; align-items: center; gap: 8px; padding: 0 12px;
      border-bottom: 1px solid var(--border); background: var(--surface-2); }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted); }
    .dim { font-size: 10px; color: var(--dim); } .sp { flex: 1; }
    .seg { display: inline-flex; border: 1px solid var(--border); }
    .seg button { height: 20px; padding: 0 8px; border: none; border-radius: 0; background: transparent;
      color: var(--muted); font-size: 11px; cursor: pointer; font-family: var(--mono); }
    .seg button.on { background: var(--accent-soft); color: var(--accent); }
    .rb { flex: 1; overflow: auto; min-height: 0; }
    .sline { display: flex; gap: 10px; padding: 8px 14px; border-bottom: 1px solid var(--border); cursor: pointer;
      border-left: 2px solid transparent; }
    .sline.on { background: var(--accent-soft); border-left-color: var(--accent); }
    .dot { width: 9px; height: 9px; margin-top: 3px; flex-shrink: 0; opacity: 0.85; }
    .si { min-width: 0; flex: 1; }
    .st { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
    .sa { font-size: 8.5px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }
    .sad { font-size: 9px; color: var(--dim); }
    .sb { font-family: var(--sans); font-size: 11.5px; color: var(--muted); line-height: 1.5;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .empty { padding: 18px; font-size: 11px; color: var(--dim); }
    .none { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 8px; color: var(--dim); text-align: center; padding: 24px; }
    .none .ic { font-size: 22px; opacity: 0.5; } .none .s { font-size: 10px; max-width: 240px; line-height: 1.5; }
  `],
})
export class RwReader {
  r = input.required<RecordDetail>();
  view = input.required<'reading' | 'segments' | 'source'>();
  activeKey = input<string | null>(null);
  pick = output<PickEvent>();
  setView = output<'reading' | 'segments' | 'source'>();
  readonly views: [string, string][] = [['reading', '¶'], ['segments', '≣'], ['source', '‹∕›']];
  readonly key = segKey;
  readonly color = atomColor;
  readonly addr = firstAddr;
  readonly flat = computed(() => flatSegments(this.r()));
}

// ---- RIGHT · inspector (full metadata) ----
@Component({
  selector: 'rw-inspector',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip, CxTypeBadge],
  template: `
    <div class="insp cx-scroll">
      <div class="hd">
        <div class="chips"><cx-mime-chip [m]="r().mime" />
          @if (r().visibility && r().visibility !== 'visible') { <span class="vis">{{ r().visibility }}</span> }</div>
        <div class="meta"><span class="st"><span class="dot" [style.background]="statusColor(r().status)"></span>{{ r().status }}</span>
          <span class="dim">· {{ r().corpus }}</span>
          @if (r().captured) { <span class="dim">· captured {{ r().captured!.slice(0, 10) }}</span> }</div>
        @if (r().description) { <div class="desc">{{ r().description }}</div> }
      </div>

      @if (ext().length) {
        <div class="sec"><div class="t-label">extended fields · {{ ext().length }}</div>
          @for (g of groupedExt(); track g.label) {
            <div class="eg">{{ g.label }}</div>
            @for (f of g.fields; track f.label) {
              <div class="er"><cx-type-badge [type]="f.type" /><span class="el">{{ f.label }}</span>
                <span class="sp"></span><span class="ev">{{ f.value }}</span></div>
            }
          }
        </div>
      }
      <div class="sec"><div class="t-label">origin &amp; transport</div>
        @for (o of r().origins; track $index) {
          <div class="kv"><span class="k">origin</span><span class="v">{{ host(o.uri[0]) }}</span></div>
        }
        <div class="kv"><span class="k">transport</span><span class="v">{{ r().transport.name }} · {{ fmtBytes(r().transport.size) }}</span></div>
        <div class="kv"><span class="k">captured</span><span class="v">{{ r().captured || '—' }}</span></div>
      </div>
      @if (composites().length) {
        <div class="sec"><div class="t-label">classifications</div>
          <div class="cls">@for (c of composites(); track c) { <span class="pill">{{ c }}</span> }</div></div>
      }
      @if (hashes().length) {
        <div class="sec"><div class="t-label">hashes</div>
          @for (h of hashes(); track h[0]) { <div class="kv"><span class="k">{{ h[0] }}</span><span class="v brk">{{ h[1] }}</span></div> }</div>
      }
      @if (r().touch.length) {
        <div class="sec"><div class="t-label">lineage · {{ r().touch.length }}</div>
          @for (t of r().touch; track $index) {
            <div class="tl"><span class="tn">{{ $index === 0 ? '●' : '↳' }}</span><span class="tt">{{ t }}</span></div>
          }</div>
      }
    </div>
  `,
  styles: [`
    .insp { height: 100%; overflow: auto; background: var(--surface); font-family: var(--mono); }
    .hd { padding: 11px 12px 9px; } .chips { display: flex; gap: 6px; margin-bottom: 9px; }
    .vis { font-size: 8.5px; color: var(--warn); border: 1px solid var(--warn); padding: 0 4px; height: 14px;
      display: inline-flex; align-items: center; }
    .meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 10.5px; }
    .st { display: inline-flex; align-items: center; gap: 5px; } .dot { width: 7px; height: 7px; border-radius: 50%; }
    .dim { color: var(--dim); } .desc { font-family: var(--sans); font-size: 12px; color: var(--muted); line-height: 1.55; margin-top: 10px; }
    .sec { border-top: 1px solid var(--border); padding: 10px 12px; }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted); margin-bottom: 8px; }
    .eg { font-size: 8.5px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.10em; margin: 4px 0; }
    .er { display: flex; align-items: center; gap: 8px; padding: 3px 0; border-bottom: 1px solid var(--border); }
    .el { font-size: 10px; color: var(--muted); } .sp { flex: 1; }
    .ev { font-size: 10.5px; color: var(--text); font-weight: 500; text-align: right; max-width: 180px;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .kv { display: flex; gap: 10px; font-size: 10.5px; margin-bottom: 4px; }
    .kv .k { width: 74px; flex-shrink: 0; color: var(--dim); font-size: 9.5px; }
    .kv .v { flex: 1; color: var(--text); word-break: break-word; } .v.brk { word-break: break-all; font-size: 9.5px; color: var(--muted); }
    .cls { display: flex; flex-wrap: wrap; gap: 5px; }
    .pill { display: inline-flex; align-items: center; height: 17px; padding: 0 6px; font-size: 9px;
      background: var(--surface-2); border: 1px solid var(--border); color: var(--muted); }
    .tl { display: flex; align-items: center; gap: 7px; padding: 2px 0; font-size: 9.5px; color: var(--muted); }
    .tn { color: var(--dim); width: 10px; text-align: center; } .tt { word-break: break-all; }
  `],
})
export class RwInspector {
  private store = inject(CorpusStore);
  r = input.required<RecordDetail>();
  readonly fmtBytes = fmtBytes;
  readonly host = hostOf;
  readonly composites = computed(() => this.r().classifications.filter((c) => c.includes('/')));
  readonly hashes = computed(() => Object.entries(this.r().hashes));
  readonly ext = computed(() => {
    const r = this.r();
    const by = this.store.fieldById();
    const out: { label: string; type: string; groupLabel: string; value: string }[] = [];
    const push = (key: string, gl: string, fields: Record<string, unknown>) => {
      for (const [k, v] of Object.entries(fields)) {
        if (v == null || v === '') continue;
        const def = by.get(`${key}::${k}`);
        const type = def?.type ?? 'string';
        const val = Array.isArray(v) ? v.join(', ') : String(v);
        out.push({ label: def?.label ?? k, type, groupLabel: gl, value: fmtVal(val, type) });
      }
    };
    push(`mime/${r.mime}`, r.mime.split('/').pop() ?? r.mime, r.artifactFields);
    for (const o of r.origins) {
      const h = hostOf(o.uri[0] ?? '');
      if (h) push(`origin/${h}`, h, o.fields);
    }
    for (const c of r.classifyBlocks) push(`composite/${c.ns}/${c.id}`, `${c.ns}/${c.id}`, c.fields);
    return out;
  });
  readonly groupedExt = computed(() => {
    const by = new Map<string, { label: string; type: string; groupLabel: string; value: string }[]>();
    for (const f of this.ext()) {
      const arr = by.get(f.groupLabel) ?? [];
      arr.push(f);
      by.set(f.groupLabel, arr);
    }
    return [...by.entries()].map(([label, fields]) => ({ label, fields }));
  });
  statusColor(s: string): string {
    return s === 'normalized' ? 'var(--ok)' : s === 'draft' ? 'var(--warn)' : 'var(--dim)';
  }
}

// ---- BOTTOM · related (neighbors + annotations) ----
@Component({
  selector: 'rw-related',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip],
  template: `
    <div class="rel">
      <div class="cols">
        @for (col of cols(); track col.title) {
          <div class="col">
            <div class="t-label">{{ col.title }} · {{ col.items.length }}</div>
            <div class="cl cx-scroll">
              @for (n of col.items; track n.id) {
                <div class="nr" (click)="store.openRecord(n.id)">
                  <cx-mime-chip [m]="n.mime" /><span class="nt">{{ title(n) }}</span><span class="ch">›</span>
                </div>
              }
              @if (col.items.length === 0) { <span class="dim">{{ col.empty }}</span> }
            </div>
          </div>
        }
        <div class="col w">
          <div class="t-label">annotations · {{ r().annotations.length }}</div>
          <div class="cl cx-scroll">
            @for (a of r().annotations; track $index) {
              <div class="ann"><span class="as" [style.background]="sev(a)"></span>
                <div class="ai"><div class="at">{{ a.namespace }}/{{ a.id }}</div>
                  <div class="anote">{{ note(a) }}</div></div></div>
            }
            @if (r().annotations.length === 0) { <span class="dim">— clean</span> }
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .rel { height: 100%; display: flex; flex-direction: column; min-height: 0; background: var(--surface);
      font-family: var(--mono); }
    .cols { flex: 1; min-height: 0; display: flex; }
    .col { flex: 1; min-width: 160px; border-right: 1px solid var(--border); padding: 9px 12px; min-height: 0;
      display: flex; flex-direction: column; } .col.w { flex: 1.3; }
    .t-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted); margin-bottom: 8px; }
    .cl { overflow: auto; min-height: 0; display: flex; flex-direction: column; gap: 5px; }
    .nr { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--border);
      cursor: pointer; background: var(--surface); }
    .nr:hover { background: var(--surface-2); }
    .nt { font-family: var(--sans); font-size: 11.5px; font-weight: 500; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; flex: 1; min-width: 0; }
    .ch { color: var(--dim); }
    .dim { font-size: 9.5px; color: var(--dim); }
    .ann { display: flex; gap: 8px; padding: 6px 8px; border: 1px solid var(--border); }
    .as { width: 6px; height: 6px; margin-top: 3px; flex-shrink: 0; } .ai { min-width: 0; }
    .at { font-size: 9.5px; color: var(--text); font-weight: 600; }
    .anote { font-family: var(--sans); font-size: 11px; color: var(--muted); line-height: 1.45; }
  `],
})
export class RwRelated {
  readonly store = inject(CorpusStore);
  r = input.required<RecordDetail>();
  readonly title = titleFor;
  readonly cols = computed(() => {
    const r = this.r();
    const rows = this.store.wbRows().filter((x) => x.id !== r.id);
    const cls = new Set(r.classifications);
    const hosts = new Set(r.origins.map((o) => hostOf(o.uri[0] ?? '')));
    const byClass = rows.filter((x) => x.classifications.some((c) => cls.has(c))).slice(0, 24);
    const byOrigin = rows.filter((x) => hosts.has(x.origin_host)).slice(0, 24);
    return [
      { title: 'same classification', items: byClass, empty: 'no shared class' },
      { title: 'same origin', items: byOrigin, empty: 'no origin peers' },
    ];
  });
  sev(a: Record<string, unknown>): string {
    return a['severity'] === 'warning' ? 'var(--warn)' : a['severity'] === 'error' ? 'var(--err)' : 'var(--dim)';
  }
  note(a: Record<string, unknown>): string {
    return String(a['note'] || a['quote'] || a['attribution_text'] || '—');
  }
}
