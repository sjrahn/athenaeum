// ingest.ts — bytes on disk → an artifact subject: hash, sniff, attest, place the bytes, write the two op lines
// (`attests`, `captured_from`). A container's members become subjects of their own (spec §5.1). No network.
import { basename } from "node:path";
import { blake3Hex } from "../../lib/hash.ts";
import type { JsonObject } from "../../lib/jsonl.ts";
import { bytesPath, placeBytes } from "../layer/bytes.ts";
import type { Chain } from "../layer/config.ts";
import { attest, INGEST_OP } from "../ops/index.ts";
import { sniffMime } from "../ops/sniff.ts";
import { appendLines } from "./file.ts";

export interface Provenance {
  origin?: string;
  uri?: string;
  via?: "capture" | "upload" | "export";
  received?: string;
  snapshot?: string;
  note?: string;
  fidelity?: string;
  [k: string]: unknown;
}

export interface IngestOptions {
  provenance?: Provenance;
  /** Symlink the bytes instead of copying them. */
  link?: boolean;
  /** The op's own attestation stamp. */
  date: string;
  /** Members of a container also ingest (default true). */
  members?: boolean;
}

export interface Ingested {
  blake3: string;
  mime: string;
  bytes: number;
  path: string;
  attests: JsonObject;
  capturedFrom: JsonObject | null;
  members: Ingested[];
  /** Whether the subject's file already held these op lines. */
  existed: boolean;
}

/** Ingest a file. */
export async function ingestFile(chain: Chain, file: string, o: IngestOptions): Promise<Ingested> {
  const bytes = new Uint8Array(await Bun.file(file).arrayBuffer());
  return ingestBytes(chain, bytes, { ...o, name: basename(file), source: file });
}

export async function ingestBytes(
  chain: Chain,
  bytes: Uint8Array,
  o: IngestOptions & { name?: string; source?: string; container?: { blake3: string; path: string } },
): Promise<Ingested> {
  const blake3 = await blake3Hex(bytes);
  const mime = sniffMime(bytes, o.name ?? "");
  const result = await attest(bytes, mime);
  const attestsLine: JsonObject = { at: "whole", predicate: "attests", value: result.value, by: INGEST_OP };
  let captured: JsonObject | null = null;
  const prov: Record<string, unknown> = {};
  if (o.container) Object.assign(prov, { container: `corpus://${o.container.blake3}`, path: o.container.path });
  if (result.capturedFrom) Object.assign(prov, result.capturedFrom);
  if (o.provenance) for (const [k, v] of Object.entries(o.provenance)) if (v !== undefined) prov[k] = v;
  if (Object.keys(prov).length) captured = { at: "whole", predicate: "captured_from", value: prov, by: INGEST_OP };

  // bytes first, then lines
  let path: string;
  if (o.source && !o.container) path = placeBytes(chain, blake3, o.source, o.link);
  else {
    path = bytesPath(chain.top, blake3);
    if (!(await Bun.file(path).exists())) await Bun.write(path, bytes);
  }
  const lines = captured ? [attestsLine, captured] : [attestsLine];
  const report = appendLines(chain, "corpus", blake3, lines, { by: INGEST_OP, date: o.date, noCorrect: true });

  const members: Ingested[] = [];
  if (o.members !== false && result.members) {
    for (const m of result.members) {
      members.push(
        await ingestBytes(chain, m.bytes, { date: o.date, name: m.name ?? m.path, container: { blake3, path: m.path }, members: false }),
      );
    }
  }
  return { blake3, mime, bytes: bytes.length, path, attests: attestsLine, capturedFrom: captured, members, existed: report.added === 0 };
}
