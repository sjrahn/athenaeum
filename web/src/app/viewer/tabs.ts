import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { CorpusStore } from '../core/store';
import { EmbedBlock, RecordDetail, Region } from '../core/models';
import { firstAddr, mimeInfo, parseAddr } from '../core/util';
import { CxAddress, CxMimeChip } from '../chips/chips';
import { PickEvent } from './body';

/** View one embedded transport (its own bytes, directly addressed). */
@Component({
  selector: 'cx-embed-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip, CxAddress],
  template: `
    <div class="ev">
      <div class="bar">
        <cx-mime-chip [m]="embed().mime" />
        <span class="dim">embedded transport · {{ embed().transport }}</span>
        <span class="spacer"></span>
        <cx-address [address]="addr()" [active]="true" />
      </div>
      <div class="stage">
        @if (isImg()) {
          <img [src]="url()" alt="embedded image" />
        } @else {
          <div class="other">embedded {{ label() }}</div>
        }
        <div class="meta">
          <div>alt · {{ embed().alt || '—' }}</div>
          <div>description · {{ embed().description || '—' }}</div>
          @if (multi()) { <div class="multi">appears at {{ count() }} positions · one embed, deduped by transport hash</div> }
        </div>
      </div>
    </div>
  `,
  styles: [`
    .ev { flex: 1; display: flex; flex-direction: column; min-height: 0; background: #151310; }
    .bar { flex-shrink: 0; height: 30px; border-bottom: 1px solid var(--border); background: var(--surface);
      display: flex; align-items: center; gap: 8px; padding: 0 12px; font-family: var(--mono); font-size: 10px; }
    .dim { color: var(--dim); } .spacer { flex: 1; }
    .stage { flex: 1; overflow: auto; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 24px; gap: 12px; }
    img { max-width: 360px; max-height: 60vh; box-shadow: 0 8px 30px rgba(0,0,0,0.4); }
    .other { padding: 24px; background: var(--surface); border: 1px solid var(--border); font-family: var(--mono); font-size: 11px; color: var(--muted); }
    .meta { font-family: var(--mono); font-size: 10px; color: #9a9588; line-height: 1.6; text-align: center; }
    .multi { color: var(--accent); margin-top: 3px; }
  `],
})
export class CxEmbedView {
  embed = input.required<EmbedBlock>();
  recordId = input.required<string>();
  private store = inject(CorpusStore);
  addr = computed(() => firstAddr(this.embed().address));
  isImg = computed(() => /png|jpe?g|tiff|webp|gif/.test(mimeInfo(this.embed().mime).short));
  label = computed(() => mimeInfo(this.embed().mime).label);
  url = computed(() => this.store.resolveUrl(`corpus://${this.recordId()}?${this.addr()}`));
  multi = computed(() => Array.isArray(this.embed().address) && (this.embed().address as string[]).length > 1);
  count = computed(() => (Array.isArray(this.embed().address) ? (this.embed().address as string[]).length : 1));
}

/** Embeds tab — the embedded transports the artifact carries. */
@Component({
  selector: 'cx-embeds-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxMimeChip, CxAddress],
  template: `
    @if (r().embeds.length === 0) {
      <div class="empty">no embeds — this artifact carries no embedded transports.</div>
    } @else {
      <div class="wrap">
        <div class="intro">embedded transports the artifact <i>carries</i> — their own bytes (deduped by
          <code>transport</code> hash), directly addressed. A derived self-slice of the artifact (a bbox into a
          raster page) is <b>not</b> an embed.</div>
        @for (e of r().embeds; track $index) {
          <div class="card">
            <div class="top">
              <cx-mime-chip [m]="e.mime" />
              <span class="alt">{{ e.alt || '(embedded asset)' }}</span>
              @if (e.width) { <span class="dim">{{ e.width }}×{{ e.height }}</span> }
            </div>
            @if (e.description) { <div class="desc">{{ e.description }}</div> }
            <div class="addrs">
              <span class="dim">transport {{ e.transport }}</span>
              <span class="spacer"></span>
              @for (a of addrs(e); track a) {
                <span (click)="pick.emit({ key: null, seg: undefined }); pickRegion(a)"><cx-address [address]="a" /></span>
              }
            </div>
          </div>
        }
      </div>
    }
  `,
  styles: [`
    .empty { flex: 1; padding: 20px; font-family: var(--mono); font-size: 11px; color: var(--dim); }
    .wrap { flex: 1; overflow: auto; padding: 16px; }
    .intro { font-family: var(--sans); font-size: 12px; color: var(--muted); line-height: 1.6; margin-bottom: 12px; }
    code { font-family: var(--mono); } b { color: var(--text); }
    .card { border: 1px solid var(--border); padding: 11px; margin-bottom: 9px; background: var(--surface); }
    .top { display: flex; align-items: center; gap: 7px; margin-bottom: 6px; }
    .alt { font-family: var(--sans); font-size: 12px; font-weight: 500; flex: 1; }
    .dim { font-family: var(--mono); font-size: 9px; color: var(--dim); }
    .desc { font-family: var(--sans); font-size: 12px; color: var(--muted); line-height: 1.5; margin-bottom: 7px; }
    .addrs { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
    .addrs > span:last-child, .addrs span[cx-address] { cursor: pointer; }
    .spacer { flex: 1; }
  `],
})
export class CxEmbedsTab {
  r = input.required<RecordDetail>();
  pick = output<PickEvent>();
  region = output<Region>();
  addrs(e: EmbedBlock): string[] {
    return Array.isArray(e.address) ? e.address : [e.address];
  }
  pickRegion(a: string): void {
    this.region.emit(parseAddr(a));
  }
}

/** Metadata tab — frontmatter identity + derived classifications + uri view. */
@Component({
  selector: 'cx-metadata-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="wrap">
      <div class="t-label hd">frontmatter — bytes-identity header</div>
      <table class="kv"><tbody>
        @for (row of rows(); track row[0]) {
          <tr><td class="k">{{ row[0] }}</td><td class="v">{{ row[1] }}</td></tr>
        }
      </tbody></table>

      <div class="t-label hd">derived — classifications view (walks the body)</div>
      <div class="cls">
        @for (c of r().classifications; track c) { <span class="chip">{{ c }}</span> }
      </div>

      <div class="t-label hd">derived — uri view</div>
      <div class="uris">
        @for (u of uris(); track u) { <div class="u">{{ u }}</div> }
        <div class="u accent">corpus://{{ r().id }}</div>
      </div>
    </div>
  `,
  styles: [`
    .wrap { flex: 1; overflow: auto; padding: 16px; font-family: var(--mono); font-size: 11px; }
    .hd { margin-bottom: 8px; margin-top: 4px; }
    .kv { width: 100%; border-collapse: collapse; margin-bottom: 18px; }
    .kv td { padding: 5px 10px 5px 0; vertical-align: top; }
    .kv .k { color: var(--dim); width: 150px; white-space: nowrap; }
    .kv .v { word-break: break-word; }
    .kv tr { border-bottom: 1px solid var(--border); }
    .cls { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 18px; }
    .chip { display: inline-flex; align-items: center; height: 18px; padding: 0 7px; font-size: 9.5px;
      border: 1px solid var(--border); background: var(--surface-2); color: var(--muted); }
    .uris { border: 1px solid var(--border); }
    .u { padding: 5px 10px; border-bottom: 1px solid var(--border); word-break: break-all; }
    .u.accent { color: var(--accent); border-bottom: none; }
  `],
})
export class CxMetadataTab {
  r = input.required<RecordDetail>();
  rows = computed<[string, string][]>(() => {
    const r = this.r();
    const out: [string, string][] = [
      ['id', r.id],
      ['status', r.status],
      ['visibility', r.visibility ?? 'visible'],
      ['primary_mime', r.mime],
    ];
    for (const [k, v] of Object.entries(r.hashes)) out.push([k, String(v)]);
    out.push(['captured', r.captured ?? '—'], ['corpus', r.corpus]);
    return out.filter(([, v]) => v != null && v !== '');
  });
  uris = computed(() => this.r().origins.flatMap((o) => o.uri));
}

/** Provenance tab — the touch[] chain. */
@Component({
  selector: 'cx-provenance-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="wrap">
      <div class="t-label hd">touch[] — current-shape provenance chain</div>
      <div class="chain">
        @for (t of r().touch; track $index; let i = $index; let last = $last) {
          <div class="step">
            <span class="node" [class.head]="last"></span>
            <div class="row">
              <span class="ix">touch[{{ i }}]</span>
              <span class="stage">{{ stage(t) }}</span>
            </div>
            <div class="tid" [class.model]="isModel(t)">{{ t }}</div>
          </div>
        }
      </div>
      <div class="note">the latest touch's tooling version implicitly encodes the spec era under which the
        record's current shape was produced. <code>re-stub</code> resets this chain.</div>
    </div>
  `,
  styles: [`
    .wrap { flex: 1; overflow: auto; padding: 16px; font-family: var(--mono); font-size: 11px; }
    .hd { margin-bottom: 10px; }
    .chain { position: relative; padding-left: 20px; }
    .step { position: relative; margin-bottom: 12px; }
    .node { position: absolute; left: -20px; top: 2px; width: 9px; height: 9px; background: var(--surface);
      border: 1px solid var(--border-strong); }
    .node.head { background: var(--accent); border-color: var(--accent); }
    .row { display: flex; align-items: center; gap: 8px; }
    .ix { font-size: 9px; color: var(--dim); }
    .stage { font-size: 9px; padding: 1px 5px; border: 1px solid var(--border); color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.06em; }
    .tid { color: var(--text); margin-top: 3px; word-break: break-all; }
    .tid.model { color: var(--accent); }
    .note { margin-top: 8px; padding: 10px; background: var(--surface-2); border: 1px solid var(--border);
      font-family: var(--sans); font-size: 11px; color: var(--muted); line-height: 1.6; }
    code { font-family: var(--mono); }
  `],
})
export class CxProvenanceTab {
  r = input.required<RecordDetail>();
  isModel(t: string): boolean {
    return t.includes('[') || t.includes('claude') || t.includes('whisper') || t.includes('+');
  }
  stage(t: string): string {
    if (t.includes('ingest')) return 'ingest';
    if (t.includes('draft')) return 'draft';
    if (t.includes('classify')) return 'classify';
    if (t.includes('normalize') || t.includes('compile') || this.isModel(t)) return 'normalize';
    return 'pass';
  }
}

/** Annotations tab — the context blocks. */
@Component({
  selector: 'cx-annotations-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxAddress],
  template: `
    @if (r().annotations.length === 0) {
      <div class="empty">annotations zone empty — the normal state for most records. context is scarce by design.</div>
    } @else {
      <div class="wrap">
        @for (a of r().annotations; track $index) {
          <div class="card" [style.borderLeftColor]="edge(a)"
            [style.cursor]="a['address'] ? 'pointer' : 'default'" (click)="onClick(a)">
            <div class="top">
              <span class="ns" [style.color]="edge(a)" [style.borderColor]="edge(a)">{{ a.namespace }}/{{ a.id }}</span>
              @if (a['severity']) { <span class="sev" [style.color]="edge(a)">{{ a['severity'] }}</span> }
              @if (a['resolution']) { <span class="dim">· {{ a['resolution'] }}</span> }
              <span class="spacer"></span>
              @if (a['address']) { <cx-address [address]="str(a['address'])" /> }
            </div>
            @if (a['note']) { <div class="note">{{ a['note'] }}</div> }
            @if (a['attribution_text']) { <div class="note">“{{ a['attribution_text'] }}”</div> }
            @if (a['source_url'] || a['source_uri']) { <div class="src">↳ {{ a['source_url'] || a['source_uri'] }}</div> }
            @if (a['quote']) { <div class="quote">quote: “{{ a['quote'] }}”</div> }
            @if (a['detector']) { <div class="det">detector · {{ a['detector'] }}</div> }
          </div>
        }
      </div>
    }
  `,
  styles: [`
    .empty { flex: 1; padding: 20px; font-family: var(--mono); font-size: 11px; color: var(--dim); }
    .wrap { flex: 1; overflow: auto; padding: 16px; }
    .card { border: 1px solid var(--border); border-left: 3px solid var(--accent); padding: 11px; margin-bottom: 9px; background: var(--surface); }
    .top { display: flex; align-items: center; gap: 7px; margin-bottom: 5px; }
    .ns { font-family: var(--mono); font-size: 9px; font-weight: 600; padding: 1px 5px; border: 1px solid;
      text-transform: uppercase; letter-spacing: 0.06em; }
    .sev { font-family: var(--mono); font-size: 9px; }
    .dim { font-family: var(--mono); font-size: 9px; color: var(--dim); }
    .spacer { flex: 1; }
    .note { font-family: var(--sans); font-size: 12px; color: var(--text); line-height: 1.5; }
    .src { font-family: var(--mono); font-size: 10px; color: var(--muted); margin-top: 4px; }
    .quote { font-family: var(--mono); font-size: 10px; color: var(--dim); margin-top: 4px; }
    .det { font-family: var(--mono); font-size: 9px; color: var(--dim); margin-top: 5px; }
  `],
})
export class CxAnnotationsTab {
  r = input.required<RecordDetail>();
  region = output<Region>();
  edge(a: Record<string, unknown>): string {
    if (a['namespace'] !== 'issue') return 'var(--accent)';
    const sev = a['severity'];
    return sev === 'blocking' ? 'var(--err)' : sev === 'warning' ? 'var(--warn)' : 'var(--dim)';
  }
  str(v: unknown): string {
    return firstAddr(v as string | string[]);
  }
  onClick(a: Record<string, unknown>): void {
    if (a['address']) this.region.emit(parseAddr(a['address'] as string));
  }
}
