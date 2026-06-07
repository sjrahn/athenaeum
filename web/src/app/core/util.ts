// Pure display helpers ported from the prototype's corpus-data.jsx
// (cxMime / cxParseAddr / cxFmtVal / cxOverlayKey / CX_ATOM / type colors).

import {
  Address,
  RecordSummary,
  RecordDetail,
  Region,
  SectionNode,
  SegmentNode,
} from './models';

export interface MimeInfo {
  label: string;
  short: string;
  color: string;
}

const MIME: Record<string, MimeInfo> = {
  'application/pdf': { label: 'PDF', short: 'pdf', color: '#b00020' },
  'video/mp4': { label: 'MP4', short: 'mp4', color: '#7a4a8a' },
  'audio/mpeg': { label: 'MP3', short: 'mp3', color: '#8a6a3a' },
  'audio/mp4': { label: 'M4A', short: 'm4a', color: '#8a6a3a' },
  'text/html': { label: 'HTML', short: 'html', color: '#4a6b8a' },
  'image/png': { label: 'PNG', short: 'png', color: '#3a6a7a' },
  'image/jpeg': { label: 'JPG', short: 'jpg', color: '#3a6a7a' },
  'image/tiff': { label: 'TIFF', short: 'tiff', color: '#3a6a7a' },
  'image/webp': { label: 'WEBP', short: 'webp', color: '#3a6a7a' },
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
    { label: 'DOCX', short: 'docx', color: '#2b5797' },
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
    { label: 'XLSX', short: 'xlsx', color: '#207245' },
  'message/rfc822': { label: 'EML', short: 'eml', color: '#6a5a3a' },
  'text/markdown': { label: 'MD', short: 'md', color: '#4a4a4a' },
  'text/plain': { label: 'TXT', short: 'txt', color: '#4a4a4a' },
  'application/json': { label: 'JSON', short: 'json', color: '#4a7a4a' },
  'text/vtt': { label: 'VTT', short: 'vtt', color: '#7a6a4a' },
  'application/epub+zip': { label: 'EPUB', short: 'epub', color: '#8a5a2a' },
};

export function mimeInfo(m: string): MimeInfo {
  if (MIME[m]) return MIME[m];
  const short = (m || '?').split('/').pop()!.slice(0, 5).toUpperCase();
  return { label: short, short: short.toLowerCase(), color: '#5a564c' };
}

export const ATOM_COLOR: Record<string, string> = {
  text: '#4a6b8a',
  image: '#3a6a7a',
  audio: '#8a6a3a',
  video: '#7a4a8a',
};
export function atomColor(atom: string): string {
  return ATOM_COLOR[atom] ?? '#666';
}

export const TYPE_COLOR: Record<string, string> = {
  string: '#6b665a',
  number: '#4a6b8a',
  uri: '#a35a00',
  date: '#8a6a3a',
  bool: '#4a6b3a',
  list: '#7a4a8a',
  hash: '#6a5a8a',
};

export function titleFor(r: RecordSummary | RecordDetail): string {
  return r.title || `(untitled — ${r.status})`;
}

/** A content segment flattened with its owning section + a stable index. */
export interface FlatSeg {
  seg: SegmentNode;
  section: SectionNode | null;
  idx: number;
}

/** Stable per-segment key (atom + first address) — the synced-highlight identity. */
export function segKey(seg: SegmentNode): string {
  return seg.atom + ':' + firstAddr(seg.address);
}

/** Flatten the content zone into ordered segments, each tagged with its section. */
export function flatSegments(r: RecordDetail | null): FlatSeg[] {
  const out: FlatSeg[] = [];
  if (!r) return out;
  let idx = 0;
  for (const node of r.content) {
    if (node.type === 'section') {
      for (const seg of node.children) out.push({ seg, section: node, idx: idx++ });
    } else {
      out.push({ seg: node, section: null, idx: idx++ });
    }
  }
  return out;
}

/** Bare host of a URI (www. stripped); schemeless URIs name themselves by scheme. */
export function hostOf(uri: string): string {
  try {
    const u = new URL(uri);
    return (u.hostname || u.protocol.replace(':', '')).replace(/^www\./, '');
  } catch {
    return (uri || '').split('/')[0] || '—';
  }
}

/** Resolve the overlay schema key backing an applied facet, or null. */
export function overlayKey(facetKey: string, value: string): string | null {
  if (facetKey === 'origin') return `origin/${value}`;
  if (facetKey === 'mime') return `mime/${value}`;
  if (facetKey.startsWith('composite:')) {
    return `composite/${facetKey.slice('composite:'.length)}/${value}`;
  }
  return null; // status / visibility carry no overlay
}

export function firstAddr(addr: Address): string {
  return Array.isArray(addr) ? (addr[0] ?? '') : (addr ?? '');
}

/** Parse a segment address into a highlightable region (page/el/bbox/time_range). */
export function parseAddr(addr: Address): Region {
  const out: Region = {};
  const a = firstAddr(addr);
  if (typeof a !== 'string') return out;
  for (const part of a.split('&')) {
    const [k, v] = part.split('=');
    if (k === 'page') out.page = parseInt(v, 10);
    else if (k === 'el') out.el = parseInt(v, 10);
    else if (k === 'bbox') out.bbox = v.split(',').map(Number);
    else if (k === 'time_range') {
      const t = v.split('-').map(timecode);
      out.t0 = t[0];
      out.t1 = t[1];
    }
  }
  return out;
}

/** Accept raw seconds or HH:MM:SS / MM:SS timecodes. */
function timecode(s: string): number {
  if (s.includes(':')) {
    return s.split(':').reduce((acc, p) => acc * 60 + Number(p), 0);
  }
  return Number(s);
}

/** Format an extended-field value for display, honoring its declared type. */
export function fmtVal(v: string, type: string): string {
  if (type === 'number') {
    const n = Number(v);
    return Number.isFinite(n) ? n.toLocaleString() : v;
  }
  if (type === 'date' && /^\d{8}$/.test(v)) {
    return `${v.slice(0, 4)}-${v.slice(4, 6)}-${v.slice(6, 8)}`;
  }
  return v;
}

export function fmtClock(d: Date): string {
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((x) => String(x).padStart(2, '0'))
    .join(':');
}

export function fmtTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** Human artifact size from raw bytes (null -> em-dash). */
export function fmtBytes(bytes: number | null): string {
  if (bytes == null) return '—';
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes >= 1000) return `${Math.round(bytes / 1000)} KB`;
  return `${bytes} B`;
}

/** Epoch ms -> YYYY-MM-DD (UTC), for the timeline + date controls. */
export function fmtDateMs(ms: number): string {
  const d = new Date(ms);
  const p = (x: number) => String(x).padStart(2, '0');
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`;
}

/** YYYYMMDD / YYYY-MM-DD[...] -> epoch ms (UTC midnight), or null. */
export function dateToMs(value: string | null): number | null {
  if (!value) return null;
  const s = String(value);
  let y: number, mo: number, da: number;
  if (/^\d{8}$/.test(s)) {
    y = +s.slice(0, 4);
    mo = +s.slice(4, 6);
    da = +s.slice(6, 8);
  } else {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    if (!m) return null;
    y = +m[1];
    mo = +m[2];
    da = +m[3];
  }
  const t = Date.UTC(y, mo - 1, da);
  return Number.isNaN(t) ? null : t;
}
