import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { EmbedBlock, RecordDetail, SectionNode, SegmentNode } from '../core/models';
import { atomColor, firstAddr, mimeInfo } from '../core/util';
import { CorpusStore } from '../core/store';
import { CxAddress, CxAtomChip } from '../chips/chips';
import { CxMd } from './md';

export interface PickEvent {
  key: string | null;
  seg?: SegmentNode;
}

function segKey(seg: SegmentNode): string {
  return seg.atom + ':' + firstAddr(seg.address);
}
function embedFor(r: RecordDetail, seg: SegmentNode): EmbedBlock | null {
  const a = firstAddr(seg.address);
  return (
    r.embeds.find((e) => {
      const addrs = Array.isArray(e.address) ? e.address : [e.address];
      return addrs.includes(a);
    }) ?? null
  );
}

/** One interactive segment block in the rendered body. */
@Component({
  selector: 'cx-segment-block',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxAtomChip, CxAddress, CxMd],
  template: `
    <div class="block" [class.active]="active()" (click)="pick.emit()"
      (mouseenter)="hover.set(true)" (mouseleave)="hover.set(false)">
      <div class="head" [style.marginBottom.px]="isText() && seg().body ? 5 : 0">
        <cx-atom-chip [atom]="seg().atom" [overlay]="seg().overlay" />
        @if (seg().speaker != null) { <span class="spk">speaker {{ seg().speaker }}</span> }
        <span class="spacer"></span>
        @if (hover() || active()) { <cx-address [address]="addr()" [active]="active()" /> }
      </div>
      @if (isText() && seg().body) {
        <cx-md [text]="seg().body" />
      } @else if (imgUrl()) {
        <figure class="fig">
          <img [src]="imgUrl()" [alt]="alt()" loading="lazy"
            (click)="$event.stopPropagation(); view.emit(imgUrl()!)" />
          <figcaption>
            @if (embed()) { <span class="emb">↳ embed</span> } @else { <span class="slice">self-slice</span> }
            <span class="cap">{{ markerDesc() }}</span>
          </figcaption>
        </figure>
      } @else {
        <div class="marker">
          <span class="swatch" [style.background]="color()"></span>
          <div class="mtext">
            <div class="mtop">
              <span>{{ seg().atom }} positioning marker</span>
              @if (embed()) { <span class="emb">↳ embed</span> }
              @else { <span class="slice">derived self-slice</span> }
            </div>
            <div class="mdesc">{{ markerDesc() }}</div>
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    .block { position: relative; padding: 7px 16px 8px; cursor: pointer; border-left: 2px solid transparent;
      transition: background 0.12s; }
    .fig { margin: 0; border: 1px solid var(--border); background: var(--surface-2); }
    .fig img { display: block; max-width: 100%; max-height: 360px; height: auto; margin: 0 auto;
      cursor: zoom-in; background: #fff; }
    .fig figcaption { display: flex; align-items: center; gap: 6px; padding: 4px 8px; border-top: 1px solid var(--border);
      font-family: var(--mono); font-size: 9px; color: var(--dim); }
    .fig .cap { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .block.active { border-left-color: var(--accent); background: var(--accent-soft); }
    .block:hover:not(.active) { background: var(--surface-2); }
    .head { display: flex; align-items: center; gap: 6px; min-height: 16px; }
    .spk { font-family: var(--mono); font-size: 9px; color: var(--muted); }
    .spacer { flex: 1; }
    .marker { display: flex; align-items: center; gap: 8px; padding: 8px 10px;
      border: 1px dashed var(--border-strong); background: var(--surface); font-family: var(--mono);
      font-size: 10px; color: var(--muted); }
    .swatch { width: 26px; height: 26px; opacity: 0.18; flex-shrink: 0; }
    .mtext { min-width: 0; flex: 1; }
    .mtop { display: flex; align-items: center; gap: 6px; color: var(--text); }
    .emb { font-size: 8px; color: var(--accent); border: 1px solid var(--accent); padding: 0 4px; letter-spacing: 0.06em; }
    .slice { font-size: 8px; color: var(--muted); border: 1px solid var(--border-strong); padding: 0 4px; letter-spacing: 0.06em; }
    .mdesc { color: var(--dim); margin-top: 2px; }
  `],
})
export class CxSegmentBlock {
  private store = inject(CorpusStore);
  seg = input.required<SegmentNode>();
  embed = input<EmbedBlock | null>(null);
  recordId = input<string>('');
  active = input(false);
  pick = output<void>();
  view = output<string>();
  hover = signal(false);

  isText = computed(() => this.seg().atom === 'text');
  addr = computed(() => firstAddr(this.seg().address));
  color = computed(() => atomColor(this.seg().atom));
  alt = computed(() => this.embed()?.alt || this.seg().description || 'image');
  // image atoms (embed-backed or artifact self-slice) resolve to real bytes via the addressed URI.
  imgUrl = computed(() => {
    if (this.seg().atom !== 'image') return null;
    const a = this.addr();
    const id = this.recordId();
    return id && a ? this.store.resolveUrl(`corpus://${id}?${a}`) : null;
  });
  markerDesc = computed(() => {
    const e = this.embed();
    if (e) return e.description || e.alt || 'embedded transport · ' + (e.transport ?? '');
    return this.seg().description || 'materialized from the artifact on demand';
  });
}

/** Rendered markdown body — segments grouped by section, interactive + synced. */
@Component({
  selector: 'cx-rendered-body',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxSegmentBlock, CxAddress],
  template: `
    <div class="body">
      <div class="hd"><span class="t-label">normalized markdown · {{ r().normalized || 'draft' }}</span></div>
      @for (node of r().content; track $index) {
        @if (node.type === 'section') {
          <div class="sec">
            <span class="sg">§</span>
            <span class="sentry">{{ section(node).entry || addr(section(node).address) }}</span>
            @if (section(node).ns) { <span class="sns">{{ section(node).ns }}</span> }
            <div class="hair" style="flex:1"></div>
            <cx-address [address]="addr(section(node).address)" />
          </div>
          @for (seg of section(node).children; track $index) {
            <cx-segment-block [seg]="seg" [embed]="embedOf(seg)" [recordId]="r().id"
              [active]="isActive(seg)" (pick)="pickSeg(seg)" (view)="lightbox.set($event)" />
          }
        } @else {
          <cx-segment-block [seg]="segment(node)" [embed]="embedOf(segment(node))" [recordId]="r().id"
            [active]="isActive(segment(node))" (pick)="pickSeg(segment(node))" (view)="lightbox.set($event)" />
        }
      }
      @if (r().content.length === 0) {
        <div class="empty">content zone empty — {{ r().status === 'stub' ? 'awaiting draft pass.' : 'this record has no segmented body.' }}</div>
      }

      <!-- embedded assets the body doesn't position inline (orphan embeds): a viewable gallery -->
      @if (orphanImages().length) {
        <div class="sec"><span class="sg">⧉</span>
          <span class="sentry">embedded assets</span>
          <div class="hair" style="flex:1"></div>
          <span class="sct">{{ orphanImages().length }}</span></div>
        <div class="gal">
          @for (e of orphanImages(); track $index) {
            <figure class="gt" (click)="lightbox.set(embedUrl(e))">
              <img [src]="embedUrl(e)" [alt]="e.alt || 'embed'" loading="lazy" />
              <figcaption>{{ e.alt || short(e.mime) }}{{ e.width && e.height ? ' · ' + e.width + '×' + e.height : '' }}</figcaption>
            </figure>
          }
        </div>
      }
    </div>

    @if (lightbox(); as src) {
      <div class="lb" (click)="lightbox.set(null)">
        <img [src]="src" alt="embedded asset" (click)="$event.stopPropagation()" />
        <button class="lbx" (click)="lightbox.set(null)" title="close ⎋">✕</button>
      </div>
    }
  `,
  styles: [`
    .body { padding: 4px 0 40px; }
    .hd { padding: 8px 16px 6px; position: sticky; top: 0; background: var(--surface); z-index: 1;
      border-bottom: 1px solid var(--border); }
    .sec { padding: 12px 16px 4px; display: flex; align-items: center; gap: 8px; }
    .sg { font-family: var(--mono); font-size: 9px; color: var(--dim); }
    .sentry { font-family: var(--sans); font-size: 12px; font-weight: 600; color: var(--muted); }
    .sns { font-family: var(--mono); font-size: 8px; color: var(--dim); }
    .sct { font-family: var(--mono); font-size: 8px; color: var(--dim); }
    .empty { padding: 20px; font-family: var(--mono); font-size: 11px; color: var(--dim); }
    .gal { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; padding: 8px 16px 0; }
    .gt { margin: 0; border: 1px solid var(--border); background: var(--surface-2); cursor: zoom-in; }
    .gt img { display: block; width: 100%; height: 120px; object-fit: contain; background: #fff; }
    .gt figcaption { padding: 4px 6px; border-top: 1px solid var(--border); font-family: var(--mono);
      font-size: 8.5px; color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .lb { position: fixed; inset: 0; z-index: 50; background: rgba(0,0,0,0.78); display: flex;
      align-items: center; justify-content: center; padding: 32px; }
    .lb img { max-width: 100%; max-height: 100%; background: #fff; box-shadow: 0 8px 40px rgba(0,0,0,0.5); }
    .lbx { position: fixed; top: 16px; right: 18px; width: 30px; height: 30px; border: 1px solid var(--border-strong);
      background: var(--surface); color: var(--text); font-family: var(--mono); font-size: 13px; cursor: pointer; }
  `],
})
export class CxRenderedBody {
  private store = inject(CorpusStore);
  r = input.required<RecordDetail>();
  activeKey = input<string | null>(null);
  pick = output<PickEvent>();
  readonly lightbox = signal<string | null>(null);

  section = (n: SectionNode | SegmentNode) => n as SectionNode;
  segment = (n: SectionNode | SegmentNode) => n as SegmentNode;
  addr = firstAddr;
  short = (m: string) => mimeInfo(m).short;
  // Image embeds that no in-flow image segment positions (orphan embeds) — surfaced as a
  // viewable gallery so they aren't invisible. The resolver materializes each via its address.
  readonly orphanImages = computed(() => {
    const r = this.r();
    const positioned = new Set<string>();
    const walk = (nodes: (SectionNode | SegmentNode)[]): void => {
      for (const n of nodes) {
        if (n.type === 'section') walk(n.children);
        else if (n.atom !== 'text') positioned.add(firstAddr(n.address));
      }
    };
    walk(r.content);
    const list = (a: string | string[]): string[] => (Array.isArray(a) ? a : [a]);
    return r.embeds.filter(
      (e) => e.mime.startsWith('image/') && !list(e.address).some((a) => positioned.has(a)),
    );
  });
  embedUrl(e: EmbedBlock): string {
    return this.store.resolveUrl(`corpus://${this.r().id}?${firstAddr(e.address)}`);
  }
  embedOf(seg: SegmentNode): EmbedBlock | null {
    return embedFor(this.r(), seg);
  }
  isActive(seg: SegmentNode): boolean {
    return segKey(seg) === this.activeKey();
  }
  pickSeg(seg: SegmentNode): void {
    this.pick.emit({ key: segKey(seg), seg });
  }
}

// ---- raw record source (faithful, read-only) ----
function addrStr(a: string | string[]): string {
  return Array.isArray(a) ? `[${a.join(', ')}]` : a;
}
function yamlVal(v: unknown): string {
  if (Array.isArray(v)) return `[${v.join(', ')}]`;
  return String(v);
}
function emitSeg(L: string[], s: SegmentNode): void {
  L.push('');
  L.push('<!--segment ' + s.atom + (s.overlay ? '/' + s.overlay : ''));
  L.push('address: ' + addrStr(s.address));
  if (s.entry) L.push('entry: ' + s.entry);
  if (s.speaker != null) L.push('speaker: ' + s.speaker);
  if (s.description) L.push('description: ' + s.description);
  L.push('-->');
  if (s.body) {
    L.push('');
    L.push(s.body);
  }
}
export function serializeRecord(r: RecordDetail): string {
  const L: string[] = ['---', 'id: ' + r.id];
  L.push('title: ' + (r.title ? JSON.stringify(r.title) : "''"));
  L.push('description: ' + (r.description ? JSON.stringify(r.description) : "''"));
  L.push('status: ' + r.status);
  if (r.visibility && r.visibility !== 'visible') L.push('visibility: ' + r.visibility);
  for (const [k, v] of Object.entries(r.hashes)) L.push(k + ': ' + v);
  if (r.touch.length === 1) L.push('touch: ' + r.touch[0]);
  else if (r.touch.length) {
    L.push('touch:');
    for (const t of r.touch) L.push('- ' + t);
  }
  L.push('---', '');
  L.push('<!--artifact ' + r.mime);
  for (const [k, v] of Object.entries(r.artifactFields)) L.push(k + ': ' + yamlVal(v));
  L.push('-->');
  for (const o of r.origins) {
    L.push('', '<!--origin ' + (o.id || ''));
    if (o.uri.length === 1) L.push('uri: ' + o.uri[0]);
    else if (o.uri.length) {
      L.push('uri:');
      for (const u of o.uri) L.push('- ' + u);
    }
    if (o.snapshot) L.push('snapshot: ' + o.snapshot);
    for (const [k, v] of Object.entries(o.fields)) L.push(k + ': ' + yamlVal(v));
    L.push('-->');
  }
  for (const c of r.classifyBlocks) {
    L.push('', '<!--classify ' + c.ns + '/' + c.id);
    if (c.provenance) L.push('provenance: ' + c.provenance);
    for (const [k, v] of Object.entries(c.fields)) L.push(k + ': ' + yamlVal(v));
    L.push('-->');
  }
  for (const e of r.embeds) {
    L.push('', '<!--embed ' + e.mime);
    L.push('address: ' + addrStr(e.address));
    if (e.transport) L.push('transport: ' + e.transport);
    if (e.width != null) L.push('width: ' + e.width);
    if (e.height != null) L.push('height: ' + e.height);
    if (e.alt) L.push('alt: ' + e.alt);
    if (e.description) L.push('description: ' + e.description);
    L.push('-->');
  }
  for (const node of r.content) {
    if (node.type === 'section') {
      L.push('', '<!--section ' + (node.ns || ''));
      if (node.address) L.push('address: ' + addrStr(node.address));
      if (node.entry) L.push('entry: ' + node.entry);
      L.push('-->');
      for (const s of node.children) emitSeg(L, s);
    } else {
      emitSeg(L, node);
    }
  }
  for (const a of r.annotations) {
    L.push('', '<!--context ' + a.namespace + '/' + a.id);
    for (const [k, v] of Object.entries(a)) {
      if (k === 'namespace' || k === 'id' || k === 'subtype') continue;
      L.push(k + ': ' + yamlVal(v));
    }
    L.push('-->');
  }
  L.push('');
  return L.join('\n');
}

@Component({
  selector: 'cx-raw-body',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="raw">
      <div class="hd"><span class="t-label">record source · {{ r().id.slice(0, 10) }}….md</span></div>
      <pre>@for (line of lines(); track $index) {<span [class]="cls(line)">{{ line }}</span>
}</pre>
    </div>
  `,
  styles: [`
    .raw { padding: 4px 16px 40px; }
    .hd { padding: 6px 0; position: sticky; top: 0; background: var(--surface); z-index: 1; }
    pre { font-family: var(--mono); font-size: 11px; line-height: 1.55; margin: 0; white-space: pre-wrap; word-break: break-word; }
    .comment { color: var(--accent); }
    .rule { color: var(--border-strong); }
    .field { color: var(--dim); }
    .text { color: var(--text); }
  `],
})
export class CxRawBody {
  r = input.required<RecordDetail>();
  lines = computed(() => serializeRecord(this.r()).split('\n'));
  cls(line: string): string {
    if (line === '---') return 'rule';
    if (line.startsWith('<!--') || line === '-->') return 'comment';
    if (/^[a-z_]+:/.test(line) || line.startsWith('- ')) return 'field';
    return 'text';
  }
}
