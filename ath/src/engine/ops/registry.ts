// registry.ts — derivation ops by `name@version`. An op is a pure function of bytes (and an address) that yields a
// byte-fact: the attestation of what the bytes are, or the quote surface a term's `derivation` names. Ops never read
// a layer and never touch the network.
export const INGEST_OP = "ath.ingest@1";

export interface AttestResult {
  /** The `attests` value: mime, bytes, and the format's own facts. */
  value: Record<string, unknown>;
  /** A container's members: each becomes its own subject. */
  members?: { path: string; bytes: Uint8Array; blake3?: string }[];
  /** Provenance the bytes themselves carry (a capture banner), as `captured_from` fields. */
  capturedFrom?: Record<string, unknown>;
}

export type Attester = (bytes: Uint8Array, mime: string) => Promise<AttestResult>;

const attesters = new Map<string, Attester>();

/** Register the attester for a mime (exact) or a family (`image/*`). */
export function registerAttester(mime: string, fn: Attester): void {
  attesters.set(mime, fn);
}

export function attesterFor(mime: string): Attester | null {
  return attesters.get(mime) ?? attesters.get(`${mime.split("/")[0]}/*`) ?? attesters.get("*/*") ?? null;
}
