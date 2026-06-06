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
