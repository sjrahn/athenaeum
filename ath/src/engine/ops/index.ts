// index.ts — importing this module registers every attester; `attest` runs the right one for a mime.
import { sha256Hex } from "../../lib/hash.ts";
import "./csv/attest.ts";
import "./epub/attest.ts";
import "./html/attest.ts";
import "./image/headers.ts";
import "./mail/attest.ts";
import "./mail/mbox.ts";
import "./pdf/attest.ts";
import "./zip/roster.ts";
import { type AttestResult, attesterFor } from "./registry.ts";

export { INGEST_OP } from "./registry.ts";

/** The attestation for bytes of a mime; unknown mimes attest mime, size and sha256 only. */
export async function attest(bytes: Uint8Array, mime: string): Promise<AttestResult> {
  const fn = attesterFor(mime);
  if (fn) return fn(bytes, mime);
  return { value: { mime, bytes: bytes.length, sha256: sha256Hex(bytes) } };
}
