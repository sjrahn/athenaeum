import { ChangeDetectionStrategy, Component, computed, inject, input, output, signal } from '@angular/core';
import { CorpusStore } from '../core/store';
import { Viewport } from '../core/viewport';
import { Facet } from '../core/models';
import { fmtVal, overlayKey } from '../core/util';
import { CxTypeBadge } from '../chips/chips';

interface AppliedItem {
  facetKey: string;
  value: string;
  label: string;
}

/** One facet namespace in the rail: collapsible, top-5 + "N more",
 *  selected values pinned to the top, hidden when the universal filter excludes it. */
@Component({
  selector: 'cx-facet-group',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (!hidden()) {
      <div class="grp">
        <div class="head cx-tap" (click)="open.set(!open())">
          <span class="caret">{{ open() ? '▾' : '▸' }}</span>
          <span class="lbl" [style.color]="isComposite() ? 'var(--accent)' : 'var(--muted)'">{{ facet().label }}</span>
          @if (isComposite()) { <span class="ctag">composite</span> }
          <span class="spacer"></span>
          @if (sel().size) { <span class="seln">{{ sel().size }}</span> }
        </div>
        @if (open() || query()) {
          <div role="group" [attr.aria-label]="facet().label">
            @for (val of shown(); track val.v) {
              <div class="opt cx-tap" role="checkbox" [attr.aria-checked]="sel().has(val.v)"
                [class.on]="sel().has(val.v)" (click)="toggle.emit(val.v)">
                <span class="box" [class.boxon]="sel().has(val.v)">@if (sel().has(val.v)) { <span class="tick">✓</span> }</span>
                <span class="vtext">{{ val.label }}</span>
                <span class="vn">{{ val.n }}</span>
              </div>
            }
            @if (!query() && filtered().length > 5) {
              <div class="more" (click)="showAll.set(!showAll())">
                {{ showAll() ? '− less' : '+ ' + (filtered().length - 5) + ' more' }}
              </div>
            }
          </div>
        }
      </div>
    }
  `,
  styles: [`
    .grp { margin-bottom: 2px; }
    .head { display: flex; align-items: center; gap: 6px; padding: 4px 12px; cursor: pointer; }
    .caret { color: var(--dim); font-size: 8px; width: 8px; }
    .lbl { font-size: 9px; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; }
    .ctag { font-size: 8px; color: var(--dim); }
    .spacer { flex: 1; }
    .seln { font-size: 8px; color: var(--accent); }
    .opt { height: 20px; display: flex; align-items: center; gap: 7px; padding: 0 12px 0 26px;
      font-size: 10.5px; cursor: pointer; color: var(--text); }
    .opt.on { background: var(--accent-soft); color: var(--accent); }
    .box { width: 9px; height: 9px; border: 1px solid var(--border-strong); flex-shrink: 0;
      display: flex; align-items: center; justify-content: center; }
    .boxon { border-color: var(--accent); background: var(--accent); }
    .tick { color: #fff; font-size: 7px; line-height: 1; }
    .vtext { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .vn { color: var(--dim); font-size: 9px; }
    .opt.on .vn { color: var(--accent); }
    .more { padding: 2px 12px 4px 26px; font-size: 9px; color: var(--dim); cursor: pointer; }
  `],
})
export class CxFacetGroup {
  facet = input.required<Facet>();
  sel = input.required<Set<string>>();
  query = input('');
  toggle = output<string>();
  open = signal(true);
  showAll = signal(false);

  isComposite = computed(() => this.facet().key.startsWith('composite:'));
  private ordered = computed(() => {
    const s = this.sel();
    return [...this.facet().values].sort((a, b) =>
      s.has(b.v) === s.has(a.v) ? 0 : s.has(b.v) ? 1 : -1,
    );
  });
  filtered = computed(() => {
    const ql = this.query().trim().toLowerCase();
    return ql
      ? this.ordered().filter((x) => String(x.v).toLowerCase().includes(ql))
      : this.ordered();
  });
  hidden = computed(() => !!this.query().trim() && this.filtered().length === 0);
  shown = computed(() => {
    const expanded = this.showAll() || !!this.query().trim();
    return expanded ? this.filtered() : this.filtered().slice(0, 5);
  });
}

/** An applied filter, expandable to its overlay's typed extended-field refinements. */
@Component({
  selector: 'cx-applied-row',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxTypeBadge],
  template: `
    <div class="row">
      <div class="head">
        <span class="lead" (click)="expandable() && open.set(!open())" [style.cursor]="expandable() ? 'pointer' : 'default'">
          <span class="caret">{{ expandable() ? (open() ? '▾' : '▸') : '' }}</span>
          <span class="chip"><span class="op">{{ item().label }}:</span><span class="cv">{{ item().value }}</span></span>
          @if (activeUnder() > 0) { <span class="plus">+{{ activeUnder() }}</span> }
        </span>
        <span class="rm" title="remove filter" (click)="remove.emit()">×</span>
      </div>
      @if (open() && expandable()) {
        <div class="fields">
          <div class="ftitle">optional filters · extended fields</div>
          @for (f of fields(); track f.field) {
            <div class="field">
              <div class="fhead"><span class="fname">{{ f.field }}</span><cx-type-badge [type]="f.type" /></div>
              <div class="vals">
                @for (v of f.values; track v) {
                  <span class="vchip" [class.von]="isOn(f.field, v)" [title]="v"
                    (click)="toggleField.emit({ field: f.field, value: v })">{{ fmt(v, f.type) }}</span>
                }
              </div>
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .row { margin-bottom: 1px; }
    .head { display: flex; align-items: center; gap: 6px; padding: 0 12px; height: 24px; }
    .lead { flex: 1; display: flex; align-items: center; gap: 6px; min-width: 0; }
    .caret { color: var(--dim); font-size: 8px; width: 8px; flex-shrink: 0; }
    .chip { display: inline-flex; align-items: center; gap: 4px; height: 18px; padding: 0 6px;
      background: var(--accent-soft); color: var(--accent); font-size: 10px; min-width: 0; }
    .op { opacity: 0.7; flex-shrink: 0; }
    .cv { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .plus { font-size: 8px; color: var(--accent); }
    .rm { cursor: pointer; color: var(--dim); font-size: 13px; flex-shrink: 0; line-height: 1; }
    .fields { padding: 3px 12px 5px 26px; }
    .ftitle { font-size: 8px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 5px; }
    .field { margin-bottom: 6px; }
    .fhead { display: flex; align-items: center; gap: 5px; margin-bottom: 3px; }
    .fname { font-family: var(--mono); font-size: 9.5px; color: var(--muted);
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .vals { display: flex; flex-wrap: wrap; gap: 3px; }
    .vchip { display: inline-flex; align-items: center; height: 16px; padding: 0 5px; max-width: 162px;
      font-family: var(--mono); font-size: 9px; cursor: pointer; border: 1px solid var(--border);
      background: var(--bg); color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .vchip.von { border-color: var(--accent); background: var(--accent); color: #fff; }
  `],
})
export class CxAppliedRow {
  private store = inject(CorpusStore);
  item = input.required<AppliedItem>();
  remove = output<void>();
  toggleField = output<{ field: string; value: string }>();
  open = signal(false);

  overlayKey = computed(() => overlayKey(this.item().facetKey, this.item().value));
  fields = computed(() => {
    const k = this.overlayKey();
    return k ? (this.store.schema()[k] ?? []) : [];
  });
  expandable = computed(() => this.fields().length > 0);
  activeUnder = computed(() => {
    const k = this.overlayKey();
    if (!k) return 0;
    const sel = this.store.fieldSel();
    return this.fields().reduce((n, f) => n + (sel[`${k}::${f.field}`]?.size ?? 0), 0);
  });

  isOn(field: string, value: string): boolean {
    const k = this.overlayKey();
    return !!k && !!this.store.fieldSel()[`${k}::${field}`]?.has(value);
  }
  fmt = fmtVal;
}

/** The left rail: corpus header, saved views, applied filters, universal facet
 *  filter, and the dynamic facet groups. */
@Component({
  selector: 'cx-sidebar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxFacetGroup, CxAppliedRow],
  template: `
    <div class="rail cx-scroll" [class.mobile]="mobile()">
      @if (mobile()) {
        <div class="mhead">
          <span class="t-label" style="font-size:11px">filters &amp; facets</span>
          @if (store.selectionCount() > 0) { <span class="active">· {{ store.selectionCount() }} active</span> }
          <span class="spacer"></span>
          <button class="btn btn-ghost donebtn" (click)="store.closeDrawer()">done ✓</button>
        </div>
      }
      <!-- corpus header -->
      <div class="chead">
        <div class="ctop">
          <span class="cdot" [style.background]="store.corpus()?.color"></span>
          <span class="cname">{{ store.corpus()?.name }}</span>
          <span class="spacer"></span>
          <span class="crec">{{ store.corpus()?.record_count ?? 0 }} rec</span>
        </div>
        <div class="cdesc">{{ store.corpus()?.desc }}</div>
      </div>

      <!-- saved views -->
      <div class="views">
        <div class="t-label vlbl">views</div>
        @for (v of viewDefs; track v[0]) {
          <div class="vrow cx-tap" [class.on]="store.savedView() === v[0]" (click)="store.setSavedView(v[0])">
            <span class="vbox" [style.background]="store.savedView() === v[0] ? 'var(--accent)' : 'var(--border-strong)'"></span>
            <span>{{ v[1] }}</span>
          </div>
        }
      </div>

      <!-- facet rail -->
      <div class="facets cx-scroll">
        @if (store.selectionCount() > 0) {
          <div class="applied">
            <div class="ahead">
              <span class="t-label" style="color:var(--accent)">applied · {{ store.selectionCount() }}</span>
              <span class="spacer"></span>
              <span class="clear" (click)="store.clearAll()">clear all</span>
            </div>
            @for (it of appliedItems(); track it.facetKey + it.value) {
              <cx-applied-row [item]="it"
                (remove)="store.toggleFacet(it.facetKey, it.value)"
                (toggleField)="onField(it, $event)" />
            }
          </div>
        }

        <div class="fhead"><span class="t-label">facets — derived</span></div>
        <div class="ffilter">
          <div class="fbox">
            <span class="ico">⌕</span>
            <input [value]="facetQuery()" (input)="facetQuery.set($any($event.target).value)"
              placeholder="filter facets…" aria-label="filter facets" />
            @if (facetQuery()) { <span class="x" (click)="facetQuery.set('')">×</span> }
          </div>
        </div>

        @for (f of store.facets(); track f.key) {
          <cx-facet-group [facet]="f" [sel]="selFor(f.key)" [query]="facetQuery()"
            (toggle)="store.toggleFacet(f.key, $event)" />
        }
        @if (noMatches()) {
          <div class="nomatch">no facet values match “{{ facetQuery() }}”.</div>
        }
        <div style="height:12px"></div>
      </div>

      <!-- footer api line -->
      <div class="foot">
        <span class="led" [style.background]="store.endpoint().online ? 'var(--ok)' : 'var(--err)'"></span>
        <span class="fbase">{{ store.base() }}</span>
      </div>
    </div>
  `,
  styles: [`
    .rail { width: 224px; flex-shrink: 0; background: var(--surface-2); border-right: 1px solid var(--border);
      display: flex; flex-direction: column; overflow: hidden; font-family: var(--mono); }
    .chead { padding: 10px 12px 9px; border-bottom: 1px solid var(--border); }
    .ctop { display: flex; align-items: center; gap: 7px; }
    .cdot { width: 8px; height: 8px; flex-shrink: 0; }
    .cname { font-size: 12px; font-weight: 600; color: var(--text); }
    .spacer { flex: 1; }
    .crec { font-size: 10px; color: var(--dim); }
    .cdesc { font-size: 9.5px; color: var(--muted); margin-top: 5px; line-height: 1.5; }
    .views { padding: 8px 0 4px; border-bottom: 1px solid var(--border); }
    .vlbl { padding: 0 12px 4px; }
    .vrow { height: 22px; display: flex; align-items: center; gap: 7px; padding: 0 12px; font-size: 11px;
      cursor: pointer; color: var(--text); }
    .vrow.on { background: var(--accent-soft); color: var(--accent); }
    .vbox { width: 6px; height: 6px; }
    .facets { flex: 1; overflow: auto; min-height: 0; }
    .applied { border-bottom: 1px solid var(--border); background: var(--surface); padding: 8px 0 6px; }
    .ahead { display: flex; align-items: center; padding: 0 12px 5px; }
    .clear { font-size: 9px; color: var(--accent); cursor: pointer; }
    .fhead { display: flex; align-items: center; padding: 8px 12px 4px; }
    .ffilter { padding: 0 12px 6px; }
    .fbox { display: flex; align-items: center; gap: 6px; height: 22px; padding: 0 7px;
      border: 1px solid var(--border); background: var(--bg); }
    .fbox .ico { color: var(--dim); font-size: 10px; }
    .fbox input { flex: 1; min-width: 0; background: transparent; border: none; outline: none;
      color: var(--text); font-family: var(--mono); font-size: 10.5px; }
    .fbox .x { cursor: pointer; color: var(--dim); font-size: 11px; }
    .nomatch { padding: 4px 12px; font-size: 9px; color: var(--dim); }
    .foot { border-top: 1px solid var(--border); padding: 6px 12px; font-size: 9px; color: var(--dim);
      display: flex; gap: 6px; align-items: center; }
    .led { width: 5px; height: 5px; border-radius: 50%; }
    .fbase { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    /* mobile drawer */
    .rail.mobile { width: min(86vw, 330px); height: 100%; }
    .mhead { flex-shrink: 0; height: 48px; display: flex; align-items: center; gap: 8px; padding: 0 14px;
      border-bottom: 1px solid var(--border); background: var(--surface); }
    .mhead .active { font-size: 10px; color: var(--accent); }
    .mhead .donebtn { height: 34px; padding: 0 12px; gap: 6px; font-size: 12px; }
  `],
})
export class CxSidebar {
  readonly store = inject(CorpusStore);
  readonly mobile = inject(Viewport).mobile;
  readonly facetQuery = signal('');
  readonly viewDefs: [string, string][] = [
    ['all', 'all records'],
    ['queue', 'in pipeline'],
    ['issues', 'has issues'],
    ['embeds', 'has embeds'],
  ];

  readonly appliedItems = computed<AppliedItem[]>(() => {
    const out: AppliedItem[] = [];
    const facets = this.store.facets();
    for (const [facetKey, set] of Object.entries(this.store.selection())) {
      const label = facets.find((f) => f.key === facetKey)?.label ?? facetKey;
      for (const value of set) out.push({ facetKey, value, label });
    }
    return out;
  });

  readonly noMatches = computed(() => {
    const ql = this.facetQuery().trim().toLowerCase();
    if (!ql) return false;
    return !this.store
      .facets()
      .some((f) => f.values.some((x) => String(x.v).toLowerCase().includes(ql)));
  });

  private empty = new Set<string>();
  selFor(key: string): Set<string> {
    return this.store.selection()[key] ?? this.empty;
  }
  onField(it: AppliedItem, ev: { field: string; value: string }): void {
    const k = overlayKey(it.facetKey, it.value);
    if (k) this.store.toggleField(k, ev.field, ev.value);
  }
}
