// Wire types — mirror the `corpus.api` JSON shape (see tools/corpus/src/corpus/api/serialize.py).

export type Address = string | string[];

export interface Corpus {
  id: string;
  name: string;
  color: string;
  desc: string;
  record_count: number;
  online: boolean;
}

/** A configured API endpoint (one server, one or more corpora). Client-managed. */
export interface Endpoint {
  id: string;
  base: string;   // e.g. http://127.0.0.1:8099/v1
  label: string;
  online: boolean;
  corpora: Corpus[];
}

export interface FacetValue {
  v: string;
  n: number;
  label: string;
}
export interface Facet {
  key: string;     // 'mime' | 'origin' | 'status' | 'visibility' | 'composite:<ns>'
  label: string;
  values: FacetValue[];
}

export interface SchemaField {
  field: string;
  type: string;    // string | number | uri | date | bool | list | hash
  values: string[];
}
export type SchemaRegistry = Record<string, SchemaField[]>;

export interface RecordSummary {
  id: string;
  title: string;
  description: string;
  status: string;
  visibility: string | null;
  mime: string;
  corpus: string;
  origin_host: string;
  embed_count: number;
  classifications: string[];
  captured: string | null;
  normalized: string | null;
}

export interface QueryResult {
  total: number;
  records: RecordSummary[];
}

export interface Transport {
  name: string;
  mime: string;
  size: number | null;
  ext: string;
}

export interface OriginBlock {
  id: string;
  subtype: string | null;
  uri: string[];
  snapshot: string | null;
  fields: Record<string, unknown>;
}

export interface ClassifyBlock {
  ns: string;
  id: string;
  subtype: string | null;
  provenance: string | null;
  fields: Record<string, unknown>;
}

export interface EmbedBlock {
  mime: string;
  address: Address;
  transport: string | null;
  width: number | null;
  height: number | null;
  alt: string | null;
  description: string | null;
  fields: Record<string, unknown>;
}

export interface SegmentNode {
  type: 'segment';
  atom: string;
  overlay: string | null;
  address: Address;
  entry: string | null;
  description: string | null;
  body: string;
  perceptual: string | string[] | null;
  speaker?: number | string;
  [extra: string]: unknown;
}

export interface SectionNode {
  type: 'section';
  address: Address;
  entry: string | null;
  ns: string | null;
  description: string | null;
  children: SegmentNode[];
  [extra: string]: unknown;
}

export type ContentNode = SectionNode | SegmentNode;

export interface ContextBlock {
  namespace: string;
  id: string;
  subtype?: string;
  [field: string]: unknown;
}

export interface RecordDetail {
  id: string;
  title: string;
  description: string;
  status: string;
  visibility: string | null;
  mime: string;
  corpus: string;
  transport: Transport;
  hashes: Record<string, string>;
  touch: string[];
  artifactFields: Record<string, unknown>;
  origins: OriginBlock[];
  classifyBlocks: ClassifyBlock[];
  embeds: EmbedBlock[];
  content: ContentNode[];
  annotations: ContextBlock[];
  classifications: string[];
  tokens: { body: number; blocks: number; full: number };
  captured: string | null;
  normalized: string | null;
  pages: number | null;
  duration: number | null;
  imgW: number | null;
  imgH: number | null;
  isImage: boolean;
}

/** Parsed segment address -> a region the artifact pane can highlight. */
export interface Region {
  page?: number;
  el?: number;
  bbox?: number[];
  t0?: number;
  t1?: number;
}

// ---- workbench wire types (see tools/corpus/src/corpus/api/index.py workbench()) ----

export type CondOp = 'between' | 'contains' | 'in' | 'is';

/** A typed "narrow on a field" condition. `value` is `[lo,hi]` (between, number or epoch
 *  ms for dates) | substring (contains) | string[] (in) | boolean (is). */
export interface Cond {
  fid: string;
  type: string; // number | date | string | list | bool | uri | hash
  op: CondOp;
  value: unknown;
}

/** Whole-corpus per-type statistics for a field control (the design's `field.stats`). */
export interface FieldStats {
  type: string;
  min?: number;
  max?: number;
  distinct?: number;
  bins?: number[];
  binMax?: number;
  values?: { v: string; n: number }[];
}

/** A typed field in the registry (`GET /fields`): core baseline + every overlay field. */
export interface FieldStat {
  id: string;
  key: string | null; // overlay key (mime/… origin/… composite/…/…) or null for core
  group: string; // core | mime | origin | composite
  groupLabel: string;
  field: string;
  label: string;
  type: string;
  coverage: number;
  stats: FieldStats;
}

/** A ledger row (records[] of the workbench response): summary + size + segment count +
 *  the canonical artifact filename (`<id[:12]>.<ext>`) for the untitled placeholder. */
export interface WorkbenchRow extends RecordSummary {
  size: number | null; // artifact bytes
  segments: number;
  transport_name: string;
  // token-count derived view (cumulative tiers): body <= blocks <= full(+images)
  tokens_body: number;
  tokens_blocks: number;
  tokens_full: number;
}

export interface TimelineBin {
  n: number;
  normalized: number;
  draft: number;
  stub: number;
}
export interface TimelineData {
  span: [number, number]; // full captured span [minMs, maxMs]
  binCount: number;
  bins: TimelineBin[];
  inRange: {
    count: number;
    normalized: number;
    drafts: number;
    stubs: number;
    origins: number;
    spanDays: number;
  };
}

export interface OverviewData {
  headline: { records: number; pctNormalized: number; sizeMB: number; spanDays: number };
  dists: Record<string, [string, number][]>; // byMime | byStatus | byAtom | byOrigin | byGenre
}

// ---- graph mode (record connections) ---- //

/** One connection node. `kind` = origin | embed | record | link; `recId` opens a corpus
 *  record (a classification peer or a captured cross-reference); `url`/`host` for link nodes. */
export interface GraphNode {
  id: string;
  kind: 'origin' | 'embed' | 'record' | 'link';
  label: string;
  sub: string;
  recId?: string | null;
  url?: string | null;
  host?: string | null;
}

export interface GraphResponse {
  resolved: GraphNode[];
  uncaptured: GraphNode[];
}

export interface WorkbenchResponse {
  total: number;
  records: WorkbenchRow[];
  facetStack: Facet[]; // status · mime · embedmime · origin · composite:* · visibility
  timeline: TimelineData;
  availableFields: string[]; // field ids gated to the narrowed set
  overview: OverviewData;
}
